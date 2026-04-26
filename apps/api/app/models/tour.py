from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, kst_now


class TourCourseRawKmaPoint(Base):
    __tablename__ = "tour_course_raw_kma_point"
    __table_args__ = (
        UniqueConstraint("source_file_hash", "row_number", name="uq_tcrkp_file_row"),
        Index("ix_tcrkp_spot_id", "spot_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_encoding: Mapped[str] = mapped_column(String(32), nullable=False)
    source_snapshot_date: Mapped[date | None] = mapped_column(Date)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    theme_category_code: Mapped[str] = mapped_column(String(32), nullable=False)
    course_id: Mapped[str] = mapped_column(String(40), nullable=False)
    spot_id: Mapped[str] = mapped_column(String(40), nullable=False)
    region_id: Mapped[str | None] = mapped_column(String(40))
    spot_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_line: Mapped[str | None] = mapped_column(Text)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class KmaRecommendedTourCourse(TimestampMixin, Base):
    __tablename__ = "kma_recommended_tour_course"
    __table_args__ = (
        UniqueConstraint("source_file_hash", "spot_id", name="uq_krt_course_file_spot"),
        Index("ix_krt_theme_course_order", "theme_category_code", "course_id", "course_order"),
        Index("ix_krt_legal_dong", "legal_dong_code"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_encoding: Mapped[str] = mapped_column(String(32), nullable=False)
    source_snapshot_date: Mapped[date | None] = mapped_column(Date)
    theme_category_code: Mapped[str] = mapped_column(String(32), nullable=False)
    theme_category: Mapped[str] = mapped_column(String(40), nullable=False)
    theme_name: Mapped[str | None] = mapped_column(String(120))
    course_id: Mapped[str] = mapped_column(String(40), nullable=False)
    spot_id: Mapped[str] = mapped_column(String(40), nullable=False)
    region_id: Mapped[str | None] = mapped_column(String(40))
    spot_name: Mapped[str] = mapped_column(String(255), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    course_order: Mapped[int | None] = mapped_column(Integer)
    travel_time_minutes: Mapped[int | None] = mapped_column(Integer)
    indoor_type: Mapped[str | None] = mapped_column(String(40))
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_krt_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    sido_code: Mapped[str | None] = mapped_column(String(10))
    address_snapshot: Mapped[str | None] = mapped_column(String(500))
    address_mapping_method: Mapped[str] = mapped_column(String(40), nullable=False)
    marker_source_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="kma_recommended_tour_course",
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TourCourseRawKmaSpotWeather(Base):
    __tablename__ = "tour_course_raw_kma_spot_weather"
    __table_args__ = (
        Index("ix_tcrksw_course_spot_time", "course_id", "spot_id", "base_date", "base_time"),
        Index("ix_tcrksw_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    course_id: Mapped[str] = mapped_column(String(40), nullable=False)
    spot_id: Mapped[str | None] = mapped_column(String(40))
    base_date: Mapped[str | None] = mapped_column(String(8))
    base_time: Mapped[str | None] = mapped_column(String(4))
    forecast_date: Mapped[str | None] = mapped_column(String(8))
    forecast_time: Mapped[str | None] = mapped_column(String(4))
    category_code: Mapped[str | None] = mapped_column(String(16))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class TourCourseServingKmaSpotWeather(TimestampMixin, Base):
    __tablename__ = "tour_course_serving_kma_spot_weather"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "spot_id",
            "base_date",
            "base_time",
            "forecast_date",
            "forecast_time",
            "category_code",
            name="uq_tcskw_course_spot_time_category",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_tcskw_course_spot", "course_id", "spot_id"),
        Index("ix_tcskw_legal_dong", "legal_dong_code"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    source_file_hash: Mapped[str | None] = mapped_column(String(64))
    theme_category_code: Mapped[str | None] = mapped_column(String(32))
    course_id: Mapped[str] = mapped_column(String(40), nullable=False)
    spot_id: Mapped[str | None] = mapped_column(String(40))
    spot_name: Mapped[str | None] = mapped_column(String(255))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    legal_dong_code: Mapped[str | None] = mapped_column(String(10))
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    sido_code: Mapped[str | None] = mapped_column(String(10))
    base_date: Mapped[str | None] = mapped_column(String(8))
    base_time: Mapped[str | None] = mapped_column(String(4))
    forecast_date: Mapped[str | None] = mapped_column(String(8))
    forecast_time: Mapped[str | None] = mapped_column(String(4))
    category_code: Mapped[str] = mapped_column(String(16), nullable=False)
    category_name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_category: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(24))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
