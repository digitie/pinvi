"""`/admin/stats/*` — Pinvi app-owned 운영 지표."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.api_call_log import ApiCallLog
from app.models.attachment import CuratedPlanAttachment
from app.models.email_queue import EmailQueue
from app.models.poi import TripDayPoi
from app.models.storage_settings import StorageSettings
from app.models.trip import Trip
from app.models.user import User
from app.schemas.admin import (
    AdminStatsCapacitySnapshot,
    AdminStatsLoadSnapshot,
    AdminStatsOverview,
    AdminStatsSeriesBucket,
)
from app.schemas.envelope import Envelope
from app.services.backup_service import resolve_repo_path
from app.services.storage_policy import (
    DEFAULT_ATTACHMENT_MAX_UPLOAD_BYTES,
    DEFAULT_AVATAR_MAX_UPLOAD_BYTES,
    DEFAULT_TRIP_ATTACHMENT_QUOTA_BYTES,
    DEFAULT_USER_ATTACHMENT_QUOTA_BYTES,
)

router = APIRouter(prefix="/admin/stats", tags=["admin"])


@router.get("/overview", response_model=Envelope[AdminStatsOverview])
async def get_admin_stats_overview(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminStatsOverview]:
    generated_at = datetime.now(UTC)
    since = generated_at - timedelta(hours=24)
    api_calls_24h = await _count(
        db,
        select(func.count()).select_from(ApiCallLog).where(ApiCallLog.occurred_at >= since),
    )
    api_calls_failed_24h = await _count(
        db,
        select(func.count())
        .select_from(ApiCallLog)
        .where(
            ApiCallLog.occurred_at >= since,
            _api_failure_condition(),
        ),
    )

    overview = AdminStatsOverview(
        generated_at=generated_at,
        users_total=await _count(
            db,
            select(func.count()).select_from(User).where(User.deleted_at.is_(None)),
        ),
        users_24h=await _count(
            db,
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None), User.created_at >= since),
        ),
        users_pending_verification=await _count(
            db,
            select(func.count())
            .select_from(User)
            .where(
                User.deleted_at.is_(None),
                User.status == "pending_verification",
            ),
        ),
        trips_total=await _count(
            db,
            select(func.count()).select_from(Trip).where(Trip.deleted_at.is_(None)),
        ),
        trips_active=await _count(
            db,
            select(func.count())
            .select_from(Trip)
            .where(
                Trip.deleted_at.is_(None),
                Trip.status.in_(("planned", "in_progress")),
            ),
        ),
        pois_total=await _count(
            db,
            select(func.count()).select_from(TripDayPoi).where(TripDayPoi.deleted_at.is_(None)),
        ),
        email_queue_pending=await _count(
            db,
            select(func.count()).select_from(EmailQueue).where(EmailQueue.status == "pending"),
        ),
        api_calls_24h=api_calls_24h,
        api_calls_failed_24h=api_calls_failed_24h,
        api_failure_rate_pct=_failure_rate(api_calls_24h, api_calls_failed_24h),
        api_latency_p95_ms=await _api_latency_p95_ms(db, since=since),
        series_24h=await _series_24h(db, generated_at=generated_at),
        load=_load_snapshot(),
        capacity=await _capacity_snapshot(db),
    )
    return Envelope.of(overview)


async def _count(db: AsyncSession, stmt: Any) -> int:
    return int(await db.scalar(stmt) or 0)


def _api_failure_condition() -> Any:
    return or_(
        ApiCallLog.error_class.is_not(None),
        ApiCallLog.status_code >= 500,
    )


def _failure_rate(total: int, failed: int) -> float:
    if total <= 0:
        return 0.0
    return round((failed / total) * 100, 1)


async def _api_latency_p95_ms(db: AsyncSession, *, since: datetime) -> int | None:
    value = await db.scalar(
        select(func.percentile_cont(0.95).within_group(ApiCallLog.latency_ms)).where(
            ApiCallLog.occurred_at >= since,
            ApiCallLog.latency_ms.is_not(None),
        )
    )
    if value is None:
        return None
    return round(float(value))


async def _series_24h(db: AsyncSession, *, generated_at: datetime) -> list[AdminStatsSeriesBucket]:
    current_hour = generated_at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    start_hour = current_hour - timedelta(hours=23)
    buckets = {
        start_hour + timedelta(hours=offset): AdminStatsSeriesBucket(
            bucket_start=start_hour + timedelta(hours=offset)
        )
        for offset in range(24)
    }

    await _apply_count_series(
        db,
        bucket_field=User.created_at,
        start_hour=start_hour,
        target=buckets,
        value_attr="users_created",
        extra_where=(User.deleted_at.is_(None),),
    )
    await _apply_count_series(
        db,
        bucket_field=Trip.created_at,
        start_hour=start_hour,
        target=buckets,
        value_attr="trips_created",
        extra_where=(Trip.deleted_at.is_(None),),
    )
    await _apply_api_series(db, start_hour=start_hour, target=buckets)

    return [buckets[start_hour + timedelta(hours=offset)] for offset in range(24)]


async def _apply_count_series(
    db: AsyncSession,
    *,
    bucket_field: Any,
    start_hour: datetime,
    target: dict[datetime, AdminStatsSeriesBucket],
    value_attr: str,
    extra_where: tuple[Any, ...] = (),
) -> None:
    bucket_expr = func.date_trunc("hour", bucket_field)
    result = await db.execute(
        select(bucket_expr.label("bucket"), func.count().label("count"))
        .where(bucket_field >= start_hour, *extra_where)
        .group_by(bucket_expr)
    )
    for bucket, count in result.all():
        normalized = _normalize_bucket(bucket)
        if normalized in target:
            setattr(target[normalized], value_attr, int(count or 0))


async def _apply_api_series(
    db: AsyncSession,
    *,
    start_hour: datetime,
    target: dict[datetime, AdminStatsSeriesBucket],
) -> None:
    bucket_expr = func.date_trunc("hour", ApiCallLog.occurred_at)
    result = await db.execute(
        select(
            bucket_expr.label("bucket"),
            func.count().label("api_calls"),
            func.count().filter(_api_failure_condition()).label("api_failures"),
        )
        .where(ApiCallLog.occurred_at >= start_hour)
        .group_by(bucket_expr)
    )
    for bucket, api_calls, api_failures in result.all():
        normalized = _normalize_bucket(bucket)
        if normalized in target:
            target[normalized].api_calls = int(api_calls or 0)
            target[normalized].api_failures = int(api_failures or 0)


def _normalize_bucket(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _load_snapshot() -> AdminStatsLoadSnapshot:
    load_1m: float | None = None
    load_5m: float | None = None
    load_15m: float | None = None
    if hasattr(os, "getloadavg"):
        load_1m, load_5m, load_15m = (round(value, 2) for value in os.getloadavg())
    return AdminStatsLoadSnapshot(
        cpu_count=os.cpu_count(),
        load_1m=load_1m,
        load_5m=load_5m,
        load_15m=load_15m,
    )


async def _capacity_snapshot(db: AsyncSession) -> AdminStatsCapacitySnapshot:
    settings_row = await db.scalar(select(StorageSettings).where(StorageSettings.settings_id == 1))
    attachment_stats = await db.execute(
        select(
            func.coalesce(func.sum(CuratedPlanAttachment.byte_size), 0).label("total_bytes"),
            func.count(CuratedPlanAttachment.attachment_id).label("count"),
        ).where(CuratedPlanAttachment.deleted_at.is_(None))
    )
    attachments_total_bytes, attachments_count = attachment_stats.one()
    users_with_quota_override = await _count(
        db,
        select(func.count())
        .select_from(User)
        .where(
            User.deleted_at.is_(None),
            or_(
                User.attachment_max_upload_bytes_override.is_not(None),
                User.trip_attachment_quota_bytes_override.is_not(None),
                User.user_attachment_quota_bytes_override.is_not(None),
            ),
        ),
    )
    disk_total, disk_used, disk_free = _disk_usage_snapshot()

    return AdminStatsCapacitySnapshot(
        attachments_total_bytes=int(attachments_total_bytes or 0),
        attachments_count=int(attachments_count or 0),
        trip_attachment_quota_bytes=(
            settings_row.trip_attachment_quota_bytes
            if settings_row is not None
            else DEFAULT_TRIP_ATTACHMENT_QUOTA_BYTES
        ),
        user_attachment_quota_bytes=(
            settings_row.user_attachment_quota_bytes
            if settings_row is not None
            else DEFAULT_USER_ATTACHMENT_QUOTA_BYTES
        ),
        attachment_max_upload_bytes=(
            settings_row.attachment_max_upload_bytes
            if settings_row is not None
            else DEFAULT_ATTACHMENT_MAX_UPLOAD_BYTES
        ),
        avatar_max_upload_bytes=(
            settings_row.avatar_max_upload_bytes
            if settings_row is not None
            else DEFAULT_AVATAR_MAX_UPLOAD_BYTES
        ),
        users_with_quota_override=users_with_quota_override,
        disk_total_bytes=disk_total,
        disk_used_bytes=disk_used,
        disk_free_bytes=disk_free,
    )


def _disk_usage_snapshot() -> tuple[int | None, int | None, int | None]:
    target = resolve_repo_path(settings.pinvi_backup_dir)
    usage_path = _nearest_existing_path(target)
    if usage_path is None:
        return None, None, None
    try:
        usage = shutil.disk_usage(usage_path)
    except OSError:
        return None, None, None
    return usage.total, usage.used, usage.free


def _nearest_existing_path(path: Path) -> Path | None:
    current: Path | None = path
    while current is not None:
        if current.exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None
