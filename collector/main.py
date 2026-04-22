"""
DeepTrace Collector — FastAPI ingest server.
Receives spans from the SDK, validates, enriches, and routes them to:
  - Kafka (stream processing)
  - Neo4j (graph engine, via background worker)
  - Redis pub/sub (live dashboard WebSocket feed)
  - ClickHouse (time-series analytics)
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import ingest, agents, traces, security, metrics
from .services.kafka_producer import KafkaProducerService
from .services.graph_service import GraphService
from .services.clickhouse_service import ClickHouseService
from .services.redis_pubsub import RedisPubSubService
from .services.ws_manager import WebSocketManager
from .services.anomaly_engine import AnomalyEngine

logger = logging.getLogger("deeptrace.collector")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


# ─────────────────────────────────────────
# SERVICE SINGLETONS (attached to app.state)
# ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DeepTrace Collector starting...")

    app.state.kafka = KafkaProducerService(
        brokers=os.getenv("KAFKA_BROKERS", "localhost:9092"),
        topic="deeptrace-spans",
    )
    app.state.graph = GraphService(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "deeptrace"),
    )
    app.state.clickhouse = ClickHouseService(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "9000")),
        database=os.getenv("CLICKHOUSE_DB", "deeptrace"),
    )
    app.state.redis = RedisPubSubService(
        url=os.getenv("REDIS_URL", "redis://localhost:6379"),
    )
    app.state.ws_manager = WebSocketManager()
    app.state.anomaly = AnomalyEngine()

    await app.state.graph.connect()
    await app.state.clickhouse.connect()
    await app.state.redis.connect()
    await app.state.kafka.start()

    # Background task: Redis subscriber → WebSocket broadcast
    asyncio.create_task(_redis_to_ws(app))

    logger.info("DeepTrace Collector ready on :8080")
    yield

    logger.info("Shutting down DeepTrace Collector...")
    await app.state.kafka.stop()
    await app.state.redis.disconnect()
    await app.state.graph.disconnect()
    await app.state.clickhouse.disconnect()


async def _redis_to_ws(app: FastAPI):
    """Bridge Redis pub/sub messages to connected WebSocket clients."""
    async for message in app.state.redis.subscribe("deeptrace:live"):
        await app.state.ws_manager.broadcast(message)


# ─────────────────────────────────────────
# APP
# ─────────────────────────────────────────

app = FastAPI(
    title="DeepTrace Collector",
    version="2.1.0",
    description="LLM Service Mesh — Telemetry ingest and observability API",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────
# ROUTERS
# ─────────────────────────────────────────

app.include_router(ingest.router,   prefix="/ingest",   tags=["Ingest"])
app.include_router(agents.router,   prefix="/agents",   tags=["Agents"])
app.include_router(traces.router,   prefix="/traces",   tags=["Traces"])
app.include_router(security.router, prefix="/security", tags=["Security"])
app.include_router(metrics.router,  prefix="/metrics",  tags=["Metrics"])


# ─────────────────────────────────────────
# WEBSOCKET — live topology feed
# ─────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    manager: WebSocketManager = websocket.app.state.ws_manager
    await manager.connect(websocket)
    try:
        while True:
            # Keep alive — client can send ping
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/agent/{agent_id}")
async def websocket_agent(websocket: WebSocket, agent_id: str):
    """Per-agent live stream for focused debugging."""
    manager: WebSocketManager = websocket.app.state.ws_manager
    await manager.connect(websocket, room=f"agent:{agent_id}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ─────────────────────────────────────────
# HEALTH / READY
# ─────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "deeptrace-collector", "version": "2.1.0"}


@app.get("/ready", tags=["System"])
async def ready(request: Request):
    checks = {
        "neo4j": await request.app.state.graph.ping(),
        "clickhouse": await request.app.state.clickhouse.ping(),
        "redis": await request.app.state.redis.ping(),
        "kafka": request.app.state.kafka.is_connected(),
    }
    all_ok = all(checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"ready": all_ok, "checks": checks},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": str(exc)})
