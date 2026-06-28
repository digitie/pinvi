"""ADR-038 rate-limit bucket/override tables."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class RateLimitBucket(Base):
    """`app.rate_limit_buckets` — Postgres fixed-window counters."""

    __tablename__ = "rate_limit_buckets"
    __table_args__ = (CheckConstraint("count >= 0", name="count_nonnegative"),)

    bucket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    limit_name: Mapped[str] = mapped_column(String(80), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class RateLimitOverride(Base, TimestampMixin):
    """TTL based block/allow override for an HMAC bucket."""

    __tablename__ = "rate_limit_overrides"
    __table_args__ = (
        CheckConstraint(
            "identity_kind IN ('ip', 'ip_email', 'user', 'shared_token')",
            name="identity_kind_allowed",
        ),
        CheckConstraint("action IN ('blocked', 'allowed')", name="action_allowed"),
        Index("ix_rate_limit_overrides_bucket_active", "bucket_hash", "limit_name", "expires_at"),
        Index("ix_rate_limit_overrides_created_at", "created_at"),
        Index("ix_rate_limit_overrides_expires_at", "expires_at"),
    )

    override_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    limit_name: Mapped[str] = mapped_column(String(80), nullable=False)
    bucket_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_label: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text(), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    revoked_reason: Mapped[str | None] = mapped_column(Text())
