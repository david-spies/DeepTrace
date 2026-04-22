"""
ClickHouse Service — high-speed columnar storage for span telemetry.
Optimized for forensic log queries and token analytics.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("deeptrace.clickhouse")

CREATE_DB = "CREATE DATABASE IF NOT EXISTS deeptrace"

CREATE_SPANS = """
CREATE TABLE IF NOT EXISTS deeptrace.spans (
    trace_id          String,
    span_id           String,
    parent_span_id    Nullable(String),
    agent_name        LowCardinality(String),
    roles             Array(String),
    kind              LowCardinality(String),
    status            LowCardinality(String),
    timestamp         Float64,
    duration_ms       Float64,
    model             LowCardinality(String),
    token_input       UInt32,
    token_output      UInt32,
    token_total       UInt32,
    token_velocity    Float32,
    latency_tier      LowCardinality(String),
    context_fragment  Float32,
    tool_invocations  String,   -- JSON
    system_resources  Array(String),
    anomalies         Array(String),
    has_anomaly       UInt8,
    error             Nullable(String),
    metadata          String,   -- JSON
    service_name      LowCardinality(String),
    environment       LowCardinality(String),
    cost_usd          Float32,
    date              Date DEFAULT toDate(fromUnixTimestamp(toUInt32(timestamp)))
)
ENGINE = MergeTree()
PARTITION BY (environment, date)
ORDER BY (agent_name, timestamp)
TTL date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
"""

CREATE_ANOMALIES = """
CREATE TABLE IF NOT EXISTS deeptrace.anomalies (
    id              String,
    trace_id        String,
    span_id         String,
    agent_name      LowCardinality(String),
    anomaly_type    LowCardinality(String),
    severity        LowCardinality(String),
    timestamp       Float64,
    resolved        UInt8 DEFAULT 0,
    resolved_by     Nullable(String),
    is_false_pos    UInt8 DEFAULT 0,
    notes           Nullable(String),
    metadata        String,
    date            Date DEFAULT toDate(fromUnixTimestamp(toUInt32(timestamp)))
)
ENGINE = MergeTree()
PARTITION BY date
ORDER BY (agent_name, timestamp)
"""


class ClickHouseService:
    def __init__(self, host: str, port: int, database: str = "deeptrace"):
        self._host = host
        self._port = port
        self._db = database
        self._client = None

    async def connect(self):
        try:
            import clickhouse_connect
            self._client = await clickhouse_connect.get_async_client(
                host=self._host,
                port=self._port,
                username="default",
                password="",
            )
            await self._client.command(CREATE_DB)
            await self._client.command(CREATE_SPANS)
            await self._client.command(CREATE_ANOMALIES)
            logger.info("ClickHouse connected at %s:%s", self._host, self._port)
        except ImportError:
            logger.warning("clickhouse-connect not installed — analytics features disabled")
        except Exception as exc:
            logger.error("ClickHouse connection failed: %s", exc)

    async def disconnect(self):
        if self._client:
            self._client.close()

    async def ping(self) -> bool:
        if not self._client:
            return False
        try:
            result = await self._client.command("SELECT 1")
            return result == 1
        except Exception:
            return False

    def _estimate_cost(self, span: Dict) -> float:
        """Rough cost estimate based on model and token count."""
        PRICES = {  # per 1M tokens (input/output avg)
            "claude-3-opus":   15.00,
            "claude-3-sonnet":  3.00,
            "claude-3-haiku":   0.25,
            "gpt-4o":          5.00,
            "gpt-4-turbo":    10.00,
            "gpt-3.5-turbo":   0.50,
        }
        model = span.get("model", "").lower()
        price = next((v for k, v in PRICES.items() if k in model), 1.0)
        total_tokens = span.get("token_total", 0)
        return round((total_tokens / 1_000_000) * price, 6)

    async def insert_span(self, span: Dict[str, Any]):
        if not self._client:
            return
        cost = self._estimate_cost(span)
        row = {
            "trace_id":         span.get("trace_id", ""),
            "span_id":          span.get("span_id", ""),
            "parent_span_id":   span.get("parent_span_id"),
            "agent_name":       span.get("agent_name", ""),
            "roles":            span.get("roles", []),
            "kind":             span.get("kind", "AGENT"),
            "status":           span.get("status", "COMPLETED"),
            "timestamp":        span.get("timestamp", time.time()),
            "duration_ms":      span.get("duration_ms", 0),
            "model":            span.get("model", ""),
            "token_input":      span.get("token_input", 0),
            "token_output":     span.get("token_output", 0),
            "token_total":      span.get("token_total", 0),
            "token_velocity":   span.get("token_velocity", 0.0),
            "latency_tier":     span.get("latency_tier", "normal"),
            "context_fragment": span.get("context_fragment_pct", 0.0),
            "tool_invocations": json.dumps(span.get("tool_invocations", [])),
            "system_resources": span.get("system_resources", []),
            "anomalies":        span.get("anomalies", []),
            "has_anomaly":      int(span.get("has_anomaly", False)),
            "error":            span.get("error"),
            "metadata":         json.dumps(span.get("metadata", {})),
            "service_name":     span.get("service_name", ""),
            "environment":      span.get("environment", "production"),
            "cost_usd":         cost,
        }
        try:
            await self._client.insert("deeptrace.spans", [row], column_names=list(row.keys()))
        except Exception as exc:
            logger.error("ClickHouse insert error: %s", exc)

        # Insert anomaly records
        for anomaly_type in span.get("anomalies", []):
            import uuid
            a_row = {
                "id":           str(uuid.uuid4()),
                "trace_id":     span.get("trace_id", ""),
                "span_id":      span.get("span_id", ""),
                "agent_name":   span.get("agent_name", ""),
                "anomaly_type": anomaly_type,
                "severity":     "HIGH" if "ZERO_TRUST" in anomaly_type else "MEDIUM",
                "timestamp":    span.get("timestamp", time.time()),
                "metadata":     json.dumps(span.get("metadata", {})),
            }
            try:
                await self._client.insert("deeptrace.anomalies", [a_row],
                                          column_names=list(a_row.keys()))
            except Exception as exc:
                logger.error("ClickHouse anomaly insert error: %s", exc)

    async def get_trace(self, trace_id: str) -> List[Dict]:
        if not self._client:
            return []
        result = await self._client.query(
            "SELECT * FROM deeptrace.spans WHERE trace_id = {trace_id:String} ORDER BY timestamp",
            parameters={"trace_id": trace_id},
        )
        return result.named_results()

    async def get_span(self, span_id: str) -> Optional[Dict]:
        if not self._client:
            return None
        result = await self._client.query(
            "SELECT * FROM deeptrace.spans WHERE span_id = {span_id:String} LIMIT 1",
            parameters={"span_id": span_id},
        )
        rows = result.named_results()
        return rows[0] if rows else None

    async def get_agent_spans(self, agent_name: str, limit: int = 50,
                               status: Optional[str] = None) -> List[Dict]:
        if not self._client:
            return []
        where = "agent_name = {agent:String}"
        params: Dict = {"agent": agent_name, "limit": limit}
        if status:
            where += " AND status = {status:String}"
            params["status"] = status
        result = await self._client.query(
            f"SELECT * FROM deeptrace.spans WHERE {where} ORDER BY timestamp DESC LIMIT {{limit:UInt32}}",
            parameters=params,
        )
        return result.named_results()

    async def get_token_history(self, agent_name: str, window: str = "1h") -> List[Dict]:
        if not self._client:
            return []
        window_map = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}
        seconds = window_map.get(window, 3600)
        cutoff = time.time() - seconds
        result = await self._client.query("""
            SELECT
                toStartOfMinute(fromUnixTimestamp(toUInt32(timestamp))) AS minute,
                sum(token_total) AS tokens,
                avg(duration_ms) AS avg_latency,
                count() AS spans
            FROM deeptrace.spans
            WHERE agent_name = {agent:String} AND timestamp >= {cutoff:Float64}
            GROUP BY minute ORDER BY minute
        """, parameters={"agent": agent_name, "cutoff": cutoff})
        return result.named_results()

    async def get_anomalies(self, resolved: bool = False, limit: int = 100,
                             agent: Optional[str] = None) -> List[Dict]:
        if not self._client:
            return []
        where = f"resolved = {int(resolved)}"
        params: Dict = {"limit": limit}
        if agent:
            where += " AND agent_name = {agent:String}"
            params["agent"] = agent
        result = await self._client.query(
            f"SELECT * FROM deeptrace.anomalies WHERE {where} ORDER BY timestamp DESC LIMIT {{limit:UInt32}}",
            parameters=params,
        )
        return result.named_results()

    async def resolve_anomaly(self, anomaly_id: str, operator: str,
                               is_fp: bool, notes: str):
        if not self._client:
            return
        await self._client.command("""
            ALTER TABLE deeptrace.anomalies UPDATE
                resolved     = 1,
                resolved_by  = {op:String},
                is_false_pos = {fp:UInt8},
                notes        = {notes:String}
            WHERE id = {id:String}
        """, parameters={"id": anomaly_id, "op": operator, "fp": int(is_fp), "notes": notes})

    async def get_violations(self, hours: int = 24, agent: Optional[str] = None) -> List[Dict]:
        if not self._client:
            return []
        cutoff = time.time() - hours * 3600
        where = "has_anomaly = 1 AND timestamp >= {cutoff:Float64}"
        params: Dict = {"cutoff": cutoff}
        if agent:
            where += " AND agent_name = {agent:String}"
            params["agent"] = agent
        result = await self._client.query(
            f"SELECT * FROM deeptrace.spans WHERE {where} ORDER BY timestamp DESC LIMIT 500",
            parameters=params,
        )
        return result.named_results()

    async def get_recent_spans(self, hours: int = 6) -> List[Dict]:
        if not self._client:
            return []
        cutoff = time.time() - hours * 3600
        result = await self._client.query(
            "SELECT * FROM deeptrace.spans WHERE timestamp >= {cutoff:Float64} ORDER BY timestamp DESC LIMIT 5000",
            parameters={"cutoff": cutoff},
        )
        return result.named_results()

    async def get_summary(self, environment: Optional[str] = None) -> Dict:
        if not self._client:
            return {}
        where = f"environment = '{environment}'" if environment else "1=1"
        cutoff_day = time.time() - 86400
        result = await self._client.query(f"""
            SELECT
                count()                          AS total_spans,
                countIf(has_anomaly = 1)         AS anomaly_count,
                sum(token_total)                 AS total_tokens,
                sum(cost_usd)                    AS total_cost,
                avg(duration_ms)                 AS avg_latency,
                quantile(0.99)(duration_ms)      AS p99_latency,
                uniq(agent_name)                 AS unique_agents,
                uniq(trace_id)                   AS unique_traces
            FROM deeptrace.spans
            WHERE {where} AND timestamp >= {cutoff_day}
        """)
        rows = result.named_results()
        return rows[0] if rows else {}

    async def get_token_debt_ranking(self, limit: int = 20) -> List[Dict]:
        if not self._client:
            return []
        result = await self._client.query("""
            SELECT
                agent_name,
                sum(token_total)        AS total_tokens,
                avg(token_total)        AS avg_tokens_per_span,
                avg(token_velocity)     AS avg_velocity,
                sum(cost_usd)           AS total_cost,
                count()                 AS spans
            FROM deeptrace.spans
            WHERE timestamp >= {cutoff:Float64}
            GROUP BY agent_name
            ORDER BY total_tokens DESC
            LIMIT {limit:UInt32}
        """, parameters={"cutoff": time.time() - 86400, "limit": limit})
        return result.named_results()

    async def get_latency_percentiles(self, window: str = "1h") -> List[Dict]:
        if not self._client:
            return []
        window_map = {"1h": 3600, "6h": 21600, "24h": 86400}
        seconds = window_map.get(window, 3600)
        cutoff = time.time() - seconds
        result = await self._client.query("""
            SELECT
                agent_name,
                quantile(0.50)(duration_ms) AS p50,
                quantile(0.90)(duration_ms) AS p90,
                quantile(0.99)(duration_ms) AS p99,
                avg(duration_ms)            AS avg,
                max(duration_ms)            AS max
            FROM deeptrace.spans
            WHERE timestamp >= {cutoff:Float64}
            GROUP BY agent_name
            ORDER BY p99 DESC
        """, parameters={"cutoff": cutoff})
        return result.named_results()

    async def get_cost_breakdown(self, window: str = "24h") -> List[Dict]:
        if not self._client:
            return []
        window_map = {"1h": 3600, "24h": 86400, "7d": 604800}
        seconds = window_map.get(window, 86400)
        cutoff = time.time() - seconds
        result = await self._client.query("""
            SELECT agent_name, model, sum(cost_usd) AS cost, sum(token_total) AS tokens
            FROM deeptrace.spans
            WHERE timestamp >= {cutoff:Float64}
            GROUP BY agent_name, model
            ORDER BY cost DESC
        """, parameters={"cutoff": cutoff})
        return result.named_results()

    async def get_audit_trail(self, start_ts: float, end_ts: float,
                               agent: Optional[str] = None) -> List[Dict]:
        if not self._client:
            return []
        where = "timestamp >= {start:Float64} AND timestamp <= {end:Float64}"
        params: Dict = {"start": start_ts, "end": end_ts}
        if agent:
            where += " AND agent_name = {agent:String}"
            params["agent"] = agent
        result = await self._client.query(
            f"SELECT trace_id, span_id, agent_name, tool_invocations, timestamp, has_anomaly "
            f"FROM deeptrace.spans WHERE {where} ORDER BY timestamp",
            parameters=params,
        )
        return result.named_results()
