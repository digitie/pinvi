"""`app.trip_day_pois` — sort_order TEXT COLLATE "C" (SPEC V8 E-6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
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
from sqlalchemy.sql.elements import conv

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
        CheckConstraint(
            "(cache_target_lon IS NULL) = (cache_target_lat IS NULL)",
            name=conv("ck_trip_day_pois_cache_coord_pair"),
        ),
        CheckConstraint(
            "cache_target_lon IS NULL OR cache_target_lon BETWEEN 124 AND 132",
            name=conv("ck_trip_day_pois_cache_lon_korea"),
        ),
        CheckConstraint(
            "cache_target_lat IS NULL OR cache_target_lat BETWEEN 33 AND 39.5",
            name=conv("ck_trip_day_pois_cache_lat_korea"),
        ),
        CheckConstraint(
            "cache_target_radius_km > 0 AND cache_target_radius_km <= 100",
            name=conv("ck_trip_day_pois_cache_radius"),
        ),
        CheckConstraint(
            "feature_snapshot #>> '{coord,lon}' IS NULL OR feature_snapshot ->> 'lon' IS NULL "
            "OR (feature_snapshot #>> '{coord,lon}')::numeric = "
            "(feature_snapshot ->> 'lon')::numeric",
            name=conv("ck_tdp_cache_lon_consistent"),
        ),
        CheckConstraint(
            "feature_snapshot #>> '{coord,lat}' IS NULL OR feature_snapshot ->> 'lat' IS NULL "
            "OR (feature_snapshot #>> '{coord,lat}')::numeric = "
            "(feature_snapshot ->> 'lat')::numeric",
            name=conv("ck_tdp_cache_lat_consistent"),
        ),
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
    # T-VN-32C(Map ADR-068): legacy f_* 참조의 UUID shadow. 값 **채움**은
    # 검증된 alias map 이관(services/feature_uuid_cutover)이 수행한다 —
    # Map 값 전환(PR-2) 이후 canonical UUID 리터럴 참조는 같은 runner의
    # opt-in(accept_uuid_literals) 자기-정본화 경로로만 채운다.
    # M05 reconciliation은 이 축을 **이동만** 시킨다: 이미 채워져 있던 결박을
    # replacement로 옮기되, 비어 있던 행에는 새로 새기지 않는다. 채움 권한은
    # 위 이관에 남는다(services/feature_reference_reconciliation._rebound_uuid).
    feature_uuid: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    feature_link_broken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    # Map/외부 snapshot 두 canonical shape(`coord.{lon,lat}`와 top-level `lon,lat`)를
    # DB generated column 하나로 접는다. 숫자가 아닌 좌표는 cast 단계에서 write를 거부한다.
    cache_target_lon: Mapped[Decimal | None] = mapped_column(
        Numeric(),
        Computed(
            "COALESCE(feature_snapshot #>> '{coord,lon}', feature_snapshot ->> 'lon')::numeric",
            persisted=True,
        ),
    )
    cache_target_lat: Mapped[Decimal | None] = mapped_column(
        Numeric(),
        Computed(
            "COALESCE(feature_snapshot #>> '{coord,lat}', feature_snapshot ->> 'lat')::numeric",
            persisted=True,
        ),
    )
    cache_target_radius_km: Mapped[Decimal] = mapped_column(
        Numeric(),
        nullable=False,
        server_default=text("5.000"),
    )
    cache_target_update_enabled: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("true"),
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
