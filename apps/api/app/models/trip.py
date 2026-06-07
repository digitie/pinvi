"""`app.trips` 모델."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Trip(Base, TimestampMixin):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint(
            "primary_region_code IS NULL OR primary_region_code ~ '^[0-9]{2,10}$'",
            name="ck_trips_primary_region_code",
        ),
        CheckConstraint(
            "primary_region_source IS NULL OR primary_region_source IN "
            "('manual', 'poi_snapshot', 'geocoded')",
            name="ck_trips_primary_region_source",
        ),
        CheckConstraint(
            "(primary_region_code IS NULL AND primary_region_source IS NULL) OR "
            "(primary_region_code IS NOT NULL AND primary_region_source IS NOT NULL)",
            name="ck_trips_primary_region_pair",
        ),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())
    region_hint: Mapped[str | None] = mapped_column(String(120))
    primary_region_code: Mapped[str | None] = mapped_column(String(10))
    primary_region_source: Mapped[str | None] = mapped_column(String(16))
    cover_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    start_date: Mapped[date | None] = mapped_column(Date())
    end_date: Mapped[date | None] = mapped_column(Date())
    fuel_types: Mapped[list[str] | None] = mapped_column(ARRAY(String(16)))
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, server_default="private")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
