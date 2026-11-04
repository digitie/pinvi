"""30일 휴지통과 첨부 객체의 영속·재시도 가능한 정리."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from sqlalchemy import and_, case, exists, func, or_, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.models.attachment import CuratedPlanAttachment as A
from app.models.poi import TripDayPoi
from app.models.storage_lifecycle import AttachmentGcObject as G
from app.models.storage_lifecycle import AttachmentUploadIntent as I
from app.models.trip import Trip
from app.services.storage_lifecycle import TRASH_RETENTION_DAYS, lock_object


def upload_collectable(now: datetime) -> Any:
    return and_(
        I.registered_at.is_(None),
        I.purged_at.is_(None),
        I.expires_at <= now,
        or_(
            I.uploaded_bytes.is_not(None),
            I.write_started_at.is_(None),
            I.write_started_at <= now - timedelta(minutes=30),
        ),
    )


def eligible_attachment(now: datetime, *, preview: bool = False) -> Any:
    expired: ColumnElement[bool] = Trip.purge_started_at.is_not(None)
    if preview:
        expired = or_(expired, Trip.deleted_at <= now - timedelta(days=TRASH_RETENTION_DAYS))
    expired_trip = exists(select(Trip.trip_id).where(Trip.trip_id == A.trip_id, expired))
    deleted_poi = exists(
        select(TripDayPoi.attachment_id).where(
            TripDayPoi.attachment_id == A.trip_poi_id,
            or_(
                TripDayPoi.deleted_at.is_not(None),
                exists(select(Trip.trip_id).where(Trip.trip_id == TripDayPoi.trip_id, expired)),
            ),
        )
    )
    return or_(
        and_(A.deleted_at.is_not(None), A.moderation_hold.is_(False)), expired_trip, deleted_poi
    )


async def retention_status(db: AsyncSession) -> dict[str, Any]:
    now = datetime.now(UTC)
    expired = int(
        await db.scalar(
            select(func.count())
            .select_from(Trip)
            .where(Trip.deleted_at <= now - timedelta(days=TRASH_RETENTION_DAYS))
        )
        or 0
    )
    eligible = int(
        await db.scalar(
            select(func.count())
            .select_from(A)
            .where(A.purged_at.is_(None), eligible_attachment(now, preview=True))
        )
        or 0
    )
    held = int(
        await db.scalar(
            select(func.count())
            .select_from(A)
            .where(
                A.purged_at.is_(None),
                A.deleted_at.is_not(None),
                A.moderation_hold.is_(True),
                ~eligible_attachment(now, preview=True),
            )
        )
        or 0
    )
    uploads = int(
        await db.scalar(select(func.count()).select_from(I).where(upload_collectable(now))) or 0
    )
    protected = int(
        await db.scalar(
            select(func.count())
            .select_from(I)
            .where(
                I.registered_at.is_(None),
                I.purged_at.is_(None),
                I.expires_at <= now,
                ~upload_collectable(now),
            )
        )
        or 0
    )
    pending = int(
        await db.scalar(select(func.count()).select_from(G).where(G.deleted_at.is_(None))) or 0
    )
    leased = int(
        await db.scalar(
            select(func.count())
            .select_from(G)
            .where(G.deleted_at.is_(None), G.lease_expires_at > now)
        )
        or 0
    )
    phase = case((G.deleted_at.is_(None), "delete"), else_="verify")
    errors = (
        await db.execute(
            select(G.last_error_code, phase, func.count())
            .where(G.last_error_code.is_not(None))
            .group_by(G.last_error_code, phase)
            .order_by(G.last_error_code)
        )
    ).all()
    return {
        "retention_days": TRASH_RETENTION_DAYS,
        "expired_trips": expired,
        "eligible_attachments": eligible,
        "held_attachments": held,
        "expired_uploads": uploads,
        "protected_uploads": protected,
        "pending_objects": pending,
        "in_progress_objects": leased,
        "errors": [{"code": code, "phase": phase, "count": count} for code, phase, count in errors],
    }


async def _stage(db: AsyncSession, now: datetime, batch_size: int) -> tuple[int, int]:
    trips = list(
        await db.scalars(
            select(Trip)
            .where(
                Trip.deleted_at <= now - timedelta(days=TRASH_RETENTION_DAYS),
                Trip.purge_started_at.is_(None),
            )
            .order_by(Trip.trip_id)
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
    )
    for trip in trips:
        trip.purge_started_at = now
    await db.flush()
    candidates = (
        await db.execute(
            select(A.bucket, A.storage_key)
            .where(
                A.purged_at.is_(None),
                eligible_attachment(now),
                ~exists(
                    select(G.bucket).where(G.bucket == A.bucket, G.storage_key == A.storage_key)
                ),
            )
            .distinct()
            .order_by(A.bucket, A.storage_key)
            .limit(batch_size)
        )
    ).all()
    uploads = (
        await db.execute(
            select(I.bucket, I.storage_key)
            .where(
                upload_collectable(now),
                ~exists(
                    select(G.bucket).where(G.bucket == I.bucket, G.storage_key == I.storage_key)
                ),
            )
            .order_by(I.bucket, I.storage_key)
            .limit(batch_size)
        )
    ).all()
    retired = 0
    for bucket, key in sorted(set(list(candidates) + list(uploads))):
        if not await lock_object(db, bucket, key, try_only=True):
            continue
        refs = await db.scalar(
            select(func.count())
            .select_from(A)
            .where(
                A.bucket == bucket,
                A.storage_key == key,
                A.purged_at.is_(None),
                ~eligible_attachment(now),
            )
        )
        intent = await db.get(I, (bucket, key), populate_existing=True)
        pending_upload = (
            intent is not None
            and intent.registered_at is None
            and intent.purged_at is None
            and (
                intent.expires_at > now
                or (
                    intent.uploaded_bytes is None
                    and intent.write_started_at is not None
                    and intent.write_started_at > now - timedelta(minutes=30)
                )
            )
        )
        if refs or pending_upload:
            retired_ids = list(
                await db.scalars(
                    update(A)
                    .where(
                        A.bucket == bucket,
                        A.storage_key == key,
                        A.purged_at.is_(None),
                        eligible_attachment(now),
                    )
                    .values(purged_at=now)
                    .returning(A.attachment_id)
                    .execution_options(synchronize_session="fetch")
                )
            )
            retired += len(retired_ids)
            if (
                refs
                and intent is not None
                and intent.registered_at is None
                and intent.expires_at <= now
            ):
                intent.purged_at = now
            continue
        if await db.get(G, (bucket, key)) is None:
            db.add(G(bucket=bucket, storage_key=key))
    await db.commit()  # 이 커밋 전에는 절대 S3 DELETE를 보내지 않는다.
    return len(trips), retired


def _delete_sync(bucket: str, key: str) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=settings.pinvi_rustfs_endpoint_url,
        aws_access_key_id=settings.pinvi_rustfs_access_key_id,
        aws_secret_access_key=settings.pinvi_rustfs_secret_access_key,
        region_name="us-east-1",
        config=Config(connect_timeout=3, read_timeout=5, retries={"total_max_attempts": 1}),
    )
    versioning = client.get_bucket_versioning(Bucket=bucket).get("Status")
    if versioning not in {None, "Enabled", "Suspended"}:
        raise ClientError({"Error": {"Code": "INVALID_VERSIONING_STATE"}}, "GetBucketVersioning")
    if versioning is None:
        client.delete_object(Bucket=bucket, Key=key)
        return
    page = client.list_object_versions(Bucket=bucket, Prefix=key, MaxKeys=1000)
    versions = [
        row for row in page.get("Versions", []) + page.get("DeleteMarkers", []) if row["Key"] == key
    ]
    if versions:
        result = client.delete_objects(
            Bucket=bucket,
            Delete={
                "Objects": [{"Key": key, "VersionId": row["VersionId"]} for row in versions],
                "Quiet": True,
            },
        )
        if result.get("Errors"):
            raise ClientError({"Error": result["Errors"][0]}, "DeleteObjects")
    remaining = client.list_object_versions(Bucket=bucket, Prefix=key, MaxKeys=1000)
    if any(
        row["Key"] == key
        for row in remaining.get("Versions", []) + remaining.get("DeleteMarkers", [])
    ):
        raise ClientError({"Error": {"Code": "MORE_VERSIONS"}}, "ListObjectVersions")


async def delete_attachment_object(bucket: str, key: str) -> None:
    await asyncio.to_thread(_delete_sync, bucket, key)


async def _delete_one(bucket: str, key: str, semaphore: asyncio.Semaphore) -> str | None:
    async with semaphore:
        try:
            await delete_attachment_object(bucket, key)
            return None
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "STORAGE_ERROR"))
            if code in {"NoSuchKey", "NotFound"}:
                return None
            operation = str(exc.operation_name)
            if re.fullmatch(r"[A-Za-z0-9_]{1,64}", code) and re.fullmatch(
                r"[A-Za-z0-9_]{1,64}", operation
            ):
                return code + ":" + operation
            return "STORAGE_ERROR"
        except Exception:
            return "STORAGE_UNAVAILABLE"


async def _remove_completed_trips(db: AsyncSession) -> tuple[int, list[str]]:
    poi_ids = (
        select(TripDayPoi.attachment_id).where(TripDayPoi.trip_id == Trip.trip_id).correlate(Trip)
    )
    remaining = exists(
        select(A.attachment_id)
        .where(
            A.purged_at.is_(None),
            or_(A.trip_id == Trip.trip_id, A.trip_poi_id.in_(poi_ids)),
        )
        .correlate(Trip)
    )
    ids = list(
        await db.scalars(
            select(Trip.trip_id)
            .where(
                Trip.purge_started_at.is_not(None),
                ~remaining,
            )
            .order_by(Trip.trip_id)
            .limit(20)
        )
    )
    previous = str(await db.scalar(text("SHOW lock_timeout")))
    removed = 0
    errors = []
    await db.execute(text("SET LOCAL lock_timeout = '1s'"))
    try:
        for trip_id in ids:
            try:
                async with db.begin_nested():
                    trip = await db.scalar(
                        select(Trip)
                        .where(
                            Trip.trip_id == trip_id,
                            Trip.purge_started_at.is_not(None),
                            ~remaining,
                        )
                        .with_for_update(skip_locked=True)
                    )
                    if trip is None:
                        continue
                    await db.delete(trip)
                    await db.flush()
                removed += 1
            except DBAPIError as exc:
                code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
                if code in {"40P01", "55P03"}:
                    errors.append("TRIP_BUSY")
                elif code == "23503":
                    errors.append("TRIP_REFERENCED")
                else:
                    raise
    finally:
        await db.execute(
            text("SELECT set_config('lock_timeout', :value, true)"), {"value": previous}
        )
    await db.commit()
    return removed, errors


async def execute_attachment_retention(db: AsyncSession, *, batch_size: int = 20) -> dict[str, Any]:
    if not 1 <= batch_size <= 20:
        raise ValueError("batch_size must be 1..20")
    now = datetime.now(UTC)
    started, retired = await _stage(db, now, batch_size)
    objects = list(
        await db.scalars(
            select(G)
            .where(
                G.deleted_at.is_(None),
                or_(G.lease_expires_at.is_(None), G.lease_expires_at <= now),
            )
            .order_by(G.attempts, G.queued_at, G.bucket, G.storage_key)
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
    )
    work = []
    for obj in objects:
        obj.lease_token = uuid.uuid4()
        obj.lease_expires_at = now + timedelta(minutes=5)
        obj.attempts += 1
        work.append((obj.bucket, obj.storage_key, obj.lease_token, False))
    last_attempt = func.coalesce(G.last_verification_attempt_at, G.last_verified_at, G.deleted_at)
    verification = list(
        await db.scalars(
            select(G)
            .where(
                G.deleted_at.is_not(None),
                last_attempt <= now - timedelta(hours=1),
                or_(G.lease_expires_at.is_(None), G.lease_expires_at <= now),
            )
            .order_by(last_attempt, G.bucket, G.storage_key)
            .with_for_update(skip_locked=True)
            .limit(2)
        )
    )
    for obj in verification:
        obj.last_verification_attempt_at = now
        obj.lease_token = uuid.uuid4()
        obj.lease_expires_at = now + timedelta(minutes=5)
        obj.attempts += 1
        work.append((obj.bucket, obj.storage_key, obj.lease_token, True))
    await db.commit()
    semaphore = asyncio.Semaphore(4)
    results = await asyncio.gather(
        *[_delete_one(bucket, key, semaphore) for bucket, key, _, _ in work]
    )
    deleted = failed = verified = verification_failed = 0
    for (bucket, key, token, is_verification), error in zip(work, results, strict=True):
        claimed_obj = await db.scalar(
            select(G)
            .where(
                G.bucket == bucket,
                G.storage_key == key,
                G.lease_token == token,
            )
            .with_for_update()
        )
        if claimed_obj is None:
            continue  # lease가 만료되어 다른 실행이 인수했다.
        claimed_obj.lease_token = None
        claimed_obj.lease_expires_at = None
        claimed_obj.last_error_code = error
        if error is None:
            done = datetime.now(UTC)
            claimed_obj.last_verified_at = done
            if is_verification:
                verified += 1
                continue
            claimed_obj.deleted_at = done
            await db.execute(
                update(A)
                .where(
                    A.bucket == bucket,
                    A.storage_key == key,
                    A.purged_at.is_(None),
                    eligible_attachment(done),
                )
                .values(purged_at=done)
                .execution_options(synchronize_session="fetch")
            )
            await db.execute(
                update(I)
                .where(
                    I.bucket == bucket,
                    I.storage_key == key,
                )
                .values(purged_at=done)
                .execution_options(synchronize_session="fetch")
            )
            deleted += 1
        else:
            if is_verification:
                verification_failed += 1
            else:
                failed += 1
    await db.commit()
    removed_trips, cleanup_errors = await _remove_completed_trips(db)
    return {
        "expired_trips_started": started,
        "retired_references": retired,
        "objects_deleted": deleted,
        "objects_failed": failed,
        "trips_deleted": removed_trips,
        "trip_cleanup_errors": cleanup_errors,
        "objects_verified": verified,
        "verification_failed": verification_failed,
        "status": await retention_status(db),
    }
