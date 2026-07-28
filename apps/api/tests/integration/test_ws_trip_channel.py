"""Trip WebSocket channel integration tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.models.user import User
from app.services.realtime_broker import realtime_broker

pytestmark = pytest.mark.asyncio


def _metric_sample(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    if value is None:
        return 0.0
    return float(value)


async def test_ws_trip_channel_presence_and_poi_broadcast(
    session_factory,
    verified_user,
    auth_cookies,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["pinvi_access"]

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
                "lon": 126.978414,
                "lat": 37.566681,
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
    rejected_before = _metric_sample(
        "pinvi_api_ws_connections_total",
        {"channel": "trip", "result": "rejected", "reason": "permission_denied"},
    )
    close_before = _metric_sample(
        "pinvi_api_ws_closes_total",
        {"channel": "trip", "code": "4403", "reason": "permission_denied"},
    )

    with TestClient(app) as sync_client:
        created = sync_client.post("/trips", json={"title": "비공개 여행"}, cookies=owner_cookies)
        assert created.status_code == 201, created.text
        trip_id = created.json()["data"]["trip_id"]

        async with session_factory() as db:
            other = User(
                email=f"ws_other_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=datetime.now(UTC),
            )
            db.add(other)
            await db.commit()
            await db.refresh(other)
            other_token = auth_cookies(str(other.user_id))["pinvi_access"]

        with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={other_token}") as websocket:
            rejected = websocket.receive_json()
            assert rejected == {"code": 4403, "reason": "permission_denied"}
            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_json()
            assert exc_info.value.code == 4403
    assert _metric_sample(
        "pinvi_api_ws_connections_total",
        {"channel": "trip", "result": "rejected", "reason": "permission_denied"},
    ) == (rejected_before + 1)
    assert _metric_sample(
        "pinvi_api_ws_closes_total",
        {"channel": "trip", "code": "4403", "reason": "permission_denied"},
    ) == (close_before + 1)


async def test_handshake_close_settle_seconds_clamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1.ws import _handshake_close_settle_seconds

    monkeypatch.setattr(settings, "pinvi_ws_handshake_close_settle_seconds", -1.0)
    assert _handshake_close_settle_seconds() == 0.0
    monkeypatch.setattr(settings, "pinvi_ws_handshake_close_settle_seconds", 10.0)
    assert _handshake_close_settle_seconds() == 5.0
    monkeypatch.setattr(settings, "pinvi_ws_handshake_close_settle_seconds", 0.25)
    assert _handshake_close_settle_seconds() == 0.25


async def test_ws_trip_channel_reject_settles_before_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reject는 settle을 close **이전에** 넣어 close code가 edge를 건너게 한다(C7 #820).

    단순히 sleep이 호출됐는지가 아니라 settle→close **순서**를 검증한다(리뷰 P3).
    """
    import app.api.v1.ws as ws_module
    from app.main import app

    await realtime_broker.reset()
    monkeypatch.setattr(settings, "pinvi_ws_handshake_close_settle_seconds", 0.031)
    ws_module._reject_settle_inflight[0] = 0
    events: list[str] = []
    real_sleep = asyncio.sleep
    real_close = ws_module._close_websocket

    async def recording_sleep(delay: float, *args: object, **kwargs: object) -> None:
        if delay == 0.031:
            events.append("settle")
        await real_sleep(delay)

    async def recording_close(*args: object, **kwargs: object) -> None:
        events.append("close")
        await real_close(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ws_module.asyncio, "sleep", recording_sleep)
    monkeypatch.setattr(ws_module, "_close_websocket", recording_close)

    with TestClient(app) as sync_client:
        trip_id = uuid.uuid4()
        with sync_client.websocket_connect(
            f"/ws/trips/{trip_id}?token=not-a-valid-token"
        ) as websocket:
            rejected = websocket.receive_json()
            assert rejected == {"code": 4401, "reason": "token_invalid"}
            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_json()
            assert exc_info.value.code == 4401
    # settle이 close 이전에(정확히 이 순서로) 적용됐다.
    assert events == ["settle", "close"]


async def test_reject_settle_concurrency_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """동시 settle이 cap을 넘으면 settle을 생략한다(미인증 flood 증폭 방지, 리뷰 P2)."""
    import app.api.v1.ws as ws_module

    monkeypatch.setattr(settings, "pinvi_ws_handshake_close_settle_seconds", 0.05)
    monkeypatch.setattr(settings, "pinvi_ws_max_concurrent_reject_settles", 1)
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def recording_sleep(delay: float, *args: object, **kwargs: object) -> None:
        slept.append(delay)
        await real_sleep(delay)

    monkeypatch.setattr(ws_module.asyncio, "sleep", recording_sleep)

    # cap 미만: settle 적용 + inflight 카운터가 올랐다 내려온다.
    ws_module._reject_settle_inflight[0] = 0
    await ws_module._settle_before_reject_close()
    assert slept == [0.05]
    assert ws_module._reject_settle_inflight[0] == 0

    # cap 도달(inflight == 1 == cap): settle 생략.
    ws_module._reject_settle_inflight[0] = 1
    await ws_module._settle_before_reject_close()
    assert slept == [0.05]  # 추가 sleep 없음
    ws_module._reject_settle_inflight[0] = 0


