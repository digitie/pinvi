"""Trip 도메인 — CRUD + 동반자 + 공유 토큰. `docs/api/trips.md`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_opaque_token
from app.models.companion import TripCompanion
from app.models.share_link import TripShareLink
from app.models.trip import Trip
from app.services.hash_chain import sha256_hex


class TripError(Exception):
    code: str = "INTERNAL_ERROR"


class TripNotFoundError(TripError):
    code = "RESOURCE_NOT_FOUND"


class TripVersionConflictError(TripError):
    code = "VERSION_CONFLICT"


class TripPermissionError(TripError):
    code = "PERMISSION_DENIED"


async def create_trip(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    title: str,
    description: str | None,
    region_hint: str | None,
    start_date,
    end_date,
    visibility: str,
) -> Trip:
    trip = Trip(
        owner_user_id=owner_user_id,
        title=title,
        description=description,
        region_hint=region_hint,
        start_date=start_date,
        end_date=end_date,
        visibility=visibility,
    )
    db.add(trip)
    await db.commit()
    await db.refresh(trip)
    return trip


async def get_trip_for_user(
    db: AsyncSession, *, trip_id: uuid.UUID, user_id: uuid.UUID
) -> Trip:
    trip = await db.scalar(
        select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None))
    )
    if trip is None:
        raise TripNotFoundError("여행을 찾을 수 없습니다.")
    if trip.owner_user_id != user_id and not await _is_companion(db, trip_id, user_id):
        raise TripPermissionError("이 여행에 대한 권한이 없습니다.")
    return trip


async def list_trips_for_owner(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 20
) -> list[Trip]:
    result = await db.execute(
        select(Trip)
        .where(Trip.owner_user_id == user_id, Trip.deleted_at.is_(None))
        .order_by(Trip.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def update_trip(
    db: AsyncSession,
    *,
    trip: Trip,
    expected_version: int,
    patch: dict,
) -> Trip:
    if trip.version != expected_version:
        raise TripVersionConflictError("동시 편집 충돌 — 다시 불러와 주세요.")
    for key, value in patch.items():
        if value is not None or key in {"description", "region_hint", "cover_attachment_id"}:
            setattr(trip, key, value)
    trip.version += 1
    await db.commit()
    await db.refresh(trip)
    return trip


async def invite_companion(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    email: str | None,
    user_id: uuid.UUID | None,
    display_name: str | None,
    role: str,
) -> TripCompanion:
    companion = TripCompanion(
        trip_id=trip_id,
        invited_email=email,
        user_id=user_id,
        invited_nickname=display_name,
        role=role,
        invited_at=datetime.now(UTC),
        joined_at=datetime.now(UTC) if user_id else None,
    )
    db.add(companion)
    await db.commit()
    await db.refresh(companion)
    return companion


async def issue_share_link(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    visibility: str,
    expires_at: datetime | None,
) -> tuple[TripShareLink, str]:
    raw_token = generate_opaque_token(32)
    share = TripShareLink(
        trip_id=trip_id,
        token_hash=sha256_hex(raw_token),
        created_by_user_id=created_by_user_id,
        visibility=visibility,
        expires_at=expires_at,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share, raw_token


async def revoke_share_link(
    db: AsyncSession, *, share_id: uuid.UUID, trip_id: uuid.UUID
) -> None:
    share = await db.scalar(
        select(TripShareLink).where(
            TripShareLink.share_id == share_id, TripShareLink.trip_id == trip_id
        )
    )
    if share is None:
        raise TripNotFoundError("공유 토큰을 찾을 수 없습니다.")
    if share.revoked_at is None:
        share.revoked_at = datetime.now(UTC)
        await db.commit()


async def _is_companion(
    db: AsyncSession, trip_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    row = await db.scalar(
        select(TripCompanion.companion_id).where(
            TripCompanion.trip_id == trip_id,
            TripCompanion.user_id == user_id,
        )
    )
    return row is not None
