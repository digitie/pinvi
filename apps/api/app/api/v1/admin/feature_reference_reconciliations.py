"""`/admin/feature-reference-reconciliations` — M05 local evidence read API."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Subquery

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


def _latest_attempts_subquery() -> Subquery:
    """event별 마지막 attempt만 DB에서 선택한다."""

    previous = aliased(KtmFeatureReferenceReconciliationDeliveryAttempt)
    latest_sequence = (
        select(func.max(previous.attempt_sequence))
        .where(previous.event_id == KtmFeatureReferenceReconciliationDeliveryAttempt.event_id)
        .correlate(KtmFeatureReferenceReconciliationDeliveryAttempt)
        .scalar_subquery()
    )
    return (
        select(
            KtmFeatureReferenceReconciliationDeliveryAttempt.event_id.label("event_id"),
            KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence.label(
                "attempt_sequence"
            ),
            KtmFeatureReferenceReconciliationDeliveryAttempt.status.label("attempt_status"),
        )
        .where(KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence == latest_sequence)
        .subquery()
    )


@router.get("", response_model=Envelope[AdminFeatureReferenceReconciliationPagedResponse])
async def list_feature_reference_reconciliations(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    status_filter: Annotated[Literal["blocked", "applied", "all"], Query(alias="status")] = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[AdminFeatureReferenceReconciliationPagedResponse]:
    """terminal receipt와 아직 ACK하지 않은 마지막 blocked 관측만 조회한다."""

    latest = _latest_attempts_subquery()
    applied = select(
        KtmFeatureReferenceReconciliationAppliedReceipt.event_id.label("event_id"),
        literal("applied").label("evidence_status"),
        KtmFeatureReferenceReconciliationAppliedReceipt.event_sequence.label("event_sequence"),
        KtmFeatureReferenceReconciliationAppliedReceipt.event_sha256.label("event_sha256"),
        KtmFeatureReferenceReconciliationAppliedReceipt.applied_at.label("observed_at"),
    ).join(latest, latest.c.event_id == KtmFeatureReferenceReconciliationAppliedReceipt.event_id)
    blocked = (
        select(
            KtmFeatureReferenceReconciliationDeliveryAttempt.event_id.label("event_id"),
            literal("blocked").label("evidence_status"),
            KtmFeatureReferenceReconciliationDeliveryAttempt.event_sequence.label("event_sequence"),
            KtmFeatureReferenceReconciliationDeliveryAttempt.event_sha256.label("event_sha256"),
            KtmFeatureReferenceReconciliationDeliveryAttempt.observed_at.label("observed_at"),
        )
        .join(
            latest,
            (latest.c.event_id == KtmFeatureReferenceReconciliationDeliveryAttempt.event_id)
            & (
                latest.c.attempt_sequence
                == KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence
            ),
        )
        .outerjoin(
            KtmFeatureReferenceReconciliationAppliedReceipt,
            KtmFeatureReferenceReconciliationAppliedReceipt.event_id
            == KtmFeatureReferenceReconciliationDeliveryAttempt.event_id,
        )
        .where(
            KtmFeatureReferenceReconciliationAppliedReceipt.event_id.is_(None),
            KtmFeatureReferenceReconciliationDeliveryAttempt.status == "blocked",
        )
    )
    if status_filter == "applied":
        candidates = applied.subquery()
    elif status_filter == "blocked":
        candidates = blocked.subquery()
    else:
        candidates = union_all(applied, blocked).subquery()
    total = int(await db.scalar(select(func.count()).select_from(candidates)) or 0)
    start = (page - 1) * limit
    page_rows = list(
        (
            await db.execute(
                select(candidates)
                .order_by(candidates.c.observed_at.desc(), candidates.c.event_id.desc())
                .offset(start)
                .limit(limit)
            )
        ).mappings()
    )
    event_ids = [row["event_id"] for row in page_rows]
    receipt_by_event = {
        row.event_id: row
        for row in (
            await db.scalars(
                select(KtmFeatureReferenceReconciliationAppliedReceipt).where(
                    KtmFeatureReferenceReconciliationAppliedReceipt.event_id.in_(event_ids)
                )
            )
        ).all()
    }
    attempt_rows = list(
        (
            await db.scalars(
                select(KtmFeatureReferenceReconciliationDeliveryAttempt)
                .where(KtmFeatureReferenceReconciliationDeliveryAttempt.event_id.in_(event_ids))
                .order_by(
                    KtmFeatureReferenceReconciliationDeliveryAttempt.event_id,
                    KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence.desc(),
                )
            )
        ).all()
    )
    latest_by_event: dict[uuid.UUID, KtmFeatureReferenceReconciliationDeliveryAttempt] = {}
    for attempt in attempt_rows:
        latest_by_event.setdefault(attempt.event_id, attempt)
    items: list[AdminFeatureReferenceReconciliationSummary] = []
    for row in page_rows:
        event_id = row["event_id"]
        latest_attempt = latest_by_event.get(event_id)
        if latest_attempt is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "FEATURE_REFERENCE_RECONCILIATION_EVIDENCE_INVALID",
                    "message": "증거 행에 대응하는 delivery attempt가 없습니다.",
                },
            )
        evidence_status = row["evidence_status"]
        items.append(
            AdminFeatureReferenceReconciliationSummary(
                event_id=event_id,
                status=evidence_status,
                event_sequence=row["event_sequence"],
                event_sha256=row["event_sha256"],
                observed_at=row["observed_at"],
                receipt=(
                    _receipt(receipt_by_event[event_id]) if evidence_status == "applied" else None
                ),
                latest_attempt=_attempt(latest_attempt),
            )
        )
    return Envelope.of(
        AdminFeatureReferenceReconciliationPagedResponse(
            items=items, total=total, page=page, limit=limit
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
