"""`app.telegram_system_notification_outbox` — Telegram 알림 outbox — `docs/integrations/telegram.md` §2.3/§8.

이름은 doc §2.3을 따른다. 사용자 알림 category(`trip_created`, `companion_invited`)도
같은 outbox로 흐른다 — payload에 `user_id`/`text`를 담고 worker가 default target을
해석해 전송한다(§8 재시도 패턴).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TelegramNotificationOutbox(Base):
    __tablename__ = "telegram_system_notification_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    # pending → sent | skipped(대상/토큰 없음) | failed(재시도 소진)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text())
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
