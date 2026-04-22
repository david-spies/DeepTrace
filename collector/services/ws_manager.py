"""
WebSocket Manager — manages connected dashboard clients and rooms.
"""
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("deeptrace.ws")


class WebSocketManager:
    def __init__(self):
        self._global: List[WebSocket] = []
        self._rooms: Dict[str, List[WebSocket]] = defaultdict(list)

    async def connect(self, ws: WebSocket, room: Optional[str] = None):
        await ws.accept()
        if room:
            self._rooms[room].append(ws)
        else:
            self._global.append(ws)
        logger.debug("WebSocket connected (room=%s). Total global: %d", room, len(self._global))

    def disconnect(self, ws: WebSocket):
        if ws in self._global:
            self._global.remove(ws)
        for room_clients in self._rooms.values():
            if ws in room_clients:
                room_clients.remove(ws)

    async def broadcast(self, message: str, room: Optional[str] = None):
        targets = self._rooms.get(room, []) if room else self._global
        dead = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to_room(self, room: str, message: str):
        await self.broadcast(message, room=room)

    @property
    def connection_count(self) -> int:
        return len(self._global) + sum(len(v) for v in self._rooms.values())
