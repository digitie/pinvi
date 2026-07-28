"""`/ws/*` — Trip realtime WebSocket channels."""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections import deque
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import app.db.session as db_session
from app.core.config import settings
from app.core.security import InvalidTokenError, decode_access_token
from app.services import realtime_metrics
from app.services.realtime_broker import (
    RealtimeConnection,
    RealtimeConnectionLimitError,
    realtime_broker,
)
from app.services.trip import TripNotFoundError, TripPermissionError, get_trip_for_user

router = APIRouter(prefix="/ws", tags=["websocket"])
log = structlog.get_logger("websocket")

_CLOSE_UNAUTHORIZED = 4401
_CLOSE_PERMISSION_DENIED = 4403
_CLOSE_BAD_MESSAGE = 4400
_CLOSE_CONNECTION_LIMIT = 4408
_CLOSE_RATE_LIMITED = 4429
_HEARTBEAT_TIMEOUT_SECONDS = 35


def _handshake_close_settle_seconds() -> float:
    """handshake-time reject의 accept→close 사이 settle(초), 0..5s로 clamp.

    kor-travel-map C7(#820)과 동일 계층: 101 upgrade와 close frame이 같은 backend
    write로 합쳐지면 리버스 프록시가 close code를 떨궈 브라우저가 1006을 관측한다.
    accept 뒤 이 시간만큼 yield하면 101이 별도 write로 flush돼 close code가 살아남는다.
    """
    raw = settings.pinvi_ws_handshake_close_settle_seconds
    if raw < 0:
        return 0.0
    if raw > 5.0:
        return 5.0
    return raw


# 동시 reject-settle 수. settle은 broker cap/rate-limit 이전(accept 직후) 소켓을 붙잡으므로,
# 미인증 reject flood가 settle로 FD를 증폭하지 못하게 이 수로 상한을 둔다(단일 event loop → lock 불필요).
_reject_settle_inflight = [0]


async def _settle_before_reject_close() -> None:
    """reject의 accept→close 사이 settle. 동시 settle 수를 cap해(리뷰 P2) 미인증 flood가
    settle로 소켓/코루틴을 무제한 붙잡는 증폭을 막는다. cap 초과 시 settle 없이 즉시 진행한다.
    """
    settle = _handshake_close_settle_seconds()
    if settle <= 0.0:
        return
    cap = settings.pinvi_ws_max_concurrent_reject_settles
    if cap > 0 and _reject_settle_inflight[0] >= cap:
        return
    _reject_settle_inflight[0] += 1
    try:
        await asyncio.sleep(settle)
    finally:
        _reject_settle_inflight[0] -= 1


@router.websocket("/trips/{trip_id}")
async def trip_channel(websocket: WebSocket, trip_id: uuid.UUID) -> None:
    user_id = await _authenticate(websocket, trip_id=trip_id)
    if user_id is None:
        return

    async with db_session.async_session_factory() as db:
        try:
            await get_trip_for_user(db, trip_id=trip_id, user_id=user_id)
        except (TripNotFoundError, TripPermissionError):
            await _reject(
                websocket,
                code=_CLOSE_PERMISSION_DENIED,
                reason="permission_denied",
                trip_id=trip_id,
                user_id=user_id,
            )
            return

    await websocket.accept()
    try:
        connection = await realtime_broker.connect(websocket, trip_id=trip_id, user_id=user_id)
    except RealtimeConnectionLimitError as exc:
        # C7(#820): accept(위)와 close 사이 settle로 4408 close code가 edge를 건너게 한다.
        await _settle_before_reject_close()
        await websocket.send_json({"code": _CLOSE_CONNECTION_LIMIT, "reason": exc.reason})
        await _close_websocket(
            websocket,
            code=_CLOSE_CONNECTION_LIMIT,
            reason=exc.reason,
            trip_id=trip_id,
            user_id=user_id,
        )
        return

    active_connection: RealtimeConnection | None = connection
    rate_limiter = _ClientMessageRateLimiter()
    try:
        while True:
            message = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=_HEARTBEAT_TIMEOUT_SECONDS,
            )
            realtime_metrics.record_ws_message(
                direction="client",
                event_type=message.get("type") if isinstance(message, dict) else None,
            )
            if not rate_limiter.allow():
                await realtime_broker.send_error(
                    connection,
                    code="RATE_LIMITED",
                    message="WebSocket 메시지 전송 한도를 초과했습니다.",
                )
                # grace 동안 broker 슬롯을 유지한다 — 슬롯을 먼저 비우면 닫히는 중인 소켓이
                # cap에 계상되지 않아 connect→spam→reconnect 누적으로 FD/메모리가 새어
                # cap을 우회한다. finally에서 close 이후 정리한다.
                await asyncio.sleep(settings.pinvi_ws_rate_limit_close_grace_seconds)
                await _close_websocket(
                    websocket,
                    code=_CLOSE_RATE_LIMITED,
                    reason="rate_limited",
                    trip_id=trip_id,
                    user_id=user_id,
                )
                return
            await _handle_client_message(connection, message)
    except TimeoutError:
        await _close_websocket(
            websocket,
            code=_CLOSE_BAD_MESSAGE,
            reason="heartbeat_timeout",
            trip_id=trip_id,
            user_id=user_id,
        )
    except WebSocketDisconnect as exc:
        _record_close(
            code=exc.code,
            reason="client_disconnect",
            trip_id=trip_id,
            user_id=user_id,
        )
    finally:
        if active_connection is not None:
            await realtime_broker.disconnect(active_connection)


