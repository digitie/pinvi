"""`/ws/*` — Trip realtime WebSocket channels."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import app.db.session as db_session
from app.core.security import InvalidTokenError, decode_access_token
from app.services.realtime_broker import RealtimeConnection, realtime_broker
from app.services.trip import TripNotFoundError, TripPermissionError, get_trip_for_user

router = APIRouter(prefix="/ws", tags=["websocket"])

_CLOSE_UNAUTHORIZED = 4401
_CLOSE_PERMISSION_DENIED = 4403
_CLOSE_BAD_MESSAGE = 4400
_HEARTBEAT_TIMEOUT_SECONDS = 35


@router.websocket("/trips/{trip_id}")
async def trip_channel(websocket: WebSocket, trip_id: uuid.UUID) -> None:
    user_id = await _authenticate(websocket)
    if user_id is None:
        return

    async with db_session.async_session_factory() as db:
        try:
            await get_trip_for_user(db, trip_id=trip_id, user_id=user_id)
        except (TripNotFoundError, TripPermissionError):
            await _reject(websocket, code=_CLOSE_PERMISSION_DENIED, reason="permission_denied")
            return

    await websocket.accept()
    connection = await realtime_broker.connect(websocket, trip_id=trip_id, user_id=user_id)
    try:
        while True:
            message = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=_HEARTBEAT_TIMEOUT_SECONDS,
            )
            await _handle_client_message(connection, message)
    except TimeoutError:
        await websocket.close(code=_CLOSE_BAD_MESSAGE, reason="heartbeat_timeout")
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_broker.disconnect(connection)


async def _authenticate(websocket: WebSocket) -> uuid.UUID | None:
    token = websocket.cookies.get("tripmate_access") or websocket.query_params.get("token")
    if not token:
        await _reject(websocket, code=_CLOSE_UNAUTHORIZED, reason="token_missing")
        return None
    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise InvalidTokenError("토큰 sub 클레임이 잘못되었습니다.")
        return uuid.UUID(subject)
    except (InvalidTokenError, ValueError):
        await _reject(websocket, code=_CLOSE_UNAUTHORIZED, reason="token_invalid")
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
        viewing_day = payload.get("viewing_day")
        await realtime_broker.mark_seen(
            connection,
            viewing_day=viewing_day if isinstance(viewing_day, int) else None,
        )
        await realtime_broker.publish_presence(connection, is_online=True)
        return

    if event_type == "presence.cursor":
        await realtime_broker.mark_seen(connection)
        await realtime_broker.publish_event(
            trip_id=connection.trip_id,
            event_type="presence.cursor",
            actor_user_id=connection.user_id,
            payload={
                "user_id": str(connection.user_id),
                "lat": payload.get("lat"),
                "lng": payload.get("lng"),
            },
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


async def _reject(websocket: WebSocket, *, code: int, reason: str) -> None:
    await websocket.accept()
    await websocket.send_json({"code": code, "reason": reason})
    await websocket.close(code=code, reason=reason)
