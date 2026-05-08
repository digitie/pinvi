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
    ForeignKeyConstraint,
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


class WeatherShortTermGridMapping(TimestampMixin, Base):
    __tablename__ = "weather_short_term_grid_mapping"
    __table_args__ = (
        UniqueConstraint("region_code_type", "region_code", name="uq_wstgm_region"),
        Index("ix_wstgm_grid", "nx", "ny"),
        Index("ix_wstgm_legal_dong", "legal_dong_code"),
        Index("ix_wstgm_sigungu", "sigungu_code"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    region_code_type: Mapped[str] = mapped_column(String(32), nullable=False)
    region_code: Mapped[str] = mapped_column(String(32), nullable=False)
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_wstgm_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    sido_code: Mapped[str | None] = mapped_column(String(10))
    representative_lon: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    representative_lat: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    nx: Mapped[int] = mapped_column(Integer, nullable=False)
    ny: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_method: Mapped[str] = mapped_column(String(40), nullable=False)
    source_boundary_version: Mapped[str | None] = mapped_column(String(64))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WeatherRawShortTerm(Base):
    __tablename__ = "weather_raw_short_term"
    __table_args__ = (
        Index("ix_wrst_grid_base", "nx", "ny", "base_date", "base_time"),
        Index("ix_wrst_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    nx: Mapped[int] = mapped_column(Integer, nullable=False)
    ny: Mapped[int] = mapped_column(Integer, nullable=False)
    base_date: Mapped[str] = mapped_column(String(8), nullable=False)
    base_time: Mapped[str] = mapped_column(String(4), nullable=False)
    forecast_date: Mapped[str | None] = mapped_column(String(8))
    forecast_time: Mapped[str | None] = mapped_column(String(4))
    category_code: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class WeatherServingShortTerm(TimestampMixin, Base):
    __tablename__ = "weather_serving_short_term"
    __table_args__ = (
        UniqueConstraint(
            "endpoint",
            "nx",
            "ny",
            "base_date",
            "base_time",
            "forecast_date",
            "forecast_time",
            "category_code",
            name="uq_wsst_endpoint_grid_time_category",
        ),
        Index("ix_wsst_grid_category", "nx", "ny", "category_code"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    nx: Mapped[int] = mapped_column(Integer, nullable=False)
    ny: Mapped[int] = mapped_column(Integer, nullable=False)
    base_date: Mapped[str] = mapped_column(String(8), nullable=False)
    base_time: Mapped[str] = mapped_column(String(4), nullable=False)
    forecast_date: Mapped[str | None] = mapped_column(String(8))
    forecast_time: Mapped[str | None] = mapped_column(String(4))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    forecast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category_code: Mapped[str] = mapped_column(String(16), nullable=False)
    category_name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_category: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(24))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WeatherBeachLocation(TimestampMixin, Base):
    __tablename__ = "weather_beach_location"
    __table_args__ = (
        UniqueConstraint("provider", "beach_num", name="uq_wbl_provider_beach_num"),
        Index("ix_wbl_map_feature_id", "map_feature_id"),
        Index("ix_wbl_legal_dong", "legal_dong_code"),
        Index("ix_wbl_sigungu", "sigungu_code"),
        Index("ix_wbl_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="kma")
    beach_num: Mapped[str] = mapped_column(String(8), nullable=False)
    beach_name: Mapped[str] = mapped_column(String(200), nullable=False)
    map_feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_wbl_map_feature_id", ondelete="CASCADE"),
        nullable=False,
    )
    nx: Mapped[int] = mapped_column(Integer, nullable=False)
    ny: Mapped[int] = mapped_column(Integer, nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_wbl_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    sido_code: Mapped[str | None] = mapped_column(String(10))
    road_name_code: Mapped[str | None] = mapped_column(String(12))
    road_address_management_no: Mapped[str | None] = mapped_column(String(64))
    address_mapping_method: Mapped[str] = mapped_column(String(40), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WeatherRawBeach(Base):
    __tablename__ = "weather_raw_beach"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "endpoint",
            "beach_num",
            "response_hash",
            name="uq_wrb_provider_endpoint_beach_hash",
        ),
        Index("ix_wrb_endpoint_beach_collected", "endpoint", "beach_num", "collected_at"),
        Index("ix_wrb_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="kma")
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    beach_num: Mapped[str] = mapped_column(String(8), nullable=False)
    request_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class WeatherServingBeach(TimestampMixin, Base):
    __tablename__ = "weather_serving_beach"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "endpoint",
            "beach_num",
            "source_record_key",
            "category_code",
            name="uq_wsb_provider_endpoint_key_category",
        ),
        Index("ix_wsb_beach_location_id", "beach_location_id"),
        Index("ix_wsb_map_feature_id", "map_feature_id"),
        Index("ix_wsb_beach_category", "beach_num", "category_code"),
        Index("ix_wsb_forecast_at", "forecast_at"),
        Index("ix_wsb_observed_at", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    beach_location_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "weather_beach_location.id",
            name="fk_wsb_beach_location_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    map_feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_wsb_map_feature_id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="kma")
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    beach_num: Mapped[str] = mapped_column(String(8), nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(180), nullable=False)
    base_date: Mapped[str | None] = mapped_column(String(8))
    base_time: Mapped[str | None] = mapped_column(String(4))
    forecast_date: Mapped[str | None] = mapped_column(String(8))
    forecast_time: Mapped[str | None] = mapped_column(String(4))
    source_observed_time: Mapped[str | None] = mapped_column(String(20))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    forecast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category_code: Mapped[str] = mapped_column(String(24), nullable=False)
    category_name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_category: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(24))
    station_name: Mapped[str | None] = mapped_column(String(120))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WeatherKmaAlertStationCode(TimestampMixin, Base):
    __tablename__ = "weather_kma_alert_station_code"

    stn_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    station_name: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WeatherRawKmaAlert(Base):
    __tablename__ = "weather_raw_kma_alert"
    __table_args__ = (
        Index("ix_wrka_type_stn_tm", "alert_type", "stn_id", "tm_fc"),
        Index("ix_wrka_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    stn_id: Mapped[str | None] = mapped_column(String(12))
    title: Mapped[str | None] = mapped_column(String(500))
    tm_fc: Mapped[str | None] = mapped_column(String(20))
    tm_seq: Mapped[str | None] = mapped_column(String(20))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class WeatherServingKmaAlert(TimestampMixin, Base):
    __tablename__ = "weather_serving_kma_alert"
    __table_args__ = (
        UniqueConstraint(
            "alert_type",
            "stn_id",
            "tm_fc",
            "tm_seq",
            "title",
            name="uq_wska_type_station_fc_seq_title",
        ),
        Index("ix_wska_alert_type_tm", "alert_type", "tm_fc"),
        Index("ix_wska_stn_id", "stn_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    stn_id: Mapped[str | None] = mapped_column(
        String(12),
        ForeignKey(
            "weather_kma_alert_station_code.stn_id",
            name="fk_wska_station_code",
            ondelete="SET NULL",
        ),
    )
    title: Mapped[str | None] = mapped_column(String(500))
    tm_fc: Mapped[str | None] = mapped_column(String(20))
    tm_seq: Mapped[str | None] = mapped_column(String(20))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WeatherMidForecastRegion(TimestampMixin, Base):
    __tablename__ = "weather_mid_forecast_region"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "endpoint",
            "region_kind",
            "provider_region_id",
            name="uq_wmfr_provider_endpoint_kind_region",
        ),
        Index("ix_wmfr_kind_region", "region_kind", "provider_region_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="kma")
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    region_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_region_id: Mapped[str] = mapped_column(String(20), nullable=False)
    region_name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_region_id: Mapped[str | None] = mapped_column(String(20))
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WeatherMidRegionAddressMapping(TimestampMixin, Base):
    __tablename__ = "weather_mid_region_address_mapping"
    __table_args__ = (
        ForeignKeyConstraint(
            ["provider", "endpoint", "provider_region_kind", "provider_region_id"],
            [
                "weather_mid_forecast_region.provider",
                "weather_mid_forecast_region.endpoint",
                "weather_mid_forecast_region.region_kind",
                "weather_mid_forecast_region.provider_region_id",
            ],
            name="fk_wmram_forecast_region",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "provider",
            "endpoint",
            "provider_region_kind",
            "provider_region_id",
            "sido_code",
            "sigungu_code",
            "legal_dong_code_prefix",
            name="uq_wmram_provider_region_address_scope",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_wmram_sido_sigungu", "sido_code", "sigungu_code"),
        Index("ix_wmram_region", "provider_region_kind", "provider_region_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="kma")
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_region_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_region_id: Mapped[str] = mapped_column(String(20), nullable=False)
    sido_code: Mapped[str | None] = mapped_column(String(10))
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    legal_dong_code_prefix: Mapped[str | None] = mapped_column(String(10))
    mapping_method: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    valid_from: Mapped[str | None] = mapped_column(String(8))
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WeatherRawMidTerm(Base):
    __tablename__ = "weather_raw_mid_term"
    __table_args__ = (
        Index("ix_wrmt_endpoint_region_tm", "endpoint", "provider_region_id", "tm_fc"),
        Index("ix_wrmt_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    region_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_region_id: Mapped[str] = mapped_column(String(20), nullable=False)
    tm_fc: Mapped[str | None] = mapped_column(String(20))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class WeatherServingMidTerm(TimestampMixin, Base):
    __tablename__ = "weather_serving_mid_term"
    __table_args__ = (
        UniqueConstraint(
            "endpoint",
            "region_kind",
            "provider_region_id",
            "tm_fc",
            "forecast_date",
            "forecast_slot",
            name="uq_wsmt_endpoint_region_forecast_slot",
        ),
        Index("ix_wsmt_region_date", "provider_region_id", "forecast_date"),
        Index("ix_wsmt_date_slot", "forecast_date", "forecast_slot"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    region_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_region_id: Mapped[str] = mapped_column(String(20), nullable=False)
    source_region_code: Mapped[str] = mapped_column(String(20), nullable=False)
    tm_fc: Mapped[str] = mapped_column(String(20), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_slot: Mapped[str] = mapped_column(String(16), nullable=False)
    weather_summary: Mapped[str | None] = mapped_column(Text)
    rain_probability: Mapped[str | None] = mapped_column(String(20))
    min_temperature: Mapped[str | None] = mapped_column(String(20))
    max_temperature: Mapped[str | None] = mapped_column(String(20))
    mapping_method: Mapped[str | None] = mapped_column(String(40))
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(255))
    display_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AirQualityRawStation(Base):
    __tablename__ = "air_quality_raw_station"
    __table_args__ = (
        Index("ix_aqrs_station", "station_name"),
        Index("ix_aqrs_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    request_sido_name: Mapped[str | None] = mapped_column(String(40))
    station_name: Mapped[str] = mapped_column(String(120), nullable=False)
    mang_name: Mapped[str | None] = mapped_column(String(80))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class AirQualityServingStation(TimestampMixin, Base):
    __tablename__ = "air_quality_serving_station"
    __table_args__ = (
        UniqueConstraint("station_name", "mang_name", "address", name="uq_aqss_station_address"),
        Index("ix_aqss_legal_dong", "legal_dong_code"),
        Index("ix_aqss_sigungu", "sigungu_code"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    station_name: Mapped[str] = mapped_column(String(120), nullable=False)
    mang_name: Mapped[str | None] = mapped_column(String(80))
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    sido_name: Mapped[str | None] = mapped_column(String(40))
    item: Mapped[str | None] = mapped_column(String(255))
    installation_year: Mapped[str | None] = mapped_column(String(8))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_aqss_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    mapping_method: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AirQualityRawForecast(Base):
    __tablename__ = "air_quality_raw_forecast"
    __table_args__ = (
        Index("ix_aqrf_code_time", "inform_code", "data_time"),
        Index("ix_aqrf_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    inform_code: Mapped[str | None] = mapped_column(String(16))
    data_time: Mapped[str | None] = mapped_column(String(40))
    inform_data: Mapped[str | None] = mapped_column(String(40))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class AirQualityServingForecast(TimestampMixin, Base):
    __tablename__ = "air_quality_serving_forecast"
    __table_args__ = (
        UniqueConstraint(
            "inform_code",
            "data_time",
            "inform_data",
            "inform_overall",
            name="uq_aqsf_code_time_data_overall",
        ),
        Index("ix_aqsf_code_time", "inform_code", "data_time"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    inform_code: Mapped[str] = mapped_column(String(16), nullable=False)
    data_time: Mapped[str] = mapped_column(String(40), nullable=False)
    inform_data: Mapped[str | None] = mapped_column(String(40))
    inform_overall: Mapped[str | None] = mapped_column(String(1000))
    inform_cause: Mapped[str | None] = mapped_column(String(1000))
    inform_grade: Mapped[str | None] = mapped_column(String(1000))
    action_knack: Mapped[str | None] = mapped_column(String(1000))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AirQualityRawSidoMeasurement(Base):
    __tablename__ = "air_quality_raw_sido_measurement"
    __table_args__ = (
        Index("ix_aqrsm_station_time", "sido_name", "station_name", "data_time"),
        Index("ix_aqrsm_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    sido_name: Mapped[str] = mapped_column(String(40), nullable=False)
    station_name: Mapped[str] = mapped_column(String(120), nullable=False)
    data_time: Mapped[str | None] = mapped_column(String(40))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class AirQualityServingSidoMeasurement(TimestampMixin, Base):
    __tablename__ = "air_quality_serving_sido_measurement"
    __table_args__ = (
        UniqueConstraint(
            "sido_name",
            "station_name",
            "data_time",
            name="uq_aqssm_sido_station_time",
        ),
        Index("ix_aqssm_station_time", "station_name", "data_time"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    sido_name: Mapped[str] = mapped_column(String(40), nullable=False)
    station_name: Mapped[str] = mapped_column(String(120), nullable=False)
    mang_name: Mapped[str | None] = mapped_column(String(80))
    data_time: Mapped[str] = mapped_column(String(40), nullable=False)
    khai_value: Mapped[str | None] = mapped_column(String(20))
    khai_grade: Mapped[str | None] = mapped_column(String(20))
    pm10_value: Mapped[str | None] = mapped_column(String(20))
    pm10_grade: Mapped[str | None] = mapped_column(String(20))
    pm25_value: Mapped[str | None] = mapped_column(String(20))
    pm25_grade: Mapped[str | None] = mapped_column(String(20))
    no2_value: Mapped[str | None] = mapped_column(String(20))
    no2_grade: Mapped[str | None] = mapped_column(String(20))
    o3_value: Mapped[str | None] = mapped_column(String(20))
    o3_grade: Mapped[str | None] = mapped_column(String(20))
    co_value: Mapped[str | None] = mapped_column(String(20))
    co_grade: Mapped[str | None] = mapped_column(String(20))
    so2_value: Mapped[str | None] = mapped_column(String(20))
    so2_grade: Mapped[str | None] = mapped_column(String(20))
    pm10_flag: Mapped[str | None] = mapped_column(String(20))
    pm25_flag: Mapped[str | None] = mapped_column(String(20))
    no2_flag: Mapped[str | None] = mapped_column(String(20))
    o3_flag: Mapped[str | None] = mapped_column(String(20))
    co_flag: Mapped[str | None] = mapped_column(String(20))
    so2_flag: Mapped[str | None] = mapped_column(String(20))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
