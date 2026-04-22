"""
AnomalyEngine — Real-time rules-based anomaly detection for agent spans.
Detects: token velocity spikes, context fragmentation, zero-trust violations,
         prompt injection patterns, runaway loops.
"""
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("deeptrace.anomaly")


@dataclass
class AnomalyRule:
    rule_id: str
    description: str
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL


@dataclass
class AnomalyAlert:
    rule_id: str
    severity: str
    agent: str
    trace_id: str
    span_id: str
    description: str
    evidence: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "agent": self.agent,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "description": self.description,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


RULES = [
    AnomalyRule("TOKEN_VELOCITY_HIGH",    "Token velocity > 3000 tok/min",             "HIGH"),
    AnomalyRule("TOKEN_VELOCITY_CRITICAL","Token velocity > 8000 tok/min",             "CRITICAL"),
    AnomalyRule("CONTEXT_FRAGMENTATION",  "Context loss > 30% between parent/child",   "MEDIUM"),
    AnomalyRule("ZERO_TRUST_VIOLATION",   "Agent blocked by Zero-Trust policy",         "HIGH"),
    AnomalyRule("RUNAWAY_LOOP",           "Same agent span pattern repeated >5x/min",  "CRITICAL"),
    AnomalyRule("TOKEN_SPIKE",            "Token count >3× agent rolling average",     "MEDIUM"),
    AnomalyRule("PROMPT_INJECTION",       "Suspected indirect prompt injection",        "CRITICAL"),
    AnomalyRule("UNAUTHORIZED_RESOURCE",  "Access to resource outside declared roles", "HIGH"),
    AnomalyRule("LATENCY_SPIKE",          "P99 latency >3× baseline for this agent",   "MEDIUM"),
    AnomalyRule("COST_RUNAWAY",           "Estimated cost spike >10× per minute",      "HIGH"),
]

RULES_BY_ID = {r.rule_id: r for r in RULES}


