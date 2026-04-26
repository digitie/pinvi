from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
    o3_value: Mapped[str | None] = mapped_column(String(20))
    co_value: Mapped[str | None] = mapped_column(String(20))
    so2_value: Mapped[str | None] = mapped_column(String(20))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
