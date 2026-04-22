"""
Metrics router — token analytics, cost tracking, latency percentiles.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Request

logger = logging.getLogger("deeptrace.metrics")
router = APIRouter()


@router.get("/summary", summary="Global session metrics summary")
async def get_summary(request: Request, environment: Optional[str] = None):
    ch = request.app.state.clickhouse
    summary = await ch.get_summary(environment=environment)
    return summary


@router.get("/token-debt", summary="Token debt by agent (high-to-low)")
async def get_token_debt(request: Request, limit: int = 20):
    """
    Identifies which agents are consuming the most tokens —
    helping developers prune verbose prompts.
    """
    ch = request.app.state.clickhouse
    ranking = await ch.get_token_debt_ranking(limit=limit)
    return {"ranking": ranking}


@router.get("/latency-percentiles", summary="P50/P90/P99 latency by agent")
async def get_latency_percentiles(request: Request, window: str = "1h"):
    ch = request.app.state.clickhouse
    percentiles = await ch.get_latency_percentiles(window=window)
    return {"percentiles": percentiles, "window": window}


@router.get("/cost-breakdown", summary="Cost breakdown by agent and model")
async def get_cost_breakdown(request: Request, window: str = "24h"):
    ch = request.app.state.clickhouse
    breakdown = await ch.get_cost_breakdown(window=window)
    return {"breakdown": breakdown, "window": window}


@router.get("/topology", summary="Live graph topology snapshot")
async def get_topology(request: Request):
    """
    Returns nodes and edges for the current agent mesh —
    consumed by the React topology canvas.
    """
    graph = request.app.state.graph
    topology = await graph.get_topology_snapshot()
    return topology
