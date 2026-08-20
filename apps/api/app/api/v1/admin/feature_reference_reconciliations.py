"""`/admin/feature-reference-reconciliations` — M05 local evidence read API."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.feature_reference_reconciliation import (
    KtmFeatureReferenceReconciliationAppliedReceipt,
    KtmFeatureReferenceReconciliationDeliveryAttempt,
    KtmFeatureReferenceReconciliationImpact,
)
from app.models.user import User
from app.schemas.admin_feature_reference_reconciliation import (
    AdminFeatureReferenceReconciliationAttempt,
    AdminFeatureReferenceReconciliationDetail,
    AdminFeatureReferenceReconciliationPagedResponse,
    AdminFeatureReferenceReconciliationReceipt,
    AdminFeatureReferenceReconciliationSummary,
)
from app.schemas.admin_feature_reference_reconciliation import (
    AdminFeatureReferenceReconciliationImpact as AdminImpact,
)
from app.schemas.envelope import Envelope

router = APIRouter(prefix="/admin/feature-reference-reconciliations", tags=["admin"])


def _attempt(
    row: KtmFeatureReferenceReconciliationDeliveryAttempt,
) -> AdminFeatureReferenceReconciliationAttempt:
    return AdminFeatureReferenceReconciliationAttempt(
        event_id=row.event_id,
        attempt_sequence=row.attempt_sequence,
        event_sequence=row.event_sequence,
        event_sha256=row.event_sha256,
        status=row.status,
        block_fingerprint_sha256=row.block_fingerprint_sha256,
        observation_root_sha256=row.observation_root_sha256,
        observed_at=row.observed_at,
    )


def _receipt(
    row: KtmFeatureReferenceReconciliationAppliedReceipt,
) -> AdminFeatureReferenceReconciliationReceipt:
    return AdminFeatureReferenceReconciliationReceipt(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        event_sha256=row.event_sha256,
        action=row.action,
        old_feature_id=row.old_feature_id,
        old_feature_uuid=row.old_feature_uuid,
        replacement_feature_id=row.replacement_feature_id,
        replacement_feature_uuid=row.replacement_feature_uuid,
        impact_root_sha256=row.impact_root_sha256,
        impact_count=row.impact_count,
        receipt_sha256=row.receipt_sha256,
        applied_at=row.applied_at,
    )


def _impact(row: KtmFeatureReferenceReconciliationImpact) -> AdminImpact:
    return AdminImpact(
        event_id=row.event_id,
        impact_index=row.impact_index,
        target_relation=row.target_relation,
        target_id=row.target_id,
        old_feature_id=row.old_feature_id,
        old_feature_uuid=row.old_feature_uuid,
        replacement_feature_id=row.replacement_feature_id,
        replacement_feature_uuid=row.replacement_feature_uuid,
        outcome=row.outcome,
        recorded_at=row.recorded_at,
    )


async def _latest_attempts_by_event(
    db: DbSession,
) -> dict[uuid.UUID, KtmFeatureReferenceReconciliationDeliveryAttempt]:
    rows = list(
        (
            await db.scalars(
                select(KtmFeatureReferenceReconciliationDeliveryAttempt).order_by(
                    KtmFeatureReferenceReconciliationDeliveryAttempt.event_id,
                    KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence.desc(),
                )
            )
        ).all()
    )
    latest: dict[uuid.UUID, KtmFeatureReferenceReconciliationDeliveryAttempt] = {}
    for row in rows:
        latest.setdefault(row.event_id, row)
    return latest


@router.get("", response_model=Envelope[AdminFeatureReferenceReconciliationPagedResponse])
async def list_feature_reference_reconciliations(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    status_filter: Annotated[Literal["blocked", "applied", "all"], Query(alias="status")] = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[AdminFeatureReferenceReconciliationPagedResponse]:
    """terminal receipt와 아직 ACK하지 않은 마지막 blocked 관측만 조회한다."""

    latest = await _latest_attempts_by_event(db)
    receipts = list(
        (
            await db.scalars(
                select(KtmFeatureReferenceReconciliationAppliedReceipt).order_by(
                    KtmFeatureReferenceReconciliationAppliedReceipt.applied_at.desc(),
                    KtmFeatureReferenceReconciliationAppliedReceipt.event_id.desc(),
                )
            )
        ).all()
    )
    terminal_ids = {row.event_id for row in receipts}
    items: list[AdminFeatureReferenceReconciliationSummary] = []
    if status_filter in {"all", "applied"}:
        for receipt_row in receipts:
            latest_attempt = latest.get(receipt_row.event_id)
            if latest_attempt is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "code": "FEATURE_REFERENCE_RECONCILIATION_EVIDENCE_INVALID",
                        "message": "terminal receipt에 대응하는 delivery attempt가 없습니다.",
                    },
                )
            items.append(
                AdminFeatureReferenceReconciliationSummary(
                    event_id=receipt_row.event_id,
                    status="applied",
                    event_sequence=receipt_row.event_sequence,
                    event_sha256=receipt_row.event_sha256,
                    observed_at=receipt_row.applied_at,
                    receipt=_receipt(receipt_row),
                    latest_attempt=_attempt(latest_attempt),
                )
            )
    if status_filter in {"all", "blocked"}:
        for event_id, attempt_row in latest.items():
            if event_id in terminal_ids or attempt_row.status != "blocked":
                continue
            items.append(
                AdminFeatureReferenceReconciliationSummary(
                    event_id=event_id,
                    status="blocked",
                    event_sequence=attempt_row.event_sequence,
                    event_sha256=attempt_row.event_sha256,
                    observed_at=attempt_row.observed_at,
                    receipt=None,
                    latest_attempt=_attempt(attempt_row),
                )
            )
    items.sort(key=lambda row: (row.observed_at, str(row.event_id)), reverse=True)
    total = len(items)
    start = (page - 1) * limit
    return Envelope.of(
        AdminFeatureReferenceReconciliationPagedResponse(
            items=items[start : start + limit], total=total, page=page, limit=limit
        )
    )


@router.get("/{event_id}", response_model=Envelope[AdminFeatureReferenceReconciliationDetail])
async def get_feature_reference_reconciliation(
    event_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminFeatureReferenceReconciliationDetail]:
    """append-only local receipt, attempts, impacts를 원문 hash와 함께 반환한다."""

    receipt_row = await db.get(KtmFeatureReferenceReconciliationAppliedReceipt, event_id)
    attempt_rows = list(
        (
            await db.scalars(
                select(KtmFeatureReferenceReconciliationDeliveryAttempt)
                .where(KtmFeatureReferenceReconciliationDeliveryAttempt.event_id == event_id)
                .order_by(KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence.desc())
            )
        ).all()
    )
    if receipt_row is None and not attempt_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "조정 증거를 찾을 수 없습니다."},
        )
    impact_rows = (
        list(
            (
                await db.scalars(
                    select(KtmFeatureReferenceReconciliationImpact)
                    .where(KtmFeatureReferenceReconciliationImpact.event_id == event_id)
                    .order_by(KtmFeatureReferenceReconciliationImpact.impact_index)
                )
            ).all()
        )
        if receipt_row is not None
        else []
    )
    return Envelope.of(
        AdminFeatureReferenceReconciliationDetail(
            event_id=event_id,
            status="applied" if receipt_row is not None else "blocked",
            receipt=_receipt(receipt_row) if receipt_row is not None else None,
            attempts=[_attempt(row) for row in attempt_rows],
            impacts=[_impact(row) for row in impact_rows],
        )
    )
