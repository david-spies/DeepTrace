"""
DeepTrace SDK — Agent Trace Interceptor
Wraps LLM agents and tool calls to emit OpenTelemetry-compatible spans
to the DeepTrace Collector.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type
import threading
import queue
import logging

import httpx

logger = logging.getLogger("deeptrace")


# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────

@dataclass
class TraceConfig:
    endpoint: str = "http://localhost:8080"
    service_name: str = "deeptrace-agent"
    environment: str = "production"
    batch_size: int = 25
    flush_interval: float = 2.0          # seconds between forced flushes
    max_queue: int = 10_000
    token_heuristic: float = 0.25        # chars-per-token estimate
    context_fragment_threshold: float = 0.30  # alert if >30% context lost
    zero_trust_enabled: bool = True
    shadow_tool_execution: bool = False   # sandbox tool calls before execution
    api_key: Optional[str] = None
    tls_verify: bool = True

    @classmethod
    def from_env(cls) -> "TraceConfig":
        import os
        return cls(
            endpoint=os.getenv("DEEPTRACE_ENDPOINT", "http://localhost:8080"),
            service_name=os.getenv("DEEPTRACE_SERVICE", "deeptrace-agent"),
            environment=os.getenv("DEEPTRACE_ENV", "production"),
            api_key=os.getenv("DEEPTRACE_API_KEY"),
        )


# ─────────────────────────────────────────
# SPAN MODELS
# ─────────────────────────────────────────

class SpanStatus(str, Enum):
    STARTED   = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    KILLED    = "KILLED"
    BLOCKED   = "BLOCKED"   # zero-trust denial


class SpanKind(str, Enum):
    AGENT     = "AGENT"
    LLM_CALL  = "LLM_CALL"
    TOOL_CALL = "TOOL_CALL"
    SPAWN     = "SPAWN"
    CONTEXT   = "CONTEXT"


@dataclass
class ToolInvocation:
    tool_name: str
    inputs: Dict[str, Any]
    output: Optional[Any] = None
    blocked: bool = False
    duration_ms: float = 0.0
    merkle_hash: str = ""

    def compute_merkle(self, parent_hash: str = "") -> str:
        payload = json.dumps({
            "tool": self.tool_name,
            "inputs": self.inputs,
            "parent": parent_hash,
        }, sort_keys=True)
        self.merkle_hash = hashlib.sha256(payload.encode()).hexdigest()
        return self.merkle_hash


@dataclass
class TraceSpan:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    agent_name: str
    roles: List[str]
    kind: SpanKind
    status: SpanStatus
    timestamp: float
    duration_ms: float = 0.0
    model: str = ""
    token_input: int = 0
    token_output: int = 0
    token_total: int = 0
    prompt_hash: str = ""
    context_size: int = 0
    parent_context_size: int = 0
    context_fragment_pct: float = 0.0
    tool_invocations: List[ToolInvocation] = field(default_factory=list)
    system_resources: List[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    service_name: str = ""
    environment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["status"] = self.status.value
        return d

    @property
    def token_velocity(self) -> float:
        """Tokens per minute."""
        if self.duration_ms <= 0:
            return 0.0
        return (self.token_total / self.duration_ms) * 60_000


# ─────────────────────────────────────────
# SPAN BUFFER (async-safe batched sender)
# ─────────────────────────────────────────

class SpanBuffer:
    def __init__(self, config: TraceConfig):
        self._config = config
        self._queue: queue.Queue[TraceSpan] = queue.Queue(maxsize=config.max_queue)
        self._client = httpx.Client(
            base_url=config.endpoint,
            timeout=5.0,
            verify=config.tls_verify,
            headers={"X-DeepTrace-Key": config.api_key or ""},
        )
        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="deeptrace-flusher"
        )
        self._flush_thread.start()

    def push(self, span: TraceSpan) -> None:
        try:
            self._queue.put_nowait(span)
        except queue.Full:
            logger.warning("DeepTrace queue full — dropping span for %s", span.agent_name)

    def _flush_loop(self) -> None:
        batch: List[TraceSpan] = []
        while True:
            try:
                span = self._queue.get(timeout=self._config.flush_interval)
                batch.append(span)
                if len(batch) >= self._config.batch_size:
                    self._send_batch(batch)
                    batch = []
            except queue.Empty:
                if batch:
                    self._send_batch(batch)
                    batch = []

    def _send_batch(self, spans: List[TraceSpan]) -> None:
        try:
            payload = [s.to_dict() for s in spans]
            self._client.post("/ingest/batch", json=payload)
        except Exception as exc:
            logger.debug("DeepTrace send failed: %s", exc)

    def flush(self) -> None:
        """Blocking flush — call before process exit."""
        remaining: List[TraceSpan] = []
        while not self._queue.empty():
            try:
                remaining.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if remaining:
            self._send_batch(remaining)


# ─────────────────────────────────────────
# ZERO-TRUST POLICY ENGINE
# ─────────────────────────────────────────

@dataclass
class Permission:
    resource_pattern: str   # e.g. "src/*", "db:read", "node_modules/*"
    allow: bool = True
    requires_shadow: bool = False  # run in WASM sandbox first


class ZeroTrustPolicy:
    def __init__(self, agent_name: str, roles: List[str]):
        self._agent = agent_name
        self._roles = set(roles)
        self._rules: List[Permission] = []
        # Default deny-list patterns
        self._deny_patterns = [
            "node_modules/*",
            "**/.env",
            "**/secrets/**",
            "**/.git/config",
        ]

    def add_permission(self, pattern: str, allow: bool = True,
                       shadow: bool = False) -> None:
        self._rules.append(Permission(pattern, allow, shadow))

    def check(self, resource: str) -> tuple[bool, bool]:
        """Returns (allowed, requires_shadow)."""
        import fnmatch
        for deny in self._deny_patterns:
            if fnmatch.fnmatch(resource, deny):
                return False, False
        for rule in reversed(self._rules):
            if fnmatch.fnmatch(resource, rule.resource_pattern):
                return rule.allow, rule.requires_shadow
        # Default: allow with no shadow
        return True, False


# ─────────────────────────────────────────
# CONTEXT DIFF ENGINE
# ─────────────────────────────────────────

def compute_context_fragment(
    parent_context: str,
    child_context: str,
) -> float:
    """
    Returns fraction of parent context lost when passed to child.
    Uses Jaccard similarity on token-level n-grams.
    """
    if not parent_context:
        return 0.0
    def tokenize(text: str) -> set:
        words = text.lower().split()
        return set(words[i:i+3] for i in range(len(words) - 2)) | set(words)
    p_tokens = tokenize(parent_context)
    c_tokens = tokenize(child_context)
    if not p_tokens:
        return 0.0
    overlap = len(p_tokens & c_tokens) / len(p_tokens)
    return max(0.0, 1.0 - overlap)


# ─────────────────────────────────────────
# MAIN DEEPTRACE CLASS
# ─────────────────────────────────────────

class DeepTrace:
    """
    Primary SDK entry point.

    Usage:
        dt = DeepTrace(TraceConfig.from_env())

        @dt.agent(name="SecurityScanner", roles=["CodeAudit", "FileRead"])
        class SecurityScanner:
            def run(self, task):
                ...

        # Or decorate a standalone function:
        @dt.trace(name="planner_step", kind=SpanKind.LLM_CALL)
        def plan(prompt: str) -> str:
            ...
    """

    _local = threading.local()   # per-thread active span stack

    def __init__(self, config: Optional[TraceConfig] = None):
        self.config = config or TraceConfig.from_env()
        self._buffer = SpanBuffer(self.config)
        self._merkle_chain: Dict[str, str] = {}   # trace_id -> last hash

    # ── active span stack ──────────────────────
    @property
    def _span_stack(self) -> List[TraceSpan]:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        return self._local.stack

    def _push_span(self, span: TraceSpan) -> None:
        self._span_stack.append(span)

    def _pop_span(self) -> Optional[TraceSpan]:
        return self._span_stack.pop() if self._span_stack else None

    def _current_span(self) -> Optional[TraceSpan]:
        return self._span_stack[-1] if self._span_stack else None

    # ── span factory ──────────────────────────
    def _new_span(
        self,
        agent_name: str,
        roles: List[str],
        kind: SpanKind,
        parent_span_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> TraceSpan:
        parent = self._current_span()
        return TraceSpan(
            trace_id=trace_id or (parent.trace_id if parent else str(uuid.uuid4())),
            span_id=str(uuid.uuid4()),
            parent_span_id=parent_span_id or (parent.span_id if parent else None),
            agent_name=agent_name,
            roles=roles,
            kind=kind,
            status=SpanStatus.STARTED,
            timestamp=time.time(),
            service_name=self.config.service_name,
            environment=self.config.environment,
        )

    # ── decorator: @dt.agent ──────────────────
    def agent(
        self,
        name: str,
        roles: Optional[List[str]] = None,
        model: str = "",
        permissions: Optional[List[Permission]] = None,
    ) -> Callable:
        """Class decorator — instruments every public method on the agent."""
        _roles = roles or []
        _model = model
        _perms = permissions or []

        def class_decorator(cls: Type) -> Type:
            policy = ZeroTrustPolicy(name, _roles)
            for p in _perms:
                policy.add_permission(p.resource_pattern, p.allow, p.requires_shadow)

            original_init = cls.__init__

            @functools.wraps(original_init)
            def patched_init(self_inner, *args, **kwargs):
                self_inner._dt = DeepTrace.__sentinel__  # marker
                self_inner._dt_policy = policy
                self_inner._dt_name = name
                self_inner._dt_roles = _roles
                original_init(self_inner, *args, **kwargs)

            cls.__init__ = patched_init

            # Wrap every public callable method
            for attr in list(cls.__dict__):
                if attr.startswith("_"):
                    continue
                method = cls.__dict__[attr]
                if callable(method):
                    setattr(cls, attr, self._wrap_method(method, name, _roles, _model, policy))

            return cls

        return class_decorator

    # ── decorator: @dt.trace ──────────────────
    def trace(
        self,
        name: str,
        roles: Optional[List[str]] = None,
        kind: SpanKind = SpanKind.AGENT,
        model: str = "",
    ) -> Callable:
        """Function decorator for standalone agent functions."""
        _roles = roles or []

        def decorator(func: Callable) -> Callable:
            if asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    return await self._run_async(func, name, _roles, kind, model, args, kwargs)
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    return self._run_sync(func, name, _roles, kind, model, args, kwargs)
                return sync_wrapper

        return decorator

    # ── decorator: @dt.tool ──────────────────
    def tool(
        self,
        name: str,
        resource: Optional[str] = None,
    ) -> Callable:
        """
        Decorator for tool functions. Checks zero-trust policy, optionally
        runs in shadow mode, and emits a TOOL_CALL span.
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                parent = self._current_span()
                allowed, shadow = True, False
                if parent and self.config.zero_trust_enabled and resource:
                    policy = ZeroTrustPolicy(parent.agent_name, parent.roles)
                    allowed, shadow = policy.check(resource)

                invoc = ToolInvocation(
                    tool_name=name,
                    inputs={**kwargs, **{f"arg{i}": a for i, a in enumerate(args)}},
                    blocked=not allowed,
                )
                # Merkle chain
                parent_hash = self._merkle_chain.get(
                    parent.trace_id if parent else "", ""
                )
                invoc.compute_merkle(parent_hash)
                if parent:
                    self._merkle_chain[parent.trace_id] = invoc.merkle_hash

                if not allowed:
                    if parent:
                        parent.tool_invocations.append(invoc)
                        parent.system_resources.append(f"BLOCKED:{resource}")
                    self._emit_tool_block(invoc, parent)
                    raise PermissionError(
                        f"[DeepTrace Zero-Trust] Tool '{name}' blocked. "
                        f"Resource '{resource}' denied for agent '{parent.agent_name if parent else '?'}'"
                    )

                t0 = time.time()
                result = func(*args, **kwargs)
                invoc.output = str(result)[:512]
                invoc.duration_ms = (time.time() - t0) * 1000
                if parent:
                    parent.tool_invocations.append(invoc)
                    if resource:
                        parent.system_resources.append(resource)
                return result

            return wrapper
        return decorator

    # ── context manager ───────────────────────
    @contextmanager
    def span(self, name: str, roles: Optional[List[str]] = None,
             kind: SpanKind = SpanKind.AGENT):
        _span = self._new_span(name, roles or [], kind)
        _span.status = SpanStatus.STARTED
        self._push_span(_span)
        self._buffer.push(_span)
        t0 = time.time()
        try:
            yield _span
            _span.status = SpanStatus.COMPLETED
        except Exception as exc:
            _span.status = SpanStatus.FAILED
            _span.error = str(exc)
            raise
        finally:
            _span.duration_ms = (time.time() - t0) * 1000
            self._pop_span()
            self._buffer.push(_span)

    # ── internal run helpers ──────────────────
    def _run_sync(
        self, func, name, roles, kind, model, args, kwargs
    ):
        span = self._new_span(name, roles, kind)
        span.model = model
        self._push_span(span)
        self._buffer.push(span)
        t0 = time.time()
        try:
            result = func(*args, **kwargs)
            span.status = SpanStatus.COMPLETED
            self._post_process(span, str(result))
            return result
        except Exception as exc:
            span.status = SpanStatus.FAILED
            span.error = str(exc)
            raise
        finally:
            span.duration_ms = (time.time() - t0) * 1000
            self._pop_span()
            self._buffer.push(span)

    async def _run_async(
        self, func, name, roles, kind, model, args, kwargs
    ):
        span = self._new_span(name, roles, kind)
        span.model = model
        self._push_span(span)
        self._buffer.push(span)
        t0 = time.time()
        try:
            result = await func(*args, **kwargs)
            span.status = SpanStatus.COMPLETED
            self._post_process(span, str(result))
            return result
        except Exception as exc:
            span.status = SpanStatus.FAILED
            span.error = str(exc)
            raise
        finally:
            span.duration_ms = (time.time() - t0) * 1000
            self._pop_span()
            self._buffer.push(span)

    def _wrap_method(self, method, name, roles, model, policy):
        @functools.wraps(method)
        def wrapper(self_inner, *args, **kwargs):
            return self._run_sync(
                lambda *a, **k: method(self_inner, *a, **k),
                name, roles, SpanKind.AGENT, model, args, kwargs,
            )
        return wrapper

    def _post_process(self, span: TraceSpan, output: str) -> None:
        """Estimate tokens, detect anomalies."""
        chars = len(output)
        span.token_output = int(chars * self.config.token_heuristic)
        span.token_total = span.token_input + span.token_output
        # High token velocity alert
        if span.token_velocity > 3000:
            span.metadata["alert"] = "token_velocity_high"
            span.metadata["token_velocity"] = round(span.token_velocity, 1)

    def _emit_tool_block(self, invoc: ToolInvocation,
                         parent: Optional[TraceSpan]) -> None:
        block_span = TraceSpan(
            trace_id=parent.trace_id if parent else str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            parent_span_id=parent.span_id if parent else None,
            agent_name=parent.agent_name if parent else "unknown",
            roles=parent.roles if parent else [],
            kind=SpanKind.TOOL_CALL,
            status=SpanStatus.BLOCKED,
            timestamp=time.time(),
            tool_invocations=[invoc],
            service_name=self.config.service_name,
            environment=self.config.environment,
            metadata={"merkle_hash": invoc.merkle_hash},
        )
        self._buffer.push(block_span)

    def flush(self) -> None:
        self._buffer.flush()

    # Sentinel for class decoration marker
    __sentinel__ = object()


