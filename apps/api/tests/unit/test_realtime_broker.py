"""Realtime broker unit tests."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from app.services.realtime_broker import RealtimeBroker, RealtimeConnectionLimitError

pytestmark = pytest.mark.asyncio


class FakeSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.delay_seconds = 0.0

    async def send_json(self, data: Any) -> None:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if not isinstance(data, dict):
            raise TypeError("broker messages must be JSON objects")
        self.messages.append(data)


async def test_broker_broadcasts_event_to_trip_connections() -> None:
    broker = RealtimeBroker()
    trip_id = uuid.uuid4()
    user_id = uuid.uuid4()
    socket_a = FakeSocket()
    socket_b = FakeSocket()

    await broker.connect(socket_a, trip_id=trip_id, user_id=user_id)
    await broker.connect(socket_b, trip_id=trip_id, user_id=uuid.uuid4())
    await broker.publish_event(
        trip_id=trip_id,
        event_type="trip.updated",
        actor_user_id=user_id,
        payload={"changes": {"title": "새 제목"}, "version": 2},
        version=2,
    )

    event_a = socket_a.messages[-1]
    event_b = socket_b.messages[-1]
    assert event_a == event_b
    assert event_a["type"] == "trip.updated"
    assert event_a["trip_id"] == str(trip_id)
    assert event_a["actor_user_id"] == str(user_id)
    assert event_a["version"] == 2
    assert event_a["payload"]["changes"]["title"] == "새 제목"


async def test_broker_updates_presence_and_removes_connection() -> None:
    broker = RealtimeBroker()
    trip_id = uuid.uuid4()
    user_id = uuid.uuid4()
    socket = FakeSocket()

    connection = await broker.connect(socket, trip_id=trip_id, user_id=user_id)
    await broker.mark_seen(connection, viewing_day=3)
    await broker.publish_presence(connection, is_online=True)

    assert await broker.connection_count(trip_id) == 1
    assert socket.messages[-1]["type"] == "presence.update"
    assert socket.messages[-1]["payload"] == {
        "user_id": str(user_id),
        "viewing_day": 3,
        "is_online": True,
    }

    await broker.disconnect(connection)
    assert await broker.connection_count(trip_id) == 0


async def test_broker_rejects_trip_connection_cap() -> None:
    broker = RealtimeBroker(max_connections_per_trip=1, max_connections_total=0)
    trip_id = uuid.uuid4()

    await broker.connect(FakeSocket(), trip_id=trip_id, user_id=uuid.uuid4())

    with pytest.raises(RealtimeConnectionLimitError) as exc_info:
        await broker.connect(FakeSocket(), trip_id=trip_id, user_id=uuid.uuid4())

    assert exc_info.value.reason == "trip_connection_limit_exceeded"
    assert await broker.connection_count(trip_id) == 1


async def test_broker_rejects_process_connection_cap() -> None:
    broker = RealtimeBroker(max_connections_per_trip=10, max_connections_total=1)

    await broker.connect(FakeSocket(), trip_id=uuid.uuid4(), user_id=uuid.uuid4())

    with pytest.raises(RealtimeConnectionLimitError) as exc_info:
        await broker.connect(FakeSocket(), trip_id=uuid.uuid4(), user_id=uuid.uuid4())

    assert exc_info.value.reason == "process_connection_limit_exceeded"
    assert await broker.total_connection_count() == 1


async def test_broker_drops_slow_connection_without_blocking_broadcast() -> None:
    broker = RealtimeBroker(send_timeout_seconds=0.001)
    trip_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    fast_socket = FakeSocket()
    slow_socket = FakeSocket()

    await broker.connect(fast_socket, trip_id=trip_id, user_id=actor_id)
    await broker.connect(slow_socket, trip_id=trip_id, user_id=uuid.uuid4())
    slow_socket.delay_seconds = 0.05

    await broker.publish_event(
        trip_id=trip_id,
        event_type="trip.updated",
        actor_user_id=actor_id,
        payload={"changes": {"title": "새 제목"}},
        version=3,
    )

    assert fast_socket.messages[-1]["type"] == "trip.updated"
    assert await broker.connection_count(trip_id) == 1
