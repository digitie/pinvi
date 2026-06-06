"""Admin POI 관리 — 목록/상세/로컬 link status."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import ColumnElement

from app.models.audit import AdminAuditLog
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.user import User


class AdminPoiError(Exception):
    code: str = "INTERNAL_ERROR"


class AdminPoiNotFoundError(AdminPoiError):
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
    await db.commit()
    await db.refresh(poi)
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
