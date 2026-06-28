"""`/admin/moderation` — 콘텐츠 신고 심사 / takedown / restore."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.v1.admin.ops_proxy import parse_request_id
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.envelope import Envelope
from app.schemas.moderation import (
    ContentModerationActionRequest,
    ContentReportListResponse,
    ContentReportRecord,
)
from app.services.admin_audit import append_admin_audit
from app.services.moderation import (
    ContentModerationActionName,
    ContentReportNotFoundError,
    ContentReportTransitionError,
    get_content_report,
    list_content_reports,
    moderate_content_report,
    to_content_report_record,
)

router = APIRouter(prefix="/admin/moderation", tags=["admin"])


@router.get("/reports", response_model=Envelope[ContentReportListResponse])
async def list_admin_content_reports(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    status_filter: Annotated[
        str | None,
        Query(
            alias="status",
            pattern="^(received|reviewing|hidden|taken_down|rejected|appealed|restored)$",
        ),
    ] = None,
    target_type: Annotated[
        str | None,
        Query(pattern="^(trip|comment|attachment|share_link)$"),
    ] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Envelope[ContentReportListResponse]:
    result = await list_content_reports(
        db,
        status_filter=status_filter,
        target_type=target_type,
        page_size=page_size,
    )
    return Envelope.of(result)


@router.post("/reports/{report_id}/review", response_model=Envelope[ContentReportRecord])
async def review_content_report_endpoint(
    report_id: uuid.UUID,
    body: ContentModerationActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[ContentReportRecord]:
    return await _mutate_content_report(
        db=db,
        request=request,
        actor=admin,
        request_id=parse_request_id(x_request_id),
        report_id=report_id,
        action="review",
        body=body,
    )


@router.post("/reports/{report_id}/hide", response_model=Envelope[ContentReportRecord])
async def hide_content_report_endpoint(
    report_id: uuid.UUID,
    body: ContentModerationActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[ContentReportRecord]:
    return await _mutate_content_report(
        db=db,
        request=request,
        actor=admin,
        request_id=parse_request_id(x_request_id),
        report_id=report_id,
        action="hide",
        body=body,
    )


@router.post("/reports/{report_id}/takedown", response_model=Envelope[ContentReportRecord])
async def takedown_content_report_endpoint(
    report_id: uuid.UUID,
    body: ContentModerationActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[ContentReportRecord]:
    return await _mutate_content_report(
        db=db,
        request=request,
        actor=admin,
        request_id=parse_request_id(x_request_id),
        report_id=report_id,
        action="takedown",
        body=body,
    )


@router.post("/reports/{report_id}/restore", response_model=Envelope[ContentReportRecord])
async def restore_content_report_endpoint(
    report_id: uuid.UUID,
    body: ContentModerationActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[ContentReportRecord]:
    return await _mutate_content_report(
        db=db,
        request=request,
        actor=admin,
        request_id=parse_request_id(x_request_id),
        report_id=report_id,
        action="restore",
        body=body,
    )


@router.post("/reports/{report_id}/reject", response_model=Envelope[ContentReportRecord])
async def reject_content_report_endpoint(
    report_id: uuid.UUID,
    body: ContentModerationActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[ContentReportRecord]:
    return await _mutate_content_report(
        db=db,
        request=request,
        actor=admin,
        request_id=parse_request_id(x_request_id),
        report_id=report_id,
        action="reject",
        body=body,
    )


async def _mutate_content_report(
    *,
    db: DbSession,
    request: Request,
    actor: User,
    request_id: uuid.UUID,
    report_id: uuid.UUID,
    action: ContentModerationActionName,
    body: ContentModerationActionRequest,
) -> Envelope[ContentReportRecord]:
    try:
        before_row = await get_content_report(db, report_id=report_id)
        before = to_content_report_record(before_row).model_dump(mode="json")
        row = await moderate_content_report(
            db,
            report_id=report_id,
            actor_user_id=actor.user_id,
            action=action,
            body=body,
        )
    except ContentReportNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "신고를 찾을 수 없습니다."},
        ) from exc
    except ContentReportTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE", "message": str(exc)},
        ) from exc

    after = to_content_report_record(row).model_dump(mode="json")
    await append_admin_audit(
        db,
        actor_user_id=actor.user_id,
        action=f"content_moderation.{action}",
        resource_type="content_report",
        resource_id=str(row.report_id),
        before_state=before,
        after_state=after,
        access_reason=body.access_reason,
        target_pii_fields=["user_content"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
    await db.commit()
    return Envelope.of(to_content_report_record(row))
