"""`/admin/dsr` — CPO data subject request workflow."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.v1.admin.ops_proxy import parse_request_id
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.dsr import DsrRequest
from app.models.user import User
from app.schemas.dsr import (
    DsrCompleteRequest,
    DsrIdentityCheckRequest,
    DsrProcessRequest,
    DsrRejectRequest,
    DsrRequestListResponse,
    DsrRequestRecord,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.dsr_requests import (
    DsrRequestNotFoundError,
    DsrRequestTransitionError,
    complete_dsr_request,
    get_dsr_request,
    identity_check_dsr_request,
    list_dsr_requests,
    process_dsr_request,
    reject_dsr_request,
    to_dsr_request_record,
)

router = APIRouter(prefix="/admin/dsr", tags=["admin"])


@router.get("", response_model=Envelope[DsrRequestListResponse])
async def list_admin_dsr_requests(
    _admin: Annotated[User, Depends(require_role("admin", "cpo"))],
    db: DbSession,
    status_filter: Annotated[
        str | None,
        Query(
            alias="status",
            pattern="^(received|identity_check|processing|completed|rejected|withdrawn)$",
        ),
    ] = None,
    request_type: Annotated[
        str | None,
        Query(pattern="^(access|correction|delete|suspend)$"),
    ] = None,
    overdue: bool | None = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Envelope[DsrRequestListResponse]:
    result = await list_dsr_requests(
        db,
        status_filter=status_filter,
        request_type=request_type,
        overdue=overdue,
        page_size=page_size,
    )
    return Envelope.of(result)


@router.post(
    "/{request_id}/identity-check",
    response_model=Envelope[DsrRequestRecord],
)
async def identity_check_request(
    request_id: uuid.UUID,
    body: DsrIdentityCheckRequest,
    request: Request,
    cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[DsrRequestRecord]:
    return await _mutate_dsr_request(
        db=db,
        request=request,
        actor=cpo,
        request_id=parse_request_id(x_request_id),
        dsr_request_id=request_id,
        access_reason=body.access_reason,
        action="dsr.identity_check",
        target_pii_fields=["email"],
        mutate=lambda: identity_check_dsr_request(
            db,
            request_id=request_id,
            body=body,
            cpo_user_id=cpo.user_id,
        ),
    )


@router.post(
    "/{request_id}/process",
    response_model=Envelope[DsrRequestRecord],
)
async def process_request(
    request_id: uuid.UUID,
    body: DsrProcessRequest,
    request: Request,
    cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[DsrRequestRecord]:
    return await _mutate_dsr_request(
        db=db,
        request=request,
        actor=cpo,
        request_id=parse_request_id(x_request_id),
        dsr_request_id=request_id,
        access_reason=body.access_reason,
        action="dsr.process",
        target_pii_fields=["email"],
        mutate=lambda: process_dsr_request(
            db,
            request_id=request_id,
            body=body,
            cpo_user_id=cpo.user_id,
        ),
    )


@router.post(
    "/{request_id}/complete",
    response_model=Envelope[DsrRequestRecord],
)
async def complete_request(
    request_id: uuid.UUID,
    body: DsrCompleteRequest,
    request: Request,
    cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[DsrRequestRecord]:
    return await _mutate_dsr_request(
        db=db,
        request=request,
        actor=cpo,
        request_id=parse_request_id(x_request_id),
        dsr_request_id=request_id,
        access_reason=body.access_reason,
        action="dsr.complete",
        target_pii_fields=["email", "profile", "location"],
        mutate=lambda: complete_dsr_request(
            db,
            request_id=request_id,
            body=body,
            cpo_user_id=cpo.user_id,
        ),
    )


@router.post(
    "/{request_id}/reject",
    response_model=Envelope[DsrRequestRecord],
)
async def reject_request(
    request_id: uuid.UUID,
    body: DsrRejectRequest,
    request: Request,
    cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[DsrRequestRecord]:
    return await _mutate_dsr_request(
        db=db,
        request=request,
        actor=cpo,
        request_id=parse_request_id(x_request_id),
        dsr_request_id=request_id,
        access_reason=body.access_reason,
        action="dsr.reject",
        target_pii_fields=["email"],
        mutate=lambda: reject_dsr_request(
            db,
            request_id=request_id,
            body=body,
            cpo_user_id=cpo.user_id,
        ),
    )


async def _mutate_dsr_request(
    *,
    db: DbSession,
    request: Request,
    actor: User,
    request_id: uuid.UUID,
    dsr_request_id: uuid.UUID,
    access_reason: str,
    action: str,
    target_pii_fields: list[str],
    mutate: Callable[[], Awaitable[DsrRequest]],
) -> Envelope[DsrRequestRecord]:
    try:
        before_row = await get_dsr_request(db, request_id=dsr_request_id)
        before = to_dsr_request_record(before_row).model_dump(mode="json")
        row = await mutate()
    except DsrRequestNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "DSR 요청을 찾을 수 없습니다."},
        ) from exc
    except DsrRequestTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE", "message": str(exc)},
        ) from exc

    after = to_dsr_request_record(row).model_dump(mode="json")
    await append_admin_audit(
        db,
        actor_user_id=actor.user_id,
        action=action,
        resource_type="dsr_request",
        resource_id=str(row.request_id),
        before_state=before,
        after_state=after,
        access_reason=access_reason,
        target_pii_fields=target_pii_fields,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
    await db.commit()
    return Envelope.of(to_dsr_request_record(row))
