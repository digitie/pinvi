from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.etl.opinet.loader import find_opinet_region_code_for_legal_dong
from app.models.fuel import FuelServingAvgPrice, FuelServingLowestStation


@dataclass(frozen=True)
class DailyFuelAverage:
    fuel_type: str
    provider_fuel_code: str
    provider_fuel_name: str
    price: Decimal
    price_unit: str
    trade_date: str | None


@dataclass(frozen=True)
class NearbyFuelSummary:
    legal_dong_code: str
    provider_region_code: str | None
    fuel_type: str
    station_count: int
    lowest_price: Decimal | None
    nearby_average_price: Decimal | None
    lowest_candidate_average_price: Decimal | None
    candidate_average_price: Decimal | None
    national_average_price: Decimal | None
    price_unit: str


def get_latest_daily_fuel_averages(session: Session) -> list[DailyFuelAverage]:
    latest_timestamp = session.scalar(select(func.max(FuelServingAvgPrice.timestamp)))
    if latest_timestamp is None:
        return []
    rows = session.scalars(
        select(FuelServingAvgPrice)
        .where(FuelServingAvgPrice.region_key == "national")
        .where(FuelServingAvgPrice.timestamp == latest_timestamp)
        .order_by(FuelServingAvgPrice.fuel_type)
    ).all()
    return [
        DailyFuelAverage(
            fuel_type=row.fuel_type,
            provider_fuel_code=row.provider_fuel_code,
            provider_fuel_name=row.provider_fuel_name,
            price=row.price,
            price_unit=row.price_unit,
            trade_date=row.trade_date,
        )
        for row in rows
    ]


def get_nearby_fuel_summary(
    session: Session,
    *,
    legal_dong_code: str,
    fuel_type: str = "gasoline",
) -> NearbyFuelSummary:
    provider_region_code = find_opinet_region_code_for_legal_dong(session, legal_dong_code)
    national_average_price = session.scalar(
        select(FuelServingAvgPrice.price)
        .where(FuelServingAvgPrice.region_key == "national")
        .where(FuelServingAvgPrice.fuel_type == fuel_type)
        .order_by(FuelServingAvgPrice.timestamp.desc())
        .limit(1)
    )
    if provider_region_code is None:
        return NearbyFuelSummary(
            legal_dong_code=legal_dong_code,
            provider_region_code=None,
            fuel_type=fuel_type,
            station_count=0,
            lowest_price=None,
            nearby_average_price=None,
            lowest_candidate_average_price=None,
            candidate_average_price=None,
            national_average_price=national_average_price,
            price_unit="KRW_PER_LITER",
        )

    latest_timestamp = session.scalar(
        select(func.max(FuelServingLowestStation.timestamp))
        .where(FuelServingLowestStation.provider_region_code == provider_region_code)
        .where(FuelServingLowestStation.fuel_type == fuel_type)
    )
    if latest_timestamp is None:
        return NearbyFuelSummary(
            legal_dong_code=legal_dong_code,
            provider_region_code=provider_region_code,
            fuel_type=fuel_type,
            station_count=0,
            lowest_price=None,
            nearby_average_price=None,
            lowest_candidate_average_price=None,
            candidate_average_price=None,
            national_average_price=national_average_price,
            price_unit="KRW_PER_LITER",
        )

    station_count = session.scalar(
        select(func.count())
        .select_from(FuelServingLowestStation)
        .where(FuelServingLowestStation.provider_region_code == provider_region_code)
        .where(FuelServingLowestStation.fuel_type == fuel_type)
        .where(FuelServingLowestStation.timestamp == latest_timestamp)
    )
    lowest_price = session.scalar(
        select(func.min(FuelServingLowestStation.price))
        .where(FuelServingLowestStation.provider_region_code == provider_region_code)
        .where(FuelServingLowestStation.fuel_type == fuel_type)
        .where(FuelServingLowestStation.timestamp == latest_timestamp)
    )
    candidate_average_price = session.scalar(
        select(func.avg(FuelServingLowestStation.price))
        .where(FuelServingLowestStation.provider_region_code == provider_region_code)
        .where(FuelServingLowestStation.fuel_type == fuel_type)
        .where(FuelServingLowestStation.timestamp == latest_timestamp)
    )

    return NearbyFuelSummary(
        legal_dong_code=legal_dong_code,
        provider_region_code=provider_region_code,
        fuel_type=fuel_type,
        station_count=int(station_count or 0),
        lowest_price=lowest_price,
        nearby_average_price=candidate_average_price,
        lowest_candidate_average_price=candidate_average_price,
        candidate_average_price=candidate_average_price,
        national_average_price=national_average_price,
        price_unit="KRW_PER_LITER",
    )
