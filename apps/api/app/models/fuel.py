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
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, kst_now


class FuelRawOpiNetRegionCode(Base):
    __tablename__ = "fuel_raw_opinet_region_code"
    __table_args__ = (
        Index("ix_frorc_region_code", "provider_region_code"),
        Index("ix_frorc_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_area_code: Mapped[str | None] = mapped_column(String(8))
    provider_region_code: Mapped[str] = mapped_column(String(8), nullable=False)
    provider_region_name: Mapped[str] = mapped_column(String(80), nullable=False)
    region_level: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_provider_region_code: Mapped[str | None] = mapped_column(String(8))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class FuelServingOpiNetRegionCode(TimestampMixin, Base):
    __tablename__ = "fuel_serving_opinet_region_code"
    __table_args__ = (
        Index("ix_fsorc_parent", "parent_provider_region_code"),
        Index("ix_fsorc_address_code", "address_code_standard_code"),
    )

    provider_region_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    provider_region_name: Mapped[str] = mapped_column(String(80), nullable=False)
    region_level: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_provider_region_code: Mapped[str | None] = mapped_column(String(8))
    address_code_standard_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_fsorc_address_code_standard",
            ondelete="SET NULL",
        ),
    )
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False)
    mapping_source: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FuelRegionLegalDongMapping(TimestampMixin, Base):
    __tablename__ = "fuel_region_legal_dong_mapping"
    __table_args__ = (
        UniqueConstraint("provider_region_code", name="uq_frlm_provider_region_code"),
        Index("ix_frlm_legal_dong_code", "legal_dong_code"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_region_code: Mapped[str] = mapped_column(
        String(8),
        ForeignKey(
            "fuel_serving_opinet_region_code.provider_region_code",
            name="fk_frlm_provider_region_code",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    provider_region_name: Mapped[str] = mapped_column(String(80), nullable=False)
    region_level: Mapped[str] = mapped_column(String(32), nullable=False)
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_frlm_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    mapping_source: Mapped[str] = mapped_column(String(40), nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[int] = mapped_column(nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(255))


class FuelRawAvgPrice(Base):
    __tablename__ = "fuel_raw_avg_price"
    __table_args__ = (
        Index("ix_frap_trade_fuel", "trade_date", "provider_fuel_code"),
        Index("ix_frap_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_region_code: Mapped[str | None] = mapped_column(String(8))
    legal_dong_code: Mapped[str | None] = mapped_column(String(10))
    trade_date: Mapped[str | None] = mapped_column(String(8))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_fuel_code: Mapped[str] = mapped_column(String(8), nullable=False)
    provider_fuel_name: Mapped[str] = mapped_column(String(80), nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    diff: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_unit: Mapped[str] = mapped_column(String(24), nullable=False, default="KRW_PER_LITER")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class FuelServingAvgPrice(TimestampMixin, Base):
    __tablename__ = "fuel_serving_avg_price"
    __table_args__ = (
        UniqueConstraint(
            "region_key",
            "trade_date",
            "fuel_type",
            name="uq_fsap_region_trade_fuel",
        ),
        Index("ix_fsap_legal_fuel_ts", "legal_dong_code", "fuel_type", "timestamp"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    region_key: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_region_code: Mapped[str | None] = mapped_column(String(8))
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_fsap_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    trade_date: Mapped[str] = mapped_column(String(8), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_fuel_code: Mapped[str] = mapped_column(String(8), nullable=False)
    provider_fuel_name: Mapped[str] = mapped_column(String(80), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    diff: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_unit: Mapped[str] = mapped_column(String(24), nullable=False, default="KRW_PER_LITER")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FuelRawLowestStation(Base):
    __tablename__ = "fuel_raw_lowest_station"
    __table_args__ = (
        Index("ix_frls_region_fuel", "provider_region_code", "provider_fuel_code"),
        Index("ix_frls_station", "station_id"),
        Index("ix_frls_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_region_code: Mapped[str] = mapped_column(String(8), nullable=False)
    legal_dong_code: Mapped[str | None] = mapped_column(String(10))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_fuel_code: Mapped[str] = mapped_column(String(8), nullable=False)
    provider_fuel_name: Mapped[str] = mapped_column(String(80), nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    station_id: Mapped[str] = mapped_column(String(40), nullable=False)
    station_name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    poll_div_code: Mapped[str | None] = mapped_column(String(16))
    van_address: Mapped[str | None] = mapped_column(String(255))
    road_address: Mapped[str | None] = mapped_column(String(255))
    gis_x: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    gis_y: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    price_unit: Mapped[str] = mapped_column(String(24), nullable=False, default="KRW_PER_LITER")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class FuelServingLowestStation(TimestampMixin, Base):
    __tablename__ = "fuel_serving_lowest_station"
    __table_args__ = (
        UniqueConstraint(
            "provider_region_code",
            "fuel_type",
            "station_id",
            "timestamp",
            name="uq_fsls_region_fuel_station_timestamp",
        ),
        Index("ix_fsls_legal_fuel_price", "legal_dong_code", "fuel_type", "price"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_region_code: Mapped[str] = mapped_column(String(8), nullable=False)
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_fsls_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_fuel_code: Mapped[str] = mapped_column(String(8), nullable=False)
    provider_fuel_name: Mapped[str] = mapped_column(String(80), nullable=False)
    station_id: Mapped[str] = mapped_column(String(40), nullable=False)
    station_name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    poll_div_code: Mapped[str | None] = mapped_column(String(16))
    van_address: Mapped[str | None] = mapped_column(String(255))
    road_address: Mapped[str | None] = mapped_column(String(255))
    gis_x: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    gis_y: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    price_unit: Mapped[str] = mapped_column(String(24), nullable=False, default="KRW_PER_LITER")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
