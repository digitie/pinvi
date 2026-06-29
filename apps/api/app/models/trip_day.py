"""`app.trip_days` 모델 — composite PK (trip_id, day_index)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKeyConstraint, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class TripDay(Base, TimestampMixin):
    __tablename__ = "trip_days"
    __table_args__ = (
        PrimaryKeyConstraint("trip_id", "day_index", name="pk_trip_days"),
        ForeignKeyConstraint(
            ["trip_id"],
            ["app.trips.trip_id"],
            name="fk_trip_days_trip_id",
            ondelete="CASCADE",
        ),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date | None] = mapped_column(Date())
    title: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text())
    # optimistic lock — trip/POI와 동일한 정수 version (If-Match 헤더로 검증, T-287).
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
