"""`/admin/integrity/*` — kor-travel-map consistency read proxy."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError

from app.api.v1.admin.ops_proxy import map_ops_errors, next_cursor, parse_request_id
from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminConsistencyReportRecord,
    AdminConsistencyReportsResponse,
    AdminIntegrityIssueActionRequest,
    AdminIntegrityIssueActionResponse,
    AdminIntegrityIssueRecord,
    AdminIntegrityIssuesResponse,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit

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


@router.post(
    "/issues/{issue_id}/action",
    response_model=Envelope[AdminIntegrityIssueActionResponse],
)
async def action_integrity_issue(
    issue_id: str,
    body: AdminIntegrityIssueActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    admin_client: KorTravelMapAdminClientDep,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminIntegrityIssueActionResponse]:
    """kor-travel-map `/v1/admin/issues/{id}` 상태 조치 relay + Pinvi audit."""
    reason = body.kor_travel_map_reason or body.access_reason
    with map_ops_errors(message_subject="kor_travel_map integrity issue action"):
        payload = await admin_client.patch_admin_issue(
            issue_id,
            action=body.action,
            reason=reason,
            operator="pinvi-admin",
        )
    issue = _validate_issue(
        payload,
        "kor_travel_map integrity issue action 응답 형식이 올바르지 않습니다.",
    )
    result = AdminIntegrityIssueActionResponse(action=body.action, issue=issue)

    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="integrity_issue.action",
        resource_type="integrity_issue",
        resource_id=issue_id,
        before_state=None,
        after_state={
            "action": body.action,
            "status": issue.status,
            "feature_id": issue.feature_id,
            "provider": issue.provider,
            "dataset_key": issue.dataset_key,
            "violation_type": issue.violation_type,
        },
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=parse_request_id(x_request_id),
    )
    await db.commit()
    return Envelope.of(result)


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


def _validate_issue(payload: dict[str, Any], message: str) -> AdminIntegrityIssueRecord:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map consistency 응답 data 형식이 올바르지 않습니다.",
            },
        )
    issue = data.get("issue")
    if not isinstance(issue, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "FEATURE_SERVICE_BAD_GATEWAY", "message": message},
        )
    try:
        return AdminIntegrityIssueRecord.model_validate(issue)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "FEATURE_SERVICE_BAD_GATEWAY", "message": message},
        ) from exc


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
