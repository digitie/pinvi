"""POI 도메인 — CRUD + reorder (LexoRank)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
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
        # ADR-055: date는 override-only. auto-create는 NULL로 두고 effective_date를 파생한다.
        day = TripDay(trip_id=trip_id, day_index=day_index)
        db.add(day)
        await db.flush()
    return day


async def trip_day_effective_locdate(
    db: AsyncSession, *, trip_id: uuid.UUID, day_index: int, override: date | None
) -> date | None:
    """POI rise/set seed용 effective 날짜(ADR-055).

    day.date override가 있으면 그것, 없으면 trip.start_date + (day_index-1)로 파생한다.
    trip.start_date가 없으면 None(rise/set은 pending_date로 남는다).
    """
    if override is not None:
        return override
    start_date = await db.scalar(select(Trip.start_date).where(Trip.trip_id == trip_id))
    if start_date is None:
        return None
    return start_date + timedelta(days=day_index - 1)


async def create_poi(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_index: int,
    sort_order: str,
    feature_id: str | None,
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
    source: str | None = None,
    external_ref: dict[str, Any] | None = None,
) -> TripDayPoi:
    await db.scalar(select(Trip).where(Trip.trip_id == trip_id).with_for_update())
    day = await ensure_trip_day(db, trip_id=trip_id, day_index=day_index)
    # ADR-055: day.date는 override-only. rise/set seed는 effective_date(override 또는 파생)로.
    locdate = await trip_day_effective_locdate(
        db, trip_id=trip_id, day_index=day_index, override=day.date
    )
    poi = TripDayPoi(
        trip_id=trip_id,
        day_index=day_index,
        sort_order=sort_order,
        feature_id=feature_id,
        feature_snapshot=feature_snapshot,
        custom_marker_color=custom_marker_color,
        custom_marker_icon=custom_marker_icon,
        source=source
        or (
            "feature" if feature_id else external_ref.get("provider") if external_ref else "manual"
        ),
        external_ref=external_ref,
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
                locdate=locdate,
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
    await db.scalar(select(Trip).where(Trip.trip_id == poi.trip_id).with_for_update())
    await db.refresh(poi, with_for_update=True)
    if poi.deleted_at is not None:
        raise PoiNotFoundError("POI를 찾을 수 없습니다.")
    if poi.version != expected_version:
        raise PoiVersionConflictError("동시 편집 충돌 — 다시 불러와 주세요.")
    destination = patch.get("day_index")
    moved = destination is not None and destination != poi.day_index
    if moved:
        day = await db.scalar(
            select(TripDay).where(TripDay.trip_id == poi.trip_id, TripDay.day_index == destination)
        )
        if day is None:
            raise PoiNotFoundError("이동할 여행 일자를 찾을 수 없습니다.")
        if patch.get("sort_order") is None:
            last = await db.scalar(
                select(TripDayPoi.sort_order)
                .where(
                    TripDayPoi.trip_id == poi.trip_id,
                    TripDayPoi.day_index == destination,
                    TripDayPoi.deleted_at.is_(None),
                )
                .order_by(TripDayPoi.sort_order.desc())
                .limit(1)
            )
            patch = {**patch, "sort_order": last + "0" if last is not None else "a0"}
            if len(patch["sort_order"]) > 80:
                raise SortOrderConflictError("이동할 일자의 정렬 위치를 다시 정리해 주세요.")
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
    try:
        if moved:
            assert day is not None
            old_rise_set = await db.get(TripPoiRiseSet, poi.attachment_id)
            if old_rise_set is not None:
                await db.delete(old_rise_set)
                await db.flush()
            locdate = await trip_day_effective_locdate(
                db, trip_id=poi.trip_id, day_index=poi.day_index, override=day.date
            )
            db.add(
                build_initial_poi_rise_set(
                    poi=poi, locdate=locdate, feature_snapshot=poi.feature_snapshot
                )
            )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise SortOrderConflictError(
            "정렬 위치가 충돌했습니다. 다시 불러온 후 시도해 주세요."
        ) from exc
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


async def get_poi_rise_sets(
    db: AsyncSession,
    *,
    poi_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, TripPoiRiseSet]:
    unique_poi_ids = list(dict.fromkeys(poi_ids))
    if not unique_poi_ids:
        return {}
    result = await db.execute(
        select(TripPoiRiseSet).where(TripPoiRiseSet.poi_id.in_(unique_poi_ids))
    )
    return {row.poi_id: row for row in result.scalars()}


def poi_rise_set_to_dict(rise_set: TripPoiRiseSet | None) -> dict[str, Any] | None:
    if rise_set is None:
        return None
    return {
        "status": rise_set.status,
        "locdate": rise_set.locdate,
        "sunrise_at": rise_set.sunrise_at,
        "sunset_at": rise_set.sunset_at,
        "moonrise_at": rise_set.moonrise_at,
        "moonset_at": rise_set.moonset_at,
        "fetched_at": rise_set.fetched_at,
        "updated_at": rise_set.updated_at,
    }


async def reorder_pois(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    moves: list[tuple[uuid.UUID, str]],
    day_index: int,
) -> list[TripDayPoi]:
    await db.scalar(select(Trip).where(Trip.trip_id == trip_id).with_for_update())
    poi_ids = [pid for pid, _ in moves]
    if len(set(poi_ids)) != len(poi_ids):
        raise SortOrderConflictError("같은 POI를 두 번 정렬할 수 없습니다.")
    result = await db.execute(
        select(TripDayPoi)
        .where(
            TripDayPoi.attachment_id.in_(poi_ids),
            TripDayPoi.trip_id == trip_id,
            TripDayPoi.deleted_at.is_(None),
        )
        .with_for_update()
    )
    pois = {p.attachment_id: p for p in result.scalars()}
    if len(pois) != len(poi_ids):
        raise PoiNotFoundError("정렬할 POI를 찾을 수 없습니다.")
    if any(p.day_index != day_index for p in pois.values()):
        raise SortOrderConflictError("장소의 일자가 변경됐습니다. 다시 불러온 후 정렬해 주세요.")
    final_positions = [(pois[pid].day_index, rank) for pid, rank in moves]
    if len(set(final_positions)) != len(final_positions):
        raise SortOrderConflictError("같은 일자의 정렬 위치가 중복됩니다.")
    updated = [pois[pid] for pid in poi_ids]
    try:
        # 하나의 트랜잭션에서 임시 고유 위치로 옮긴 뒤 최종 순서를 적용한다.
        nonce = uuid.uuid4().hex
        for index, poi in enumerate(updated):
            poi.sort_order = f"reorder_{nonce}_{index}"
        await db.flush()
        for poi_id, new_sort in moves:
            pois[poi_id].sort_order = new_sort
            pois[poi_id].version += 1
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise SortOrderConflictError(
            "정렬 위치가 충돌했습니다. 다시 불러온 후 시도해 주세요."
        ) from exc

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