async def _authenticate(websocket: WebSocket, *, trip_id: uuid.UUID) -> uuid.UUID | None:
    token = websocket.cookies.get("pinvi_access") or websocket.query_params.get("token")
    if not token:
        await _reject(
            websocket,
            code=_CLOSE_UNAUTHORIZED,
            reason="token_missing",
            trip_id=trip_id,
        )
        return None
    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise InvalidTokenError("토큰 sub 클레임이 잘못되었습니다.")
        return uuid.UUID(subject)
    except (InvalidTokenError, ValueError):
        await _reject(
            websocket,
            code=_CLOSE_UNAUTHORIZED,
            reason="token_invalid",
            trip_id=trip_id,
        )
        return None


async def _handle_client_message(connection: RealtimeConnection, message: Any) -> None:
    if not isinstance(message, dict):
        await realtime_broker.send_error(
            connection,
            code="BAD_MESSAGE",
            message="JSON object 메시지만 허용합니다.",
        )
        return

    event_type = message.get("type")
    payload = message.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    if event_type == "presence.heartbeat":
        viewing_day = _viewing_day(payload.get("viewing_day"))
        await realtime_broker.mark_seen(
            connection,
            viewing_day=viewing_day,
        )
        await realtime_broker.publish_presence(connection, is_online=True)
        return

    if event_type == "presence.cursor":
        cursor_payload = _presence_cursor_payload(connection, payload)
        if cursor_payload is None:
            await realtime_broker.send_error(
                connection,
                code="BAD_CURSOR",
                message="presence.cursor 좌표는 latitude/longitude 숫자 범위 안이어야 합니다.",
            )
            return

        await realtime_broker.mark_seen(connection)
        await realtime_broker.publish_event(
            trip_id=connection.trip_id,
            event_type="presence.cursor",
            actor_user_id=connection.user_id,
            payload=cursor_payload,
        )
        return

    if event_type == "pong":
        await realtime_broker.mark_seen(connection)
        return

    await realtime_broker.send_error(
        connection,
        code="UNKNOWN_EVENT",
        message=f"지원하지 않는 WebSocket 이벤트입니다: {event_type}",
    )


class _ClientMessageRateLimiter:
    def __init__(self) -> None:
        self._seen_at: deque[float] = deque()

    def allow(self) -> bool:
        per_second = settings.pinvi_ws_client_rate_per_second
        per_minute = settings.pinvi_ws_client_rate_per_minute
        if per_second <= 0 and per_minute <= 0:
            return True

        now = time.monotonic()
        minute_cutoff = now - 60.0
        while self._seen_at and self._seen_at[0] <= minute_cutoff:
            self._seen_at.popleft()

        recent_second = sum(1 for seen_at in self._seen_at if seen_at > now - 1.0)
        if per_second > 0 and recent_second >= per_second:
            return False
        if per_minute > 0 and len(self._seen_at) >= per_minute:
            return False

        self._seen_at.append(now)
        return True


def _viewing_day(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 1 or value > 366:
        return None
    return value


def _presence_cursor_payload(
    connection: RealtimeConnection,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    latitude = _coordinate(payload.get("latitude", payload.get("lat")), minimum=-90.0, maximum=90.0)
    longitude = _coordinate(
        payload.get("longitude", payload.get("lng")),
        minimum=-180.0,
        maximum=180.0,
    )
    if latitude is None or longitude is None:
        return None
    return {
        "user_id": str(connection.user_id),
        "lon": longitude,
        "lat": latitude,
    }


def _coordinate(value: Any, *, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    if number < minimum or number > maximum:
        return None
    return round(number, 6)


async def _reject(
    websocket: WebSocket,
    *,
    code: int,
    reason: str,
    trip_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    realtime_metrics.record_ws_connection_rejected(reason=reason)
    try:
        await websocket.accept()
    except Exception:  # accept 실패면 소켓이 죽었으므로 close를 호출하지 않는다(C7 #809)
        return
    # C7(#809/#820): 101 handshake를 flush한 뒤 close해야 close code가 리버스 프록시 edge를
    # 건너 살아남는다(미적용 시 브라우저가 4401/4403 대신 1006 관측 → 클라이언트 오분류).
    await _settle_before_reject_close()
    await websocket.send_json({"code": code, "reason": reason})
    await _close_websocket(
        websocket,
        code=code,
        reason=reason,
        trip_id=trip_id,
        user_id=user_id,
    )


async def _close_websocket(
    websocket: WebSocket,
    *,
    code: int,
    reason: str,
    trip_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> None:
    _record_close(code=code, reason=reason, trip_id=trip_id, user_id=user_id)
    await websocket.close(code=code, reason=reason)


def _record_close(
    *,
    code: int | None,
    reason: str,
    trip_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> None:
    realtime_metrics.record_ws_close(code=code, reason=reason)
    fields: dict[str, object] = {
        "channel": "trip",
        "code": realtime_metrics.close_code_label(code),
        "reason": realtime_metrics.reason_label(reason),
    }
    if trip_id is not None:
        fields["trip_id"] = str(trip_id)
    if user_id is not None:
        fields["user_id"] = str(user_id)
    log.info("pinvi.websocket.close", **fields)
