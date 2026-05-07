from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
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


class OceanActivityIndexLocation(TimestampMixin, Base):
    __tablename__ = "ocean_activity_index_locations"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "provider_location_id",
            name="uq_oail_provider_dataset_location",
        ),
        Index("ix_oail_dataset_name", "provider_dataset_key", "normalized_name"),
        Index("ix_oail_legal_dong_code", "legal_dong_code"),
        Index("ix_oail_sigungu_code", "sigungu_code"),
        Index("ix_oail_sido_code", "sido_code"),
        Index("ix_oail_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_location_id: Mapped[str] = mapped_column(String(180), nullable=False)
    provider_place_code: Mapped[str | None] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    geom: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False),
    )
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_oail_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    sido_code: Mapped[str | None] = mapped_column(String(10))
    address_snapshot: Mapped[str | None] = mapped_column(String(700))
    address_mapping_method: Mapped[str] = mapped_column(String(48), nullable=False)
    source_specific_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class OceanActivityIndexSourceRecord(Base):
    __tablename__ = "ocean_activity_index_source_records"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "dataset_key",
            "source_record_id",
            "response_hash",
            name="uq_oaisr_provider_dataset_record_hash",
        ),
        Index("ix_oaisr_dataset_record", "dataset_key", "source_record_id"),
        Index("ix_oaisr_collected_at", "collected_at"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(180), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class OceanActivityIndexForecast(TimestampMixin, Base):
    __tablename__ = "ocean_activity_index_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "location_id",
            "forecast_date",
            "forecast_slot",
            "activity_time_key",
            name="uq_oaif_provider_location_date_slot_time",
        ),
        Index("ix_oaif_location_date", "location_id", "forecast_date"),
        Index("ix_oaif_forecast_date", "forecast_date"),
        Index("ix_oaif_source_record_id", "source_record_id"),
        Index("ix_oaif_dataset_date", "provider_dataset_key", "forecast_date"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    location_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "ocean_activity_index_locations.id",
            name="fk_oaif_location_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_record_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "ocean_activity_index_source_records.id",
            name="fk_oaif_source_record_id",
            ondelete="SET NULL",
        ),
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_place_code: Mapped[str | None] = mapped_column(String(80))
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_slot: Mapped[str] = mapped_column(String(24), nullable=False)
    activity_time_key: Mapped[str] = mapped_column(String(120), nullable=False)
    activity_time_text: Mapped[str | None] = mapped_column(Text)
    activity_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activity_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weather: Mapped[str | None] = mapped_column(String(80))
    air_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    wind_speed_ms: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    index_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    total_index: Mapped[str | None] = mapped_column(String(80))
    grade: Mapped[str | None] = mapped_column(String(80))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
