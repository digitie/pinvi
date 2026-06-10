"""`/users/me/telegram-targets/*` — `docs/integrations/telegram.md` §6. T-106.

bot token은 받지 않는다(§1). 사용자는 TripMate 시스템 봇을 자기 chat에 추가한 뒤
chat_id를 등록한다. 등록/verify 시 시스템 봇 토큰으로 `getChat`을 호출한다.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.clients.telegram import TelegramClient
from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.models.telegram_target import TelegramTarget
from app.schemas.envelope import Envelope
from app.schemas.telegram import TelegramTargetCreate, TelegramTargetResponse
from app.services.telegram_targets import (
    TelegramTargetNotFoundError,
    TelegramTargetVerifyError,
    create_target,
    delete_target,
    list_targets,
    verify_existing,
)

router = APIRouter(prefix="/users/me/telegram-targets", tags=["telegram"])


async def get_telegram_client() -> AsyncIterator[TelegramClient]:
    http = httpx.AsyncClient(base_url=settings.tripmate_telegram_api_base)
    client = TelegramClient(http, timeout_seconds=settings.tripmate_telegram_timeout_seconds)
    try:
        yield client
    finally:
        await client.aclose()


TelegramClientDep = Annotated[TelegramClient, Depends(get_telegram_client)]


def _system_bot_token() -> str | None:
    return settings.tripmate_telegram_bot_token_default or None


def _response(row: TelegramTarget) -> TelegramTargetResponse:
    return TelegramTargetResponse(
        id=row.id,
        telegram_chat_id=row.telegram_chat_id,
        telegram_chat_type=row.telegram_chat_type,
        telegram_message_thread_id=row.telegram_message_thread_id,
        telegram_label=row.telegram_label,
        title_snapshot=row.title_snapshot,
        is_default=row.is_default,
        is_enabled=row.is_enabled,
        last_verified_at=row.last_verified_at,
        last_send_status=row.last_send_status,
        created_at=row.created_at,
    )


def _verify_http(exc: TelegramTargetVerifyError) -> HTTPException:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.telegram_code, "message": str(exc)},
        headers=headers,
    )


def _not_found(exc: TelegramTargetNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("", response_model=Envelope[list[TelegramTargetResponse]])
async def list_telegram_targets(
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[TelegramTargetResponse]]:
    rows = await list_targets(db, user_id=uuid.UUID(current_user_id))
    return Envelope.of([_response(row) for row in rows])


@router.post("", response_model=Envelope[TelegramTargetResponse], status_code=201)
async def create_telegram_target(
    body: TelegramTargetCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
    client: TelegramClientDep,
) -> Envelope[TelegramTargetResponse]:
    try:
        row = await create_target(
            db,
            user_id=uuid.UUID(current_user_id),
            telegram_chat_id=body.telegram_chat_id,
            telegram_label=body.telegram_label,
            telegram_message_thread_id=body.telegram_message_thread_id,
            is_default=body.is_default,
            bot_token=_system_bot_token(),
            client=client,
        )
    except TelegramTargetVerifyError as exc:
        await db.rollback()
        raise _verify_http(exc) from exc
    await db.commit()
    await db.refresh(row)
    return Envelope.of(_response(row))


@router.post("/{target_id}/verify", response_model=Envelope[TelegramTargetResponse])
async def verify_telegram_target(
    target_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
    client: TelegramClientDep,
) -> Envelope[TelegramTargetResponse]:
    try:
        row = await verify_existing(
            db,
            target_id=target_id,
            user_id=uuid.UUID(current_user_id),
            bot_token=_system_bot_token(),
            client=client,
        )
    except TelegramTargetNotFoundError as exc:
        raise _not_found(exc) from exc
    except TelegramTargetVerifyError as exc:
        await db.commit()  # 실패 기록(last_send_status)은 보존.
        raise _verify_http(exc) from exc
    await db.commit()
    await db.refresh(row)
    return Envelope.of(_response(row))


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_telegram_target(
    target_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    try:
        await delete_target(db, target_id=target_id, user_id=uuid.UUID(current_user_id))
    except TelegramTargetNotFoundError as exc:
        raise _not_found(exc) from exc
    await db.commit()
