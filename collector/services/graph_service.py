"""
Graph Service — Neo4j driver for agent topology and relationships.
Maps agents as nodes, interactions as edges.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("deeptrace.graph")


class GraphService:
    def __init__(self, uri: str, user: str, password: str):
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None

    async def connect(self):
        try:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            await self._driver.verify_connectivity()
            await self._bootstrap_schema()
            logger.info("Neo4j connected at %s", self._uri)
        except ImportError:
            logger.warning("neo4j package not installed — graph features disabled")
        except Exception as exc:
            logger.error("Neo4j connection failed: %s", exc)

    async def disconnect(self):
        if self._driver:
            await self._driver.close()

    async def ping(self) -> bool:
        if not self._driver:
            return False
        try:
            async with self._driver.session() as s:
                await s.run("RETURN 1")
            return True
        except Exception:
            return False

    async def _bootstrap_schema(self):
        """Create constraints and indexes on first run."""
        if not self._driver:
            return
        constraints = [
            "CREATE CONSTRAINT agent_name IF NOT EXISTS FOR (a:Agent) REQUIRE a.name IS UNIQUE",
            "CREATE CONSTRAINT trace_id IF NOT EXISTS FOR (t:Trace) REQUIRE t.trace_id IS UNIQUE",
            "CREATE CONSTRAINT span_id IF NOT EXISTS FOR (s:Span) REQUIRE s.span_id IS UNIQUE",
            "CREATE INDEX agent_env IF NOT EXISTS FOR (a:Agent) ON (a.environment)",
            "CREATE INDEX span_status IF NOT EXISTS FOR (s:Span) ON (s.status)",
        ]
        async with self._driver.session() as session:
            for stmt in constraints:
                try:
                    await session.run(stmt)
                except Exception:
                    pass  # Already exists

    async def upsert_span(self, span: Dict[str, Any]):
        if not self._driver:
            return
        async with self._driver.session() as session:
            # Upsert agent node
            await session.run("""
                MERGE (a:Agent {name: $agent_name})
                SET a.status        = $status,
                    a.model         = $model,
                    a.roles         = $roles,
                    a.last_seen     = $timestamp,
                    a.token_total   = COALESCE(a.token_total, 0) + $token_total,
                    a.call_count    = COALESCE(a.call_count, 0) + 1,
                    a.environment   = $environment,
                    a.has_anomaly   = $has_anomaly
            """, {
                "agent_name": span["agent_name"],
                "status": span["status"],
                "model": span.get("model", ""),
                "roles": span.get("roles", []),
                "timestamp": span["timestamp"],
                "token_total": span.get("token_total", 0),
                "environment": span.get("environment", "production"),
                "has_anomaly": span.get("has_anomaly", False),
            })

            # Create span node
            await session.run("""
                MERGE (s:Span {span_id: $span_id})
                SET s.trace_id    = $trace_id,
                    s.status      = $status,
                    s.kind        = $kind,
                    s.duration_ms = $duration_ms,
                    s.timestamp   = $timestamp,
                    s.anomalies   = $anomalies

                WITH s
                MATCH (a:Agent {name: $agent_name})
                MERGE (a)-[:EXECUTED]->(s)
            """, {
                "span_id": span["span_id"],
                "trace_id": span["trace_id"],
                "status": span["status"],
                "kind": span.get("kind", "AGENT"),
                "duration_ms": span.get("duration_ms", 0),
                "timestamp": span["timestamp"],
                "anomalies": span.get("anomalies", []),
                "agent_name": span["agent_name"],
            })

            # Parent-child span relationship
            if span.get("parent_span_id"):
                await session.run("""
                    MATCH (parent:Span {span_id: $parent_id})
                    MATCH (child:Span  {span_id: $child_id})
                    MERGE (parent)-[:SPAWNED]->(child)
                """, {"parent_id": span["parent_span_id"], "child_id": span["span_id"]})

            # Agent-to-system edges for tool invocations
            for tool in span.get("tool_invocations", []):
                resource = tool.get("tool_name", "unknown")
                rel_type = "BLOCKED_ACCESS" if tool.get("blocked") else "INVOKED"
                await session.run(f"""
                    MATCH (a:Agent {{name: $agent_name}})
                    MERGE (sys:SystemResource {{name: $resource}})
                    MERGE (a)-[r:{rel_type}]->(sys)
                    SET r.count       = COALESCE(r.count, 0) + 1,
                        r.last_called = $timestamp,
                        r.blocked     = $blocked
                """, {
                    "agent_name": span["agent_name"],
                    "resource": resource,
                    "timestamp": span["timestamp"],
                    "blocked": tool.get("blocked", False),
                })

    async def get_all_agents(self, environment: Optional[str] = None) -> List[Dict]:
        if not self._driver:
            return []
        async with self._driver.session() as session:
            filter_clause = "WHERE a.environment = $env" if environment else ""
            result = await session.run(f"""
                MATCH (a:Agent)
                {filter_clause}
                OPTIONAL MATCH (a)-[:INVOKED]->(sys:SystemResource)
                RETURN a, collect(DISTINCT sys.name) AS resources
                ORDER BY a.token_total DESC
            """, {"env": environment or ""})
            rows = await result.data()
            return [
                {**dict(r["a"]), "system_resources": r["resources"]}
                for r in rows
            ]

    async def get_agent(self, name: str) -> Optional[Dict]:
        if not self._driver:
            return None
        async with self._driver.session() as session:
            result = await session.run("""
                MATCH (a:Agent {name: $name})
                OPTIONAL MATCH (a)-[:INVOKED]->(sys:SystemResource)
                OPTIONAL MATCH (a)-[:BLOCKED_ACCESS]->(blocked:SystemResource)
                RETURN a,
                       collect(DISTINCT sys.name)     AS resources,
                       collect(DISTINCT blocked.name) AS blocked_resources
            """, {"name": name})
            row = await result.single()
            if not row:
                return None
            return {
                **dict(row["a"]),
                "system_resources": row["resources"],
                "blocked_resources": row["blocked_resources"],
            }

    async def get_topology_snapshot(self) -> Dict[str, Any]:
        if not self._driver:
            return {"nodes": [], "edges": []}
        async with self._driver.session() as session:
            # Nodes
            r_nodes = await session.run("""
                MATCH (a:Agent)
                RETURN a.name AS id, a.status AS status, a.model AS model,
                       a.roles AS roles, a.token_total AS token_total,
                       a.call_count AS calls, a.has_anomaly AS has_anomaly,
                       a.environment AS environment
                ORDER BY a.token_total DESC
            """)
            nodes = await r_nodes.data()

            # System resource nodes
            r_sys = await session.run("""
                MATCH (s:SystemResource)
                RETURN s.name AS id, 'SYSTEM' AS status, '' AS model,
                       [] AS roles, 0 AS token_total, 0 AS calls,
                       false AS has_anomaly, '' AS environment
            """)
            sys_nodes = await r_sys.data()
            nodes += sys_nodes

            # Edges (agent-to-agent via shared trace)
            r_edges = await session.run("""
                MATCH (a:Agent)-[:EXECUTED]->(s:Span)<-[:SPAWNED]-(ps:Span)<-[:EXECUTED]-(b:Agent)
                WHERE a.name <> b.name
                WITH a.name AS from, b.name AS to,
                     count(*) AS weight, avg(s.duration_ms) AS avg_latency
                RETURN from, to, weight, avg_latency
                ORDER BY weight DESC LIMIT 100
            """)
            agent_edges = await r_edges.data()

            # Agent-to-system edges
            r_sys_edges = await session.run("""
                MATCH (a:Agent)-[r:INVOKED|BLOCKED_ACCESS]->(s:SystemResource)
                RETURN a.name AS from, s.name AS to, r.count AS weight,
                       type(r) AS relation, r.blocked AS blocked
            """)
            sys_edges = await r_sys_edges.data()

            all_edges = [
                {
                    "from": e["from"], "to": e["to"],
                    "weight": e["weight"],
                    "latency_ms": round(e.get("avg_latency") or 0, 1),
                    "kind": "AGENT_TO_AGENT",
                }
                for e in agent_edges
            ] + [
                {
                    "from": e["from"], "to": e["to"],
                    "weight": e["weight"] or 1,
                    "blocked": e.get("blocked", False),
                    "kind": "AGENT_TO_SYSTEM",
                    "relation": e["relation"],
                }
                for e in sys_edges
            ]

            return {"nodes": nodes, "edges": all_edges}

    async def set_agent_status(self, agent_name: str, status: str):
        if not self._driver:
            return
        async with self._driver.session() as session:
            await session.run(
                "MATCH (a:Agent {name: $name}) SET a.status = $status",
                {"name": agent_name, "status": status},
            )

    async def get_permission_matrix(self, environment: Optional[str] = None) -> Dict:
        if not self._driver:
            return {"agents": [], "resources": [], "cells": {}}
        async with self._driver.session() as session:
            r = await session.run("""
                MATCH (a:Agent)-[rel:INVOKED|BLOCKED_ACCESS]->(sys:SystemResource)
                RETURN a.name AS agent, sys.name AS resource,
                       type(rel) AS rel_type, rel.blocked AS blocked
            """)
            rows = await r.data()

            agents = sorted(set(row["agent"] for row in rows))
            resources = sorted(set(row["resource"] for row in rows))
            cells = {}
            for row in rows:
                key = f"{row['agent']}-{row['resource']}"
                if row.get("blocked"):
                    cells[key] = "BLOCKED"
                else:
                    cells[key] = "ALLOWED"

            return {"agents": agents, "resources": resources, "cells": cells}

    async def get_policies(self, agent: Optional[str] = None) -> List[Dict]:
        if not self._driver:
            return []
        async with self._driver.session() as session:
            filter_clause = "WHERE p.agent_name = $agent" if agent else ""
            result = await session.run(f"""
                MATCH (p:Policy) {filter_clause}
                RETURN p ORDER BY p.created_at DESC
            """, {"agent": agent or ""})
            rows = await result.data()
            return [dict(r["p"]) for r in rows]

    async def upsert_policy(self, policy: Dict):
        if not self._driver:
            return
        import uuid, time
        async with self._driver.session() as session:
            await session.run("""
                MERGE (p:Policy {agent_name: $agent_name, resource_pattern: $resource_pattern})
                SET p.allow           = $allow,
                    p.requires_shadow = $requires_shadow,
                    p.reason          = $reason,
                    p.updated_at      = $updated_at
                ON CREATE SET p.created_at = $updated_at, p.id = $id
            """, {
                **policy,
                "updated_at": time.time(),
                "id": str(uuid.uuid4()),
            })

    async def delete_policy(self, policy_id: str):
        if not self._driver:
            return
        async with self._driver.session() as session:
            await session.run("MATCH (p:Policy {id: $id}) DETACH DELETE p", {"id": policy_id})

    async def get_agent_permissions(self, agent_name: str) -> List[Dict]:
        if not self._driver:
            return []
        async with self._driver.session() as session:
            result = await session.run("""
                MATCH (a:Agent {name: $name})-[r]->(sys)
                RETURN type(r) AS relation, sys.name AS resource, r.count AS count, r.blocked AS blocked
            """, {"name": agent_name})
            rows = await result.data()
            return rows

    async def record_hotpatch(self, agent_name: str, delta: str, operator: str):
        if not self._driver:
            return
        import time
        async with self._driver.session() as session:
            await session.run("""
                MATCH (a:Agent {name: $name})
                CREATE (p:HotPatch {delta: $delta, operator: $operator, timestamp: $ts})
                CREATE (a)-[:RECEIVED_PATCH]->(p)
            """, {"name": agent_name, "delta": delta[:1000], "operator": operator, "ts": time.time()})

    async def record_replay(self, trace_id: str, replay_id: str, modifications: Dict):
        if not self._driver:
            return
        import time, json
        async with self._driver.session() as session:
            await session.run("""
                MATCH (t:Trace {trace_id: $trace_id})
                CREATE (r:Replay {replay_id: $replay_id, modifications: $mods, timestamp: $ts})
                CREATE (t)-[:HAS_REPLAY]->(r)
            """, {
                "trace_id": trace_id,
                "replay_id": replay_id,
                "mods": json.dumps(modifications),
                "ts": time.time(),
            })
