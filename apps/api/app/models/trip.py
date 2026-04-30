from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from app.core.json_types import JsonValue
from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.place import MapFeature
    from app.models.tour import TourServingPublicCulturalFestival
    from app.models.user import User


class Trip(TimestampMixin, Base):
    __tablename__ = "trips"
    __table_args__ = (CheckConstraint("end_date >= start_date", name="date_range_order"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    destination: Mapped[str] = mapped_column(String(120), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    planning_status: Mapped[str] = mapped_column(String(32), default="idea", nullable=False)

    user: Mapped[User] = relationship(back_populates="trips")
    days: Mapped[list[TripDay]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripDay.day_index",
    )


class TripDay(TimestampMixin, Base):
    __tablename__ = "trip_days"
    __table_args__ = (
        UniqueConstraint("trip_id", "date", name="uq_trip_days_trip_id_date"),
        UniqueConstraint("trip_id", "day_index", name="uq_trip_days_trip_id_day_index"),
        CheckConstraint("day_index >= 1", name="positive_day_index"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    trip_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    trip: Mapped[Trip] = relationship(back_populates="days")
    items: Mapped[list[TripPlanItem]] = relationship(
        back_populates="trip_day",
        cascade="all, delete-orphan",
        order_by="TripPlanItem.sort_order",
    )


class TripPlanItem(TimestampMixin, Base):
    __tablename__ = "trip_plan_items"
    __table_args__ = (
        UniqueConstraint("trip_day_id", "sort_order", name="uq_tpi_day_sort_order"),
        CheckConstraint(
            "resource_type IN ("
            "'place', 'event', 'route', 'area', 'notice', "
            "'festival', 'trail', 'scenic_road', 'custom'"
            ")",
            name=conv("ck_tpi_resource_type"),
        ),
        CheckConstraint("sort_order >= 1", name=conv("ck_tpi_positive_sort_order")),
        CheckConstraint(
            "map_feature_id IS NULL OR resource_type IN ("
            "'place', 'event', 'route', 'area', 'notice'"
            ")",
            name=conv("ck_tpi_map_feature_type_match"),
        ),
        CheckConstraint(
            "festival_id IS NULL OR resource_type = 'festival'",
            name=conv("ck_tpi_festival_type_match"),
        ),
        CheckConstraint(
            "NOT (map_feature_id IS NOT NULL AND festival_id IS NOT NULL)",
            name=conv("ck_tpi_single_fk_resource"),
        ),
        CheckConstraint(
            "resource_key IS NULL OR resource_type IN ('trail', 'scenic_road', 'route', 'custom')",
            name=conv("ck_tpi_resource_key_type"),
        ),
        Index("ix_tpi_trip_day_sort", "trip_day_id", "sort_order"),
        Index("ix_tpi_map_feature_id", "map_feature_id"),
        Index("ix_tpi_festival_id", "festival_id"),
        Index("ix_tpi_resource_type", "resource_type"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    trip_day_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trip_days.id", name="fk_tpi_trip_day_id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    map_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_tpi_map_feature_id", ondelete="RESTRICT"),
    )
    festival_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "tour_serving_public_cultural_festival.id",
            name="fk_tpi_festival_id",
            ondelete="RESTRICT",
        ),
    )
    resource_key: Mapped[str | None] = mapped_column(String(180))
    title_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    address_snapshot: Mapped[str | None] = mapped_column(String(700))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operating_hours_snapshot: Mapped[str | None] = mapped_column(String(255))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    note: Mapped[str | None] = mapped_column(String(1000))
    resource_metadata: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    trip_day: Mapped[TripDay] = relationship(back_populates="items")
    map_feature: Mapped[MapFeature | None] = relationship()
    festival: Mapped[TourServingPublicCulturalFestival | None] = relationship()
