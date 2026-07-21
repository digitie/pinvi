"""KASI 특일과 POI 출몰시각 저장 모델."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class KasiSpecialDay(Base, TimestampMixin):
    __tablename__ = "kasi_special_days"

    special_day_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    dataset: Mapped[str] = mapped_column(String(40), nullable=False)
    sol_date: Mapped[date] = mapped_column(Date(), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sequence: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")
    is_holiday: Mapped[bool | None] = mapped_column(Boolean())
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class TripPoiRiseSet(Base, TimestampMixin):
    __tablename__ = "trip_poi_rise_sets"

    poi_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.trip_day_pois.attachment_id", ondelete="CASCADE"),
        primary_key=True,
    )
    locdate: Mapped[date | None] = mapped_column(Date())
    longitude: Mapped[float | None] = mapped_column(Float(precision=53))
    latitude: Mapped[float | None] = mapped_column(Float(precision=53))
    sunrise_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sunset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moonrise_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moonset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending_date",
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB(astext_type=Text()))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TripDayRiseSet(Base, TimestampMixin):
    """일자 단위 일출/일몰(ADR-055 §6). key `(trip_id, day_index)`, 기준 좌표는 일자 POI centroid."""

    __tablename__ = "trip_day_rise_sets"
    __table_args__ = (
        PrimaryKeyConstraint("trip_id", "day_index", name="pk_trip_day_rise_sets"),
        ForeignKeyConstraint(
            ["trip_id", "day_index"],
            ["app.trip_days.trip_id", "app.trip_days.day_index"],
            name="fk_trip_day_rise_sets_day",
            ondelete="CASCADE",
        ),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    locdate: Mapped[date | None] = mapped_column(Date())
    reference_poi_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    reference_label: Mapped[str | None] = mapped_column(Text())
    longitude: Mapped[float | None] = mapped_column(Float(precision=53))
    latitude: Mapped[float | None] = mapped_column(Float(precision=53))
    sunrise_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sunset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moonrise_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moonset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending_date")
    stale: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB(astext_type=Text()))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
