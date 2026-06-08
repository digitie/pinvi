"""Trip WebSocket channel integration tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.models.user import User
from app.services.realtime_broker import realtime_broker

pytestmark = pytest.mark.asyncio


async def test_ws_trip_channel_presence_and_poi_broadcast(
    session_factory,
    verified_user,
    auth_cookies,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["tripmate_access"]

    with TestClient(app) as sync_client:
        created = sync_client.post("/trips", json={"title": "실시간 여행"}, cookies=cookies)
        assert created.status_code == 201, created.text
        trip_id = created.json()["data"]["trip_id"]

        with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={token}") as websocket:
            online = websocket.receive_json()
            assert online["type"] == "presence.update"
            assert online["trip_id"] == trip_id
            assert online["payload"] == {
                "user_id": user_id,
                "viewing_day": None,
                "is_online": True,
            }

            websocket.send_json({"type": "presence.heartbeat", "payload": {"viewing_day": 2}})
            heartbeat = websocket.receive_json()
            assert heartbeat["type"] == "presence.update"
            assert heartbeat["payload"]["viewing_day"] == 2

            websocket.send_json(
                {
                    "type": "presence.cursor",
                    "payload": {"latitude": 37.566681, "longitude": 126.978414},
                }
            )
            cursor = websocket.receive_json()
            assert cursor["type"] == "presence.cursor"
            assert cursor["payload"] == {
                "user_id": user_id,
                "longitude": 126.978414,
                "latitude": 37.566681,
            }

            poi = sync_client.post(
                f"/trips/{trip_id}/pois",
                json={
                    "day_index": 1,
                    "sort_order": "a0",
                    "feature_id": "manual-place-1",
                    "feature_snapshot": {"name": "수동 장소"},
                },
                cookies=cookies,
            )
            assert poi.status_code == 201, poi.text

            event = websocket.receive_json()
            assert event["type"] == "poi.created"
            assert event["trip_id"] == trip_id
            assert event["actor_user_id"] == user_id
            assert event["version"] == 1
            assert event["payload"]["poi"]["feature_id"] == "manual-place-1"


async def test_ws_trip_channel_rejects_non_member(
    session_factory,
    verified_user,
    auth_cookies,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    owner_id, _ = verified_user
    owner_cookies = auth_cookies(owner_id)

    with TestClient(app) as sync_client:
        created = sync_client.post("/trips", json={"title": "비공개 여행"}, cookies=owner_cookies)
        assert created.status_code == 201, created.text
        trip_id = created.json()["data"]["trip_id"]

        async with session_factory() as db:
            other = User(
                email=f"ws_other_{uuid.uuid4().hex[:8]}@tripmate.test",
                status="active",
                email_verified_at=datetime.now(UTC),
            )
            db.add(other)
            await db.commit()
            await db.refresh(other)
            other_token = auth_cookies(str(other.user_id))["tripmate_access"]

        with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={other_token}") as websocket:
            rejected = websocket.receive_json()
            assert rejected == {"code": 4403, "reason": "permission_denied"}
            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_json()
            assert exc_info.value.code == 4403


async def test_ws_trip_channel_rate_limits_client_messages(
    session_factory,
    verified_user,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    monkeypatch.setattr(settings, "tripmate_ws_client_rate_per_second", 2)
    monkeypatch.setattr(settings, "tripmate_ws_client_rate_per_minute", 60)
    monkeypatch.setattr(settings, "tripmate_ws_rate_limit_close_grace_seconds", 0.0)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["tripmate_access"]

    with TestClient(app) as sync_client:
        created = sync_client.post("/trips", json={"title": "rate limited"}, cookies=cookies)
        assert created.status_code == 201, created.text
        trip_id = created.json()["data"]["trip_id"]

        with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={token}") as websocket:
            assert websocket.receive_json()["type"] == "presence.update"

            websocket.send_json({"type": "pong", "payload": {}})
            websocket.send_json({"type": "pong", "payload": {}})
            websocket.send_json({"type": "pong", "payload": {}})

            limited = websocket.receive_json()
            assert limited["type"] == "error"
            assert limited["payload"]["code"] == "RATE_LIMITED"

            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_json()
            assert exc_info.value.code == 4429


async def test_ws_trip_channel_releases_cap_before_rate_limit_grace_close(
    session_factory,
    verified_user,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    monkeypatch.setattr(settings, "tripmate_ws_client_rate_per_second", 2)
    monkeypatch.setattr(settings, "tripmate_ws_client_rate_per_minute", 60)
    monkeypatch.setattr(settings, "tripmate_ws_rate_limit_close_grace_seconds", 0.5)
    monkeypatch.setattr(settings, "tripmate_ws_max_connections_per_trip", 1)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["tripmate_access"]

    with TestClient(app) as sync_client:
        created = sync_client.post("/trips", json={"title": "rate grace cap"}, cookies=cookies)
        assert created.status_code == 201, created.text
        trip_id = created.json()["data"]["trip_id"]
        trip_uuid = uuid.UUID(trip_id)

        with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={token}") as first:
            assert first.receive_json()["type"] == "presence.update"

            first.send_json({"type": "pong", "payload": {}})
            first.send_json({"type": "pong", "payload": {}})
            first.send_json({"type": "pong", "payload": {}})

            limited = first.receive_json()
            assert limited["type"] == "error"
            assert limited["payload"]["code"] == "RATE_LIMITED"

            for _ in range(50):
                if await realtime_broker.connection_count(trip_uuid) == 0:
                    break
                await asyncio.sleep(0.01)
            assert await realtime_broker.connection_count(trip_uuid) == 0

            with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={token}") as second:
                assert second.receive_json()["type"] == "presence.update"

            with pytest.raises(WebSocketDisconnect) as exc_info:
                first.receive_json()
            assert exc_info.value.code == 4429


async def test_ws_trip_channel_rejects_connection_cap(
    session_factory,
    verified_user,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    monkeypatch.setattr(settings, "tripmate_ws_max_connections_per_trip", 1)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["tripmate_access"]

    with TestClient(app) as sync_client:
        created = sync_client.post("/trips", json={"title": "connection cap"}, cookies=cookies)
        assert created.status_code == 201, created.text
        trip_id = created.json()["data"]["trip_id"]

        with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={token}") as first:
            assert first.receive_json()["type"] == "presence.update"
            with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={token}") as second:
                rejected = second.receive_json()
                assert rejected == {
                    "code": 4408,
                    "reason": "trip_connection_limit_exceeded",
                }
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    second.receive_json()
                assert exc_info.value.code == 4408


async def test_ws_trip_channel_rejects_invalid_cursor(
    session_factory,
    verified_user,
    auth_cookies,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["tripmate_access"]

    with TestClient(app) as sync_client:
        created = sync_client.post("/trips", json={"title": "invalid cursor"}, cookies=cookies)
        assert created.status_code == 201, created.text
        trip_id = created.json()["data"]["trip_id"]

        with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={token}") as websocket:
            assert websocket.receive_json()["type"] == "presence.update"
            websocket.send_json(
                {
                    "type": "presence.cursor",
                    "payload": {"latitude": 37.5, "longitude": 999.0},
                }
            )
            error = websocket.receive_json()
            assert error["type"] == "error"
            assert error["payload"]["code"] == "BAD_CURSOR"
