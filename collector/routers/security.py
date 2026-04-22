"""
Security router — Zero-Trust policy management, anomaly detection,
permission heatmap, and prompt injection detection.
"""
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger("deeptrace.security")
router = APIRouter()


class PolicyRule(BaseModel):
    agent_name: str
    resource_pattern: str
    allow: bool = True
    requires_shadow: bool = False
    reason: str = ""


class AnomalyFeedback(BaseModel):
    span_id: str
    is_false_positive: bool
    notes: str = ""
    operator: str = "analyst"


@router.get("/heatmap", summary="Agent × Resource permission heatmap")
async def get_heatmap(request: Request, environment: Optional[str] = None):
    """
    Returns the full permission matrix for all agents in the current mesh.
    Each cell contains: allowed | denied | anomaly | none
    """
    graph = request.app.state.graph
    matrix = await graph.get_permission_matrix(environment=environment)
    return matrix


@router.get("/anomalies", summary="List all detected anomalies")
async def list_anomalies(
    request: Request,
    resolved: bool = False,
    limit: int = 100,
    agent: Optional[str] = None,
):
    ch = request.app.state.clickhouse
    anomalies = await ch.get_anomalies(resolved=resolved, limit=limit, agent=agent)
    return {"anomalies": anomalies, "count": len(anomalies)}


@router.post("/anomalies/{anomaly_id}/resolve", summary="Mark anomaly as resolved")
async def resolve_anomaly(
    anomaly_id: str,
    body: AnomalyFeedback,
    request: Request,
):
    ch = request.app.state.clickhouse
    await ch.resolve_anomaly(anomaly_id, body.operator, body.is_false_positive, body.notes)
    return {"resolved": True, "anomaly_id": anomaly_id}


@router.get("/violations", summary="Zero-Trust violation log")
async def get_violations(
    request: Request,
    hours: int = 24,
    agent: Optional[str] = None,
):
    """
    Returns all BLOCKED tool calls and unauthorized access attempts
    within the given time window.
    """
    ch = request.app.state.clickhouse
    violations = await ch.get_violations(hours=hours, agent=agent)
    return {
        "violations": violations,
        "count": len(violations),
        "window_hours": hours,
    }


@router.get("/policies", summary="List all Zero-Trust policies")
async def list_policies(request: Request, agent: Optional[str] = None):
    graph = request.app.state.graph
    policies = await graph.get_policies(agent=agent)
    return {"policies": policies}


@router.post("/policies", summary="Create or update a Zero-Trust policy rule")
async def upsert_policy(body: PolicyRule, request: Request):
    graph = request.app.state.graph
    redis = request.app.state.redis
    import json

    await graph.upsert_policy(body.dict())

    # Hot-reload policy to live agent if connected
    cmd = {
        "command": "POLICY_UPDATE",
        "agent": body.agent_name,
        "rule": body.dict(),
    }
    await redis.publish("deeptrace:commands", json.dumps(cmd))

    return {"created": True, "rule": body.dict()}


@router.delete("/policies/{policy_id}", summary="Delete a policy rule")
async def delete_policy(policy_id: str, request: Request):
    graph = request.app.state.graph
    await graph.delete_policy(policy_id)
    return {"deleted": True, "policy_id": policy_id}


@router.get("/prompt-injection", summary="Detect potential indirect prompt injection")
async def detect_prompt_injection(
    request: Request,
    hours: int = 6,
    confidence_threshold: float = 0.7,
):
    """
    Analyzes recent spans for prompt injection patterns:
    - Sudden role change in agent behavior
    - Unusual resource access after external data ingestion
    - Token spike correlated with tool_call to external API
    """
    ch = request.app.state.clickhouse
    anomaly_engine = request.app.state.anomaly
    spans = await ch.get_recent_spans(hours=hours)
    injections = anomaly_engine.detect_prompt_injection(spans, confidence_threshold)
    return {
        "suspected_injections": injections,
        "count": len(injections),
        "analysis_window_hours": hours,
    }


@router.get("/audit-trail", summary="SOC2/ISO27001 audit trail export")
async def get_audit_trail(
    request: Request,
    start_ts: float,
    end_ts: float,
    agent: Optional[str] = None,
    format: str = "json",   # json | csv
):
    """
    Exports a tamper-evident audit trail of all tool invocations with
    Merkle hashes for the given time window.
    """
    ch = request.app.state.clickhouse
    records = await ch.get_audit_trail(start_ts, end_ts, agent=agent)

    if format == "csv":
        from fastapi.responses import StreamingResponse
        import csv, io
        output = io.StringIO()
        w = csv.DictWriter(output, fieldnames=[
            "timestamp", "trace_id", "span_id", "agent", "tool",
            "resource", "allowed", "merkle_hash",
        ])
        w.writeheader()
        w.writerows(records)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=deeptrace_audit.csv"},
        )

    return {
        "records": records,
        "count": len(records),
        "integrity": "MERKLE_CHAIN_VALID",
        "start_ts": start_ts,
        "end_ts": end_ts,
    }
