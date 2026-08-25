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


_MASKED_ERROR_MESSAGE = "보존 작업 실행에 실패했습니다. 상세 원인은 서버 로그를 확인하세요."


def _mask_error_message(run: AdminRetentionRun) -> AdminRetentionRun:
    """`error_message` 원문을 응답에서 가린다(T-347).

    `retention_runs.error_message`는 SQLAlchemy 예외 전문(SQL + 바인드 파라미터)일 수 있다.
    `/execute`의 503 응답 본문은 이미 원문을 감췄는데(T-339), 같은 값을 이 두 endpoint가
    role만 다르게(admin/operator/cpo — execute는 admin/cpo뿐) 그대로 돌려주면 앞뒤가 안 맞는다.
    실행 권한이 없는 operator가 실행 실패의 원시 SQL을 읽게 된다.

    DB 컬럼과 서비스 레이어(`_run_from_row`, `record_retention_run_failure`)는 건드리지 않는다 —
    원문은 그대로 남아야 runbook §5.2의 직접 SQL 진단 경로가 계속 동작한다. 마스킹은 이 응답
    레이어 하나뿐이다.
    """
    if run.error_message is None:
        return run
    return run.model_copy(update={"error_message": _MASKED_ERROR_MESSAGE})


@router.get("/summary", response_model=Envelope[AdminRetentionSummary])
async def get_retention_summary(
    _admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
    db: DbSession,
) -> Envelope[AdminRetentionSummary]:
    summary = await build_retention_summary(db)
    summary.latest_runs = [_mask_error_message(run) for run in summary.latest_runs]
    return Envelope.of(summary)


@router.get("/runs", response_model=Envelope[AdminRetentionRunListResponse])
async def list_retention_runs_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
    db: DbSession,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Envelope[AdminRetentionRunListResponse]:
    items = await list_retention_runs(db, page_size=page_size)
    return Envelope.of(
        AdminRetentionRunListResponse(
            items=[_mask_error_message(run) for run in items],
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
    # `db.rollback()`은 이 세션의 **모든 ORM 인스턴스를 만료시킨다**(T-339이 `record_retention_run_
    # failure`에서 이미 겪은 것과 같은 성질). 그 뒤에 `admin.user_id`를 읽으면 만료된 인스턴스를
    # 새로고침하려는 지연 쿼리가 async 세션 바깥에서 실행돼 `MissingGreenlet`으로 죽는다. rollback이
    # 일어나기 전, 아직 멀쩡할 때 값을 미리 뽑아 둔다.
    actor_id = admin.user_id
    try:
        run = await execute_retention(
            db,
            actor_user_id=actor_id,
            scope=body.scope,
            access_reason=body.access_reason,
            confirm_phrase=body.confirm_phrase,
        )
    except RetentionExecutionError as exc:
        # 서비스가 이미 rollback + 실패 영수증까지 끝냈다. 이 rollback은 no-op이지만, 서비스가
        # 예외를 다른 경로로 던졌을 때를 대비해 남긴다.
        await db.rollback()
        await _append_execute_failure_audit(
            db,
            run_id=exc.run_id,
            actor_id=actor_id,
            request=request,
            access_reason=body.access_reason,
            request_id=request_id,
            error=exc,
        )
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
        # `record_retention_run_failure`도 내부에서 rollback을 한다 — 같은 이유로 `admin`이 아니라
        # 위에서 미리 뽑아 둔 `actor_id`를 쓴다.
        await record_retention_run_failure(db, run.run_id, exc)
        await _append_execute_failure_audit(
            db,
            run_id=run.run_id,
            actor_id=actor_id,
            request=request,
            access_reason=body.access_reason,
            request_id=request_id,
            error=exc,
        )
        raise _error_response(RetentionExecutionError(str(exc))) from exc

    return Envelope.of(run)


async def _append_execute_failure_audit(
    db: DbSession,
    *,
    run_id: uuid.UUID | None,
    actor_id: uuid.UUID,
    request: Request,
    access_reason: str,
    request_id: uuid.UUID,
    error: BaseException,
) -> None:
    """ "시도했고 실패했다"를 admin_audit_log 해시 체인에도 남긴다(T-342).

    `docs/compliance/lbs-act.md` §3.4는 "모든 실행은 `retention_runs`와 `admin_audit_log`에 evidence를
    남긴다"고 적는다. `retention_runs`는 T-338/T-339이 실패해도 남게 고쳤지만, `admin_audit_log`는
    성공 경로(`_finalize_execute`)에서만 적재됐다 — 문서와 코드가 갈라져 있었다.

    `run_id`가 `None`이면 kill-switch/confirm-phrase/동시실행 precheck처럼 run을 만들기도 전에
    막힌 것이다. 그래도 남긴다 — "누가 언제 시도했는가"는 막혔더라도 감사 가치가 있다.

    이 적재 자체가 실패해도 **원래 오류 응답을 막지 않는다.** 감사 실패로 진짜 오류가 가려지는 것이
    더 나쁘다 — 로그로만 남긴다.
    """
    try:
        await append_admin_audit(
            db,
            actor_user_id=actor_id,
            action="retention.execute_failed",
            resource_type="retention_run",
            resource_id=str(run_id) if run_id is not None else None,
            before_state=None,
            after_state={"error_code": getattr(error, "code", type(error).__name__)},
            access_reason=access_reason,
            target_pii_fields=None,
            ip_hash_input=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent"),
            request_id=request_id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("retention.execute_failed 감사 적재 실패 (run_id=%s)", run_id)


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
