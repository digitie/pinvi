"""`/admin/retention/*` — PII/location retention 실행 콘솔."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminRetentionDryRunRequest,
    AdminRetentionExecuteRequest,
    AdminRetentionRun,
    AdminRetentionRunListResponse,
    AdminRetentionSummary,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.admin_retention import (
    RetentionConfirmPhraseError,
    RetentionExecutionError,
    RetentionKillSwitchDisabledError,
    RetentionPrecheckError,
    build_retention_summary,
    create_retention_dry_run,
    execute_retention,
    list_retention_runs,
)

router = APIRouter(prefix="/admin/retention", tags=["admin"])


def _request_uuid(value: str | None) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except ValueError:
        return uuid.uuid4()


def _error_response(exc: RetentionExecutionError) -> HTTPException:
    if isinstance(exc, RetentionKillSwitchDisabledError):
        http_status = status.HTTP_409_CONFLICT
    elif isinstance(exc, RetentionConfirmPhraseError):
        http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(exc, RetentionPrecheckError):
        http_status = status.HTTP_409_CONFLICT
    else:
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    return HTTPException(
        status_code=http_status,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.get("/summary", response_model=Envelope[AdminRetentionSummary])
async def get_retention_summary(
    _admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
    db: DbSession,
) -> Envelope[AdminRetentionSummary]:
    return Envelope.of(await build_retention_summary(db))


@router.get("/runs", response_model=Envelope[AdminRetentionRunListResponse])
async def list_retention_runs_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
    db: DbSession,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Envelope[AdminRetentionRunListResponse]:
    return Envelope.of(
        AdminRetentionRunListResponse(
            items=await list_retention_runs(db, page_size=page_size),
            page_size=page_size,
        )
    )


@router.post("/dry-run", response_model=Envelope[AdminRetentionRun])
async def create_retention_dry_run_endpoint(
    body: AdminRetentionDryRunRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminRetentionRun]:
    request_id = _request_uuid(x_request_id)
    run = await create_retention_dry_run(
        db,
        actor_user_id=admin.user_id,
        scope=body.scope,
        access_reason=body.access_reason,
    )
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="retention.dry_run",
        resource_type="retention_run",
        resource_id=str(run.run_id),
        before_state=None,
        after_state=run.model_dump(mode="json"),
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
    await db.commit()
    return Envelope.of(run)


@router.post("/execute", response_model=Envelope[AdminRetentionRun])
async def execute_retention_endpoint(
    body: AdminRetentionExecuteRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin", "cpo"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminRetentionRun]:
    request_id = _request_uuid(x_request_id)
    try:
        run = await execute_retention(
            db,
            actor_user_id=admin.user_id,
            scope=body.scope,
            access_reason=body.access_reason,
            confirm_phrase=body.confirm_phrase,
        )
    except RetentionExecutionError as exc:
        await db.rollback()
        raise _error_response(exc) from exc

    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="retention.execute",
        resource_type="retention_run",
        resource_id=str(run.run_id),
        before_state=run.candidate_snapshot,
        after_state=run.model_dump(mode="json"),
        access_reason=body.access_reason,
        target_pii_fields=["email", "password_hash", "oauth_identity", "location_access_log"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
    await db.commit()
    return Envelope.of(run)
