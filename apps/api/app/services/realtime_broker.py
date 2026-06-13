"""Trip WebSocket channel broker.

Sprint 5/T-128 scope is a single-process in-memory broker. Multi-worker delivery
is a future Redis Streams or LISTEN/NOTIFY decision.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, cast

from fastapi.encoders import jsonable_encoder

from app.core.config import settings
from app.core.time import kst_now

logger = logging.getLogger(__name__)


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
    # 동시 broadcast task가 같은 소켓에 send_json을 겹쳐 호출하면 프레임이 인터리브된다.
    # 연결별 lock으로 송신을 직렬화한다(프레임 무결성 보장).
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class RealtimeConnectionLimitError(RuntimeError):
    """Raised when process-local WebSocket connection caps are exhausted."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class RealtimeBroker:
    """In-memory trip-channel broker for one FastAPI process."""

    def __init__(
        self,
        *,
        max_connections_per_trip: int | None = None,
        max_connections_total: int | None = None,
        send_timeout_seconds: float | None = None,
    ) -> None:
        self._connections: dict[uuid.UUID, set[RealtimeConnection]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._max_connections_per_trip_override = max_connections_per_trip
        self._max_connections_total_override = max_connections_total
        self._send_timeout_seconds_override = send_timeout_seconds
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def connect(
        self,
        websocket: JsonWebSocket,
        *,
        trip_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> RealtimeConnection:
        connection = RealtimeConnection(websocket=websocket, trip_id=trip_id, user_id=user_id)
        async with self._lock:
            trip_connections = self._connections.get(trip_id, set())
            per_trip_limit = self._max_connections_per_trip()
            if per_trip_limit > 0 and len(trip_connections) >= per_trip_limit:
                raise RealtimeConnectionLimitError("trip_connection_limit_exceeded")

            total_limit = self._max_connections_total()
            if total_limit > 0 and self._connection_count_unlocked() >= total_limit:
                raise RealtimeConnectionLimitError("process_connection_limit_exceeded")

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

    def publish_event_nowait(
        self,
        *,
        trip_id: uuid.UUID,
        event_type: str,
        actor_user_id: uuid.UUID | None,
        payload: Mapping[str, Any],
        version: int | None = None,
    ) -> asyncio.Task[None]:
        message = self._event_message(
            trip_id=trip_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            payload=payload,
            version=version,
        )
        task = asyncio.create_task(
            self._broadcast(trip_id, message),
            name=f"pinvi-realtime-broadcast:{event_type}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._finalize_background_task)
        return task

    async def send_error(
        self,
        connection: RealtimeConnection,
        *,
        code: str,
        message: str,
    ) -> None:
        try:
            async with connection.send_lock:
                await asyncio.wait_for(
                    connection.websocket.send_json(
                        {
                            "type": "error",
                            "trip_id": str(connection.trip_id),
                            "actor_user_id": None,
                            "ts": kst_now().isoformat(),
                            "version": None,
                            "payload": {"code": code, "message": message},
                        }
                    ),
                    timeout=self._send_timeout_seconds(),
                )
        except Exception:
            await self._remove(connection)

    async def connection_count(self, trip_id: uuid.UUID) -> int:
        async with self._lock:
            return len(self._connections.get(trip_id, set()))

    async def total_connection_count(self) -> int:
        async with self._lock:
            return self._connection_count_unlocked()

    async def reset(self) -> None:
        background_tasks = list(self._background_tasks)
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        self._background_tasks.clear()
        async with self._lock:
            self._connections.clear()

    async def _broadcast(self, trip_id: uuid.UUID, message: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections.get(trip_id, set()))

        stale: list[RealtimeConnection] = []
        results = await asyncio.gather(
            *(self._send_or_stale(connection, message) for connection in connections)
        )
        stale.extend(connection for connection in results if connection is not None)

        for connection in stale:
            await self._remove(connection)

    async def _send_or_stale(
        self,
        connection: RealtimeConnection,
        message: dict[str, Any],
    ) -> RealtimeConnection | None:
        try:
            async with connection.send_lock:
                await asyncio.wait_for(
                    connection.websocket.send_json(message),
                    timeout=self._send_timeout_seconds(),
                )
            return None
        except Exception:
            return connection

    async def _remove(self, connection: RealtimeConnection) -> bool:
        async with self._lock:
            connections = self._connections.get(connection.trip_id)
            if connections is None or connection not in connections:
                return False
            connections.remove(connection)
            if not connections:
                self._connections.pop(connection.trip_id, None)
            return True

    def _connection_count_unlocked(self) -> int:
        return sum(len(connections) for connections in self._connections.values())

    def _finalize_background_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Realtime background broadcast failed.")

    def _max_connections_per_trip(self) -> int:
        if self._max_connections_per_trip_override is not None:
            return self._max_connections_per_trip_override
        return settings.pinvi_ws_max_connections_per_trip

    def _max_connections_total(self) -> int:
        if self._max_connections_total_override is not None:
            return self._max_connections_total_override
        return settings.pinvi_ws_max_connections_total

    def _send_timeout_seconds(self) -> float:
        if self._send_timeout_seconds_override is not None:
            return self._send_timeout_seconds_override
        return settings.pinvi_ws_send_timeout_seconds

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
