"""POI 도메인 — CRUD + reorder (LexoRank)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.poi import TripDayPoi
from app.models.trip_day import TripDay


class PoiError(Exception):
    code: str = "INTERNAL_ERROR"


class PoiNotFoundError(PoiError):
    code = "RESOURCE_NOT_FOUND"


class PoiVersionConflictError(PoiError):
    code = "VERSION_CONFLICT"


class SortOrderConflictError(PoiError):
    code = "SORT_ORDER_CONFLICT"


async def ensure_trip_day(
    db: AsyncSession, *, trip_id: uuid.UUID, day_index: int
) -> TripDay:
    day = await db.scalar(
        select(TripDay).where(TripDay.trip_id == trip_id, TripDay.day_index == day_index)
    )
    if day is None:
        day = TripDay(trip_id=trip_id, day_index=day_index)
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
    user_note: str | None = None,
) -> TripDayPoi:
    await ensure_trip_day(db, trip_id=trip_id, day_index=day_index)
    poi = TripDayPoi(
        trip_id=trip_id,
        day_index=day_index,
        sort_order=sort_order,
        feature_id=feature_id,
        feature_snapshot=feature_snapshot,
        custom_marker_color=custom_marker_color,
        custom_marker_icon=custom_marker_icon,
        user_note=user_note,
        added_by_user_id=added_by_user_id,
    )
    db.add(poi)
    await db.commit()
    await db.refresh(poi)
    return poi


async def get_poi(
    db: AsyncSession, *, attachment_id: uuid.UUID, trip_id: uuid.UUID
) -> TripDayPoi:
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
    poi.deleted_at = datetime.now(timezone.utc)
    await db.commit()


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
    except Exception as exc:  # noqa: BLE001 — PG UNIQUE 위반 등
        await db.rollback()
        raise SortOrderConflictError(str(exc)) from exc

    for poi in updated:
        await db.refresh(poi)
    return updated
