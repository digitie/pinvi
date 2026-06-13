"""`/admin/stats/*` — Pinvi app-owned 운영 지표."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.api_call_log import ApiCallLog
from app.models.email_queue import EmailQueue
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.user import User
from app.schemas.admin import AdminStatsOverview
from app.schemas.envelope import Envelope

router = APIRouter(prefix="/admin/stats", tags=["admin"])


@router.get("/overview", response_model=Envelope[AdminStatsOverview])
async def get_admin_stats_overview(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminStatsOverview]:
    since = datetime.now(UTC) - timedelta(hours=24)

    overview = AdminStatsOverview(
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
        api_calls_24h=await _count(
            db,
            select(func.count()).select_from(ApiCallLog).where(ApiCallLog.occurred_at >= since),
        ),
        api_calls_failed_24h=await _count(
            db,
            select(func.count())
            .select_from(ApiCallLog)
            .where(
                ApiCallLog.occurred_at >= since,
                or_(
                    ApiCallLog.error_class.is_not(None),
                    ApiCallLog.status_code >= 500,
                ),
            ),
        ),
    )
    return Envelope.of(overview)


async def _count(db: AsyncSession, stmt: Any) -> int:
    return int(await db.scalar(stmt) or 0)
