"""`/admin/incidents` — PIPA security incident CPO workflow."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.v1.admin.ops_proxy import parse_request_id
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.security import SecurityIncident
from app.models.user import User
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
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.admin_security_incidents import (
    SecurityIncidentNotFoundError,
    SecurityIncidentTransitionError,
    close_security_incident,
    create_security_incident,
    decide_security_incident_notification,
    get_security_incident,
    list_security_incidents,
    notify_security_incident_subjects,
    report_security_incident_external,
    to_security_incident_record,
    triage_security_incident,
)

router = APIRouter(prefix="/admin/incidents", tags=["admin"])


@router.get("", response_model=Envelope[AdminSecurityIncidentListResponse])
async def list_incidents(
    _admin: Annotated[User, Depends(require_role("admin", "cpo"))],
    db: DbSession,
    status_filter: Annotated[
        str | None,
        Query(
            alias="status",
            pattern="^(detected|triage|notification_decision|reported|closed)$",
        ),
    ] = None,
    severity: Annotated[
        str | None,
        Query(pattern="^(low|medium|high|critical)$"),
    ] = None,
    overdue: Annotated[
        str | None,
        Query(pattern="^(cpo_review|external_report)$"),
    ] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Envelope[AdminSecurityIncidentListResponse]:
    result = await list_security_incidents(
        db,
        status_filter=status_filter,
        severity=severity,
        overdue=overdue,
        page_size=page_size,
    )
    return Envelope.of(result)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[AdminSecurityIncidentRecord],
)
async def create_incident(
    body: AdminSecurityIncidentCreateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin", "cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminSecurityIncidentRecord]:
    request_id = parse_request_id(x_request_id)
    incident = await create_security_incident(
        db,
        body=body,
        actor_user_id=admin.user_id,
        request_id=request_id,
    )
    after = to_security_incident_record(incident).model_dump(mode="json")
    await _append_audit(
        db,
        request=request,
        actor=admin,
        action="security_incident.create",
        resource_id=str(incident.incident_id),
        before_state=None,
        after_state=after,
        access_reason=body.access_reason,
        request_id=request_id,
        target_pii_fields=None,
    )
    await db.commit()
    return Envelope.of(to_security_incident_record(incident))


@router.post(
    "/{incident_id}/triage",
    response_model=Envelope[AdminSecurityIncidentRecord],
)
async def triage_incident(
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentTriageRequest,
    request: Request,
    cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminSecurityIncidentRecord]:
    return await _mutate_incident(
        db=db,
        request=request,
        actor=cpo,
        request_id=parse_request_id(x_request_id),
        incident_id=incident_id,
        access_reason=body.access_reason,
        action="security_incident.triage",
        target_pii_fields=None,
        mutate=lambda: triage_security_incident(
            db,
            incident_id=incident_id,
            body=body,
            cpo_user_id=cpo.user_id,
        ),
    )


@router.post(
    "/{incident_id}/notification-decision",
    response_model=Envelope[AdminSecurityIncidentRecord],
)
async def decide_notification(
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentDecisionRequest,
    request: Request,
    cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminSecurityIncidentRecord]:
    return await _mutate_incident(
        db=db,
        request=request,
        actor=cpo,
        request_id=parse_request_id(x_request_id),
        incident_id=incident_id,
        access_reason=body.access_reason,
        action="security_incident.notification_decision",
        target_pii_fields=None,
        mutate=lambda: decide_security_incident_notification(
            db,
            incident_id=incident_id,
            body=body,
        ),
    )


@router.post(
    "/{incident_id}/notify",
    response_model=Envelope[AdminSecurityIncidentRecord],
)
async def notify_subjects(
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentNotifyRequest,
    request: Request,
    cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminSecurityIncidentRecord]:
    return await _mutate_incident(
        db=db,
        request=request,
        actor=cpo,
        request_id=parse_request_id(x_request_id),
        incident_id=incident_id,
        access_reason=body.access_reason,
        action="security_incident.notify_subjects",
        target_pii_fields=["email"] if body.recipient_email else None,
        mutate=lambda: notify_security_incident_subjects(
            db,
            incident_id=incident_id,
            body=body,
        ),
    )


@router.post(
    "/{incident_id}/report",
    response_model=Envelope[AdminSecurityIncidentRecord],
)
async def report_external(
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentReportRequest,
    request: Request,
    cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminSecurityIncidentRecord]:
    return await _mutate_incident(
        db=db,
        request=request,
        actor=cpo,
        request_id=parse_request_id(x_request_id),
        incident_id=incident_id,
        access_reason=body.access_reason,
        action="security_incident.report_external",
        target_pii_fields=None,
        mutate=lambda: report_security_incident_external(
            db,
            incident_id=incident_id,
            body=body,
        ),
    )


@router.post(
    "/{incident_id}/close",
    response_model=Envelope[AdminSecurityIncidentRecord],
)
async def close_incident(
    incident_id: uuid.UUID,
    body: AdminSecurityIncidentCloseRequest,
    request: Request,
    cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminSecurityIncidentRecord]:
    return await _mutate_incident(
        db=db,
        request=request,
        actor=cpo,
        request_id=parse_request_id(x_request_id),
        incident_id=incident_id,
        access_reason=body.access_reason,
        action="security_incident.close",
        target_pii_fields=None,
        mutate=lambda: close_security_incident(
            db,
            incident_id=incident_id,
            body=body,
        ),
    )


async def _mutate_incident(
    *,
    db: DbSession,
    request: Request,
    actor: User,
    request_id: uuid.UUID,
    incident_id: uuid.UUID,
    access_reason: str,
    action: str,
    target_pii_fields: list[str] | None,
    mutate: Callable[[], Awaitable[SecurityIncident]],
) -> Envelope[AdminSecurityIncidentRecord]:
    try:
        before_incident = await get_security_incident(db, incident_id=incident_id)
        before = to_security_incident_record(before_incident).model_dump(mode="json")
        incident = await mutate()
    except SecurityIncidentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "incident를 찾을 수 없습니다."},
        ) from exc
    except SecurityIncidentTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE", "message": str(exc)},
        ) from exc

    after = to_security_incident_record(incident).model_dump(mode="json")
    await _append_audit(
        db,
        request=request,
        actor=actor,
        action=action,
        resource_id=str(incident.incident_id),
        before_state=before,
        after_state=after,
        access_reason=access_reason,
        request_id=request_id,
        target_pii_fields=target_pii_fields,
    )
    await db.commit()
    return Envelope.of(to_security_incident_record(incident))


async def _append_audit(
    db: DbSession,
    *,
    request: Request,
    actor: User,
    action: str,
    resource_id: str,
    before_state: dict[str, object] | None,
    after_state: dict[str, object] | None,
    access_reason: str,
    request_id: uuid.UUID,
    target_pii_fields: list[str] | None,
) -> None:
    await append_admin_audit(
        db,
        actor_user_id=actor.user_id,
        action=action,
        resource_type="security_incident",
        resource_id=resource_id,
        before_state=before_state,
        after_state=after_state,
        access_reason=access_reason,
        target_pii_fields=target_pii_fields,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
