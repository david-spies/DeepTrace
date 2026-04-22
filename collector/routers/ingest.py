"""
Ingest router — receives spans from the DeepTrace SDK.
Handles single spans and batches, validates, enriches, then fans out.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, validator

logger = logging.getLogger("deeptrace.ingest")
router = APIRouter()


# ─────────────────────────────────────────
# REQUEST MODELS
# ─────────────────────────────────────────

class ToolInvocationModel(BaseModel):
    tool_name: str
    inputs: Dict[str, Any] = {}
    output: Optional[str] = None
    blocked: bool = False
    duration_ms: float = 0.0
    merkle_hash: str = ""


class SpanIngestModel(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    agent_name: str
    roles: List[str] = []
    kind: str = "AGENT"
    status: str = "COMPLETED"
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
    tool_invocations: List[ToolInvocationModel] = []
    system_resources: List[str] = []
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}
    service_name: str = ""
    environment: str = "production"

    @validator("status")
    def validate_status(cls, v):
        valid = {"STARTED", "COMPLETED", "FAILED", "KILLED", "BLOCKED"}
        if v.upper() not in valid:
            raise ValueError(f"status must be one of {valid}")
        return v.upper()

    @validator("kind")
    def validate_kind(cls, v):
        valid = {"AGENT", "LLM_CALL", "TOOL_CALL", "SPAWN", "CONTEXT"}
        if v.upper() not in valid:
            raise ValueError(f"kind must be one of {valid}")
        return v.upper()


class BatchIngestModel(BaseModel):
    spans: List[SpanIngestModel]


# ─────────────────────────────────────────
# ENRICHMENT
# ─────────────────────────────────────────

def enrich_span(span: SpanIngestModel) -> Dict[str, Any]:
    """Add derived fields before storage."""
    data = span.dict()

    # Token velocity (tok/min)
    if span.duration_ms > 0:
        data["token_velocity"] = round((span.token_total / span.duration_ms) * 60_000, 1)
    else:
        data["token_velocity"] = 0.0

    # Latency tier
    if span.duration_ms < 200:
        data["latency_tier"] = "fast"
    elif span.duration_ms < 2000:
        data["latency_tier"] = "normal"
    else:
        data["latency_tier"] = "slow"

    # Anomaly flags
    anomalies = []
    if data.get("token_velocity", 0) > 3000:
        anomalies.append("TOKEN_VELOCITY_HIGH")
    if span.context_fragment_pct > 0.30:
        anomalies.append("CONTEXT_FRAGMENTATION")
    if any(t.blocked for t in span.tool_invocations):
        anomalies.append("ZERO_TRUST_VIOLATION")
    if span.status == "BLOCKED":
        anomalies.append("ZERO_TRUST_VIOLATION")

    data["anomalies"] = anomalies
    data["has_anomaly"] = len(anomalies) > 0

    return data


# ─────────────────────────────────────────
# FAN-OUT TASKS
# ─────────────────────────────────────────

async def fanout_span(enriched: Dict[str, Any], request: Request):
    """Push enriched span to all downstream sinks."""
    kafka = request.app.state.kafka
    graph = request.app.state.graph
    clickhouse = request.app.state.clickhouse
    redis = request.app.state.redis
    anomaly = request.app.state.anomaly

    # 1. Kafka — async stream processing
    try:
        await kafka.send(enriched)
    except Exception as exc:
        logger.warning("Kafka send failed: %s", exc)

    # 2. Neo4j — update agent graph topology
    try:
        await graph.upsert_span(enriched)
    except Exception as exc:
        logger.warning("Neo4j upsert failed: %s", exc)

    # 3. ClickHouse — time-series analytics
    try:
        await clickhouse.insert_span(enriched)
    except Exception as exc:
        logger.warning("ClickHouse insert failed: %s", exc)

    # 4. Anomaly engine — real-time rules evaluation
    alerts = anomaly.evaluate(enriched)
    if alerts:
        enriched["live_alerts"] = alerts
        try:
            await redis.publish("deeptrace:alerts", json.dumps(alerts))
        except Exception as exc:
            logger.warning("Redis alert publish failed: %s", exc)

    # 5. Redis pub/sub — live dashboard feed
    try:
        await redis.publish("deeptrace:live", json.dumps(enriched))
    except Exception as exc:
        logger.warning("Redis live publish failed: %s", exc)


# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@router.post("/span", status_code=202, summary="Ingest a single span")
async def ingest_span(
    span: SpanIngestModel,
    request: Request,
    background_tasks: BackgroundTasks,
):
    enriched = enrich_span(span)
    background_tasks.add_task(fanout_span, enriched, request)
    return {"accepted": True, "span_id": span.span_id, "trace_id": span.trace_id}


@router.post("/batch", status_code=202, summary="Ingest a batch of spans")
async def ingest_batch(
    body: List[SpanIngestModel],
    request: Request,
    background_tasks: BackgroundTasks,
):
    if len(body) > 500:
        raise HTTPException(status_code=413, detail="Batch too large (max 500 spans)")

    enriched_batch = [enrich_span(span) for span in body]

    for enriched in enriched_batch:
        background_tasks.add_task(fanout_span, enriched, request)

    return {
        "accepted": True,
        "count": len(enriched_batch),
        "anomalies": sum(1 for e in enriched_batch if e.get("has_anomaly")),
    }


@router.post("/event", status_code=202, summary="Ingest a raw event (legacy/OTEL)")
async def ingest_event(
    payload: Dict[str, Any],
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Accepts raw OpenTelemetry-style JSON for compatibility with
    existing OTEL exporters pointing at the collector endpoint.
    """
    # Map OTEL fields to DeepTrace fields
    mapped = {
        "trace_id": payload.get("traceId", payload.get("trace_id", "")),
        "span_id": payload.get("spanId", payload.get("span_id", "")),
        "parent_span_id": payload.get("parentSpanId"),
        "agent_name": payload.get("serviceName", payload.get("agent", "unknown")),
        "roles": payload.get("roles", []),
        "kind": payload.get("kind", "AGENT"),
        "status": payload.get("status", "COMPLETED"),
        "timestamp": payload.get("startTimeUnixNano", 0) / 1e9 if "startTimeUnixNano" in payload else payload.get("timestamp", 0),
        "duration_ms": payload.get("durationMs", 0),
        "model": payload.get("attributes", {}).get("llm.model", ""),
        "token_total": payload.get("attributes", {}).get("llm.token_count.total", 0),
        "metadata": payload.get("attributes", {}),
        "service_name": payload.get("serviceName", ""),
        "environment": payload.get("environment", "production"),
    }

    try:
        span = SpanIngestModel(**mapped)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"OTEL mapping error: {exc}")

    enriched = enrich_span(span)
    background_tasks.add_task(fanout_span, enriched, request)
    return {"accepted": True, "span_id": span.span_id}
