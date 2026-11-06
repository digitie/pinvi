"""첨부 객체의 예약/참조와 GC tombstone 사이 잠금 경계."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import CuratedPlanAttachment
from app.models.storage_lifecycle import AttachmentGcObject, AttachmentUploadIntent
from app.models.trip import Trip
from app.models.user import User
from app.services.rustfs_storage import InvalidStorageRefError

ATTACHMENT_PURPOSES = frozenset(
    {
        "trip_attachment",
        "trip_day_attachment",
        "poi_attachment",
        "curated_plan_attachment",
        "curated_poi_attachment",
    }
)
TRASH_RETENTION_DAYS = 30


def object_lock_id(bucket: str, key: str) -> int:
    return int.from_bytes(
        hashlib.sha256(("pinvi-attachment:" + bucket + ":" + key).encode()).digest()[:8],
        "big",
        signed=True,
    )


async def lock_object(db: AsyncSession, bucket: str, key: str, *, try_only: bool = False) -> bool:
    function = "pg_try_advisory_xact_lock" if try_only else "pg_advisory_xact_lock"
    result = await db.scalar(text(f"SELECT {function}(:key)"), {"key": object_lock_id(bucket, key)})
    return bool(result) if try_only else True


async def assert_objects_writable(db: AsyncSession, objects: list[tuple[str, str]]) -> None:
    for bucket, key in sorted(set(objects)):
        await lock_object(db, bucket, key)
        if await db.get(AttachmentGcObject, (bucket, key)) is not None:
            raise InvalidStorageRefError("정리가 시작된 파일입니다. 파일을 다시 업로드해 주세요.")


async def reserve_attachment_upload(
    db: AsyncSession, *, user: User, bucket: str, key: str, byte_size: int, expires_at: datetime
) -> None:
    from app.services.storage_policy import (
        AttachmentQuotaError,
        attachment_bytes_for_user,
        effective_attachment_quota,
        get_storage_settings,
    )

    locked = await db.scalar(
        select(User)
        .where(User.user_id == user.user_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise InvalidStorageRefError("업로드 사용자를 찾을 수 없습니다.")
    quota = effective_attachment_quota(await get_storage_settings(db), locked)
    if (
        await attachment_bytes_for_user(db, user_id=user.user_id) + byte_size
        > quota.user_quota_bytes
    ):
        raise AttachmentQuotaError(
            f"사용자 첨부 총량은 최대 {quota.user_quota_bytes} bytes까지 가능합니다."
        )
    await assert_objects_writable(db, [(bucket, key)])
    db.add(
        AttachmentUploadIntent(
            bucket=bucket,
            storage_key=key,
            user_id=user.user_id,
            byte_size=byte_size,
            expires_at=expires_at,
        )
    )
    await db.flush()


async def claim_attachment_upload(
    db: AsyncSession, *, user_id: uuid.UUID, bucket: str, key: str, byte_size: int
) -> None:
    # 모든 참조 생성자는 사용자 잠금 뒤 객체 잠금을 잡는다.
    await db.scalar(select(User).where(User.user_id == user_id).with_for_update(key_share=True))
    await assert_objects_writable(db, [(bucket, key)])
    intent = await db.get(AttachmentUploadIntent, (bucket, key), populate_existing=True)
    if intent is not None:
        if intent.user_id != user_id or intent.uploaded_bytes != byte_size:
            raise InvalidStorageRefError("완료된 업로드의 크기와 첨부 정보가 일치하지 않습니다.")
        if intent.purged_at is not None:
            raise InvalidStorageRefError("이미 정리된 파일입니다.")
        intent.registered_at = intent.registered_at or datetime.now(UTC)
        await db.flush()


async def pending_upload_bytes(db: AsyncSession, user_id: uuid.UUID) -> int:
    value = await db.scalar(
        select(func.coalesce(func.sum(AttachmentUploadIntent.byte_size), 0)).where(
            AttachmentUploadIntent.user_id == user_id,
            AttachmentUploadIntent.registered_at.is_(None),
            AttachmentUploadIntent.purged_at.is_(None),
            # 쓰기를 시작하지 않은 채 만료된 예약은 PUT이 거부되므로 바이트를 가질 수 없다.
            # 수동 GC 전까지 취소·실패한 선택이 사용자 총량을 잠그지 않게 제외한다.
            or_(
                AttachmentUploadIntent.write_started_at.is_not(None),
                AttachmentUploadIntent.expires_at > datetime.now(UTC),
            ),
        )
    )
    return int(value or 0)


async def lock_restorable_trip(db: AsyncSession, trip_id: uuid.UUID) -> Trip:
    from app.models.trip import Trip

    trip = await db.scalar(
        select(Trip)
        .where(Trip.trip_id == trip_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        trip is None
        or trip.purge_started_at is not None
        or (
            trip.deleted_at is not None
            and trip.deleted_at <= datetime.now(UTC) - timedelta(days=TRASH_RETENTION_DAYS)
        )
    ):
        raise InvalidStorageRefError(
            "보관 기한이 지났거나 정리가 시작된 여행은 복원할 수 없습니다."
        )
    return trip


async def lock_restorable_attachment(
    db: AsyncSession, attachment_id: uuid.UUID
) -> CuratedPlanAttachment:
    from app.models.attachment import CuratedPlanAttachment
    from app.models.poi import TripDayPoi

    row: CuratedPlanAttachment | None = await db.get(CuratedPlanAttachment, attachment_id)
    if row is None:
        raise InvalidStorageRefError("첨부를 찾을 수 없습니다.")
    parent_trip = row.trip_id
    if row.trip_poi_id is not None:
        parent_trip = await db.scalar(
            select(TripDayPoi.trip_id).where(TripDayPoi.attachment_id == row.trip_poi_id)
        )
    if parent_trip is not None:
        await lock_restorable_trip(db, parent_trip)
    if row.trip_poi_id is not None:
        poi = await db.scalar(
            select(TripDayPoi)
            .where(
                TripDayPoi.attachment_id == row.trip_poi_id,
                TripDayPoi.trip_id == parent_trip,
                TripDayPoi.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if poi is None:
            raise InvalidStorageRefError("첨부의 장소가 변경되었거나 삭제되었습니다.")
    await assert_objects_writable(db, [(row.bucket, row.storage_key)])
    row = await db.scalar(
        select(CuratedPlanAttachment)
        .where(
            CuratedPlanAttachment.attachment_id == attachment_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.purged_at is not None or row.restore_blocked:
        raise InvalidStorageRefError("부모가 삭제되었거나 이미 정리된 첨부는 복원할 수 없습니다.")
    if row.trip_id is not None and row.trip_id != parent_trip:
        raise InvalidStorageRefError("첨부 대상이 변경되었습니다.")
    return row


async def assert_copy_sources_writable(
    db: AsyncSession, attachments: list[CuratedPlanAttachment]
) -> None:
    await assert_objects_writable(db, [(row.bucket, row.storage_key) for row in attachments])
    ids = {row.attachment_id for row in attachments}
    if not ids:
        return
    current = list(
        await db.scalars(
            select(CuratedPlanAttachment.attachment_id)
            .where(
                CuratedPlanAttachment.attachment_id.in_(ids),
                CuratedPlanAttachment.deleted_at.is_(None),
                CuratedPlanAttachment.purged_at.is_(None),
            )
            .order_by(CuratedPlanAttachment.attachment_id)
            .with_for_update(read=True, key_share=True)
        )
    )
    if len(current) != len(ids):
        raise InvalidStorageRefError(
            "복사할 파일이 변경되었거나 정리되었습니다. 다시 불러와 주세요."
        )
