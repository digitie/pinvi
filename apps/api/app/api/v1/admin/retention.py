"""`/admin/retention/*` — PII/location retention 실행 콘솔."""

from __future__ import annotations

import logging
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
    record_retention_run_failure,
)

logger = logging.getLogger(__name__)

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
        # 실행 실패의 원인 문자열은 SQLAlchemy 예외 전문(SQL + 바인드 파라미터)일 수 있다.
        # 그대로 HTTP 본문에 실으면 스키마와 데이터가 새어 나간다 — 상세는 영수증
        # (`retention_runs.error_message`)과 서버 로그에만 둔다.
        logger.warning("retention execute failed: %s", exc)
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": exc.code,
                "message": "보존 작업 실행에 실패했습니다. 실행 영수증에서 원인을 확인하세요.",
            },
        )
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
        # 서비스가 이미 rollback + 실패 영수증까지 끝냈다. 이 rollback은 no-op이지만, 서비스가
        # 예외를 다른 경로로 던졌을 때를 대비해 남긴다.
        await db.rollback()
        raise _error_response(exc) from exc

    # 여기까지 오면 파괴적 작업과 `completed` UPDATE가 **아직 커밋되지 않은** 상태다. 아래 감사
    # 적재나 commit이 실패하면 파괴 작업은 폐기되는데, 그때 영수증이 `executing`으로 굳으면
    # "무엇을 시도했고 어디서 멈췄는가"가 남지 않는다 — 이 후단도 복구 대상이다(T-339).
    try:
        await _finalize_execute(
            db,
            run=run,
            admin=admin,
            request=request,
            access_reason=body.access_reason,
            request_id=request_id,
        )
    except Exception as exc:
        await record_retention_run_failure(db, run.run_id, exc)
        raise _error_response(RetentionExecutionError(str(exc))) from exc

    return Envelope.of(run)


async def _finalize_execute(
    db: DbSession,
    *,
    run: AdminRetentionRun,
    admin: User,
    request: Request,
    access_reason: str,
    request_id: uuid.UUID,
) -> None:
    """파괴적 작업과 감사 기록을 **한 커밋으로** 확정한다.

    이 커밋이 성공해야 비로소 무언가 지워진 것이다. 그 전에 실패하면 전부 폐기된다 — 그래서
    `executing`/`failed` 영수증은 곧 "아무것도 지워지지 않았다"를 뜻한다.
    """
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="retention.execute",
        resource_type="retention_run",
        resource_id=str(run.run_id),
        before_state=run.candidate_snapshot,
        after_state=run.model_dump(mode="json"),
        access_reason=access_reason,
        target_pii_fields=["email", "password_hash", "oauth_identity", "location_access_log"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
    await db.commit()
