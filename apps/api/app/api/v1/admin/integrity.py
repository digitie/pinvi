"""`/admin/integrity/*` — kor-travel-map consistency read proxy."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from app.api.v1.admin.ops_proxy import map_ops_errors, next_cursor
from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminConsistencyReportRecord,
    AdminConsistencyReportsResponse,
    AdminIntegrityIssueRecord,
    AdminIntegrityIssuesResponse,
)
from app.schemas.envelope import Envelope

router = APIRouter(prefix="/admin/integrity", tags=["admin"])


@router.get("/issues", response_model=Envelope[AdminIntegrityIssuesResponse])
async def list_integrity_issues(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    status_filter: Annotated[
        str | None,
        Query(alias="status", pattern="^(open|acknowledged|resolved|ignored)$"),
    ] = "open",
    severity: Annotated[
        str | None,
        Query(pattern="^(info|warning|error|critical)$"),
    ] = None,
    violation_type: Annotated[str | None, Query()] = None,
    provider: Annotated[str | None, Query()] = None,
    dataset_key: Annotated[str | None, Query()] = None,
    feature_id: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> Envelope[AdminIntegrityIssuesResponse]:
    """kor-travel-map `/v1/ops/consistency/issues` proxy."""
    with map_ops_errors(message_subject="kor_travel_map integrity issue"):
        payload = await admin_client.list_integrity_issues(
            status_filter=status_filter,
            severity=severity,
            violation_type=violation_type,
            provider=provider,
            dataset_key=dataset_key,
            feature_id=feature_id,
            page_size=page_size,
            cursor=cursor,
        )
    return Envelope.of(
        AdminIntegrityIssuesResponse(
            items=_validate_items(
                payload,
                AdminIntegrityIssueRecord,
                "kor_travel_map integrity issue item 형식이 올바르지 않습니다.",
            ),
            page_size=page_size,
            next_cursor=next_cursor(_meta(payload)),
        )
    )


@router.get("/reports", response_model=Envelope[AdminConsistencyReportsResponse])
async def list_consistency_reports(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    severity_max: Annotated[str | None, Query(pattern="^(OK|WARN|ERROR)$")] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> Envelope[AdminConsistencyReportsResponse]:
    """kor-travel-map `/v1/ops/consistency/reports` proxy."""
    with map_ops_errors(message_subject="kor_travel_map consistency report"):
        payload = await admin_client.list_consistency_reports(
            severity_max=severity_max,
            page_size=page_size,
            cursor=cursor,
        )
    return Envelope.of(
        AdminConsistencyReportsResponse(
            items=_validate_items(
                payload,
                AdminConsistencyReportRecord,
                "kor_travel_map consistency report item 형식이 올바르지 않습니다.",
            ),
            page_size=page_size,
            next_cursor=next_cursor(_meta(payload)),
        )
    )


def _meta(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map consistency 응답 meta 형식이 올바르지 않습니다.",
            },
        )
    return meta


def _validate_items(
    payload: dict[str, Any],
    model: type[AdminIntegrityIssueRecord] | type[AdminConsistencyReportRecord],
    message: str,
) -> Any:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map consistency 응답 data 형식이 올바르지 않습니다.",
            },
        )
    items = data.get("items")
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map consistency 목록에 items가 없습니다.",
            },
        )
    try:
        return [model.model_validate(item) for item in items]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "FEATURE_SERVICE_BAD_GATEWAY", "message": message},
        ) from exc
