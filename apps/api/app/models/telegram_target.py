"""`app.telegram_targets` — 사용자 Telegram 알림 대상 — `docs/integrations/telegram.md` §2.1.

bot token 원본은 저장하지 않는다(§1). `telegram_bot_token_ref`는 토큰을 보관한
설정/vault 키 이름이며, 현 단계는 Pinvi 시스템 봇(`system`)만 지원한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class TelegramTarget(Base, TimestampMixin):
    __tablename__ = "telegram_targets"
    __table_args__ = (
        CheckConstraint(
            "char_length(telegram_chat_id) BETWEEN 1 AND 64",
            name="telegram_targets_chat_id_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_bot_token_ref: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default=text("'system'")
    )
    telegram_chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    telegram_chat_type: Mapped[str | None] = mapped_column(String(16))
    telegram_message_thread_id: Mapped[str | None] = mapped_column(String(64))
    telegram_label: Mapped[str | None] = mapped_column(String(80))
    title_snapshot: Mapped[str | None] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_send_status: Mapped[str | None] = mapped_column(String(32))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
