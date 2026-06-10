"""`/trips/{trip_id}/telegram-targets/*` — `docs/integrations/telegram.md` §6.5/6.6. T-106.

여행 소유자가 자기 Telegram 대상을 여행에 연결/해제한다(여행당 ≤3). target 자체 CRUD는
`/users/me/telegram-targets`(별 라우터)에서 한다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.v1.telegram_targets import _response  # 공통 응답 매퍼 재사용
from app.core.deps import CurrentUserId, DbSession
from app.schemas.envelope import Envelope
from app.schemas.telegram import TelegramTargetResponse, TripTelegramTargetLink
from app.services.telegram_targets import (
    TelegramTargetNotFoundError,
    TripTargetConflictError,
    TripTargetLimitError,
    link_trip_target,
    list_trip_targets,
    unlink_trip_target,
)
from app.services.trip import (
    TripNotFoundError,
    TripPermissionError,
    get_trip_owned_by_user,
)

router = APIRouter(prefix="/trips/{trip_id}/telegram-targets", tags=["telegram"])


def _raise_trip(exc: TripNotFoundError | TripPermissionError) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if isinstance(exc, TripNotFoundError)
        else status.HTTP_403_FORBIDDEN
    )
    return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})


@router.get("", response_model=Envelope[list[TelegramTargetResponse]])
async def list_trip_telegram_targets(
    trip_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[TelegramTargetResponse]]:
    user_id = uuid.UUID(current_user_id)
    try:
        await get_trip_owned_by_user(db, trip_id=trip_id, user_id=user_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        raise _raise_trip(exc) from exc
    rows = await list_trip_targets(db, trip_id=trip_id, user_id=user_id)
    return Envelope.of([_response(row) for row in rows])


@router.post("", response_model=Envelope[TelegramTargetResponse], status_code=201)
async def link_trip_telegram_target(
    trip_id: uuid.UUID,
    body: TripTelegramTargetLink,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[TelegramTargetResponse]:
    user_id = uuid.UUID(current_user_id)
    try:
        await get_trip_owned_by_user(db, trip_id=trip_id, user_id=user_id)
        target = await link_trip_target(
            db, trip_id=trip_id, target_id=body.telegram_target_id, user_id=user_id
        )
    except (TripNotFoundError, TripPermissionError) as exc:
        raise _raise_trip(exc) from exc
    except TelegramTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripTargetConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripTargetLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "reason": "max_targets_reached"},
        ) from exc
    await db.commit()
    return Envelope.of(_response(target))


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_trip_telegram_target(
    trip_id: uuid.UUID,
    target_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    user_id = uuid.UUID(current_user_id)
    try:
        await get_trip_owned_by_user(db, trip_id=trip_id, user_id=user_id)
        await unlink_trip_target(db, trip_id=trip_id, target_id=target_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        raise _raise_trip(exc) from exc
    except TelegramTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await db.commit()
