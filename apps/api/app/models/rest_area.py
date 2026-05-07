from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, kst_now


class RestAreaRawMaster(Base):
    __tablename__ = "rest_area_raw_master"
    __table_args__ = (
        Index("ix_rarm_source_key", "source_key"),
        Index("ix_rarm_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    source_api_id: Mapped[str] = mapped_column(String(16), nullable=False)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source_snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class RestAreaServingMaster(TimestampMixin, Base):
    __tablename__ = "rest_area_serving_master"
    __table_args__ = (
        Index("ix_rasm_route", "route_code", "direction"),
        Index("ix_rasm_name", "name"),
    )

    svar_cd: Mapped[str] = mapped_column(String(16), primary_key=True)
    provider_service_area_code: Mapped[str | None] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(80))
    route_code: Mapped[str | None] = mapped_column(String(16))
    route_name: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(255))
    convenience_raw: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(80))
    maintenance_yn: Mapped[str | None] = mapped_column(String(8))
    truck_sa_yn: Mapped[str | None] = mapped_column(String(8))
    representative_food: Mapped[str | None] = mapped_column(String(255))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    lat: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RestAreaRawOilPrice(Base):
    __tablename__ = "rest_area_raw_oil_price"
    __table_args__ = (
        Index("ix_rarop_source_key", "source_key"),
        Index("ix_rarop_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    source_api_id: Mapped[str] = mapped_column(String(16), nullable=False)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    service_area_code2: Mapped[str | None] = mapped_column(String(16))
    source_snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class RestAreaServingOilPrice(TimestampMixin, Base):
    __tablename__ = "rest_area_serving_oil_price"
    __table_args__ = (
        UniqueConstraint(
            "svar_cd",
            "provider_fuel_code",
            "collected_at",
            name="uq_rasop_svar_fuel_collected_at",
        ),
        Index("ix_rasop_fuel_price", "fuel_type", "price_per_liter_krw"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    svar_cd: Mapped[str] = mapped_column(
        String(16),
        ForeignKey(
            "rest_area_serving_master.svar_cd",
            name="fk_rasop_svar_cd",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    provider_service_area_code: Mapped[str | None] = mapped_column(String(24))
    station_name: Mapped[str | None] = mapped_column(String(160))
    route_code: Mapped[str | None] = mapped_column(String(16))
    route_name: Mapped[str | None] = mapped_column(String(120))
    direction: Mapped[str | None] = mapped_column(String(80))
    oil_company: Mapped[str | None] = mapped_column(String(80))
    lpg_yn: Mapped[str | None] = mapped_column(String(8))
    provider_fuel_code: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_fuel_name: Mapped[str] = mapped_column(String(80), nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    price_per_liter_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    price_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price_time_source: Mapped[str] = mapped_column(String(40), nullable=False)
    price_unit: Mapped[str] = mapped_column(String(24), nullable=False, default="KRW_PER_LITER")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RestAreaRawService(Base):
    __tablename__ = "rest_area_raw_service"
    __table_args__ = (
        Index("ix_rars_source_key", "source_key"),
        Index("ix_rars_response_hash", "response_hash"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    source_api_id: Mapped[str] = mapped_column(String(16), nullable=False)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    service_area_code2: Mapped[str | None] = mapped_column(String(16))
    source_snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class RestAreaServingService(TimestampMixin, Base):
    __tablename__ = "rest_area_serving_service"
    __table_args__ = (
        UniqueConstraint(
            "svar_cd",
            "provider_service_code",
            "source_snapshot_date",
            name="uq_rass_svar_service_snapshot",
        ),
        Index("ix_rass_service_name", "provider_service_name"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    svar_cd: Mapped[str] = mapped_column(
        String(16),
        ForeignKey(
            "rest_area_serving_master.svar_cd",
            name="fk_rass_svar_cd",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    provider_service_area_code: Mapped[str | None] = mapped_column(String(24))
    route_code: Mapped[str | None] = mapped_column(String(16))
    route_name: Mapped[str | None] = mapped_column(String(120))
    direction: Mapped[str | None] = mapped_column(String(80))
    provider_service_code: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_service_name: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(80))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
