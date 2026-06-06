"""Trip 도메인 — CRUD + 동반자 + 공유 토큰. `docs/api/trips.md`."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_opaque_token
from app.models.comment import TripComment
from app.models.companion import TripCompanion
from app.models.share_link import TripShareLink
from app.models.trip import Trip
from app.models.user import User
from app.services.email_service import enqueue_trip_invite_email
from app.services.hash_chain import sha256_hex


class TripError(Exception):
    code: str = "INTERNAL_ERROR"


class TripNotFoundError(TripError):
    code = "RESOURCE_NOT_FOUND"


class TripVersionConflictError(TripError):
    code = "VERSION_CONFLICT"


class TripPermissionError(TripError):
    code = "PERMISSION_DENIED"


class TripCompanionConflictError(TripError):
    code = "COMPANION_ALREADY_EXISTS"


class TripCommentNotFoundError(TripError):
    code = "RESOURCE_NOT_FOUND"


async def create_trip(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    title: str,
    description: str | None,
    region_hint: str | None,
    start_date: date | None,
    end_date: date | None,
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


async def get_trip_owned_by_user(
    db: AsyncSession, *, trip_id: uuid.UUID, user_id: uuid.UUID
) -> Trip:
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)))
    if trip is None:
        raise TripNotFoundError("여행을 찾을 수 없습니다.")
    if trip.owner_user_id != user_id:
        raise TripPermissionError("여행 소유자만 수행할 수 있습니다.")
    return trip


async def get_trip_for_user(db: AsyncSession, *, trip_id: uuid.UUID, user_id: uuid.UUID) -> Trip:
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)))
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
    patch: dict[str, Any],
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
    trip: Trip,
    invited_by_user_id: uuid.UUID,
    email: str,
    display_name: str | None,
    role: str,
) -> TripCompanion:
    normalized_email = email.strip().lower()
    matched_user = await db.scalar(
        select(User).where(
            func.lower(User.email) == normalized_email,
            User.deleted_at.is_(None),
        )
    )
    if matched_user is not None and matched_user.user_id == trip.owner_user_id:
        raise TripCompanionConflictError("여행 소유자는 동반자로 초대할 수 없습니다.")

    duplicate_filters = [func.lower(TripCompanion.invited_email) == normalized_email]
    if matched_user is not None:
        duplicate_filters.append(TripCompanion.user_id == matched_user.user_id)
    existing = await db.scalar(
        select(TripCompanion.companion_id).where(
            TripCompanion.trip_id == trip.trip_id,
            or_(*duplicate_filters),
        )
    )
    if existing is not None:
        raise TripCompanionConflictError("이미 초대된 동반자입니다.")

    companion = TripCompanion(
        trip_id=trip.trip_id,
        invited_email=normalized_email,
        user_id=None if matched_user is None else matched_user.user_id,
        invited_nickname=display_name,
        role=role,
        invited_at=datetime.now(UTC),
        joined_at=datetime.now(UTC) if matched_user is not None else None,
    )
    db.add(companion)
    await db.flush()
    await enqueue_trip_invite_email(
        db,
        to_email=normalized_email,
        trip_id=trip.trip_id,
        trip_title=trip.title,
        companion_id=companion.companion_id,
        invited_by_user_id=invited_by_user_id,
        target_user_id=None if matched_user is None else matched_user.user_id,
    )
    await db.commit()
    await db.refresh(companion)
    return companion


async def remove_companion(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    companion_id: uuid.UUID,
) -> None:
    companion = await db.scalar(
        select(TripCompanion).where(
            TripCompanion.trip_id == trip_id,
            TripCompanion.companion_id == companion_id,
        )
    )
    if companion is None:
        raise TripNotFoundError("동반자를 찾을 수 없습니다.")
    await db.delete(companion)
    await db.commit()


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


async def revoke_share_link(db: AsyncSession, *, share_id: uuid.UUID, trip_id: uuid.UUID) -> None:
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


async def list_comments(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    limit: int = 50,
) -> list[TripComment]:
    result = await db.execute(
        select(TripComment)
        .where(TripComment.trip_id == trip_id, TripComment.deleted_at.is_(None))
        .order_by(TripComment.created_at.asc(), TripComment.comment_id.asc())
        .limit(limit)
    )
    return list(result.scalars())


async def create_comment(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    author_user_id: uuid.UUID,
    body: str,
    target_type: str,
    target_id: uuid.UUID | None,
    day_index: int | None,
) -> TripComment:
    comment = TripComment(
        trip_id=trip_id,
        author_user_id=author_user_id,
        body=body.strip(),
        target_type=target_type,
        target_id=target_id,
        day_index=day_index,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def delete_comment(
    db: AsyncSession,
    *,
    trip: Trip,
    comment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> TripComment:
    comment = await db.scalar(
        select(TripComment).where(
            TripComment.trip_id == trip.trip_id,
            TripComment.comment_id == comment_id,
            TripComment.deleted_at.is_(None),
        )
    )
    if comment is None:
        raise TripCommentNotFoundError("댓글을 찾을 수 없습니다.")
    if comment.author_user_id != actor_user_id and trip.owner_user_id != actor_user_id:
        raise TripPermissionError("댓글 작성자 또는 여행 소유자만 삭제할 수 있습니다.")
    comment.deleted_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(comment)
    return comment


async def _is_companion(db: AsyncSession, trip_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = await db.scalar(
        select(TripCompanion.companion_id).where(
            TripCompanion.trip_id == trip_id,
            TripCompanion.user_id == user_id,
        )
    )
    return row is not None
