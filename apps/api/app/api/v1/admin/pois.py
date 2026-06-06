"""`/admin/pois/*` — POI admin 관리."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.audit import AdminAuditLog
from app.models.user import User
from app.schemas.admin import (
    AdminAuditEntry,
    AdminPoiDetail,
    AdminPoiLinkStatusRequest,
    AdminPoiPagedResponse,
    AdminPoiSummary,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.admin_pois import (
    AdminPoiNotFoundError,
    AdminPoiRow,
    extract_feature_label,
    get_admin_poi,
    list_admin_pois,
    list_recent_poi_audit,
    update_admin_poi_link_status,
)
from app.services.admin_users import mask_email

router = APIRouter(prefix="/admin/pois", tags=["admin"])


def _to_audit_entry(r: AdminAuditLog) -> AdminAuditEntry:
    return AdminAuditEntry(
        log_id=r.log_id,
        actor_user_id=r.actor_user_id,
        action=r.action,
        resource_type=r.resource_type,
        resource_id=r.resource_id,
        access_reason=r.access_reason,
        target_pii_fields=r.target_pii_fields,
        prev_hash=r.prev_hash,
        content_hash=r.content_hash,
        occurred_at=r.occurred_at,
    )


def _to_summary(row: AdminPoiRow) -> AdminPoiSummary:
    poi = row.poi
    return AdminPoiSummary(
        attachment_id=poi.attachment_id,
        trip_id=poi.trip_id,
        trip_title=row.trip_title,
        owner_user_id=row.owner_user_id,
        owner_email_masked=mask_email(row.owner_email),
        day_index=poi.day_index,
        sort_order=poi.sort_order,
        feature_id=poi.feature_id,
        feature_label=extract_feature_label(poi.feature_snapshot),
        feature_link_broken_at=poi.feature_link_broken_at,
        version=poi.version,
        created_at=poi.created_at,
        updated_at=poi.updated_at,
    )


async def _to_detail(db: AsyncSession, row: AdminPoiRow) -> AdminPoiDetail:
    poi = row.poi
    summary = _to_summary(row)
    recent_audit = await list_recent_poi_audit(db, poi_id=poi.attachment_id)
    return AdminPoiDetail(
        **summary.model_dump(),
        added_by_user_id=poi.added_by_user_id,
        added_by_email_masked=mask_email(row.added_by_email) if row.added_by_email else None,
        feature_snapshot=poi.feature_snapshot,
        custom_marker_color=poi.custom_marker_color,
        custom_marker_icon=poi.custom_marker_icon,
        planned_arrival_at=poi.planned_arrival_at,
        planned_departure_at=poi.planned_departure_at,
        user_note=poi.user_note,
        budget_amount=poi.budget_amount,
        actual_amount=poi.actual_amount,
        currency=poi.currency,
        user_url=poi.user_url,
        recent_audit=[_to_audit_entry(r) for r in recent_audit],
    )


def _parse_request_id(value: str | None) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "X-Request-Id 형식이 올바르지 않습니다.",
            },
        ) from exc


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@router.get("", response_model=Envelope[AdminPoiPagedResponse])
async def list_pois_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    page: int = 1,
    limit: int = 50,
    trip_id: uuid.UUID | None = None,
    has_broken_link: bool | None = None,
    q: str | None = None,
) -> Envelope[AdminPoiPagedResponse]:
    page = max(1, page)
    limit = min(100, max(1, limit))
    rows, total = await list_admin_pois(
        db,
        page=page,
        limit=limit,
        trip_id=trip_id,
        has_broken_link=has_broken_link,
        q=q,
    )
    return Envelope.of(
        AdminPoiPagedResponse(
            items=[_to_summary(row) for row in rows],
            total=total,
            page=page,
            limit=limit,
        )
    )


@router.get("/{poi_id}", response_model=Envelope[AdminPoiDetail])
async def get_poi_endpoint(
    poi_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminPoiDetail]:
    try:
        row = await get_admin_poi(db, poi_id=poi_id)
    except AdminPoiNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(await _to_detail(db, row))


@router.patch("/{poi_id}/link-status", response_model=Envelope[AdminPoiDetail])
async def update_poi_link_status_endpoint(
    poi_id: uuid.UUID,
    body: AdminPoiLinkStatusRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminPoiDetail]:
    try:
        poi, before = await update_admin_poi_link_status(
            db,
            poi_id=poi_id,
            broken=body.broken,
        )
        row = await get_admin_poi(db, poi_id=poi.attachment_id)
    except AdminPoiNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="poi.update_link_status",
        resource_type="poi",
        resource_id=str(poi.attachment_id),
        before_state={"feature_link_broken_at": _dt(before)},
        after_state={"feature_link_broken_at": _dt(poi.feature_link_broken_at)},
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    return Envelope.of(await _to_detail(db, row))
