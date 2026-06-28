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
    AdminAvatarApplyRequest,
    AdminAvatarDeleteRequest,
    AdminPagedResponse,
    AdminUserDetail,
    AdminUserFileQuota,
    AdminUserFileQuotaUpdateRequest,
    AdminUserRoleMutationRequest,
    AdminUserSummary,
)
from app.schemas.envelope import Envelope
from app.schemas.storage import (
    AVATAR_CONTENT_TYPES,
    AvatarUploadUrlRequest,
    DownloadUrlResponse,
    UploadUrlResponse,
)
from app.services.admin_audit import append_admin_audit
from app.services.admin_users import (
    AdminUserNotFoundError,
    AdminUserPermissionError,
    AdminUserRoleTransitionError,
    disable_user,
    force_verify,
    grant_user_role,
    list_recent_user_audit,
    list_users,
    mask_email,
    normalize_roles,
    revoke_user_role,
)
from app.services.avatar_storage import (
    apply_avatar,
    avatar_state,
    clear_avatar,
    get_storage_settings,
    validate_avatar_apply,
)
from app.services.rustfs_admin import delete_object
from app.services.rustfs_storage import (
    FileTooLargeError,
    InvalidStorageRefError,
    MimeNotAllowedError,
    make_download_url,
    make_upload_url,
)
from app.services.storage_policy import effective_attachment_quota, user_quota_override_state

router = APIRouter(prefix="/admin/users", tags=["admin"])


def _to_summary(u: User) -> AdminUserSummary:
    return AdminUserSummary(
        user_id=u.user_id,
        email_masked=mask_email(u.email),
        nickname=u.nickname,
        status=u.status,
        roles=normalize_roles(u.roles),
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
    file_quota: AdminUserFileQuota | None = None,
) -> AdminUserDetail:
    base = _to_summary(u)
    return AdminUserDetail(
        **base.model_dump(),
        email=u.email if email_revealed else mask_email(u.email),
        email_revealed=email_revealed,
        email_status=u.email_status,
        is_active=u.is_active,
        avatar_url=u.avatar_url,
        avatar_kind=u.avatar_kind,
        avatar_content_type=u.avatar_content_type,
        avatar_byte_size=u.avatar_byte_size,
        avatar_updated_at=u.avatar_updated_at,
        has_avatar=bool(u.avatar_bucket and u.avatar_storage_key),
        file_quota=file_quota
        or AdminUserFileQuota(
            attachment_max_upload_bytes_override=u.attachment_max_upload_bytes_override,
            trip_attachment_quota_bytes_override=u.trip_attachment_quota_bytes_override,
            user_attachment_quota_bytes_override=u.user_attachment_quota_bytes_override,
        ),
        recent_audit=recent_audit or [],
    )


async def _detail_with_recent_audit(
    db: AsyncSession,
    u: User,
    *,
    email_revealed: bool = False,
) -> AdminUserDetail:
    rows = await list_recent_user_audit(db, user_id=u.user_id)
    settings_row = await get_storage_settings(db)
    quota = effective_attachment_quota(settings_row, u)
    return _to_detail(
        u,
        email_revealed=email_revealed,
        file_quota=AdminUserFileQuota(
            attachment_max_upload_bytes_override=u.attachment_max_upload_bytes_override,
            trip_attachment_quota_bytes_override=u.trip_attachment_quota_bytes_override,
            user_attachment_quota_bytes_override=u.user_attachment_quota_bytes_override,
            effective_attachment_max_upload_bytes=quota.max_upload_bytes,
            effective_trip_attachment_quota_bytes=quota.trip_quota_bytes,
            effective_user_attachment_quota_bytes=quota.user_quota_bytes,
        ),
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


def _storage_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (FileTooLargeError, MimeNotAllowedError, InvalidStorageRefError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "STORAGE_UNAVAILABLE", "message": "객체 저장소 요청에 실패했습니다."},
    )


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


