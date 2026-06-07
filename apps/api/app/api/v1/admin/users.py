"""`/admin/users/*` — `docs/api/admin.md` §6."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.audit import AdminAuditLog
from app.models.user import User
from app.schemas.admin import (
    AdminActionRequest,
    AdminAuditEntry,
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
    list_recent_user_audit,
    list_users,
    mask_email,
)

router = APIRouter(prefix="/admin/users", tags=["admin"])


def _to_summary(u: User) -> AdminUserSummary:
    return AdminUserSummary(
        user_id=u.user_id,
        email_masked=mask_email(u.email),
        nickname=u.nickname,
        status=u.status,
        roles=u.roles,
        email_verified_at=u.email_verified_at,
        created_at=u.created_at,
    )


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


def _to_detail(
    u: User,
    *,
    recent_audit: list[AdminAuditEntry] | None = None,
    email_revealed: bool = False,
) -> AdminUserDetail:
    base = _to_summary(u)
    return AdminUserDetail(
        **base.model_dump(),
        email=u.email if email_revealed else mask_email(u.email),
        email_revealed=email_revealed,
        email_status=u.email_status,
        is_active=u.is_active,
        recent_audit=recent_audit or [],
    )


async def _detail_with_recent_audit(
    db: AsyncSession,
    u: User,
    *,
    email_revealed: bool = False,
) -> AdminUserDetail:
    rows = await list_recent_user_audit(db, user_id=u.user_id)
    return _to_detail(
        u,
        email_revealed=email_revealed,
        recent_audit=[_to_audit_entry(row) for row in rows],
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


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    from sqlalchemy import select

    u = await db.scalar(select(User).where(User.user_id == user_id, User.deleted_at.is_(None)))
    if u is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
        )
    return u


@router.get("", response_model=Envelope[AdminPagedResponse])
async def list_users_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    page: int = 1,
    limit: int = 50,
    status_filter: str | None = None,
    q: str | None = None,
) -> Envelope[AdminPagedResponse]:
    page = max(1, page)
    limit = min(100, max(1, limit))
    users, total = await list_users(
        db,
        page=page,
        limit=limit,
        status_filter=status_filter,
        q=q,
    )
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
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    reveal: bool = False,
) -> Envelope[AdminUserDetail]:
    u = await _get_user_or_404(db, user_id)
    if reveal:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "PII 원본 조회는 POST /admin/users/{user_id}/reveal-pii를 사용합니다.",
            },
        )

    return Envelope.of(await _detail_with_recent_audit(db, u, email_revealed=reveal))


@router.post("/{user_id}/reveal-pii", response_model=Envelope[AdminUserDetail])
async def reveal_user_pii_endpoint(
    user_id: uuid.UUID,
    body: AdminActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminUserDetail]:
    u = await _get_user_or_404(db, user_id)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="user.reveal_pii",
        resource_type="user",
        resource_id=str(u.user_id),
        before_state=None,
        after_state=None,
        access_reason=body.access_reason,
        target_pii_fields=["email"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    return Envelope.of(await _detail_with_recent_audit(db, u, email_revealed=True))


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
        request_id=_parse_request_id(x_request_id),
    )
    return Envelope.of(await _detail_with_recent_audit(db, target))


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
        request_id=_parse_request_id(x_request_id),
    )
    return Envelope.of(await _detail_with_recent_audit(db, target))
