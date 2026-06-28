"""Email deliverability state — suppression source + Resend webhook events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class EmailSuppression(Base, TimestampMixin):
    """수신자 단위 발송 차단 source. 원문 이메일 대신 정규화 이메일 hash만 저장한다."""

    __tablename__ = "email_suppressions"
    __table_args__ = (UniqueConstraint("email_hash", name="uq_email_suppressions_email_hash"),)

    suppression_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="resend")
    provider_event_id: Mapped[str | None] = mapped_column(String(128))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    release_reason: Mapped[str | None] = mapped_column(Text())


class ResendWebhookEvent(Base):
    """Resend/Svix webhook idempotency ledger."""

    __tablename__ = "resend_webhook_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    svix_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_ref: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    resend_email_id: Mapped[str | None] = mapped_column(String(128))
    event_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