@router.post("/{user_id}/avatar/upload-url", response_model=Envelope[UploadUrlResponse])
async def create_user_avatar_upload_url(
    user_id: uuid.UUID,
    body: AvatarUploadUrlRequest,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[UploadUrlResponse]:
    target = await _get_user_or_404(db, user_id)
    settings_row = await get_storage_settings(db)
    try:
        response = make_upload_url(
            purpose="avatar",
            user_id=target.user_id,
            filename=body.filename,
            content_type=body.content_type,
            content_length=body.content_length,
            max_upload_bytes=settings_row.avatar_max_upload_bytes,
            allowed_content_types=AVATAR_CONTENT_TYPES,
        )
    except (FileTooLargeError, MimeNotAllowedError) as exc:
        raise _storage_error(exc) from exc
    return Envelope.of(response)


@router.put("/{user_id}/avatar", response_model=Envelope[AdminUserDetail])
async def update_user_avatar_endpoint(
    user_id: uuid.UUID,
    body: AdminAvatarApplyRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminUserDetail]:
    target = await _get_user_or_404(db, user_id)
    settings_row = await get_storage_settings(db)
    try:
        validate_avatar_apply(
            body,
            user_id=target.user_id,
            max_upload_bytes=settings_row.avatar_max_upload_bytes,
        )
    except (FileTooLargeError, MimeNotAllowedError, InvalidStorageRefError) as exc:
        raise _storage_error(exc) from exc

    before_state = avatar_state(target)
    apply_avatar(target, body)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="user.avatar_replace",
        resource_type="user",
        resource_id=str(target.user_id),
        before_state=before_state,
        after_state=avatar_state(target),
        access_reason=body.access_reason,
        target_pii_fields=["avatar"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(target)
    return Envelope.of(await _detail_with_recent_audit(db, target))


@router.get("/{user_id}/avatar/download-url", response_model=Envelope[DownloadUrlResponse])
async def get_user_avatar_download_url(
    user_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[DownloadUrlResponse]:
    target = await _get_user_or_404(db, user_id)
    if not target.avatar_bucket or not target.avatar_storage_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "아바타가 없습니다."},
        )
    try:
        response = make_download_url(
            bucket=target.avatar_bucket,
            storage_key=target.avatar_storage_key,
            public_url=target.avatar_url,
        )
    except Exception as exc:
        raise _storage_error(exc) from exc
    return Envelope.of(response)


@router.delete("/{user_id}/avatar", response_model=Envelope[AdminUserDetail])
async def delete_user_avatar_endpoint(
    user_id: uuid.UUID,
    body: AdminAvatarDeleteRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminUserDetail]:
    target = await _get_user_or_404(db, user_id)
    before_state = avatar_state(target)
    if target.avatar_storage_key:
        try:
            await delete_object(key=target.avatar_storage_key)
        except Exception as exc:
            raise _storage_error(exc) from exc
    clear_avatar(target)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="user.avatar_delete",
        resource_type="user",
        resource_id=str(target.user_id),
        before_state=before_state,
        after_state=avatar_state(target),
        access_reason=body.access_reason,
        target_pii_fields=["avatar"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(target)
    return Envelope.of(await _detail_with_recent_audit(db, target))


@router.put("/{user_id}/file-quota", response_model=Envelope[AdminUserDetail])
async def update_user_file_quota_endpoint(
    user_id: uuid.UUID,
    body: AdminUserFileQuotaUpdateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminUserDetail]:
    target = await _get_user_or_404(db, user_id)
    before_state = user_quota_override_state(target)
    target.attachment_max_upload_bytes_override = body.attachment_max_upload_bytes_override
    target.trip_attachment_quota_bytes_override = body.trip_attachment_quota_bytes_override
    target.user_attachment_quota_bytes_override = body.user_attachment_quota_bytes_override
    after_state = user_quota_override_state(target)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="user.file_quota_update",
        resource_type="user",
        resource_id=str(target.user_id),
        before_state=before_state,
        after_state=after_state,
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(target)
    return Envelope.of(await _detail_with_recent_audit(db, target))


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
    await db.commit()
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
        target, before_state = await force_verify(db, user_id=user_id, actor_id=admin.user_id)
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
        before_state=before_state,
        after_state={
            "status": target.status,
            "email_verified_at": target.email_verified_at.isoformat()
            if target.email_verified_at
            else None,
        },
        access_reason=body.access_reason,
        target_pii_fields=["email"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(target)
    return Envelope.of(await _detail_with_recent_audit(db, target))


async def _mutate_user_role(
    *,
    db: DbSession,
    request: Request,
    actor: User,
    user_id: uuid.UUID,
    body: AdminUserRoleMutationRequest,
    action: str,
    x_request_id: str | None,
) -> Envelope[AdminUserDetail]:
    try:
        if action == "grant":
            target, before_state = await grant_user_role(
                db,
                user_id=user_id,
                actor_id=actor.user_id,
                role=body.role,
            )
            audit_action = "user.role_grant"
        else:
            target, before_state = await revoke_user_role(
                db,
                user_id=user_id,
                actor_id=actor.user_id,
                role=body.role,
            )
            audit_action = "user.role_revoke"
    except AdminUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except AdminUserPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except AdminUserRoleTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    await append_admin_audit(
        db,
        actor_user_id=actor.user_id,
        action=audit_action,
        resource_type="user",
        resource_id=str(target.user_id),
        before_state=before_state,
        after_state={"roles": normalize_roles(target.roles)},
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(target)
    return Envelope.of(await _detail_with_recent_audit(db, target))


@router.post("/{user_id}/roles/grant", response_model=Envelope[AdminUserDetail])
async def grant_user_role_endpoint(
    user_id: uuid.UUID,
    body: AdminUserRoleMutationRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminUserDetail]:
    return await _mutate_user_role(
        db=db,
        request=request,
        actor=admin,
        user_id=user_id,
        body=body,
        action="grant",
        x_request_id=x_request_id,
    )


@router.post("/{user_id}/roles/revoke", response_model=Envelope[AdminUserDetail])
async def revoke_user_role_endpoint(
    user_id: uuid.UUID,
    body: AdminUserRoleMutationRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminUserDetail]:
    return await _mutate_user_role(
        db=db,
        request=request,
        actor=admin,
        user_id=user_id,
        body=body,
        action="revoke",
        x_request_id=x_request_id,
    )


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
        target, before_state = await disable_user(db, user_id=user_id, actor_id=admin.user_id)
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
        before_state=before_state,
        after_state={"status": "disabled", "is_active": False},
        access_reason=body.access_reason,
        target_pii_fields=["email"],
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(target)
    return Envelope.of(await _detail_with_recent_audit(db, target))
