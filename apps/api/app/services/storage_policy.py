"""RustFS attachment quota / storage settings policy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import CuratedPlanAttachment
from app.models.poi import TripDayPoi
from app.models.storage_settings import StorageSettings
from app.models.trip import Trip
from app.models.user import User

DEFAULT_AVATAR_MAX_UPLOAD_BYTES = 2 * 1024 * 1024
DEFAULT_ATTACHMENT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_TRIP_ATTACHMENT_QUOTA_BYTES = 100 * 1024 * 1024
DEFAULT_USER_ATTACHMENT_QUOTA_BYTES = 1024 * 1024 * 1024

AttachmentScope = Literal["trip", "day", "poi", "curated_plan", "curated_poi"]


class AttachmentQuotaError(Exception):
    code = "ATTACHMENT_QUOTA_EXCEEDED"


@dataclass(frozen=True)
class EffectiveAttachmentQuota:
    max_upload_bytes: int
    trip_quota_bytes: int
    user_quota_bytes: int


async def get_storage_settings(db: AsyncSession) -> StorageSettings:
    row = await db.scalar(select(StorageSettings).where(StorageSettings.settings_id == 1))
    if row is not None:
        return row
    row = StorageSettings(
        settings_id=1,
        avatar_max_upload_bytes=DEFAULT_AVATAR_MAX_UPLOAD_BYTES,
        attachment_max_upload_bytes=DEFAULT_ATTACHMENT_MAX_UPLOAD_BYTES,
        trip_attachment_quota_bytes=DEFAULT_TRIP_ATTACHMENT_QUOTA_BYTES,
        user_attachment_quota_bytes=DEFAULT_USER_ATTACHMENT_QUOTA_BYTES,
    )
    db.add(row)
    await db.flush()
    return row


async def set_avatar_max_upload_bytes(
    db: AsyncSession,
    *,
    avatar_max_upload_bytes: int,
) -> tuple[StorageSettings, dict[str, int]]:
    row = await get_storage_settings(db)
    before_state = {"avatar_max_upload_bytes": row.avatar_max_upload_bytes}
    row.avatar_max_upload_bytes = avatar_max_upload_bytes
    await db.flush()
    return row, before_state


async def set_attachment_storage_settings(
    db: AsyncSession,
    *,
    attachment_max_upload_bytes: int,
    trip_attachment_quota_bytes: int,
    user_attachment_quota_bytes: int,
) -> tuple[StorageSettings, dict[str, int]]:
    row = await get_storage_settings(db)
    before_state = storage_settings_state(row)
    row.attachment_max_upload_bytes = attachment_max_upload_bytes
    row.trip_attachment_quota_bytes = trip_attachment_quota_bytes
    row.user_attachment_quota_bytes = user_attachment_quota_bytes
    await db.flush()
    return row, before_state


def storage_settings_state(row: StorageSettings) -> dict[str, int]:
    return {
        "avatar_max_upload_bytes": row.avatar_max_upload_bytes,
        "attachment_max_upload_bytes": row.attachment_max_upload_bytes,
        "trip_attachment_quota_bytes": row.trip_attachment_quota_bytes,
        "user_attachment_quota_bytes": row.user_attachment_quota_bytes,
    }


def user_quota_override_state(user: User) -> dict[str, int | None]:
    return {
        "attachment_max_upload_bytes_override": user.attachment_max_upload_bytes_override,
        "trip_attachment_quota_bytes_override": user.trip_attachment_quota_bytes_override,
        "user_attachment_quota_bytes_override": user.user_attachment_quota_bytes_override,
    }


def effective_attachment_quota(
    settings_row: StorageSettings, user: User
) -> EffectiveAttachmentQuota:
    return EffectiveAttachmentQuota(
        max_upload_bytes=(
            user.attachment_max_upload_bytes_override or settings_row.attachment_max_upload_bytes
        ),
        trip_quota_bytes=(
            user.trip_attachment_quota_bytes_override or settings_row.trip_attachment_quota_bytes
        ),
        user_quota_bytes=(
            user.user_attachment_quota_bytes_override or settings_row.user_attachment_quota_bytes
        ),
    )


async def attachment_bytes_for_trip(db: AsyncSession, *, trip_id: uuid.UUID) -> int:
    poi_ids = select(TripDayPoi.attachment_id).where(TripDayPoi.trip_id == trip_id)
    total = await db.scalar(
        select(func.coalesce(func.sum(CuratedPlanAttachment.byte_size), 0)).where(
            CuratedPlanAttachment.deleted_at.is_(None),
            or_(
                CuratedPlanAttachment.trip_id == trip_id,
                CuratedPlanAttachment.trip_poi_id.in_(poi_ids),
            ),
        )
    )
    return int(total or 0)


async def attachment_bytes_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    total = await db.scalar(
        select(func.coalesce(func.sum(CuratedPlanAttachment.byte_size), 0)).where(
            CuratedPlanAttachment.deleted_at.is_(None),
            CuratedPlanAttachment.uploaded_by_user_id == user_id,
        )
    )
    return int(total or 0)


async def assert_attachment_quota(
    db: AsyncSession,
    *,
    user: User,
    trip_id: uuid.UUID,
    byte_size: int,
) -> EffectiveAttachmentQuota:
    settings_row = await get_storage_settings(db)
    quota = effective_attachment_quota(settings_row, user)
    if byte_size > quota.max_upload_bytes:
        raise AttachmentQuotaError(
            f"개별 파일은 최대 {quota.max_upload_bytes} bytes까지 가능합니다."
        )
    trip_used = await attachment_bytes_for_trip(db, trip_id=trip_id)
    if trip_used + byte_size > quota.trip_quota_bytes:
        raise AttachmentQuotaError(
            f"여행계획 첨부 총량은 최대 {quota.trip_quota_bytes} bytes까지 가능합니다."
        )
    user_used = await attachment_bytes_for_user(db, user_id=user.user_id)
    if user_used + byte_size > quota.user_quota_bytes:
        raise AttachmentQuotaError(
            f"사용자 첨부 총량은 최대 {quota.user_quota_bytes} bytes까지 가능합니다."
        )
    return quota


def attachment_scope(attachment: CuratedPlanAttachment) -> AttachmentScope:
    if attachment.trip_poi_id is not None:
        return "poi"
    if attachment.trip_id is not None and attachment.trip_day_index is not None:
        return "day"
    if attachment.trip_id is not None:
        return "trip"
    if attachment.curated_poi_id is not None:
        return "curated_poi"
    return "curated_plan"


def attachment_state(attachment: CuratedPlanAttachment) -> dict[str, Any]:
    return {
        "attachment_id": str(attachment.attachment_id),
        "scope": attachment_scope(attachment),
        "trip_id": str(attachment.trip_id) if attachment.trip_id else None,
        "trip_day_index": attachment.trip_day_index,
        "trip_poi_id": str(attachment.trip_poi_id) if attachment.trip_poi_id else None,
        "curated_plan_id": str(attachment.curated_plan_id) if attachment.curated_plan_id else None,
        "curated_poi_id": str(attachment.curated_poi_id) if attachment.curated_poi_id else None,
        "bucket": attachment.bucket,
        "storage_key": attachment.storage_key,
        "original_filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "byte_size": attachment.byte_size,
        "uploaded_by_user_id": str(attachment.uploaded_by_user_id),
        "deleted_at": attachment.deleted_at.isoformat() if attachment.deleted_at else None,
    }


async def list_user_file_library(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    offset: int = 0,
) -> tuple[list[tuple[CuratedPlanAttachment, str | None, str | None]], int]:
    owner_trip_ids = select(Trip.trip_id).where(
        Trip.owner_user_id == user_id,
        Trip.deleted_at.is_(None),
    )
    accessible_filters = [
        CuratedPlanAttachment.uploaded_by_user_id == user_id,
        CuratedPlanAttachment.trip_id.in_(owner_trip_ids),
        CuratedPlanAttachment.trip_poi_id.in_(
            select(TripDayPoi.attachment_id).where(TripDayPoi.trip_id.in_(owner_trip_ids))
        ),
    ]
    where = [CuratedPlanAttachment.deleted_at.is_(None), or_(*accessible_filters)]
    total = int(
        await db.scalar(select(func.count(CuratedPlanAttachment.attachment_id)).where(*where)) or 0
    )
    result = await db.execute(
        select(CuratedPlanAttachment, Trip.title, TripDayPoi.feature_snapshot["name"].as_string())
        .outerjoin(Trip, Trip.trip_id == CuratedPlanAttachment.trip_id)
        .outerjoin(TripDayPoi, TripDayPoi.attachment_id == CuratedPlanAttachment.trip_poi_id)
        .where(*where)
        .order_by(CuratedPlanAttachment.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        (attachment, trip_title, poi_name) for attachment, trip_title, poi_name in result
    ], total


async def get_user_library_attachment(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> CuratedPlanAttachment | None:
    owner_trip_ids = select(Trip.trip_id).where(
        Trip.owner_user_id == user_id,
        Trip.deleted_at.is_(None),
    )
    result = await db.scalar(
        select(CuratedPlanAttachment).where(
            CuratedPlanAttachment.attachment_id == attachment_id,
            CuratedPlanAttachment.deleted_at.is_(None),
            or_(
                CuratedPlanAttachment.uploaded_by_user_id == user_id,
                CuratedPlanAttachment.trip_id.in_(owner_trip_ids),
                CuratedPlanAttachment.trip_poi_id.in_(
                    select(TripDayPoi.attachment_id).where(TripDayPoi.trip_id.in_(owner_trip_ids))
                ),
            ),
        )
    )
    return result


async def list_admin_file_library(
    db: AsyncSession,
    *,
    q: str | None,
    scope: AttachmentScope | None,
    user_id: uuid.UUID | None,
    trip_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[CuratedPlanAttachment, str | None, str | None, str]], int]:
    filters: list[Any] = [CuratedPlanAttachment.deleted_at.is_(None)]
    if user_id is not None:
        filters.append(CuratedPlanAttachment.uploaded_by_user_id == user_id)
    if trip_id is not None:
        poi_ids = select(TripDayPoi.attachment_id).where(TripDayPoi.trip_id == trip_id)
        filters.append(
            or_(
                CuratedPlanAttachment.trip_id == trip_id,
                CuratedPlanAttachment.trip_poi_id.in_(poi_ids),
            )
        )
    if scope == "trip":
        filters.extend(
            [
                CuratedPlanAttachment.trip_id.is_not(None),
                CuratedPlanAttachment.trip_day_index.is_(None),
                CuratedPlanAttachment.trip_poi_id.is_(None),
            ]
        )
    elif scope == "day":
        filters.extend(
            [
                CuratedPlanAttachment.trip_id.is_not(None),
                CuratedPlanAttachment.trip_day_index.is_not(None),
                CuratedPlanAttachment.trip_poi_id.is_(None),
            ]
        )
    elif scope == "poi":
        filters.append(CuratedPlanAttachment.trip_poi_id.is_not(None))
    elif scope == "curated_plan":
        filters.append(CuratedPlanAttachment.curated_plan_id.is_not(None))
    elif scope == "curated_poi":
        filters.append(CuratedPlanAttachment.curated_poi_id.is_not(None))
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                CuratedPlanAttachment.original_filename.ilike(pattern),
                CuratedPlanAttachment.content_type.ilike(pattern),
                Trip.title.ilike(pattern),
                User.email.ilike(pattern),
            )
        )

    base = (
        select(
            CuratedPlanAttachment,
            Trip.title,
            TripDayPoi.feature_snapshot["name"].as_string(),
            User.email,
        )
        .outerjoin(Trip, Trip.trip_id == CuratedPlanAttachment.trip_id)
        .outerjoin(TripDayPoi, TripDayPoi.attachment_id == CuratedPlanAttachment.trip_poi_id)
        .join(User, User.user_id == CuratedPlanAttachment.uploaded_by_user_id)
        .where(*filters)
    )
    count_base = (
        select(func.count(CuratedPlanAttachment.attachment_id))
        .outerjoin(Trip, Trip.trip_id == CuratedPlanAttachment.trip_id)
        .outerjoin(TripDayPoi, TripDayPoi.attachment_id == CuratedPlanAttachment.trip_poi_id)
        .join(User, User.user_id == CuratedPlanAttachment.uploaded_by_user_id)
        .where(*filters)
    )
    total = int(await db.scalar(count_base) or 0)
    result = await db.execute(
        base.order_by(CuratedPlanAttachment.created_at.desc()).offset(offset).limit(limit)
    )
    return [
        (attachment, trip_title, poi_name, uploaded_by_email)
        for attachment, trip_title, poi_name, uploaded_by_email in result
    ], total


__all__ = [
    "DEFAULT_ATTACHMENT_MAX_UPLOAD_BYTES",
    "DEFAULT_AVATAR_MAX_UPLOAD_BYTES",
    "DEFAULT_TRIP_ATTACHMENT_QUOTA_BYTES",
    "DEFAULT_USER_ATTACHMENT_QUOTA_BYTES",
    "AttachmentQuotaError",
    "AttachmentScope",
    "EffectiveAttachmentQuota",
    "assert_attachment_quota",
    "attachment_bytes_for_trip",
    "attachment_bytes_for_user",
    "attachment_scope",
    "attachment_state",
    "effective_attachment_quota",
    "get_storage_settings",
    "get_user_library_attachment",
    "list_admin_file_library",
    "list_user_file_library",
    "set_attachment_storage_settings",
    "set_avatar_max_upload_bytes",
    "storage_settings_state",
    "user_quota_override_state",
]
