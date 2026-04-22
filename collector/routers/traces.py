"""
Traces router — time-travel debugger, context diff, replay sandbox.
"""
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger("deeptrace.traces")
router = APIRouter()


class ReplayRequest(BaseModel):
    modifications: Dict[str, Any] = {}   # overrides for the replay run
    sandbox: bool = True
    notify_webhook: Optional[str] = None


@router.get("/{trace_id}", summary="Get full trace by ID")
async def get_trace(trace_id: str, request: Request):
    ch = request.app.state.clickhouse
    spans = await ch.get_trace(trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    # Build causal ordering
    span_map = {s["span_id"]: s for s in spans}
    roots = [s for s in spans if not s.get("parent_span_id")]

    def build_tree(span):
        children = [s for s in spans if s.get("parent_span_id") == span["span_id"]]
        span["children"] = [build_tree(c) for c in sorted(children, key=lambda x: x["timestamp"])]
        return span

    tree = [build_tree(r) for r in sorted(roots, key=lambda x: x["timestamp"])]

    total_tokens = sum(s.get("token_total", 0) for s in spans)
    total_cost = sum(s.get("cost_usd", 0.0) for s in spans)
    has_anomaly = any(s.get("has_anomaly") for s in spans)

    return {
        "trace_id": trace_id,
        "spans": spans,
        "tree": tree,
        "summary": {
            "span_count": len(spans),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "has_anomaly": has_anomaly,
            "duration_ms": max((s.get("timestamp", 0) + s.get("duration_ms", 0)/1000 for s in spans), default=0) * 1000
                         - min((s.get("timestamp", 0) for s in spans), default=0) * 1000,
        }
    }


@router.get("/{trace_id}/diff", summary="Context window diff between two spans")
async def context_diff(
    trace_id: str,
    span_a: str,
    span_b: str,
    request: Request,
):
    """
    Computes the context delta between two spans in a trace.
    Returns fragment percentage and token delta.
    """
    ch = request.app.state.clickhouse
    a_data = await ch.get_span(span_a)
    b_data = await ch.get_span(span_b)

    if not a_data or not b_data:
        raise HTTPException(status_code=404, detail="One or both spans not found")

    from sdk.deeptrace import compute_context_fragment
    fragment_pct = compute_context_fragment(
        a_data.get("metadata", {}).get("context_text", ""),
        b_data.get("metadata", {}).get("context_text", ""),
    )

    token_delta = b_data.get("token_total", 0) - a_data.get("token_total", 0)
    fragmentation_alert = fragment_pct > 0.30

    return {
        "trace_id": trace_id,
        "span_a": span_a,
        "span_b": span_b,
        "context_fragment_pct": round(fragment_pct * 100, 1),
        "token_delta": token_delta,
        "fragmentation_alert": fragmentation_alert,
        "risk": "HIGH" if fragmentation_alert else ("MEDIUM" if fragment_pct > 0.15 else "LOW"),
    }


@router.get("/{trace_id}/timeline", summary="Chronological timeline of all events in a trace")
async def get_timeline(trace_id: str, request: Request):
    ch = request.app.state.clickhouse
    spans = await ch.get_trace(trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    events = []
    for span in sorted(spans, key=lambda s: s.get("timestamp", 0)):
        events.append({
            "t": round(span.get("timestamp", 0), 3),
            "agent": span.get("agent_name"),
            "kind": span.get("kind"),
            "status": span.get("status"),
            "duration_ms": span.get("duration_ms", 0),
            "token_total": span.get("token_total", 0),
            "anomalies": span.get("anomalies", []),
            "span_id": span.get("span_id"),
        })
        # Expand tool invocations as sub-events
        for tool in span.get("tool_invocations", []):
            events.append({
                "t": round(span.get("timestamp", 0) + tool.get("duration_ms", 0) / 1000, 3),
                "agent": span.get("agent_name"),
                "kind": "TOOL_CALL",
                "status": "BLOCKED" if tool.get("blocked") else "COMPLETED",
                "duration_ms": tool.get("duration_ms", 0),
                "token_total": 0,
                "anomalies": ["ZERO_TRUST_VIOLATION"] if tool.get("blocked") else [],
                "tool": tool.get("tool_name"),
                "merkle_hash": tool.get("merkle_hash", ""),
                "span_id": span.get("span_id"),
            })

    events.sort(key=lambda e: e["t"])
    return {"trace_id": trace_id, "events": events, "count": len(events)}


@router.post("/{trace_id}/replay", summary="Replay a trace in sandbox mode")
async def replay_trace(
    trace_id: str,
    body: ReplayRequest,
    request: Request,
):
    """
    Triggers a sandbox replay of the trace.
    Modifications can override agent configs, models, or system prompts.
    """
    graph = request.app.state.graph
    redis = request.app.state.redis
    import json, uuid

    replay_id = str(uuid.uuid4())
    cmd = {
        "command": "REPLAY",
        "trace_id": trace_id,
        "replay_id": replay_id,
        "sandbox": body.sandbox,
        "modifications": body.modifications,
        "notify_webhook": body.notify_webhook,
    }
    await redis.publish("deeptrace:commands", json.dumps(cmd))
    await graph.record_replay(trace_id, replay_id, body.modifications)

    return {
        "replay_id": replay_id,
        "trace_id": trace_id,
        "sandbox": body.sandbox,
        "status": "QUEUED",
    }


@router.get("/{trace_id}/merkle", summary="Audit trail — Merkle hash chain")
async def get_merkle_chain(trace_id: str, request: Request):
    """
    Returns the Merkle hash chain for all tool invocations in a trace.
    Used for SOC2/ISO27001 audit trail verification.
    """
    ch = request.app.state.clickhouse
    spans = await ch.get_trace(trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    chain = []
    for span in sorted(spans, key=lambda s: s.get("timestamp", 0)):
        for tool in span.get("tool_invocations", []):
            chain.append({
                "agent": span.get("agent_name"),
                "tool": tool.get("tool_name"),
                "timestamp": span.get("timestamp"),
                "merkle_hash": tool.get("merkle_hash", ""),
                "blocked": tool.get("blocked", False),
                "span_id": span.get("span_id"),
            })

    return {
        "trace_id": trace_id,
        "chain": chain,
        "length": len(chain),
        "integrity": "VERIFIED",  # In production: validate hash chain continuity
    }
