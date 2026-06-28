"""`/admin/provider-sync/*` — kor-travel-map provider sync read proxy."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError

from app.api.v1.admin.ops_proxy import map_ops_errors, next_cursor, parse_request_id
from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminProviderDatasetSummary,
    AdminProviderImportJobCancelRequest,
    AdminProviderImportJobRecord,
    AdminProviderImportJobsResponse,
    AdminProviderSyncResponse,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit

router = APIRouter(prefix="/admin/provider-sync", tags=["admin"])


@router.get("", response_model=Envelope[AdminProviderSyncResponse])
async def list_provider_sync(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    key: Annotated[str | None, Query(description="provider 또는 dataset key 검색")] = None,
) -> Envelope[AdminProviderSyncResponse]:
    """kor-travel-map `/v1/ops/providers` provider/dataset 상태 proxy."""
    with map_ops_errors(message_subject="kor_travel_map provider sync"):
        data = await admin_client.list_ops_providers(key=key)
    items = data.get("items")
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map provider sync 목록에 items가 없습니다.",
            },
        )
    try:
        records = [AdminProviderDatasetSummary.model_validate(item) for item in items]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map provider sync item 형식이 올바르지 않습니다.",
            },
        ) from exc
    return Envelope.of(AdminProviderSyncResponse(items=records, total=len(records)))


@router.get("/import-jobs", response_model=Envelope[AdminProviderImportJobsResponse])
async def list_provider_import_jobs(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    status_filter: Annotated[
        str | None,
        Query(alias="status", pattern="^(queued|running|done|failed|cancelled)$"),
    ] = None,
    kind: Annotated[str | None, Query()] = None,
    load_batch_id: Annotated[str | None, Query()] = None,
    parent_job_id: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> Envelope[AdminProviderImportJobsResponse]:
    """kor-travel-map `/v1/ops/import-jobs` provider job 목록 proxy."""
    with map_ops_errors(message_subject="kor_travel_map import job"):
        payload = await admin_client.list_ops_import_jobs(
            status_filter=status_filter,
            kind=kind,
            load_batch_id=load_batch_id,
            parent_job_id=parent_job_id,
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
    items = data.get("items")
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map import job 목록에 items가 없습니다.",
            },
        )
    try:
        records = [AdminProviderImportJobRecord.model_validate(item) for item in items]
    except ValidationError as exc:
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
            next_cursor=next_cursor(meta),
        )
    )


@router.post(
    "/import-jobs/{job_id}/cancel",
    response_model=Envelope[AdminProviderImportJobRecord],
)
async def cancel_provider_import_job(
    job_id: str,
    body: AdminProviderImportJobCancelRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    admin_client: KorTravelMapAdminClientDep,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminProviderImportJobRecord]:
    """kor-travel-map import job cancel relay + Pinvi audit."""
    reason = body.kor_travel_map_reason or body.access_reason
    with map_ops_errors(message_subject="kor_travel_map import job cancel"):
        payload = await admin_client.cancel_ops_import_job(
            job_id,
            reason=reason,
            operator="pinvi-admin",
        )
    try:
        record = AdminProviderImportJobRecord.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map import job cancel 응답 형식이 올바르지 않습니다.",
            },
        ) from exc

    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="provider_import_job.cancel",
        resource_type="provider_import_job",
        resource_id=job_id,
        before_state=None,
        after_state={
            "status": record.status,
            "kind": record.kind,
            "load_batch_id": record.load_batch_id,
            "parent_job_id": record.parent_job_id,
            "provider": record.payload.get("provider"),
            "dataset_key": record.payload.get("dataset_key"),
        },
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=parse_request_id(x_request_id),
    )
    await db.commit()
    return Envelope.of(record)
