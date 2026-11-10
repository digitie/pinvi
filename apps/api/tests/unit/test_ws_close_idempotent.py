"""#719: 이미 닫힌 WS에 close/send를 다시 보내 ASGI 예외를 내지 않는다.

prod에서는 rate limit(4429) grace 중 클라이언트가 먼저 끊고, 그 사이 broadcast 전송이 실패해
소켓이 DISCONNECTED가 된 뒤 grace 끝의 close가 `WebSocketDisconnected`를 올렸다.
uvicorn은 끊긴 전송에 `ClientDisconnected`(OSError)를 올린다 — 여기서는 OSError로 흉내낸다.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from prometheus_client import REGISTRY
from starlette.websockets import WebSocket

import app.api.v1.ws as ws_module
from app.core.config import settings
from app.services.realtime_broker import realtime_broker


class Peer:
    """ASGI receive/send 쌍. `gone`이 서면 이후 모든 send가 전송 실패한다."""

    def __init__(self, incoming: list[dict[str, Any]]) -> None:
        self.inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for message in incoming:
            self.inbox.put_nowait(message)
        self.sent: list[dict[str, Any]] = []
        self.gone = False
        self.rate_limited = asyncio.Event()

    async def receive(self) -> dict[str, Any]:
        return await self.inbox.get()

    async def send(self, message: dict[str, Any]) -> None:
        if self.gone:
            raise OSError("client disconnected")
        self.sent.append(message)
        if message["type"] == "websocket.send" and "RATE_LIMITED" in message.get("text", ""):
            # 클라이언트는 RATE_LIMITED를 받자마자 grace 중에 끊는다.
            self.gone = True
            self.rate_limited.set()


def _websocket(peer: Peer) -> WebSocket:
    scope = {
        "type": "websocket",
        "path": "/ws/trips/x",
        "headers": [],
        "query_string": b"",
        "subprotocols": [],
    }
    return WebSocket(scope, peer.receive, peer.send)


def _closes(peer: Peer) -> list[dict[str, Any]]:
    return [message for message in peer.sent if message["type"] == "websocket.close"]


def _close_metric(code: str, reason: str) -> float:
    value = REGISTRY.get_sample_value(
        "pinvi_api_ws_closes_total", {"channel": "trip", "code": code, "reason": reason}
    )
    return float(value or 0.0)


async def _accepted(peer: Peer) -> WebSocket:
    peer.inbox.put_nowait({"type": "websocket.connect"})
    websocket = _websocket(peer)
    await websocket.accept()
    return websocket


async def test_close_twice_is_a_noop() -> None:
    peer = Peer([])
    websocket = await _accepted(peer)
    for _ in range(2):
        await ws_module._close_websocket(
            websocket, code=4429, reason="rate_limited", trip_id=None, user_id=None
        )
    assert len(_closes(peer)) == 1


async def test_close_after_failed_send_does_not_raise() -> None:
    peer = Peer([])
    websocket = await _accepted(peer)
    peer.gone = True
    with pytest.raises(ws_module.WebSocketDisconnect):
        await websocket.send_json({"type": "presence.update"})
    await ws_module._close_websocket(
        websocket, code=4429, reason="rate_limited", trip_id=None, user_id=None
    )
    assert _closes(peer) == []


async def test_close_on_vanished_transport_does_not_raise() -> None:
    peer = Peer([])
    websocket = await _accepted(peer)
    peer.gone = True
    await ws_module._close_websocket(
        websocket, code=4400, reason="heartbeat_timeout", trip_id=None, user_id=None
    )
    assert _closes(peer) == []


async def test_close_after_client_disconnect_message_is_skipped() -> None:
    peer = Peer([])
    websocket = await _accepted(peer)
    peer.inbox.put_nowait({"type": "websocket.disconnect", "code": 1001})
    await websocket.receive()
    await ws_module._close_websocket(
        websocket, code=4429, reason="rate_limited", trip_id=None, user_id=None
    )
    assert _closes(peer) == []


async def test_reject_when_client_left_during_settle_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer = Peer([{"type": "websocket.connect"}])
    websocket = _websocket(peer)
    monkeypatch.setattr(settings, "pinvi_ws_handshake_close_settle_seconds", 0.0)
    real_accept = websocket.accept

    async def accept_then_client_leaves(*args: Any, **kwargs: Any) -> None:
        await real_accept(*args, **kwargs)
        peer.gone = True

    monkeypatch.setattr(websocket, "accept", accept_then_client_leaves)
    await ws_module._reject(websocket, code=4401, reason="token_invalid")
    assert [message["type"] for message in peer.sent] == ["websocket.accept"]


def _patch_channel_deps(monkeypatch: pytest.MonkeyPatch, user_id: uuid.UUID) -> None:
    async def authenticate(_websocket: WebSocket, *, trip_id: uuid.UUID) -> uuid.UUID:
        return user_id

    async def get_trip(_db: object, *, trip_id: uuid.UUID, user_id: uuid.UUID) -> None:
        return None

    class _Session:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(ws_module, "_authenticate", authenticate)
    monkeypatch.setattr(ws_module, "get_trip_for_user", get_trip)
    monkeypatch.setattr(ws_module.db_session, "async_session_factory", _Session)


async def test_reply_send_failure_then_next_receive_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """리뷰 P1: 처리 중 응답(presence broadcast)이 끊긴 전송에서 실패하면 다음
    receive_json()이 WebSocketDisconnected를 올린다 — 정상 이탈로 끝나야 한다."""
    trip_id = uuid.uuid4()
    _patch_channel_deps(monkeypatch, uuid.uuid4())
    monkeypatch.setattr(settings, "pinvi_ws_client_rate_per_second", 0)
    monkeypatch.setattr(settings, "pinvi_ws_client_rate_per_minute", 0)
    await realtime_broker.reset()

    heartbeat = {
        "type": "websocket.receive",
        "text": json.dumps({"type": "presence.heartbeat", "payload": {}}),
    }
    peer = Peer([{"type": "websocket.connect"}])
    close_before = _close_metric("__other__", "client_disconnect")
    channel = asyncio.create_task(ws_module.trip_channel(_websocket(peer), trip_id))
    for _ in range(100):
        if any(m["type"] == "websocket.send" for m in peer.sent):
            break
        await asyncio.sleep(0.01)
    peer.gone = True  # 클라이언트가 heartbeat를 보내고 바로 떠난다.
    peer.inbox.put_nowait(heartbeat)
    await asyncio.wait_for(channel, 5)  # 수정 전: WebSocketDisconnected

    assert _closes(peer) == []
    assert _close_metric("__other__", "client_disconnect") == close_before + 1
    assert await realtime_broker.connection_count(trip_id) == 0


async def test_rate_limit_close_after_client_left_during_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prod 재현: RATE_LIMITED → 클라이언트 이탈 → grace 중 broadcast 실패 → grace 끝 close."""
    trip_id = uuid.uuid4()
    _patch_channel_deps(monkeypatch, uuid.uuid4())
    monkeypatch.setattr(settings, "pinvi_ws_client_rate_per_second", 2)
    monkeypatch.setattr(settings, "pinvi_ws_client_rate_per_minute", 60)
    monkeypatch.setattr(settings, "pinvi_ws_rate_limit_close_grace_seconds", 0.2)
    await realtime_broker.reset()

    pong = {"type": "websocket.receive", "text": json.dumps({"type": "pong", "payload": {}})}
    peer = Peer([{"type": "websocket.connect"}, pong, pong, pong])
    close_before = _close_metric("4429", "rate_limited")

    channel = asyncio.create_task(ws_module.trip_channel(_websocket(peer), trip_id))
    await asyncio.wait_for(peer.rate_limited.wait(), 5)
    # grace 중 다른 멤버의 이벤트 broadcast — 끊긴 소켓 전송이 실패해 DISCONNECTED가 된다.
    await realtime_broker.publish_event(
        trip_id=trip_id,
        event_type="presence.update",
        actor_user_id=None,
        payload={},
    )
    await asyncio.wait_for(channel, 5)  # 수정 전: WebSocketDisconnected

    assert _closes(peer) == []
    assert _close_metric("4429", "rate_limited") == close_before + 1
    assert await realtime_broker.connection_count(trip_id) == 0
