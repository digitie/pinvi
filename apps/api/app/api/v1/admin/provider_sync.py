"""`/admin/provider-sync/*` — kor-travel-map provider sync read proxy."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.v1.admin.ops_proxy import map_ops_errors, parse_request_id
from app.clients.kor_travel_map import KorTravelMapError, KorTravelMapUnavailable
from app.clients.kor_travel_map_admin import (
    KorTravelMapAdminClientDep,
    pipeline_cancellation_outcome_uncertain,
)
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminProviderImportJobCancellationResult,
    AdminProviderImportJobCancelRequest,
    AdminProviderImportJobRecord,
    AdminProviderImportJobsResponse,
    AdminProviderSyncResponse,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.kor_travel_map_ops_projection import (
    KorTravelMapOpsContractError,
    pipeline_executions_canonical_url,
    project_dataset_grid_snapshot,
    project_pipeline_cancellation,
    project_pipeline_execution,
    project_pipeline_executions,
    project_pipeline_page_next_cursor,
)

router = APIRouter(prefix="/admin/provider-sync", tags=["admin"])


def _cancel_error_audit_state(exc: KorTravelMapError) -> dict[str, Any]:
    """이미 dispatch된 취소 오류를 request_id 상관관계로 남길 안전한 상태."""

    code = getattr(exc, "code", None)
    state: dict[str, Any] = {
        "phase": "finished",
        "outcome": (
            "uncertain"
            if isinstance(exc, KorTravelMapUnavailable)
            and code == "PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN"
            else "typed_failure"
        ),
        "error_type": type(exc).__name__,
        "code": code,
    }
    details = getattr(exc, "details", None)
    retry_after = getattr(exc, "retry_after_seconds", None)
    status_code = getattr(exc, "status_code", None)
    if details is not None:
        state["details"] = details
    if retry_after is not None:
        state["retry_after_seconds"] = retry_after
    if status_code is not None:
        state["status_code"] = status_code
    return state


@router.get("", response_model=Envelope[AdminProviderSyncResponse])
async def list_provider_sync(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    key: Annotated[str | None, Query(description="provider 또는 dataset key 검색")] = None,
) -> Envelope[AdminProviderSyncResponse]:
    """kor-travel-map canonical dataset grid를 Pinvi 표시 DTO로 투영한다."""
    with map_ops_errors(message_subject="kor_travel_map provider sync"):
        data = await admin_client.list_ops_datasets()
    try:
        snapshot = project_dataset_grid_snapshot(data, key=key)
    except KorTravelMapOpsContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map dataset grid 형식이 올바르지 않습니다.",
            },
        ) from exc
    return Envelope.of(
        AdminProviderSyncResponse(
            items=snapshot.items,
            total=len(snapshot.items),
            schedule_source_status=snapshot.schedule_source_status,
            schedule_source_errors=snapshot.schedule_source_errors,
        )
    )


@router.get("/import-jobs", response_model=Envelope[AdminProviderImportJobsResponse])
async def list_provider_import_jobs(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    status_filter: Annotated[
        str | None,
        Query(alias="status", pattern=r"^(queued|running|done|failed|cancelled)$"),
    ] = None,
    load_batch_id: Annotated[UUID | None, Query()] = None,
    parent_job_id: Annotated[UUID | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> Envelope[AdminProviderImportJobsResponse]:
    """canonical pipeline execution 중 import-job root 목록을 투영한다."""
    canonical_load_batch_id = str(load_batch_id) if load_batch_id is not None else None
    canonical_parent_job_id = str(parent_job_id) if parent_job_id is not None else None
    with map_ops_errors(message_subject="kor_travel_map import job"):
        payload = await admin_client.list_ops_pipeline_executions(
            status_filter=status_filter,
            load_batch_id=canonical_load_batch_id,
            parent_job_id=canonical_parent_job_id,
            page_size=page_size,
            cursor=cursor,
        )
    data = payload.get("data")
    meta = payload.get("meta")
    if not isinstance(data, dict) or not isinstance(meta, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map import job 응답 형식이 올바르지 않습니다.",
            },
        )
    try:
        records = project_pipeline_executions(
            data,
            expected_canonical_url=pipeline_executions_canonical_url(
                status_filter=status_filter,
                load_batch_id=canonical_load_batch_id,
                parent_job_id=canonical_parent_job_id,
            ),
        )
        projected_next_cursor = project_pipeline_page_next_cursor(
            meta,
            expected_page_size=page_size,
        )
    except KorTravelMapOpsContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map import job item 형식이 올바르지 않습니다.",
            },
        ) from exc
    return Envelope.of(
        AdminProviderImportJobsResponse(
            items=records,
            page_size=page_size,
            next_cursor=projected_next_cursor,
        )
    )


@router.get(
    "/import-jobs/{job_id}",
    response_model=Envelope[AdminProviderImportJobRecord],
)
async def get_provider_import_job(
    job_id: str,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
) -> Envelope[AdminProviderImportJobRecord]:
    """취소 응답이 불확실할 때 canonical import-job 상태를 재조정한다."""

    with map_ops_errors(message_subject="kor_travel_map import job reconciliation"):
        data = await admin_client.get_ops_pipeline_execution(job_id)
    try:
        record = project_pipeline_execution(data, requested_job_id=job_id)
    except KorTravelMapOpsContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map import job 상세 형식이 올바르지 않습니다.",
            },
        ) from exc
    return Envelope.of(record)


@router.post(
    "/import-jobs/{job_id}/cancel",
    response_model=Envelope[AdminProviderImportJobCancellationResult],
)
async def cancel_provider_import_job(
    job_id: str,
    body: AdminProviderImportJobCancelRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    admin_client: KorTravelMapAdminClientDep,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminProviderImportJobCancellationResult]:
    """kor-travel-map import job cancel relay + dispatch 전후 Pinvi audit."""
    raw_request_id = getattr(request.state, "request_id", None) or x_request_id
    audit_request_id = parse_request_id(str(raw_request_id) if raw_request_id is not None else None)
    reason = body.kor_travel_map_reason or body.access_reason

    async def write_audit(action: str, after_state: dict[str, Any]) -> None:
        await append_admin_audit(
            db,
            actor_user_id=admin.user_id,
            action=action,
            resource_type="provider_import_job",
            resource_id=job_id,
            before_state=None,
            after_state=after_state,
            access_reason=body.access_reason,
            target_pii_fields=None,
            ip_hash_input=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent"),
            request_id=audit_request_id,
        )

    await write_audit(
        "provider_import_job.cancel.started",
        {
            "phase": "started",
            "outcome": "pending",
            "upstream_reason_supplied": bool(reason),
        },
    )
    # 외부 POST 전에 별도 commit하여 응답 유실/worker 종료에도 운영자·사유를 보존한다.
    await db.commit()

    try:
        payload = await admin_client.cancel_ops_pipeline_execution(
            job_id,
            reason=reason,
        )
    except KorTravelMapError as exc:
        await write_audit(
            "provider_import_job.cancel.result",
            _cancel_error_audit_state(exc),
        )
        await db.commit()
        with map_ops_errors(message_subject="kor_travel_map import job cancel"):
            raise
        raise AssertionError("map_ops_errors must raise") from None  # pragma: no cover
    try:
        result = project_pipeline_cancellation(payload, requested_job_id=job_id)
    except KorTravelMapOpsContractError as exc:
        uncertain = pipeline_cancellation_outcome_uncertain(job_id)
        await write_audit(
            "provider_import_job.cancel.result",
            _cancel_error_audit_state(uncertain),
        )
        await db.commit()
        with map_ops_errors(message_subject="kor_travel_map import job cancel"):
            raise uncertain from exc
        raise AssertionError("map_ops_errors must raise") from None  # pragma: no cover

    await write_audit(
        "provider_import_job.cancel",
        {
            "phase": "finished",
            "outcome": "accepted",
            "status": result.status,
            "root_kind": result.root_kind,
            "root_id": result.root_id,
            "cancellation_id": result.cancellation_id,
            "retryable": result.retryable,
            "unresolved_member_count": result.unresolved_member_count,
        },
    )
    await db.commit()
    return Envelope.of(result)
