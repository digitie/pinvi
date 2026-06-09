"""`app.feature_suggestions` — 사용자 feature 제안 큐."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class FeatureSuggestion(Base, TimestampMixin):
    __tablename__ = "feature_suggestions"
    __table_args__ = (
        CheckConstraint(
            "type IN ('new_place', 'correction', 'closure')",
            name="ck_feature_suggestions_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'added', 'duplicate')",
            name="ck_feature_suggestions_status",
        ),
        CheckConstraint(
            "kind IN ('place', 'event', 'notice', 'price', 'weather', 'route', 'area')",
            name="ck_feature_suggestions_kind",
        ),
        CheckConstraint(
            "lng >= 124.0 AND lng <= 132.0 AND lat >= 33.0 AND lat <= 43.0",
            name="ck_feature_suggestions_korea_coord",
        ),
        CheckConstraint("char_length(name) BETWEEN 1 AND 200", name="ck_feature_suggestions_name"),
        CheckConstraint(
            "note IS NULL OR char_length(note) <= 2000",
            name="ck_feature_suggestions_note",
        ),
        Index(
            "ix_feature_suggestions_requester_created_at",
            "requester_user_id",
            "created_at",
        ),
        Index("ix_feature_suggestions_status_created_at", "status", "created_at"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    requester_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    suggestion_type: Mapped[str] = mapped_column(
        "type",
        String(16),
        nullable=False,
        server_default="new_place",
    )
    target_feature_id: Mapped[str | None] = mapped_column(Text())
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    lng: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    lat: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    categories: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)),
        nullable=False,
        server_default=text("ARRAY[]::varchar[]"),
    )
    note: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    reviewed_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    krtour_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB(astext_type=Text()))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
