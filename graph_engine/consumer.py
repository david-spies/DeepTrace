"""
DeepTrace Graph Engine — Kafka Consumer
Processes the deeptrace-spans topic and maintains the Neo4j topology graph
independently from the FastAPI collector (enables horizontal scaling).

Run alongside the collector:
    python -m graph_engine.consumer
"""

import asyncio
import json
import logging
import os
import signal
import sys

logger = logging.getLogger("deeptrace.graph_engine")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")
KAFKA_TOPIC   = os.getenv("KAFKA_TOPIC", "deeptrace-spans")
KAFKA_GROUP   = os.getenv("KAFKA_GROUP", "deeptrace-graph-engine")
NEO4J_URI     = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER    = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS    = os.getenv("NEO4J_PASSWORD", "deeptrace")


class GraphEngineConsumer:
    def __init__(self):
        self._consumer = None
        self._driver   = None
        self._running  = False

    async def start(self):
        try:
            from aiokafka import AIOKafkaConsumer
            self._consumer = AIOKafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BROKERS,
                group_id=KAFKA_GROUP,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
                max_poll_records=100,
            )
            await self._consumer.start()
            logger.info("Kafka consumer connected — topic: %s", KAFKA_TOPIC)
        except ImportError:
            logger.error("aiokafka not installed")
            raise

        try:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS)
            )
            await self._driver.verify_connectivity()
            logger.info("Neo4j connected at %s", NEO4J_URI)
        except ImportError:
            logger.error("neo4j not installed")
            raise

        self._running = True

    async def stop(self):
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._driver:
            await self._driver.close()
        logger.info("Graph engine stopped")

    async def run(self):
        """Main consume loop."""
        batch = []
        last_flush = asyncio.get_event_loop().time()

        async for msg in self._consumer:
            if not self._running:
                break
            batch.append(msg.value)

            now = asyncio.get_event_loop().time()
            if len(batch) >= 50 or (now - last_flush) > 2.0:
                await self._process_batch(batch)
                batch = []
                last_flush = now

    async def _process_batch(self, spans: list):
        """Write a batch of spans to Neo4j using a single session."""
        if not spans:
            return
        async with self._driver.session() as session:
            async with session.begin_transaction() as tx:
                for span in spans:
                    await self._write_span(tx, span)
                await tx.commit()
        logger.debug("Wrote %d spans to Neo4j", len(spans))

    async def _write_span(self, tx, span: dict):
        """Write a single span into the graph."""
        # Upsert agent node
        await tx.run("""
            MERGE (a:Agent {name: $agent_name})
            SET a.status      = $status,
                a.model       = $model,
                a.last_seen   = $ts,
                a.token_total = COALESCE(a.token_total, 0) + $tokens,
                a.call_count  = COALESCE(a.call_count, 0) + 1,
                a.has_anomaly = ($has_anomaly OR COALESCE(a.has_anomaly, false))
        """, {
            "agent_name": span.get("agent_name", "unknown"),
            "status":     span.get("status", "COMPLETED"),
            "model":      span.get("model", ""),
            "ts":         span.get("timestamp", 0),
            "tokens":     span.get("token_total", 0),
            "has_anomaly": span.get("has_anomaly", False),
        })

        # Parent-child agent relationship (via parent span)
        if span.get("parent_span_id"):
            await tx.run("""
                MATCH (child:Agent {name: $child})
                MERGE (edge:SpawnEdge {parent_span: $parent, child_span: $child_span})
                SET edge.timestamp = $ts, edge.trace_id = $trace
                WITH edge
                MATCH (parent:Agent)-[:EXECUTED]->(ps:Span {span_id: $parent})
                MERGE (parent)-[:SPAWNED_AGENT]->(child)
            """, {
                "child":       span.get("agent_name"),
                "parent":      span.get("parent_span_id"),
                "child_span":  span.get("span_id"),
                "ts":          span.get("timestamp", 0),
                "trace":       span.get("trace_id"),
            })

        # Tool invocation edges
        for tool in span.get("tool_invocations", []):
            rel = "BLOCKED_ACCESS" if tool.get("blocked") else "INVOKED_TOOL"
            await tx.run(f"""
                MATCH (a:Agent {{name: $agent}})
                MERGE (t:Tool {{name: $tool_name}})
                MERGE (a)-[r:{rel}]->(t)
                SET r.count       = COALESCE(r.count, 0) + 1,
                    r.last_called = $ts,
                    r.merkle_hash = $hash
            """, {
                "agent":     span.get("agent_name"),
                "tool_name": tool.get("tool_name", "unknown"),
                "ts":        span.get("timestamp", 0),
                "hash":      tool.get("merkle_hash", ""),
            })


async def main():
    engine = GraphEngineConsumer()
    await engine.start()

    loop = asyncio.get_event_loop()

    def _shutdown(sig):
        logger.info("Shutdown signal received: %s", sig)
        loop.create_task(engine.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig)

    try:
        await engine.run()
    except Exception as exc:
        logger.error("Graph engine error: %s", exc)
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
