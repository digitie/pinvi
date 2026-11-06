"""소유자 일정 발송·예약 동의·발송 결과."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.deps import CurrentUserId, DbSession
from app.models.telegram_notification import TelegramNotification
from app.models.trip import Trip
from app.schemas.envelope import Envelope
from app.schemas.telegram_notifications import (
    TelegramNotificationResponse,
    TelegramPreferencesBody,
    TelegramSendRequest,
)
from app.services import telegram_notifications as service
from app.services.trip import TripNotFoundError, TripPermissionError, TripValidationError

router = APIRouter(tags=["telegram"])


def _error(exc: TripNotFoundError | TripPermissionError | TripValidationError) -> HTTPException:
    status = (
        429
        if isinstance(exc, service.TelegramSendBacklogError)
        else 404
        if isinstance(exc, TripNotFoundError)
        else 403
        if isinstance(exc, TripPermissionError)
        else 422
    )
    return HTTPException(status, detail={"code": exc.code, "message": str(exc)})


@router.post(
    "/trips/{trip_id}/telegram/send",
    response_model=Envelope[TelegramNotificationResponse],
    status_code=202,
)
async def send_itinerary(
    trip_id: uuid.UUID, body: TelegramSendRequest, current_user_id: CurrentUserId, db: DbSession
) -> Envelope[TelegramNotificationResponse]:
    try:
        row = await service.manual_send(
            db, trip_id=trip_id, user_id=uuid.UUID(current_user_id), body=body
        )
    except (TripNotFoundError, TripPermissionError, TripValidationError) as exc:
        raise _error(exc) from exc
    response = await service.notification_response(db, row)
    await db.commit()
    return Envelope.of(response)


@router.get(
    "/users/me/telegram-notification-preferences", response_model=Envelope[TelegramPreferencesBody]
)
async def get_preferences(
    current_user_id: CurrentUserId, db: DbSession
) -> Envelope[TelegramPreferencesBody]:
    return Envelope.of(
        service.preferences_body(await service.preferences(db, uuid.UUID(current_user_id)))
    )


@router.put(
    "/users/me/telegram-notification-preferences", response_model=Envelope[TelegramPreferencesBody]
)
async def update_preferences(
    body: TelegramPreferencesBody, current_user_id: CurrentUserId, db: DbSession
) -> Envelope[TelegramPreferencesBody]:
    try:
        row = await service.save_preferences(db, uuid.UUID(current_user_id), body)
    except TripValidationError as exc:
        raise _error(exc) from exc
    response = service.preferences_body(row)
    await db.commit()
    return Envelope.of(response)


@router.get(
    "/users/me/telegram-notifications", response_model=Envelope[list[TelegramNotificationResponse]]
)
async def list_notifications(
    current_user_id: CurrentUserId, db: DbSession, trip_id: uuid.UUID | None = None
) -> Envelope[list[TelegramNotificationResponse]]:
    user_id = uuid.UUID(current_user_id)
    query = select(TelegramNotification).where(TelegramNotification.user_id == user_id)
    if trip_id is not None:
        query = query.where(TelegramNotification.trip_ids.contains([str(trip_id)]))
    rows = list(
        (await db.scalars(query.order_by(TelegramNotification.created_at.desc()).limit(20))).all()
    )
    response: list[TelegramNotificationResponse] = []
    for row in rows:
        if row.trip_ids:
            owned = set(
                (
                    await db.scalars(
                        select(Trip.trip_id).where(
                            Trip.trip_id.in_([uuid.UUID(value) for value in row.trip_ids]),
                            Trip.owner_user_id == user_id,
                        )
                    )
                ).all()
            )
            if len(owned) != len(row.trip_ids):
                continue
        response.append(await service.notification_response(db, row))
    return Envelope.of(response)