async def test_ws_trip_channel_rate_limits_client_messages(
    session_factory,
    verified_user,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    monkeypatch.setattr(settings, "pinvi_ws_client_rate_per_second", 2)
    monkeypatch.setattr(settings, "pinvi_ws_client_rate_per_minute", 60)
    monkeypatch.setattr(settings, "pinvi_ws_rate_limit_close_grace_seconds", 0.0)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["pinvi_access"]
    close_before = _metric_sample(
        "pinvi_api_ws_closes_total",
        {"channel": "trip", "code": "4429", "reason": "rate_limited"},
    )

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
    assert _metric_sample(
        "pinvi_api_ws_closes_total",
        {"channel": "trip", "code": "4429", "reason": "rate_limited"},
    ) == (close_before + 1)


async def test_ws_trip_channel_holds_cap_during_rate_limit_grace_close(
    session_factory,
    verified_user,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # T-185(#91): grace 동안 broker 슬롯을 유지해야 한다 — 슬롯을 먼저 비우면 닫히는 중인
    # 소켓이 cap에 계상되지 않아 connect→spam→reconnect로 cap을 우회(FD/메모리 누수)한다.
    from app.main import app

    await realtime_broker.reset()
    monkeypatch.setattr(settings, "pinvi_ws_client_rate_per_second", 2)
    monkeypatch.setattr(settings, "pinvi_ws_client_rate_per_minute", 60)
    monkeypatch.setattr(settings, "pinvi_ws_rate_limit_close_grace_seconds", 0.5)
    monkeypatch.setattr(settings, "pinvi_ws_max_connections_per_trip", 1)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["pinvi_access"]

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

            # grace 동안 슬롯이 유지된다(아직 해제 전).
            assert await realtime_broker.connection_count(trip_uuid) == 1

            with pytest.raises(WebSocketDisconnect) as exc_info:
                first.receive_json()
            assert exc_info.value.code == 4429

        # 연결이 완전히 닫힌 뒤에야 슬롯이 해제된다.
        for _ in range(50):
            if await realtime_broker.connection_count(trip_uuid) == 0:
                break
            await asyncio.sleep(0.01)
        assert await realtime_broker.connection_count(trip_uuid) == 0


async def test_ws_trip_channel_rejects_connection_cap(
    session_factory,
    verified_user,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    monkeypatch.setattr(settings, "pinvi_ws_max_connections_per_trip", 1)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["pinvi_access"]
    rejected_before = _metric_sample(
        "pinvi_api_ws_connections_total",
        {
            "channel": "trip",
            "result": "rejected",
            "reason": "trip_connection_limit_exceeded",
        },
    )
    close_before = _metric_sample(
        "pinvi_api_ws_closes_total",
        {
            "channel": "trip",
            "code": "4408",
            "reason": "trip_connection_limit_exceeded",
        },
    )

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
    assert _metric_sample(
        "pinvi_api_ws_connections_total",
        {
            "channel": "trip",
            "result": "rejected",
            "reason": "trip_connection_limit_exceeded",
        },
    ) == (rejected_before + 1)
    assert _metric_sample(
        "pinvi_api_ws_closes_total",
        {
            "channel": "trip",
            "code": "4408",
            "reason": "trip_connection_limit_exceeded",
        },
    ) == (close_before + 1)


async def test_ws_trip_channel_closes_on_heartbeat_timeout(
    session_factory,
    verified_user,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1 import ws as ws_module
    from app.main import app

    await realtime_broker.reset()
    monkeypatch.setattr(ws_module, "_HEARTBEAT_TIMEOUT_SECONDS", 0.01)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["pinvi_access"]
    close_before = _metric_sample(
        "pinvi_api_ws_closes_total",
        {"channel": "trip", "code": "4400", "reason": "heartbeat_timeout"},
    )

    with TestClient(app) as sync_client:
        created = sync_client.post("/trips", json={"title": "heartbeat"}, cookies=cookies)
        assert created.status_code == 201, created.text
        trip_id = created.json()["data"]["trip_id"]

        with sync_client.websocket_connect(f"/ws/trips/{trip_id}?token={token}") as websocket:
            assert websocket.receive_json()["type"] == "presence.update"
            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_json()
            assert exc_info.value.code == 4400

    assert _metric_sample(
        "pinvi_api_ws_closes_total",
        {"channel": "trip", "code": "4400", "reason": "heartbeat_timeout"},
    ) == (close_before + 1)


async def test_ws_trip_channel_rejects_invalid_cursor(
    session_factory,
    verified_user,
    auth_cookies,
) -> None:
    from app.main import app

    await realtime_broker.reset()
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    token = cookies["pinvi_access"]

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