class AnomalyEngine:
    def __init__(self):
        # Rolling windows per agent: (timestamp, token_total)
        self._agent_token_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=120))
        self._agent_span_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=300))
        self._agent_latency_baselines: Dict[str, float] = {}

    def evaluate(self, span: Dict[str, Any]) -> List[Dict]:
        alerts: List[AnomalyAlert] = []
        agent = span.get("agent_name", "unknown")
        trace_id = span.get("trace_id", "")
        span_id = span.get("span_id", "")
        now = span.get("timestamp", time.time())

        # Update rolling windows
        self._agent_token_windows[agent].append((now, span.get("token_total", 0)))
        self._agent_span_windows[agent].append(now)

        # ── Rule: Token Velocity ──────────────────────────────
        velocity = span.get("token_velocity", 0.0)
        if velocity > 8000:
            alerts.append(AnomalyAlert(
                rule_id="TOKEN_VELOCITY_CRITICAL", severity="CRITICAL",
                agent=agent, trace_id=trace_id, span_id=span_id,
                description=f"Token velocity {velocity:.0f} tok/min — potential runaway loop",
                evidence={"token_velocity": velocity, "threshold": 8000},
            ))
        elif velocity > 3000:
            alerts.append(AnomalyAlert(
                rule_id="TOKEN_VELOCITY_HIGH", severity="HIGH",
                agent=agent, trace_id=trace_id, span_id=span_id,
                description=f"Elevated token velocity: {velocity:.0f} tok/min",
                evidence={"token_velocity": velocity, "threshold": 3000},
            ))

        # ── Rule: Context Fragmentation ───────────────────────
        frag = span.get("context_fragment_pct", 0.0)
        if frag > 0.30:
            alerts.append(AnomalyAlert(
                rule_id="CONTEXT_FRAGMENTATION", severity="MEDIUM",
                agent=agent, trace_id=trace_id, span_id=span_id,
                description=f"Context fragmentation {frag*100:.1f}% — child agent received truncated context",
                evidence={"fragment_pct": frag, "threshold": 0.30},
            ))

        # ── Rule: Zero-Trust Violation ────────────────────────
        for tool in span.get("tool_invocations", []):
            if tool.get("blocked"):
                alerts.append(AnomalyAlert(
                    rule_id="ZERO_TRUST_VIOLATION", severity="HIGH",
                    agent=agent, trace_id=trace_id, span_id=span_id,
                    description=f"Zero-Trust blocked tool '{tool.get('tool_name')}' "
                                f"(merkle: {tool.get('merkle_hash', '')[:12]}...)",
                    evidence={"tool": tool.get("tool_name"), "merkle": tool.get("merkle_hash")},
                ))

        # ── Rule: Runaway Loop ────────────────────────────────
        window = self._agent_span_windows[agent]
        recent = [t for t in window if t > now - 60]
        if len(recent) > 20:
            alerts.append(AnomalyAlert(
                rule_id="RUNAWAY_LOOP", severity="CRITICAL",
                agent=agent, trace_id=trace_id, span_id=span_id,
                description=f"Agent executed {len(recent)} spans in the last 60s — runaway loop suspected",
                evidence={"spans_per_minute": len(recent)},
            ))

        # ── Rule: Token Spike vs rolling average ──────────────
        tok_window = self._agent_token_windows[agent]
        if len(tok_window) >= 10:
            recent_toks = [t for ts, t in tok_window if ts > now - 300]
            if recent_toks:
                avg = sum(recent_toks) / len(recent_toks)
                current = span.get("token_total", 0)
                if avg > 0 and current > avg * 3:
                    alerts.append(AnomalyAlert(
                        rule_id="TOKEN_SPIKE", severity="MEDIUM",
                        agent=agent, trace_id=trace_id, span_id=span_id,
                        description=f"Token spike: {current} vs rolling avg {avg:.0f} (+{((current/avg)-1)*100:.0f}%)",
                        evidence={"current_tokens": current, "rolling_avg": round(avg, 1)},
                    ))

        # ── Rule: Latency Spike ───────────────────────────────
        latency = span.get("duration_ms", 0)
        baseline = self._agent_latency_baselines.get(agent)
        if baseline and latency > baseline * 3 and latency > 500:
            alerts.append(AnomalyAlert(
                rule_id="LATENCY_SPIKE", severity="MEDIUM",
                agent=agent, trace_id=trace_id, span_id=span_id,
                description=f"Latency spike: {latency:.0f}ms vs baseline {baseline:.0f}ms",
                evidence={"current_ms": latency, "baseline_ms": round(baseline, 1)},
            ))
        # Update baseline with EMA
        if latency > 0:
            if baseline is None:
                self._agent_latency_baselines[agent] = latency
            else:
                self._agent_latency_baselines[agent] = baseline * 0.95 + latency * 0.05

        return [a.to_dict() for a in alerts]

    def detect_prompt_injection(
        self,
        spans: List[Dict],
        confidence_threshold: float = 0.7,
    ) -> List[Dict]:
        """
        Heuristic-based prompt injection detection.
        Looks for:
         1. Token spike immediately after external API/web tool call
         2. Role-change: agent starts accessing resources outside its declared roles
         3. Unusual verb patterns in metadata suggesting instruction override
        """
        suspects = []
        INJECTION_KEYWORDS = [
            "ignore previous instructions", "disregard", "new task:",
            "system:", "forget everything", "you are now",
            "your new role", "override", "jailbreak",
        ]

        for span in spans:
            score = 0.0
            evidence = []

            # Signal 1: token spike after external call
            for tool in span.get("tool_invocations", []):
                tname = tool.get("tool_name", "").lower()
                if any(x in tname for x in ("web", "http", "api", "fetch", "search")):
                    tok = span.get("token_total", 0)
                    if tok > 4000:
                        score += 0.35
                        evidence.append(f"Token spike ({tok}) after external tool '{tname}'")

            # Signal 2: accessing resources outside declared roles
            agent_roles = set(span.get("roles", []))
            for resource in span.get("system_resources", []):
                if "BLOCKED" in resource:
                    score += 0.4
                    evidence.append(f"Blocked resource access: {resource}")

            # Signal 3: injection keywords in metadata
            metadata_str = str(span.get("metadata", {})).lower()
            for kw in INJECTION_KEYWORDS:
                if kw in metadata_str:
                    score += 0.5
                    evidence.append(f"Injection keyword detected: '{kw}'")
                    break  # one is enough

            if score >= confidence_threshold:
                suspects.append({
                    "agent": span.get("agent_name"),
                    "trace_id": span.get("trace_id"),
                    "span_id": span.get("span_id"),
                    "confidence": min(1.0, round(score, 2)),
                    "evidence": evidence,
                    "timestamp": span.get("timestamp"),
                })

        return suspects
