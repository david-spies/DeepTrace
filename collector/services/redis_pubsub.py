"""
Redis Pub/Sub Service — live event bus for dashboard WebSocket feed.
"""
import asyncio
import logging
from typing import AsyncGenerator, Optional

logger = logging.getLogger("deeptrace.redis")


class RedisPubSubService:
    def __init__(self, url: str):
        self._url = url
        self._redis = None
        self._pubsub = None

    async def connect(self):
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis connected at %s", self._url)
        except ImportError:
            logger.warning("redis package not installed — live feed disabled")
        except Exception as exc:
            logger.error("Redis connection failed: %s", exc)

    async def disconnect(self):
        if self._pubsub:
            await self._pubsub.unsubscribe()
        if self._redis:
            await self._redis.aclose()

    async def ping(self) -> bool:
        if not self._redis:
            return False
        try:
            return await self._redis.ping()
        except Exception:
            return False

    async def publish(self, channel: str, message: str):
        if not self._redis:
            return
        try:
            await self._redis.publish(channel, message)
        except Exception as exc:
            logger.debug("Redis publish error: %s", exc)

    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        if not self._redis:
            return
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    yield msg["data"]
        finally:
            await pubsub.unsubscribe(channel)
