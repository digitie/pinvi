"""Admin security incident workflow service — Sprint 6 T-275."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_queue import EmailQueue
from app.models.security import SecurityIncident
from app.schemas.admin import (
    AdminSecurityIncidentCloseRequest,
    AdminSecurityIncidentCreateRequest,
    AdminSecurityIncidentDecisionRequest,
    AdminSecurityIncidentListResponse,
    AdminSecurityIncidentNotifyRequest,
    AdminSecurityIncidentRecord,
    AdminSecurityIncidentReportRequest,
    AdminSecurityIncidentTriageRequest,
)
from app.services.hash_chain import sha256_hex
from app.services.telegram_outbox import enqueue_admin_notification

CPO_REVIEW_SLA = timedelta(minutes=30)
EXTERNAL_REPORT_SLA = timedelta(hours=72)


class SecurityIncidentNotFoundError(Exception):
    """Requested incident does not exist."""


class SecurityIncidentTransitionError(Exception):
    """Requested state transition is not allowed."""


async def list_security_incidents(
    db: AsyncSession,
    *,
    status_filter: str | None,
    severity: str | None,
    overdue: str | None,
    page_size: int,
) -> AdminSecurityIncidentListResponse:
    conditions: list[Any] = []
    if status_filter:
        conditions.append(SecurityIncident.status == status_filter)
    if severity:
        conditions.append(SecurityIncident.severity == severity)
    now = datetime.now(UTC)
    if overdue == "cpo_review":
        conditions.extend(
            [
                SecurityIncident.status == "detected",
                SecurityIncident.acknowledged_at.is_(None),
                SecurityIncident.cpo_review_due_at < now,
            ]
        )
    elif overdue == "external_report":
        conditions.extend(
            [
                SecurityIncident.status != "closed",
                SecurityIncident.kisa_reported_at.is_(None),
                SecurityIncident.external_report_due_at < now,
            ]
        )

    stmt = (
        select(SecurityIncident)
        .where(*conditions)
        .order_by(SecurityIncident.detected_at.desc())
        .limit(page_size)
    )
    count_stmt = select(func.count()).select_from(SecurityIncident).where(*conditions)
    rows = list((await db.scalars(stmt)).all())
    total = int(await db.scalar(count_stmt) or 0)
    return AdminSecurityIncidentListResponse(
        items=[to_security_incident_record(row, now=now) for row in rows],
        page_size=page_size,
        total=total,
    )


async def create_security_incident(
    db: AsyncSession,
    *,
    body: AdminSecurityIncidentCreateRequest,
    actor_user_id: uuid.UUID,
    request_id: uuid.UUID | None,
) -> SecurityIncident:
    detected_at = body.detected_at or datetime.now(UTC)
    incident = SecurityIncident(
        incident_type=body.incident_type,
        severity=body.severity,
        status="detected",
        source=body.source,
        summary=body.summary,
        details=body.details,
        affected_user_count=body.affected_user_count,
        assigned_cpo_user_id=actor_user_id,
        request_id=request_id,
        detected_at=detected_at,
        cpo_review_due_at=detected_at + CPO_REVIEW_SLA,
        external_report_due_at=detected_at + EXTERNAL_REPORT_SLA,
        evidence_attachment_id=body.evidence_attachment_id,
    )
    db.add(incident)
    await db.flush()
    text = (
        "[Pinvi security incident]\n"
        f"{incident.severity.upper()} {incident.incident_type}\n"
        f"{incident.summary}\n"
        f"incident_id={incident.incident_id}"
    )
    await enqueue_admin_notification(
        db,
        category="security_incident",
        text=text,
        payload={
            "incident_id": str(incident.incident_id),
            "severity": incident.severity,
            "incident_type": incident.incident_type,
        },
    )
    incident.cpo_notified_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(incident)
    return incident


async def get_security_incident(db: AsyncSession, *, incident_id: uuid.UUID) -> SecurityIncident:
    incident = await db.get(SecurityIncident, incident_id)
    if incident is None:
        raise SecurityIncidentNotFoundError
    return incident


async def triage_security_incident(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentTriageRequest,
    cpo_user_id: uuid.UUID,
) -> SecurityIncident:
    incident = await get_security_incident(db, incident_id=incident_id)
    _require_status(incident, {"detected"}, action="triage")
    incident.status = "triage"
    incident.assigned_cpo_user_id = cpo_user_id
    incident.acknowledged_at = datetime.now(UTC)
    _set_evidence(incident, body.evidence_attachment_id)
    await db.flush()
    await db.refresh(incident)
    return incident


async def decide_security_incident_notification(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentDecisionRequest,
) -> SecurityIncident:
    incident = await get_security_incident(db, incident_id=incident_id)
    _require_status(incident, {"triage"}, action="notification_decision")
    incident.status = "notification_decision"
    incident.notification_required = body.notification_required
    incident.notification_decision_at = datetime.now(UTC)
    _merge_details(
        incident,
        {
            "notification_decision": {
                "required": body.notification_required,
                "reason": body.decision_reason,
                "decided_at": incident.notification_decision_at.isoformat(),
            }
        },
    )
    _set_evidence(incident, body.evidence_attachment_id)
    await db.flush()
    await db.refresh(incident)
    return incident


async def notify_security_incident_subjects(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentNotifyRequest,
) -> SecurityIncident:
    incident = await get_security_incident(db, incident_id=incident_id)
    _require_status(incident, {"notification_decision"}, action="notify")
    if not incident.notification_required:
        raise SecurityIncidentTransitionError("정보주체 통지 필요 판정이 없는 incident입니다.")

    current = datetime.now(UTC)
    payload = {
        "incident_id": str(incident.incident_id),
        "subject": body.subject,
        "message": body.message,
        "recipient_email": body.recipient_email,
        "notified_at": current.isoformat(),
    }
    incident.notification_payload_hash = sha256_hex(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
    incident.notified_at = current
    if body.recipient_email:
        db.add(
            EmailQueue(
                user_id=None,
                to_email=body.recipient_email,
                template="security_incident_notice",
                subject=body.subject,
                payload={
                    **payload,
                    "notification_payload_hash": incident.notification_payload_hash,
                },
                status="pending",
                scheduled_at=current,
            )
        )
    _merge_details(
        incident,
        {
            "subject_notification": {
                "queued_email": bool(body.recipient_email),
                "payload_hash": incident.notification_payload_hash,
                "notified_at": current.isoformat(),
            }
        },
    )
    await db.flush()
    await db.refresh(incident)
    return incident


async def report_security_incident_external(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentReportRequest,
) -> SecurityIncident:
    incident = await get_security_incident(db, incident_id=incident_id)
    _require_status(incident, {"notification_decision"}, action="report")
    if incident.notification_required and incident.notified_at is None:
        raise SecurityIncidentTransitionError("정보주체 통지 기록 후 외부 신고를 기록해야 합니다.")
    incident.status = "reported"
    incident.kisa_reported_at = datetime.now(UTC)
    incident.external_report_receipt_ref = body.receipt_ref
    _set_evidence(incident, body.evidence_attachment_id)
    await db.flush()
    await db.refresh(incident)
    return incident


async def close_security_incident(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentCloseRequest,
) -> SecurityIncident:
    incident = await get_security_incident(db, incident_id=incident_id)
    if incident.status == "reported":
        pass
    elif incident.status == "notification_decision" and not incident.notification_required:
        pass
    else:
        raise SecurityIncidentTransitionError(
            "reported 상태이거나 통지 불필요 판정이 있어야 incident를 닫을 수 있습니다."
        )
    incident.status = "closed"
    incident.resolved_at = datetime.now(UTC)
    _merge_details(
        incident,
        {
            "closure": {
                "note": body.closure_note,
                "closed_at": incident.resolved_at.isoformat(),
            }
        },
    )
    _set_evidence(incident, body.evidence_attachment_id)
    await db.flush()
    await db.refresh(incident)
    return incident


def to_security_incident_record(
    incident: SecurityIncident,
    *,
    now: datetime | None = None,
) -> AdminSecurityIncidentRecord:
    current = now or datetime.now(UTC)
    return AdminSecurityIncidentRecord(
        incident_id=incident.incident_id,
        incident_type=incident.incident_type,
        severity=incident.severity,
        status=incident.status,
        source=incident.source,
        summary=incident.summary,
        details=incident.details or {},
        affected_user_count=incident.affected_user_count,
        notification_required=incident.notification_required,
        assigned_cpo_user_id=incident.assigned_cpo_user_id,
        request_id=incident.request_id,
        detected_at=incident.detected_at,
        cpo_review_due_at=incident.cpo_review_due_at,
        external_report_due_at=incident.external_report_due_at,
        cpo_notified_at=incident.cpo_notified_at,
        acknowledged_at=incident.acknowledged_at,
        notification_decision_at=incident.notification_decision_at,
        notified_at=incident.notified_at,
        kisa_reported_at=incident.kisa_reported_at,
        resolved_at=incident.resolved_at,
        notification_payload_hash=incident.notification_payload_hash,
        external_report_receipt_ref=incident.external_report_receipt_ref,
        evidence_attachment_id=incident.evidence_attachment_id,
        cpo_review_overdue=(
            incident.status == "detected"
            and incident.acknowledged_at is None
            and incident.cpo_review_due_at < current
        ),
        external_report_overdue=(
            incident.status != "closed"
            and incident.kisa_reported_at is None
            and incident.external_report_due_at < current
        ),
        next_action=_next_action(incident),
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


def _require_status(
    incident: SecurityIncident,
    allowed: set[str],
    *,
    action: str,
) -> None:
    if incident.status not in allowed:
        raise SecurityIncidentTransitionError(
            f"{incident.status} 상태에서는 {action} 조치를 할 수 없습니다."
        )


def _set_evidence(incident: SecurityIncident, evidence_attachment_id: uuid.UUID | None) -> None:
    if evidence_attachment_id is not None:
        incident.evidence_attachment_id = evidence_attachment_id


def _merge_details(incident: SecurityIncident, patch: dict[str, Any]) -> None:
    details = dict(incident.details or {})
    details.update(patch)
    incident.details = details


def _next_action(incident: SecurityIncident) -> str:
    if incident.status == "detected":
        return "triage"
    if incident.status == "triage":
        return "notification_decision"
    if incident.status == "notification_decision":
        if incident.notification_required and incident.notified_at is None:
            return "notify_subjects"
        if incident.kisa_reported_at is None:
            return "report_external"
        return "close"
    if incident.status == "reported":
        return "close"
    return "none"
