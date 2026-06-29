"""`/admin/abuse` — ADR-038 rate-limit and abuse operations."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.v1.admin.ops_proxy import parse_request_id
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminRateLimitAbuseSummary,
    AdminRateLimitOverrideCreateRequest,
    AdminRateLimitOverrideRecord,
    AdminRateLimitOverrideRollbackRequest,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.admin_rate_limit_abuse import (
    RateLimitOverrideNotFoundError,
    RateLimitOverrideTransitionError,
    RateLimitOverrideValidationError,
    build_rate_limit_abuse_summary,
    create_rate_limit_override,
    rollback_rate_limit_override,
    to_rate_limit_override_record,
)

router = APIRouter(prefix="/admin/abuse", tags=["admin"])


@router.get("", response_model=Envelope[AdminRateLimitAbuseSummary])
async def get_rate_limit_abuse_summary(
    _admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
    db: DbSession,
    limit_name: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 100,
) -> Envelope[AdminRateLimitAbuseSummary]:
    try:
        summary = await build_rate_limit_abuse_summary(
            db,
            limit_name=limit_name,
            page_size=page_size,
        )
    except RateLimitOverrideValidationError as exc:
        raise _http_error(exc, status.HTTP_422_UNPROCESSABLE_ENTITY) from exc
    return Envelope.of(summary)


@router.post(
    "/overrides",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[AdminRateLimitOverrideRecord],
)
async def create_override(
    body: AdminRateLimitOverrideCreateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminRateLimitOverrideRecord]:
    request_id = parse_request_id(x_request_id)
    try:
        row = await create_rate_limit_override(db, body=body, actor_user_id=admin.user_id)
    except RateLimitOverrideValidationError as exc:
        raise _http_error(exc, status.HTTP_422_UNPROCESSABLE_ENTITY) from exc
    record = to_rate_limit_override_record(row)
    after_state = record.model_dump(mode="json")
    await _append_audit(
        db=db,
        request=request,
        actor=admin,
        action="rate_limit_override.create",
        resource_id=str(row.override_id),
        before_state=None,
        after_state=after_state,
        access_reason=body.access_reason,
        request_id=request_id,
    )
    await db.commit()
    return Envelope.of(record)


@router.post(
    "/overrides/{override_id}/rollback",
    response_model=Envelope[AdminRateLimitOverrideRecord],
)
async def rollback_override(
    override_id: uuid.UUID,
    body: AdminRateLimitOverrideRollbackRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminRateLimitOverrideRecord]:
    request_id = parse_request_id(x_request_id)
    before_row = None
    try:
        from app.models.rate_limit import RateLimitOverride

        before_row = await db.get(RateLimitOverride, override_id)
        before_state = (
            to_rate_limit_override_record(before_row).model_dump(mode="json")
            if before_row is not None
            else None
        )
        row = await rollback_rate_limit_override(
            db,
            override_id=override_id,
            body=body,
            actor_user_id=admin.user_id,
        )
    except RateLimitOverrideNotFoundError as exc:
        raise _http_error(exc, status.HTTP_404_NOT_FOUND) from exc
    except RateLimitOverrideTransitionError as exc:
        raise _http_error(exc, status.HTTP_409_CONFLICT) from exc
    record = to_rate_limit_override_record(row)
    await _append_audit(
        db=db,
        request=request,
        actor=admin,
        action="rate_limit_override.rollback",
        resource_id=str(row.override_id),
        before_state=before_state,
        after_state=record.model_dump(mode="json"),
        access_reason=body.access_reason,
        request_id=request_id,
    )
    await db.commit()
    return Envelope.of(record)


async def _append_audit(
    *,
    db: DbSession,
    request: Request,
    actor: User,
    action: str,
    resource_id: str,
    before_state: dict[str, object] | None,
    after_state: dict[str, object] | None,
    access_reason: str,
    request_id: uuid.UUID,
) -> None:
    await append_admin_audit(
        db,
        actor_user_id=actor.user_id,
        action=action,
        resource_type="rate_limit_override",
        resource_id=resource_id,
        before_state=before_state,
        after_state=after_state,
        access_reason=access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )


def _http_error(exc: Exception, status_code: int) -> HTTPException:
    code = getattr(exc, "code", "RATE_LIMIT_ABUSE_ERROR")
    return HTTPException(status_code=status_code, detail={"code": code, "message": str(exc)})
