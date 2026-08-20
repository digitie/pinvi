"""`/health*` — `docs/api/health.md`."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.models.cache_target_sync import (
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
)
from app.schemas.health import (
    CacheTargetSyncHealthResponse,
    FeatureReferenceReconciliationHealthResponse,
    HealthDbResponse,
    HealthResponse,
)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/health/db", response_model=HealthDbResponse)
async def health_db(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthDbResponse:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DB_UNAVAILABLE",
                "message": "DB 연결에 실패했습니다.",
                "details": {"reason": str(exc)},
            },
        ) from exc
    latency_ms = int((time.perf_counter() - start) * 1000)
    return HealthDbResponse(latency_ms=latency_ms)


@router.get("/health/cache-target-sync", response_model=CacheTargetSyncHealthResponse)
async def cache_target_sync_health(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CacheTargetSyncHealthResponse:
    """credential/host를 제외한 paired worker durable 상태."""
    consumer = await db.get(
        KtmCacheTargetConsumer,
        settings.pinvi_kor_travel_map_cache_target_consumer_id,
    )
    applied_gap_events = (
        select(KtmCacheTargetEventClaimItem.event_id)
        .join(
            KtmCacheTargetEventClaim,
            KtmCacheTargetEventClaim.claim_id == KtmCacheTargetEventClaimItem.claim_id,
        )
        .where(
            KtmCacheTargetEventClaim.consumer_id
            == settings.pinvi_kor_travel_map_cache_target_consumer_id
        )
        .group_by(KtmCacheTargetEventClaimItem.event_id)
        .having(func.count(KtmCacheTargetEventClaimItem.acked_at) == 0)
        .subquery()
    )
    pending_gap = int(await db.scalar(select(func.count()).select_from(applied_gap_events)) or 0)
    pending_commands = int(
        await db.scalar(
            select(func.count())
            .select_from(KtmCacheTargetCommand)
            .where(KtmCacheTargetCommand.status.in_(("pending", "leased")))
        )
        or 0
    )
    dead_commands = int(
        await db.scalar(
            select(func.count())
            .select_from(KtmCacheTargetCommand)
            .where(KtmCacheTargetCommand.status == "dead_letter")
        )
        or 0
    )
    last_command_error = await db.scalar(
        select(KtmCacheTargetCommand.error_code)
        .where(KtmCacheTargetCommand.error_code.is_not(None))
        .order_by(
            KtmCacheTargetCommand.completed_at.desc().nullslast(),
            KtmCacheTargetCommand.updated_at.desc(),
        )
        .limit(1)
    )
    if not settings.pinvi_kor_travel_map_cache_target_sync_enabled:
        disabled_reason = "network_disabled_by_default"
    elif consumer is None:
        disabled_reason = "consumer_uninitialized"
    elif not consumer.ready:
        disabled_reason = f"consumer_{consumer.reconcile_status}"
    elif dead_commands:
        disabled_reason = "command_dead_letter"
    else:
        disabled_reason = None
    reconcile_status = consumer.reconcile_status if consumer is not None else "uninitialized"
    effective_ready = bool(
        settings.pinvi_kor_travel_map_cache_target_sync_enabled
        and consumer is not None
        and consumer.ready
        and consumer.reconcile_status == "matched"
        and dead_commands == 0
    )
    return CacheTargetSyncHealthResponse(
        enabled=settings.pinvi_kor_travel_map_cache_target_sync_enabled,
        ready=effective_ready,
        disabled_reason=disabled_reason,
        restore_epoch=consumer.active_restore_epoch if consumer is not None else None,
        local_applied_cursor=consumer.local_applied_cursor if consumer is not None else None,
        remote_acked_cursor=consumer.remote_acked_cursor if consumer is not None else None,
        pending_applied_gap=pending_gap,
        pending_commands=pending_commands,
        dead_letter_commands=dead_commands,
        snapshot_id=consumer.snapshot_id if consumer is not None else None,
        snapshot_count=consumer.snapshot_count if consumer is not None else None,
        snapshot_merkle_root=(
            consumer.snapshot_merkle_root.hex()
            if consumer is not None and consumer.snapshot_merkle_root is not None
            else None
        ),
        reconcile_status=reconcile_status,
        last_error=(
            str(last_command_error)
            if last_command_error is not None
            else (
                None
                if reconcile_status in {"uninitialized", "checking", "matched"}
                else reconcile_status
            )
        ),
    )


@router.get(
    "/health/feature-reference-reconciliation",
    response_model=FeatureReferenceReconciliationHealthResponse,
    responses={503: {"model": FeatureReferenceReconciliationHealthResponse}},
)
async def feature_reference_reconciliation_health(
    request: Request,
) -> FeatureReferenceReconciliationHealthResponse | JSONResponse:
    """M05 paired worker의 permanent pairing fault를 token 없이 노출한다."""

    fault = getattr(request.app.state, "feature_reference_reconciliation_runtime_fault", None)
    enabled = settings.pinvi_kor_travel_map_feature_reference_reconciliation_enabled
    response = FeatureReferenceReconciliationHealthResponse(
        enabled=enabled,
        ready=not enabled or fault is None,
        fault=fault,
    )
    if enabled and fault is not None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=response.model_dump()
        )
    return response
