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


class BeachProfile(TimestampMixin, Base):
    __tablename__ = "beach_profiles"
    __table_args__ = (
        Index("ix_beach_profiles_map_feature_id", "map_feature_id"),
        Index("ix_beach_profiles_legal_dong", "legal_dong_code"),
        Index("ix_beach_profiles_sigungu", "sigungu_code"),
        Index("ix_beach_profiles_sido", "sido_code"),
        Index("ix_beach_profiles_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    map_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_beach_profiles_map_feature_id", ondelete="SET NULL"),
    )
    representative_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    representative_dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    geom: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False),
    )
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_beach_profiles_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    sido_code: Mapped[str | None] = mapped_column(String(10))
    road_name_code: Mapped[str | None] = mapped_column(String(12))
    road_address_management_no: Mapped[str | None] = mapped_column(String(64))
    road_address: Mapped[str | None] = mapped_column(String(500))
    address_snapshot: Mapped[str | None] = mapped_column(String(700))
    address_mapping_method: Mapped[str] = mapped_column(String(48), nullable=False)
    beach_width_m: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    beach_length_m: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    beach_material: Mapped[str | None] = mapped_column(String(255))
    homepage_url: Mapped[str | None] = mapped_column(Text)
    homepage_name: Mapped[str | None] = mapped_column(String(200))
    image_url: Mapped[str | None] = mapped_column(Text)
    emergency_contact: Mapped[str | None] = mapped_column(String(120))
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


class BeachProviderRef(TimestampMixin, Base):
    __tablename__ = "beach_provider_refs"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "provider_beach_id",
            name="uq_beach_provider_refs_provider_dataset_id",
        ),
        Index("ix_beach_provider_refs_beach_id", "beach_id"),
        Index("ix_beach_provider_refs_provider_name", "provider", "stable_name"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    beach_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("beach_profiles.id", name="fk_beach_provider_refs_beach_id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_beach_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stable_name: Mapped[str | None] = mapped_column(String(255))
    stable_address: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(Text)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BeachSourceRecord(Base):
    __tablename__ = "beach_source_records"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "dataset_key",
            "source_record_id",
            "response_hash",
            name="uq_beach_source_records_provider_dataset_record_hash",
        ),
        Index("ix_beach_source_records_dataset_record", "dataset_key", "source_record_id"),
        Index("ix_beach_source_records_collected_at", "collected_at"),
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


class BeachObservation(TimestampMixin, Base):
    __tablename__ = "beach_observations"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_beach_id",
            "observed_at",
            name="uq_beach_observations_provider_beach_time",
        ),
        Index("ix_beach_observations_beach_time", "beach_id", "observed_at"),
        Index("ix_beach_observations_source_record_id", "source_record_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    beach_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("beach_profiles.id", name="fk_beach_observations_beach_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_record_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "beach_source_records.id",
            name="fk_beach_observations_source_record_id",
            ondelete="SET NULL",
        ),
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_beach_id: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_station_name: Mapped[str | None] = mapped_column(String(120))
    tide: Mapped[str | None] = mapped_column(String(80))
    wave_height_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    water_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    wind_speed_ms: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    wind_direction: Mapped[str | None] = mapped_column(String(80))
    forecast_status: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    quota_snapshot: Mapped[str | None] = mapped_column(String(120))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BeachIndexForecast(TimestampMixin, Base):
    __tablename__ = "beach_index_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "beach_id",
            "forecast_date",
            "forecast_slot",
            name="uq_beach_index_forecasts_provider_beach_date_slot",
        ),
        Index("ix_beach_index_forecasts_beach_date", "beach_id", "forecast_date"),
        Index("ix_beach_index_forecasts_forecast_date", "forecast_date"),
        Index("ix_beach_index_forecasts_source_record_id", "source_record_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    beach_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "beach_profiles.id", name="fk_beach_index_forecasts_beach_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    source_record_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "beach_source_records.id",
            name="fk_beach_index_forecasts_source_record_id",
            ondelete="SET NULL",
        ),
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_place_code: Mapped[str | None] = mapped_column(String(80))
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_slot: Mapped[str] = mapped_column(String(24), nullable=False)
    index_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    total_index: Mapped[str | None] = mapped_column(String(80))
    max_wave_height_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    avg_water_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    avg_air_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    max_wind_speed_ms: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BeachWaterQualityMeasurement(TimestampMixin, Base):
    __tablename__ = "beach_water_quality_measurements"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "source_record_key",
            name="uq_beach_water_quality_measurements_provider_source_key",
        ),
        Index("ix_beach_water_quality_measurements_beach_date", "beach_id", "survey_date"),
        Index("ix_beach_water_quality_measurements_year", "survey_year"),
        Index("ix_beach_water_quality_measurements_source_record_id", "source_record_id"),
        Index("ix_beach_water_quality_measurements_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    beach_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "beach_profiles.id",
            name="fk_beach_water_quality_measurements_beach_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_record_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "beach_source_records.id",
            name="fk_beach_water_quality_measurements_source_record_id",
            ondelete="SET NULL",
        ),
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(255), nullable=False)
    survey_year: Mapped[int] = mapped_column(nullable=False)
    survey_date: Mapped[date | None] = mapped_column(Date)
    survey_round: Mapped[str | None] = mapped_column(String(40))
    survey_kind: Mapped[str | None] = mapped_column(String(80))
    survey_location: Mapped[str | None] = mapped_column(String(255))
    survey_location_detail: Mapped[str | None] = mapped_column(String(500))
    ecoli_result: Mapped[str | None] = mapped_column(String(80))
    enterococcus_result: Mapped[str | None] = mapped_column(String(80))
    suitability: Mapped[str | None] = mapped_column(String(40))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    geom: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False),
    )
    legal_dong_code: Mapped[str | None] = mapped_column(String(10))
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    sido_code: Mapped[str | None] = mapped_column(String(10))
    address_mapping_method: Mapped[str] = mapped_column(String(48), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
