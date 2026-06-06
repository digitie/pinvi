"""Admin 여행 관리 — 목록/상세/상태 변경."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.models.audit import AdminAuditLog
from app.models.companion import TripCompanion
from app.models.poi import TripDayPoi
from app.models.share_link import TripShareLink
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User


class AdminTripError(Exception):
    code: str = "INTERNAL_ERROR"


class AdminTripNotFoundError(AdminTripError):
    code = "RESOURCE_NOT_FOUND"


async def list_admin_trips(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 50,
    status_filter: str | None = None,
    visibility_filter: str | None = None,
    owner_user_id: uuid.UUID | None = None,
    q: str | None = None,
) -> tuple[list[Trip], int]:
    filters = _trip_filters(
        status_filter=status_filter,
        visibility_filter=visibility_filter,
        owner_user_id=owner_user_id,
        q=q,
    )
    base = select(Trip).join(User, User.user_id == Trip.owner_user_id).where(*filters)
    count_base = (
        select(func.count(Trip.trip_id))
        .join(User, User.user_id == Trip.owner_user_id)
        .where(*filters)
    )
    total = await db.scalar(count_base) or 0
    offset = max(0, (page - 1) * limit)
    result = await db.execute(base.order_by(Trip.updated_at.desc()).offset(offset).limit(limit))
    return list(result.scalars()), total


async def get_admin_trip(db: AsyncSession, *, trip_id: uuid.UUID) -> Trip:
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)))
    if trip is None:
        raise AdminTripNotFoundError("여행을 찾을 수 없습니다.")
    return trip


async def update_admin_trip_status(
    db: AsyncSession, *, trip_id: uuid.UUID, status: str
) -> tuple[Trip, str]:
    trip = await get_admin_trip(db, trip_id=trip_id)
    before_status = trip.status
    trip.status = status
    trip.version += 1
    await db.commit()
    await db.refresh(trip)
    return trip, before_status


async def load_owner_emails(
    db: AsyncSession, *, owner_user_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not owner_user_ids:
        return {}
    result = await db.execute(
        select(User.user_id, User.email).where(User.user_id.in_(owner_user_ids))
    )
    return {user_id: email for user_id, email in result}


async def load_trip_counts(
    db: AsyncSession, *, trip_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    counts = {
        trip_id: {
            "day_count": 0,
            "poi_count": 0,
            "companion_count": 0,
            "share_link_count": 0,
        }
        for trip_id in trip_ids
    }
    if not trip_ids:
        return counts

    for key, column, extra_filters in (
        ("day_count", TripDay.trip_id, []),
        ("poi_count", TripDayPoi.trip_id, [TripDayPoi.deleted_at.is_(None)]),
        ("companion_count", TripCompanion.trip_id, []),
        ("share_link_count", TripShareLink.trip_id, []),
    ):
        result = await db.execute(
            select(column, func.count())
            .where(column.in_(trip_ids), *extra_filters)
            .group_by(column)
        )
        for trip_id, count in result:
            counts[trip_id][key] = int(count)
    return counts


async def list_trip_companions(db: AsyncSession, *, trip_id: uuid.UUID) -> list[TripCompanion]:
    result = await db.execute(
        select(TripCompanion)
        .where(TripCompanion.trip_id == trip_id)
        .order_by(TripCompanion.invited_at.desc())
    )
    return list(result.scalars())


async def list_trip_share_links(db: AsyncSession, *, trip_id: uuid.UUID) -> list[TripShareLink]:
    result = await db.execute(
        select(TripShareLink)
        .where(TripShareLink.trip_id == trip_id)
        .order_by(TripShareLink.created_at.desc())
    )
    return list(result.scalars())


async def list_recent_trip_audit(
    db: AsyncSession, *, trip_id: uuid.UUID, limit: int = 10
) -> list[AdminAuditLog]:
    result = await db.execute(
        select(AdminAuditLog)
        .where(
            AdminAuditLog.resource_type == "trip",
            AdminAuditLog.resource_id == str(trip_id),
        )
        .order_by(AdminAuditLog.log_id.desc())
        .limit(limit)
    )
    return list(result.scalars())


def _trip_filters(
    *,
    status_filter: str | None,
    visibility_filter: str | None,
    owner_user_id: uuid.UUID | None,
    q: str | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [Trip.deleted_at.is_(None)]
    if status_filter:
        filters.append(Trip.status == status_filter)
    if visibility_filter:
        filters.append(Trip.visibility == visibility_filter)
    if owner_user_id:
        filters.append(Trip.owner_user_id == owner_user_id)

    q_value = q.strip() if q else ""
    if q_value:
        pattern = f"%{q_value}%"
        search_filters: list[ColumnElement[bool]] = [
            Trip.title.ilike(pattern),
            Trip.region_hint.ilike(pattern),
            User.email.ilike(pattern),
        ]
        try:
            parsed = uuid.UUID(q_value)
            search_filters.extend([Trip.trip_id == parsed, Trip.owner_user_id == parsed])
        except ValueError:
            pass
        filters.append(or_(*search_filters))
    return filters
