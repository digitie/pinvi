"""`/admin/trips/*` — 여행계획 admin 관리."""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.audit import AdminAuditLog
from app.models.companion import TripCompanion
from app.models.share_link import TripShareLink
from app.models.trip import Trip
from app.models.user import User
from app.schemas.admin import (
    AdminAuditEntry,
    AdminTripCompanionSummary,
    AdminTripDetail,
    AdminTripPagedResponse,
    AdminTripShareLinkSummary,
    AdminTripStatusRequest,
    AdminTripSummary,
    TripCompanionRole,
    TripShareLinkVisibility,
    TripStatus,
    TripVisibility,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.admin_trips import (
    AdminTripNotFoundError,
    get_admin_trip,
    list_admin_trips,
    list_recent_trip_audit,
    list_trip_companions,
    list_trip_share_links,
    load_owner_emails,
    load_trip_counts,
    update_admin_trip_status,
)
from app.services.admin_users import mask_email

router = APIRouter(prefix="/admin/trips", tags=["admin"])


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


def _to_companion(c: TripCompanion) -> AdminTripCompanionSummary:
    return AdminTripCompanionSummary(
        companion_id=c.companion_id,
        user_id=c.user_id,
        invited_email_masked=mask_email(c.invited_email) if c.invited_email else None,
        invited_nickname=c.invited_nickname,
        role=cast(TripCompanionRole, c.role),
        invited_at=c.invited_at,
        joined_at=c.joined_at,
    )


def _to_share_link(s: TripShareLink) -> AdminTripShareLinkSummary:
    return AdminTripShareLinkSummary(
        share_id=s.share_id,
        visibility=cast(TripShareLinkVisibility, s.visibility),
        expires_at=s.expires_at,
        revoked_at=s.revoked_at,
        last_used_at=s.last_used_at,
        created_at=s.created_at,
    )


def _to_summary(
    trip: Trip,
    *,
    owner_email: str,
    counts: dict[str, int],
) -> AdminTripSummary:
    return AdminTripSummary(
        trip_id=trip.trip_id,
        owner_user_id=trip.owner_user_id,
        owner_email_masked=mask_email(owner_email),
        title=trip.title,
        region_hint=trip.region_hint,
        start_date=trip.start_date,
        end_date=trip.end_date,
        visibility=cast(TripVisibility, trip.visibility),
        status=cast(TripStatus, trip.status),
        version=trip.version,
        day_count=counts["day_count"],
        poi_count=counts["poi_count"],
        companion_count=counts["companion_count"],
        share_link_count=counts["share_link_count"],
        created_at=trip.created_at,
        updated_at=trip.updated_at,
    )


async def _to_detail(db: AsyncSession, trip: Trip) -> AdminTripDetail:
    owner_emails = await load_owner_emails(db, owner_user_ids=[trip.owner_user_id])
    counts = await load_trip_counts(db, trip_ids=[trip.trip_id])
    summary = _to_summary(
        trip,
        owner_email=owner_emails[trip.owner_user_id],
        counts=counts[trip.trip_id],
    )
    companions = await list_trip_companions(db, trip_id=trip.trip_id)
    share_links = await list_trip_share_links(db, trip_id=trip.trip_id)
    recent_audit = await list_recent_trip_audit(db, trip_id=trip.trip_id)
    return AdminTripDetail(
        **summary.model_dump(),
        description=trip.description,
        companions=[_to_companion(c) for c in companions],
        share_links=[_to_share_link(s) for s in share_links],
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


@router.get("", response_model=Envelope[AdminTripPagedResponse])
async def list_trips_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    page: int = 1,
    limit: int = 50,
    status_filter: str | None = None,
    visibility_filter: str | None = None,
    owner_user_id: uuid.UUID | None = None,
    q: str | None = None,
) -> Envelope[AdminTripPagedResponse]:
    page = max(1, page)
    limit = min(100, max(1, limit))
    trips, total = await list_admin_trips(
        db,
        page=page,
        limit=limit,
        status_filter=status_filter,
        visibility_filter=visibility_filter,
        owner_user_id=owner_user_id,
        q=q,
    )
    owner_emails = await load_owner_emails(
        db,
        owner_user_ids=[trip.owner_user_id for trip in trips],
    )
    counts = await load_trip_counts(db, trip_ids=[trip.trip_id for trip in trips])
    return Envelope.of(
        AdminTripPagedResponse(
            items=[
                _to_summary(
                    trip,
                    owner_email=owner_emails[trip.owner_user_id],
                    counts=counts[trip.trip_id],
                )
                for trip in trips
            ],
            total=total,
            page=page,
            limit=limit,
        )
    )


@router.get("/{trip_id}", response_model=Envelope[AdminTripDetail])
async def get_trip_endpoint(
    trip_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminTripDetail]:
    try:
        trip = await get_admin_trip(db, trip_id=trip_id)
    except AdminTripNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(await _to_detail(db, trip))


@router.patch("/{trip_id}/status", response_model=Envelope[AdminTripDetail])
async def update_trip_status_endpoint(
    trip_id: uuid.UUID,
    body: AdminTripStatusRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminTripDetail]:
    try:
        trip, before_status = await update_admin_trip_status(
            db,
            trip_id=trip_id,
            status=body.status,
        )
    except AdminTripNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="trip.update_status",
        resource_type="trip",
        resource_id=str(trip.trip_id),
        before_state={"status": before_status},
        after_state={"status": trip.status},
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    return Envelope.of(await _to_detail(db, trip))
