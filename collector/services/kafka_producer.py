"""
Kafka Producer Service — high-throughput span stream to Kafka topic.
"""
import json
import logging
from typing import Any, Dict

logger = logging.getLogger("deeptrace.kafka")


class KafkaProducerService:
    def __init__(self, brokers: str, topic: str):
        self._brokers = brokers
        self._topic = topic
        self._producer = None
        self._connected = False

    async def start(self):
        try:
            from aiokafka import AIOKafkaProducer
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._brokers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                compression_type="gzip",
                max_batch_size=131072,   # 128KB
                linger_ms=5,             # small batching window
            )
            await self._producer.start()
            self._connected = True
            logger.info("Kafka producer connected to %s", self._brokers)
        except ImportError:
            logger.warning("aiokafka not installed — Kafka streaming disabled")
        except Exception as exc:
            logger.error("Kafka producer failed: %s", exc)

    async def stop(self):
        if self._producer:
            await self._producer.stop()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def send(self, span: Dict[str, Any]):
        if not self._producer or not self._connected:
            return
        try:
            # Partition by agent name for ordered per-agent streams
            key = span.get("agent_name", "unknown").encode("utf-8")
            await self._producer.send(self._topic, value=span, key=key)
        except Exception as exc:
            logger.debug("Kafka send error: %s", exc)
