"""Data subject request workflow service — Sprint 6 T-278."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dsr import DsrRequest
from app.models.email_queue import EmailQueue
from app.models.user import User
from app.schemas.dsr import (
    DsrCompleteRequest,
    DsrIdentityCheckRequest,
    DsrProcessRequest,
    DsrRejectRequest,
    DsrRequestCreateRequest,
    DsrRequestListResponse,
    DsrRequestRecord,
    DsrRequestWithdrawRequest,
)
from app.services.admin_users import mask_email
from app.services.email_deliverability import email_hash
from app.services.hash_chain import sha256_hex

DSR_RESPONSE_SLA = timedelta(days=10)
OPEN_STATUSES = {"received", "identity_check", "processing"}
TERMINAL_STATUSES = {"completed", "rejected", "withdrawn"}


class DsrRequestNotFoundError(Exception):
    """Requested DSR row does not exist or is outside the caller scope."""


class DsrRequestTransitionError(Exception):
    """Requested state transition is not allowed."""


async def create_dsr_request(
    db: AsyncSession,
    *,
    user: User,
    body: DsrRequestCreateRequest,
) -> DsrRequest:
    received_at = datetime.now(UTC)
    row = DsrRequest(
        user_id=user.user_id,
        request_type=body.request_type,
        status="received",
        request_summary=body.request_summary,
        request_details=body.request_details,
        identity_proof_metadata={
            "method": "authenticated_session",
            "verified": False,
            "submitted_user_id": str(user.user_id),
            "submitted_at": received_at.isoformat(),
        },
        requester_email_hash=email_hash(user.email),
        requester_email_masked=mask_email(user.email),
        received_at=received_at,
        due_at=received_at + DSR_RESPONSE_SLA,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_user_dsr_requests(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    page_size: int,
) -> DsrRequestListResponse:
    conditions = [DsrRequest.user_id == user_id]
    stmt = (
        select(DsrRequest)
        .where(*conditions)
        .order_by(DsrRequest.created_at.desc())
        .limit(page_size)
    )
    count_stmt = select(func.count()).select_from(DsrRequest).where(*conditions)
    rows = list((await db.scalars(stmt)).all())
    total = int(await db.scalar(count_stmt) or 0)
    now = datetime.now(UTC)
    return DsrRequestListResponse(
        items=[to_dsr_request_record(row, now=now) for row in rows],
        page_size=page_size,
        total=total,
    )


async def list_dsr_requests(
    db: AsyncSession,
    *,
    status_filter: str | None,
    request_type: str | None,
    overdue: bool | None,
    page_size: int,
) -> DsrRequestListResponse:
    conditions: list[Any] = []
    if status_filter:
        conditions.append(DsrRequest.status == status_filter)
    if request_type:
        conditions.append(DsrRequest.request_type == request_type)
    now = datetime.now(UTC)
    if overdue is True:
        conditions.extend([DsrRequest.status.in_(OPEN_STATUSES), DsrRequest.due_at < now])
    elif overdue is False:
        conditions.append(or_(DsrRequest.status.not_in(OPEN_STATUSES), DsrRequest.due_at >= now))

    stmt = (
        select(DsrRequest)
        .where(*conditions)
        .order_by(DsrRequest.due_at.asc(), DsrRequest.created_at.desc())
        .limit(page_size)
    )
    count_stmt = select(func.count()).select_from(DsrRequest).where(*conditions)
    rows = list((await db.scalars(stmt)).all())
    total = int(await db.scalar(count_stmt) or 0)
    return DsrRequestListResponse(
        items=[to_dsr_request_record(row, now=now) for row in rows],
        page_size=page_size,
        total=total,
    )


async def get_dsr_request(db: AsyncSession, *, request_id: uuid.UUID) -> DsrRequest:
    row = await db.get(DsrRequest, request_id)
    if row is None:
        raise DsrRequestNotFoundError
    return row


async def get_user_dsr_request(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DsrRequest:
    row = await db.scalar(
        select(DsrRequest).where(DsrRequest.request_id == request_id, DsrRequest.user_id == user_id)
    )
    if row is None:
        raise DsrRequestNotFoundError
    return row


async def withdraw_dsr_request(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    user_id: uuid.UUID,
    body: DsrRequestWithdrawRequest,
) -> DsrRequest:
    row = await get_user_dsr_request(db, request_id=request_id, user_id=user_id)
    _require_status(row, OPEN_STATUSES, action="withdraw")
    current = datetime.now(UTC)
    row.status = "withdrawn"
    row.withdrawn_at = current
    _merge_request_details(
        row,
        {
            "withdrawal": {
                "reason": body.reason,
                "withdrawn_at": current.isoformat(),
            }
        },
    )
    await db.flush()
    await db.refresh(row)
    return row


async def identity_check_dsr_request(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    body: DsrIdentityCheckRequest,
    cpo_user_id: uuid.UUID,
) -> DsrRequest:
    row = await get_dsr_request(db, request_id=request_id)
    _require_status(row, {"received"}, action="identity_check")
    current = datetime.now(UTC)
    row.status = "identity_check"
    row.assigned_cpo_user_id = cpo_user_id
    row.identity_proof_metadata = {
        **(row.identity_proof_metadata or {}),
        "verified": body.identity_verified,
        "checked_by_user_id": str(cpo_user_id),
        "checked_at": current.isoformat(),
        "note": body.identity_note,
    }
    if body.identity_verified:
        row.identity_verified_at = current
    _set_evidence(row, body.evidence_attachment_id)
    await db.flush()
    await db.refresh(row)
    return row


async def process_dsr_request(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    body: DsrProcessRequest,
    cpo_user_id: uuid.UUID,
) -> DsrRequest:
    row = await get_dsr_request(db, request_id=request_id)
    _require_status(row, {"identity_check"}, action="process")
    if row.identity_verified_at is None:
        raise DsrRequestTransitionError("본인 확인 완료 기록 후 처리 단계로 전환해야 합니다.")
    current = datetime.now(UTC)
    row.status = "processing"
    row.assigned_cpo_user_id = cpo_user_id
    row.processing_started_at = current
    _merge_request_details(
        row,
        {
            "processing": {
                "note": body.processing_note,
                "started_by_user_id": str(cpo_user_id),
                "started_at": current.isoformat(),
            }
        },
    )
    _set_evidence(row, body.evidence_attachment_id)
    await db.flush()
    await db.refresh(row)
    return row


async def complete_dsr_request(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    body: DsrCompleteRequest,
    cpo_user_id: uuid.UUID,
) -> DsrRequest:
    row = await get_dsr_request(db, request_id=request_id)
    _require_status(row, {"processing"}, action="complete")
    current = datetime.now(UTC)
    row.status = "completed"
    row.assigned_cpo_user_id = cpo_user_id
    row.completed_at = current
    row.result_summary = body.result_summary
    row.export_manifest = body.export_manifest
    row.partial_response = body.partial_response
    _set_evidence(row, body.evidence_attachment_id)
    await _record_result_notice(
        db,
        row=row,
        status="completed",
        subject="Pinvi 개인정보 권리행사 처리 결과",
        result_text=body.result_summary,
        occurred_at=current,
    )
    await db.flush()
    await db.refresh(row)
    return row


async def reject_dsr_request(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    body: DsrRejectRequest,
    cpo_user_id: uuid.UUID,
) -> DsrRequest:
    row = await get_dsr_request(db, request_id=request_id)
    _require_status(row, {"identity_check", "processing"}, action="reject")
    current = datetime.now(UTC)
    row.status = "rejected"
    row.assigned_cpo_user_id = cpo_user_id
    row.rejected_at = current
    row.rejection_reason = body.rejection_reason
    row.result_summary = "요청을 처리할 수 없어 거절 통지를 기록했습니다."
    _set_evidence(row, body.evidence_attachment_id)
    await _record_result_notice(
        db,
        row=row,
        status="rejected",
        subject="Pinvi 개인정보 권리행사 처리 결과",
        result_text=body.rejection_reason,
        occurred_at=current,
    )
    await db.flush()
    await db.refresh(row)
    return row


def to_dsr_request_record(
    row: DsrRequest,
    *,
    now: datetime | None = None,
) -> DsrRequestRecord:
    current = now or datetime.now(UTC)
    return DsrRequestRecord(
        request_id=row.request_id,
        user_id=row.user_id,
        request_type=row.request_type,
        status=row.status,
        request_summary=row.request_summary,
        request_details=row.request_details or {},
        identity_proof_metadata=row.identity_proof_metadata or {},
        requester_email_masked=row.requester_email_masked,
        assigned_cpo_user_id=row.assigned_cpo_user_id,
        received_at=row.received_at,
        due_at=row.due_at,
        identity_verified_at=row.identity_verified_at,
        processing_started_at=row.processing_started_at,
        completed_at=row.completed_at,
        rejected_at=row.rejected_at,
        withdrawn_at=row.withdrawn_at,
        rejection_reason=row.rejection_reason,
        result_summary=row.result_summary,
        result_notice_hash=row.result_notice_hash,
        result_notice_email_id=row.result_notice_email_id,
        export_manifest=row.export_manifest or {},
        partial_response=row.partial_response,
        evidence_attachment_id=row.evidence_attachment_id,
        response_overdue=row.status in OPEN_STATUSES and row.due_at < current,
        next_action=_next_action(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _require_status(row: DsrRequest, allowed: set[str], *, action: str) -> None:
    if row.status not in allowed:
        raise DsrRequestTransitionError(f"{row.status} 상태에서는 {action} 조치를 할 수 없습니다.")


def _set_evidence(row: DsrRequest, evidence_attachment_id: uuid.UUID | None) -> None:
    if evidence_attachment_id is not None:
        row.evidence_attachment_id = evidence_attachment_id


def _merge_request_details(row: DsrRequest, patch: dict[str, Any]) -> None:
    details = dict(row.request_details or {})
    details.update(patch)
    row.request_details = details


async def _record_result_notice(
    db: AsyncSession,
    *,
    row: DsrRequest,
    status: str,
    subject: str,
    result_text: str,
    occurred_at: datetime,
) -> None:
    payload = {
        "request_id": str(row.request_id),
        "request_type": row.request_type,
        "status": status,
        "result_text": result_text,
        "partial_response": row.partial_response,
        "export_manifest": row.export_manifest or {},
        "occurred_at": occurred_at.isoformat(),
    }
    row.result_notice_hash = sha256_hex(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
    payload["result_notice_hash"] = row.result_notice_hash
    user = await db.get(User, row.user_id) if row.user_id else None
    if user is None or not user.email:
        return
    email = EmailQueue(
        user_id=user.user_id,
        to_email=user.email,
        template="dsr_result_notice",
        subject=subject,
        payload=payload,
        status="pending",
        scheduled_at=occurred_at,
    )
    db.add(email)
    await db.flush()
    row.result_notice_email_id = email.email_id


def _next_action(row: DsrRequest) -> str:
    if row.status == "received":
        return "identity_check"
    if row.status == "identity_check":
        return "process" if row.identity_verified_at is not None else "reject_or_verify"
    if row.status == "processing":
        return "complete_or_reject"
    if row.status in TERMINAL_STATUSES:
        return "none"
    return "review"
