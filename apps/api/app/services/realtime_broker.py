"""Trip WebSocket channel broker.

Sprint 5/T-128 scope is a single-process in-memory broker. Multi-worker delivery
is a future Redis Streams or LISTEN/NOTIFY decision.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, cast

from fastapi.encoders import jsonable_encoder

from app.core.time import kst_now


class JsonWebSocket(Protocol):
    async def send_json(self, data: Any) -> None:
        """Send a JSON-serializable payload to a WebSocket peer."""


@dataclass(eq=False)
class RealtimeConnection:
    websocket: JsonWebSocket
    trip_id: uuid.UUID
    user_id: uuid.UUID
    viewing_day: int | None = None
    last_seen_at: datetime = field(default_factory=kst_now)


class RealtimeBroker:
    """In-memory trip-channel broker for one FastAPI process."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[RealtimeConnection]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: JsonWebSocket,
        *,
        trip_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> RealtimeConnection:
        connection = RealtimeConnection(websocket=websocket, trip_id=trip_id, user_id=user_id)
        async with self._lock:
            self._connections[trip_id].add(connection)
        await self.publish_presence(connection, is_online=True)
        return connection

    async def disconnect(self, connection: RealtimeConnection) -> None:
        removed = await self._remove(connection)
        if removed:
            await self.publish_presence(connection, is_online=False)

    async def mark_seen(
        self,
        connection: RealtimeConnection,
        *,
        viewing_day: int | None = None,
    ) -> None:
        connection.last_seen_at = kst_now()
        if viewing_day is not None:
            connection.viewing_day = viewing_day

    async def publish_presence(
        self,
        connection: RealtimeConnection,
        *,
        is_online: bool,
    ) -> None:
        await self.publish_event(
            trip_id=connection.trip_id,
            event_type="presence.update",
            actor_user_id=connection.user_id,
            payload={
                "user_id": str(connection.user_id),
                "viewing_day": connection.viewing_day,
                "is_online": is_online,
            },
        )

    async def publish_event(
        self,
        *,
        trip_id: uuid.UUID,
        event_type: str,
        actor_user_id: uuid.UUID | None,
        payload: Mapping[str, Any],
        version: int | None = None,
    ) -> None:
        message = self._event_message(
            trip_id=trip_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            payload=payload,
            version=version,
        )
        await self._broadcast(trip_id, message)

    async def send_error(
        self,
        connection: RealtimeConnection,
        *,
        code: str,
        message: str,
    ) -> None:
        await connection.websocket.send_json(
            {
                "type": "error",
                "trip_id": str(connection.trip_id),
                "actor_user_id": None,
                "ts": kst_now().isoformat(),
                "version": None,
                "payload": {"code": code, "message": message},
            }
        )

    async def connection_count(self, trip_id: uuid.UUID) -> int:
        async with self._lock:
            return len(self._connections.get(trip_id, set()))

    async def reset(self) -> None:
        async with self._lock:
            self._connections.clear()

    async def _broadcast(self, trip_id: uuid.UUID, message: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections.get(trip_id, set()))

        stale: list[RealtimeConnection] = []
        for connection in connections:
            try:
                await connection.websocket.send_json(message)
            except Exception:
                stale.append(connection)

        for connection in stale:
            await self._remove(connection)

    async def _remove(self, connection: RealtimeConnection) -> bool:
        async with self._lock:
            connections = self._connections.get(connection.trip_id)
            if connections is None or connection not in connections:
                return False
            connections.remove(connection)
            if not connections:
                self._connections.pop(connection.trip_id, None)
            return True

    def _event_message(
        self,
        *,
        trip_id: uuid.UUID,
        event_type: str,
        actor_user_id: uuid.UUID | None,
        payload: Mapping[str, Any],
        version: int | None,
    ) -> dict[str, Any]:
        message = {
            "type": event_type,
            "trip_id": trip_id,
            "actor_user_id": actor_user_id,
            "ts": kst_now().isoformat(),
            "version": version,
            "payload": dict(payload),
        }
        return cast(dict[str, Any], jsonable_encoder(message))


realtime_broker = RealtimeBroker()
