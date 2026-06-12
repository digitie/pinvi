"""`app.curated_trip_plans` + `app.curated_plan_pois` — Admin 추천 여행.

외부 `/notice-plans` API 이름은 Sprint 4 호환을 위해 유지하지만, 저장소 schema는
ADR-029에 따라 system notice와 분리된 curated-trip 이름을 쓴다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CuratedTripPlan(Base, TimestampMixin):
    __tablename__ = "curated_trip_plans"

    curated_plan_id: Mapped[uuid.UUID] = mapped_column(
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
    source_system: Mapped[str | None] = mapped_column(String(80))
    source_curated_feature_id: Mapped[str | None] = mapped_column(Text())
    source_curated_feature_version: Mapped[int | None] = mapped_column(Integer)
    source_etag: Mapped[str | None] = mapped_column(String(128))
    source_imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
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

    @property
    def notice_plan_id(self) -> uuid.UUID:
        """Deprecated API alias retained for `/notice-plans` response compatibility."""

        return self.curated_plan_id


class CuratedPlanPoi(Base, TimestampMixin):
    __tablename__ = "curated_plan_pois"
    __table_args__ = (
        CheckConstraint(
            "budget_amount IS NULL OR budget_amount >= 0",
            name=conv("ck_curated_plan_pois_budget_nonnegative"),
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name=conv("ck_curated_plan_pois_currency"),
        ),
    )

    curated_poi_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    curated_plan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.curated_trip_plans.curated_plan_id", ondelete="CASCADE"),
        nullable=False,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # LexoRank — COLLATE "C"
    sort_order: Mapped[str] = mapped_column(Text(collation="C"), nullable=False)
    feature_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
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
    source_curated_feature_id: Mapped[str | None] = mapped_column(Text())
    source_curated_feature_item_id: Mapped[str | None] = mapped_column(Text())
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def notice_poi_id(self) -> uuid.UUID:
        """Deprecated API alias retained for `/notice-plans` response compatibility."""

        return self.curated_poi_id

    @property
    def notice_plan_id(self) -> uuid.UUID:
        """Deprecated API alias retained for `/notice-plans` response compatibility."""

        return self.curated_plan_id
