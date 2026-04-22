"""
Agents router — query and manage running agents in the mesh.
"""
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger("deeptrace.agents")
router = APIRouter()


class HotPatchRequest(BaseModel):
    system_prompt_delta: str
    reason: str = ""
    operator: str = "dashboard"


class KillRequest(BaseModel):
    reason: str = ""
    operator: str = "dashboard"


@router.get("/", summary="List all active agents in the mesh")
async def list_agents(request: Request, environment: Optional[str] = None):
    graph = request.app.state.graph
    agents = await graph.get_all_agents(environment=environment)
    return {"agents": agents, "count": len(agents)}


@router.get("/{agent_name}", summary="Get agent detail with latest span")
async def get_agent(agent_name: str, request: Request):
    graph = request.app.state.graph
    agent = await graph.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return agent


@router.get("/{agent_name}/spans", summary="Get recent spans for an agent")
async def get_agent_spans(
    agent_name: str,
    request: Request,
    limit: int = 50,
    status: Optional[str] = None,
):
    ch = request.app.state.clickhouse
    spans = await ch.get_agent_spans(agent_name, limit=limit, status=status)
    return {"agent": agent_name, "spans": spans, "count": len(spans)}


@router.get("/{agent_name}/token_history", summary="Token usage time-series")
async def get_token_history(
    agent_name: str,
    request: Request,
    window: str = "1h",   # 5m, 15m, 1h, 6h, 24h
):
    ch = request.app.state.clickhouse
    history = await ch.get_token_history(agent_name, window=window)
    return {"agent": agent_name, "window": window, "series": history}


@router.post("/{agent_name}/kill", summary="Kill a running agent process")
async def kill_agent(agent_name: str, body: KillRequest, request: Request):
    graph = request.app.state.graph
    redis = request.app.state.redis
    import json

    await graph.set_agent_status(agent_name, "KILLED")

    # Broadcast kill command to SDK listeners
    cmd = {
        "command": "KILL",
        "agent": agent_name,
        "reason": body.reason,
        "operator": body.operator,
    }
    await redis.publish("deeptrace:commands", json.dumps(cmd))
    logger.info("Agent %s killed by %s: %s", agent_name, body.operator, body.reason)

    return {"killed": True, "agent": agent_name}


@router.post("/{agent_name}/hotpatch", summary="Inject a system prompt delta")
async def hotpatch_agent(
    agent_name: str,
    body: HotPatchRequest,
    request: Request,
):
    redis = request.app.state.redis
    graph = request.app.state.graph
    import json, time

    patch = {
        "command": "HOTPATCH",
        "agent": agent_name,
        "delta": body.system_prompt_delta,
        "reason": body.reason,
        "operator": body.operator,
        "timestamp": time.time(),
    }
    await redis.publish("deeptrace:commands", json.dumps(patch))
    await graph.record_hotpatch(agent_name, body.system_prompt_delta, body.operator)

    logger.info("Hotpatch sent to %s by %s", agent_name, body.operator)
    return {"patched": True, "agent": agent_name, "operator": body.operator}


@router.get("/{agent_name}/permissions", summary="Get Zero-Trust permission summary")
async def get_permissions(agent_name: str, request: Request):
    graph = request.app.state.graph
    perms = await graph.get_agent_permissions(agent_name)
    return {"agent": agent_name, "permissions": perms}