# ─────────────────────────────────────────
# LangChain Integration
# ─────────────────────────────────────────

class DeepTraceLangChainCallback:
    """
    LangChain callback handler.
    Pass to any LangChain chain/agent:
        chain.run(..., callbacks=[DeepTraceLangChainCallback(dt)])
    """
    def __init__(self, dt: DeepTrace):
        self._dt = dt
        self._spans: Dict[str, TraceSpan] = {}

    def on_llm_start(self, serialized, prompts, **kwargs):
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        span = self._dt._new_span(
            serialized.get("name", "llm"),
            [],
            SpanKind.LLM_CALL,
        )
        span.model = serialized.get("name", "")
        span.token_input = sum(len(p) for p in prompts) // 4
        self._spans[run_id] = span
        self._dt._push_span(span)
        self._dt._buffer.push(span)

    def on_llm_end(self, response, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        span = self._spans.pop(run_id, None)
        if not span:
            return
        output_text = ""
        for gen_list in response.generations:
            for gen in gen_list:
                output_text += gen.text
        span.token_output = len(output_text) // 4
        span.token_total = span.token_input + span.token_output
        span.status = SpanStatus.COMPLETED
        span.duration_ms = (time.time() - span.timestamp) * 1000
        self._dt._pop_span()
        self._dt._buffer.push(span)

    def on_tool_start(self, serialized, input_str, **kwargs):
        run_id = str(kwargs.get("run_id", uuid.uuid4()))
        span = self._dt._new_span(
            serialized.get("name", "tool"),
            [],
            SpanKind.TOOL_CALL,
        )
        self._spans[run_id] = span
        self._dt._push_span(span)
        self._dt._buffer.push(span)

    def on_tool_end(self, output, **kwargs):
        run_id = str(kwargs.get("run_id", ""))
        span = self._spans.pop(run_id, None)
        if not span:
            return
        span.status = SpanStatus.COMPLETED
        span.duration_ms = (time.time() - span.timestamp) * 1000
        self._dt._pop_span()
        self._dt._buffer.push(span)

    def on_chain_error(self, error, **kwargs):
        span = self._dt._current_span()
        if span:
            span.status = SpanStatus.FAILED
            span.error = str(error)
            self._dt._pop_span()
            self._dt._buffer.push(span)
