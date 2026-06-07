"""POI 도메인 — CRUD + reorder (LexoRank)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kasi import TripPoiRiseSet
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.services.kasi import build_initial_poi_rise_set

_REGION_CODE_RE = re.compile(r"^[0-9]{2,10}$")
_REGION_CODE_KEYS = (
    "legal_dong_code",
    "bjd_code",
    "bjd_cd",
    "region_code",
    "sigungu_code",
    "sig_cd",
    "sido_code",
)
_REGION_CONTAINER_KEYS = ("region", "address", "location")


class PoiError(Exception):
    code: str = "INTERNAL_ERROR"


class PoiNotFoundError(PoiError):
    code = "RESOURCE_NOT_FOUND"


class PoiVersionConflictError(PoiError):
    code = "VERSION_CONFLICT"


class SortOrderConflictError(PoiError):
    code = "SORT_ORDER_CONFLICT"


async def ensure_trip_day(db: AsyncSession, *, trip_id: uuid.UUID, day_index: int) -> TripDay:
    day = await db.scalar(
        select(TripDay).where(TripDay.trip_id == trip_id, TripDay.day_index == day_index)
    )
    if day is None:
        trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id))
        date = None
        if trip is not None and trip.start_date is not None:
            date = trip.start_date + timedelta(days=day_index - 1)
        day = TripDay(trip_id=trip_id, day_index=day_index, date=date)
        db.add(day)
        await db.flush()
    return day


async def create_poi(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_index: int,
    sort_order: str,
    feature_id: str,
    feature_snapshot: dict[str, Any],
    added_by_user_id: uuid.UUID,
    custom_marker_color: str | None = None,
    custom_marker_icon: str | None = None,
    planned_arrival_at: datetime | None = None,
    planned_departure_at: datetime | None = None,
    user_note: str | None = None,
    budget_amount: Decimal | None = None,
    actual_amount: Decimal | None = None,
    currency: str = "KRW",
    user_url: str | None = None,
) -> TripDayPoi:
    day = await ensure_trip_day(db, trip_id=trip_id, day_index=day_index)
    poi = TripDayPoi(
        trip_id=trip_id,
        day_index=day_index,
        sort_order=sort_order,
        feature_id=feature_id,
        feature_snapshot=feature_snapshot,
        custom_marker_color=custom_marker_color,
        custom_marker_icon=custom_marker_icon,
        planned_arrival_at=planned_arrival_at,
        planned_departure_at=planned_departure_at,
        user_note=user_note,
        budget_amount=budget_amount,
        actual_amount=actual_amount,
        currency=currency,
        user_url=user_url,
        added_by_user_id=added_by_user_id,
    )
    db.add(poi)
    await _fill_trip_primary_region_from_snapshot(
        db,
        trip_id=trip_id,
        feature_snapshot=feature_snapshot,
    )
    try:
        await db.flush()
        db.add(
            build_initial_poi_rise_set(
                poi=poi,
                locdate=day.date,
                feature_snapshot=feature_snapshot,
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # (trip_id, day_index, sort_order COLLATE "C") UNIQUE 위반
        raise SortOrderConflictError("같은 위치(sort_order)에 이미 POI가 있습니다.") from exc
    await db.refresh(poi)
    return poi


async def get_poi(db: AsyncSession, *, attachment_id: uuid.UUID, trip_id: uuid.UUID) -> TripDayPoi:
    poi = await db.scalar(
        select(TripDayPoi).where(
            TripDayPoi.attachment_id == attachment_id,
            TripDayPoi.trip_id == trip_id,
            TripDayPoi.deleted_at.is_(None),
        )
    )
    if poi is None:
        raise PoiNotFoundError("POI를 찾을 수 없습니다.")
    return poi


async def update_poi(
    db: AsyncSession,
    *,
    poi: TripDayPoi,
    expected_version: int,
    patch: dict[str, Any],
) -> TripDayPoi:
    if poi.version != expected_version:
        raise PoiVersionConflictError("동시 편집 충돌 — 다시 불러와 주세요.")
    for key, value in patch.items():
        if value is None and key not in {
            "custom_marker_color",
            "custom_marker_icon",
            "user_note",
            "planned_arrival_at",
            "planned_departure_at",
            "budget_amount",
            "actual_amount",
            "user_url",
            "feature_snapshot",
        }:
            continue
        setattr(poi, key, value)
    poi.version += 1
    await db.commit()
    await db.refresh(poi)
    return poi


async def soft_delete_poi(db: AsyncSession, *, poi: TripDayPoi) -> None:
    poi.deleted_at = datetime.now(UTC)
    await db.commit()


async def get_poi_rise_set(
    db: AsyncSession,
    *,
    poi_id: uuid.UUID,
) -> TripPoiRiseSet | None:
    return await db.get(TripPoiRiseSet, poi_id)


async def reorder_pois(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    moves: list[tuple[uuid.UUID, str]],
) -> list[TripDayPoi]:
    poi_ids = [pid for pid, _ in moves]
    result = await db.execute(
        select(TripDayPoi).where(
            TripDayPoi.attachment_id.in_(poi_ids),
            TripDayPoi.trip_id == trip_id,
            TripDayPoi.deleted_at.is_(None),
        )
    )
    pois = {p.attachment_id: p for p in result.scalars()}

    updated: list[TripDayPoi] = []
    for poi_id, new_sort in moves:
        poi = pois.get(poi_id)
        if poi is None:
            raise PoiNotFoundError(f"POI {poi_id} not found")
        poi.sort_order = new_sort
        poi.version += 1
        updated.append(poi)

    try:
        await db.commit()
    except Exception as exc:  # PG UNIQUE 위반 등
        await db.rollback()
        raise SortOrderConflictError(str(exc)) from exc

    for poi in updated:
        await db.refresh(poi)
    return updated


async def _fill_trip_primary_region_from_snapshot(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    feature_snapshot: Mapping[str, Any],
) -> None:
    region_code = _extract_region_code(feature_snapshot)
    if region_code is None:
        return
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id))
    if trip is None or trip.primary_region_code is not None:
        return
    trip.primary_region_code = region_code
    trip.primary_region_source = "poi_snapshot"
    trip.version += 1


def _extract_region_code(feature_snapshot: Mapping[str, Any]) -> str | None:
    direct = _extract_region_code_from_mapping(feature_snapshot)
    if direct is not None:
        return direct
    for key in _REGION_CONTAINER_KEYS:
        value = feature_snapshot.get(key)
        if isinstance(value, Mapping):
            nested = _extract_region_code_from_mapping(value)
            if nested is not None:
                return nested
    return None


def _extract_region_code_from_mapping(value: Mapping[str, Any]) -> str | None:
    for key in _REGION_CODE_KEYS:
        candidate = value.get(key)
        if isinstance(candidate, str) and _REGION_CODE_RE.fullmatch(candidate):
            return candidate
    return None
