"""Admin POI 관리 — 목록/상세/로컬 link status."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NamedTuple

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import ColumnElement

from app.models.audit import AdminAuditLog
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.user import User
from app.services.kasi import build_initial_poi_rise_set
from app.services.poi import (
    SortOrderConflictError,
    _fill_trip_primary_region_from_snapshot,
    ensure_trip_day,
)


class AdminPoiError(Exception):
    code: str = "INTERNAL_ERROR"


class AdminPoiNotFoundError(AdminPoiError):
    code = "RESOURCE_NOT_FOUND"


class AdminPoiTripNotFoundError(AdminPoiError):
    code = "RESOURCE_NOT_FOUND"


class AdminPoiRow(NamedTuple):
    poi: TripDayPoi
    trip_title: str
    owner_user_id: uuid.UUID
    owner_email: str
    added_by_email: str | None


async def list_admin_pois(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 50,
    trip_id: uuid.UUID | None = None,
    has_broken_link: bool | None = None,
    q: str | None = None,
) -> tuple[list[AdminPoiRow], int]:
    added_by = aliased(User)
    filters = _poi_filters(trip_id=trip_id, has_broken_link=has_broken_link, q=q)
    base = (
        select(
            TripDayPoi,
            Trip.title,
            Trip.owner_user_id,
            User.email,
            added_by.email,
        )
        .join(Trip, Trip.trip_id == TripDayPoi.trip_id)
        .join(User, User.user_id == Trip.owner_user_id)
        .outerjoin(added_by, added_by.user_id == TripDayPoi.added_by_user_id)
        .where(*filters)
    )
    count_base = (
        select(func.count(TripDayPoi.attachment_id))
        .join(Trip, Trip.trip_id == TripDayPoi.trip_id)
        .join(User, User.user_id == Trip.owner_user_id)
        .where(*filters)
    )
    total = await db.scalar(count_base) or 0
    offset = max(0, (page - 1) * limit)
    result = await db.execute(
        base.order_by(TripDayPoi.updated_at.desc(), TripDayPoi.attachment_id)
        .offset(offset)
        .limit(limit)
    )
    return [
        AdminPoiRow(
            poi=poi,
            trip_title=trip_title,
            owner_user_id=owner_user_id,
            owner_email=owner_email,
            added_by_email=added_by_email,
        )
        for poi, trip_title, owner_user_id, owner_email, added_by_email in result
    ], total


async def get_admin_poi(db: AsyncSession, *, poi_id: uuid.UUID) -> AdminPoiRow:
    added_by = aliased(User)
    result = await db.execute(
        select(
            TripDayPoi,
            Trip.title,
            Trip.owner_user_id,
            User.email,
            added_by.email,
        )
        .join(Trip, Trip.trip_id == TripDayPoi.trip_id)
        .join(User, User.user_id == Trip.owner_user_id)
        .outerjoin(added_by, added_by.user_id == TripDayPoi.added_by_user_id)
        .where(
            TripDayPoi.attachment_id == poi_id,
            TripDayPoi.deleted_at.is_(None),
            Trip.deleted_at.is_(None),
        )
    )
    row = result.first()
    if row is None:
        raise AdminPoiNotFoundError("POI를 찾을 수 없습니다.")
    poi, trip_title, owner_user_id, owner_email, added_by_email = row
    return AdminPoiRow(
        poi=poi,
        trip_title=trip_title,
        owner_user_id=owner_user_id,
        owner_email=owner_email,
        added_by_email=added_by_email,
    )


async def create_admin_poi(
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
) -> TripDayPoi:
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)))
    if trip is None:
        raise AdminPoiTripNotFoundError("여행을 찾을 수 없습니다.")

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
    except IntegrityError as exc:
        raise SortOrderConflictError("같은 위치(sort_order)에 이미 POI가 있습니다.") from exc
    db.add(
        build_initial_poi_rise_set(
            poi=poi,
            locdate=day.date,
            feature_snapshot=feature_snapshot,
        )
    )
    return poi


async def update_admin_poi_link_status(
    db: AsyncSession, *, poi_id: uuid.UUID, broken: bool
) -> tuple[TripDayPoi, datetime | None]:
    row = await get_admin_poi(db, poi_id=poi_id)
    poi = row.poi
    before = poi.feature_link_broken_at
    if broken and before is None:
        poi.feature_link_broken_at = datetime.now(UTC)
    elif not broken:
        poi.feature_link_broken_at = None
    if poi.feature_link_broken_at != before:
        poi.version += 1
    return poi, before


async def list_recent_poi_audit(
    db: AsyncSession, *, poi_id: uuid.UUID, limit: int = 10
) -> list[AdminAuditLog]:
    result = await db.execute(
        select(AdminAuditLog)
        .where(
            AdminAuditLog.resource_type == "poi",
            AdminAuditLog.resource_id == str(poi_id),
        )
        .order_by(AdminAuditLog.log_id.desc())
        .limit(limit)
    )
    return list(result.scalars())


def _poi_filters(
    *,
    trip_id: uuid.UUID | None,
    has_broken_link: bool | None,
    q: str | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [
        TripDayPoi.deleted_at.is_(None),
        Trip.deleted_at.is_(None),
    ]
    if trip_id:
        filters.append(TripDayPoi.trip_id == trip_id)
    if has_broken_link is True:
        filters.append(TripDayPoi.feature_link_broken_at.is_not(None))
    elif has_broken_link is False:
        filters.append(TripDayPoi.feature_link_broken_at.is_(None))

    q_value = q.strip() if q else ""
    if q_value:
        pattern = f"%{q_value}%"
        search_filters: list[ColumnElement[bool]] = [
            TripDayPoi.feature_id.ilike(pattern),
            cast(TripDayPoi.feature_snapshot, Text).ilike(pattern),
            Trip.title.ilike(pattern),
            User.email.ilike(pattern),
        ]
        try:
            parsed = uuid.UUID(q_value)
            search_filters.extend(
                [
                    TripDayPoi.attachment_id == parsed,
                    TripDayPoi.trip_id == parsed,
                    Trip.owner_user_id == parsed,
                ]
            )
        except ValueError:
            pass
        filters.append(or_(*search_filters))
    return filters


def extract_feature_label(snapshot: dict[str, object]) -> str | None:
    for key in ("name", "title", "title_snapshot", "place_name"):
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _mapping(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _first_number(candidate: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _number(candidate.get(key))
        if value is not None:
            return value
    return None


def extract_feature_coord(snapshot: dict[str, object]) -> tuple[float | None, float | None]:
    """Snapshot field names vary by source; return `(lon, lat)` when enough data exists."""

    candidate_maps = [
        snapshot,
        _mapping(snapshot.get("coord")),
        _mapping(snapshot.get("coordinate")),
        _mapping(snapshot.get("location")),
        _mapping(snapshot.get("geometry")),
    ]
    for candidate in candidate_maps:
        if not candidate:
            continue
        lon = _first_number(candidate, ("lon", "lng", "longitude", "x"))
        lat = _first_number(candidate, ("lat", "latitude", "y"))
        if lon is not None and lat is not None:
            return lon, lat
    return None, None


def extract_feature_address_label(snapshot: dict[str, object]) -> str | None:
    for key in ("address_label", "address", "road_address", "jibun_address", "addr"):
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for nested_key in ("label", "full", "road", "jibun", "name"):
                nested = value.get(nested_key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return None
