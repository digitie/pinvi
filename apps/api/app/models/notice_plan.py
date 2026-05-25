"""`app.notice_plans` + `app.notice_pois` — Admin 추천 여행 (ADR-013).

notice_plans ≠ notice feature (라이브러리 공지/자연현상).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class NoticePlan(Base, TimestampMixin):
    __tablename__ = "notice_plans"

    notice_plan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, server_default="recommended")
    summary: Mapped[str | None] = mapped_column(Text())
    source_name: Mapped[str | None] = mapped_column(String(200))
    destination: Mapped[str | None] = mapped_column(String(120))
    starts_on: Mapped[date | None] = mapped_column(Date())
    ends_on: Mapped[date | None] = mapped_column(Date())
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NoticePoi(Base, TimestampMixin):
    __tablename__ = "notice_pois"

    notice_poi_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    notice_plan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.notice_plans.notice_plan_id", ondelete="CASCADE"),
        nullable=False,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # LexoRank — COLLATE "C"
    sort_order: Mapped[str] = mapped_column(Text(collation="C"), nullable=False)
    feature_id: Mapped[str | None] = mapped_column(Text())
    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    memo: Mapped[str | None] = mapped_column(Text())
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="KRW")
    user_url: Mapped[str | None] = mapped_column(Text())
    custom_marker_color: Mapped[str | None] = mapped_column(String(16))
    custom_marker_icon: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
