"""`app.trip_day_pois` — sort_order TEXT COLLATE "C" (SPEC V8 E-6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
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


class TripDayPoi(Base, TimestampMixin):
    __tablename__ = "trip_day_pois"
    __table_args__ = (
        ForeignKeyConstraint(
            ["trip_id", "day_index"],
            ["app.trip_days.trip_id", "app.trip_days.day_index"],
            name="fk_trip_day_pois_day",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "budget_amount IS NULL OR budget_amount >= 0",
            name="ck_trip_day_pois_budget_nonnegative",
        ),
        CheckConstraint(
            "actual_amount IS NULL OR actual_amount >= 0",
            name="ck_trip_day_pois_actual_nonnegative",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_trip_day_pois_currency"),
    )

    attachment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # LexoRank — JS ASCII와 PG 정렬 일관을 위해 COLLATE "C"
    sort_order: Mapped[str] = mapped_column(Text(collation="C"), nullable=False)
    feature_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    feature_link_broken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    custom_marker_color: Mapped[str | None] = mapped_column(String(16))
    custom_marker_icon: Mapped[str | None] = mapped_column(String(64))
    # ADR-054: POI 출처('feature'|'manual'|'kakao'|'naver'). 외부 pick은 external_ref로 opaque 참조를
    # 저장하고(제공자 콘텐츠 미저장), 승인된 feature가 생기면 reconciliation이 feature_id를 채운다.
    source: Mapped[str | None] = mapped_column(String(16))
    external_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB(astext_type=Text()))
    planned_arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_note: Mapped[str | None] = mapped_column(Text())
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="KRW")
    user_url: Mapped[str | None] = mapped_column(Text())
    added_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
