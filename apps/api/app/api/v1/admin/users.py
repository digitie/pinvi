"""`/admin/users/*` — `docs/api/admin.md` §6."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminActionRequest,
    AdminPagedResponse,
    AdminUserDetail,
    AdminUserSummary,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.admin_users import (
    AdminUserNotFoundError,
    disable_user,
    force_verify,
    list_users,
    mask_email,
)

router = APIRouter(prefix="/admin/users", tags=["admin"])


def _to_summary(u: User) -> AdminUserSummary:
    return AdminUserSummary(
        user_id=u.user_id,
        email_masked=mask_email(u.email),
        nickname=u.nickname,
        status=u.status,  # type: ignore[arg-type]
        roles=u.roles,
        email_verified_at=u.email_verified_at,
        created_at=u.created_at,
    )


def _to_detail(u: User) -> AdminUserDetail:
    base = _to_summary(u)
    return AdminUserDetail(
        **base.model_dump(),
        email=u.email,
        email_status=u.email_status,  # type: ignore[arg-type]
        is_active=u.is_active,
    )


@router.get("", response_model=Envelope[AdminPagedResponse])
async def list_users_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    page: int = 1,
    limit: int = 50,
    status_filter: str | None = None,
) -> Envelope[AdminPagedResponse]:
    users, total = await list_users(db, page=page, limit=limit, status_filter=status_filter)
    return Envelope.of(
        AdminPagedResponse(
            items=[_to_summary(u) for u in users],
            total=total,
            page=page,
            limit=limit,
        )
    )


@router.get("/{user_id}", response_model=Envelope[AdminUserDetail])
async def get_user_endpoint(
    user_id: uuid.UUID,
    admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminUserDetail]:
    from sqlalchemy import select

    u = await db.scalar(select(User).where(User.user_id == user_id, User.deleted_at.is_(None)))
    if u is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
        )
    _ = admin
    return Envelope.of(_to_detail(u))


@router.post("/{user_id}/force-verify", response_model=Envelope[AdminUserDetail])
async def force_verify_endpoint(
    user_id: uuid.UUID,
    body: AdminActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminUserDetail]:
    try:
        before_status = None
        target = await force_verify(db, user_id=user_id, actor_id=admin.user_id)
    except AdminUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    if x_request_id is None:
        x_request_id = str(uuid.uuid4())
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="user.force_verify",
        resource_type="user",
        resource_id=str(target.user_id),
        before_state={"status": before_status},
        after_state={"status": target.status, "email_verified_at": str(target.email_verified_at)},
        access_reason=body.access_reason,
        target_pii_fields=["email"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=uuid.UUID(x_request_id),
    )
    return Envelope.of(_to_detail(target))


@router.post("/{user_id}/disable", response_model=Envelope[AdminUserDetail])
async def disable_user_endpoint(
    user_id: uuid.UUID,
    body: AdminActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminUserDetail]:
    try:
        target = await disable_user(db, user_id=user_id, actor_id=admin.user_id)
    except AdminUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    if x_request_id is None:
        x_request_id = str(uuid.uuid4())
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="user.disable",
        resource_type="user",
        resource_id=str(target.user_id),
        before_state=None,
        after_state={"status": "disabled", "is_active": False},
        access_reason=body.access_reason,
        target_pii_fields=["email"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=uuid.UUID(x_request_id),
    )
    return Envelope.of(_to_detail(target))
