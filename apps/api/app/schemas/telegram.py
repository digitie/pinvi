"""Telegram 알림 대상 schemas — `docs/integrations/telegram.md` §6. T-106."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TripTelegramTargetLink(BaseModel):
    """`POST /trips/{trip_id}/telegram-targets` 본문 (§6.5)."""

    telegram_target_id: uuid.UUID


class TelegramTargetCreate(BaseModel):
    """`POST /users/me/telegram-targets` 본문.

    bot token은 받지 않는다(§1) — Pinvi 시스템 봇을 사용자가 자기 chat에 추가한 뒤
    chat_id만 등록한다. `telegram_bot_token_ref`는 현 단계 `system`만 허용.
    """

    telegram_chat_id: str = Field(min_length=1, max_length=64)
    telegram_label: str | None = Field(default=None, max_length=80)
    telegram_message_thread_id: str | None = Field(default=None, max_length=64)
    is_default: bool = False

    @field_validator("telegram_chat_id")
    @classmethod
    def _strip_chat_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("telegram_chat_id는 비어 있을 수 없습니다.")
        return stripped

    @field_validator("telegram_label")
    @classmethod
    def _normalize_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TelegramTargetResponse(BaseModel):
    id: uuid.UUID
    telegram_chat_id: str
    telegram_chat_type: str | None
    telegram_message_thread_id: str | None
    telegram_label: str | None
    title_snapshot: str | None
    is_default: bool
    is_enabled: bool
    last_verified_at: datetime | None
    last_send_status: str | None
    created_at: datetime
