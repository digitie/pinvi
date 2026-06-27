"""`/admin/settings/*` — 운영 전역 설정."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminAvatarSettings,
    AdminAvatarSettingsUpdateRequest,
    AdminFileStorageSettings,
    AdminFileStorageSettingsUpdateRequest,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.storage_policy import (
    get_storage_settings,
    set_attachment_storage_settings,
    set_avatar_max_upload_bytes,
    storage_settings_state,
)

router = APIRouter(prefix="/admin/settings", tags=["admin"])


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


@router.get("/avatar", response_model=Envelope[AdminAvatarSettings])
async def get_avatar_settings(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminAvatarSettings]:
    settings_row = await get_storage_settings(db)
    return Envelope.of(
        AdminAvatarSettings(avatar_max_upload_bytes=settings_row.avatar_max_upload_bytes)
    )


@router.put("/avatar", response_model=Envelope[AdminAvatarSettings])
async def update_avatar_settings(
    body: AdminAvatarSettingsUpdateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminAvatarSettings]:
    settings_row, before_state = await set_avatar_max_upload_bytes(
        db,
        avatar_max_upload_bytes=body.avatar_max_upload_bytes,
    )
    after_state = {"avatar_max_upload_bytes": settings_row.avatar_max_upload_bytes}
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="settings.avatar_update",
        resource_type="storage_settings",
        resource_id="avatar",
        before_state=before_state,
        after_state=after_state,
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(settings_row)
    return Envelope.of(
        AdminAvatarSettings(avatar_max_upload_bytes=settings_row.avatar_max_upload_bytes)
    )


@router.get("/files", response_model=Envelope[AdminFileStorageSettings])
async def get_file_settings(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminFileStorageSettings]:
    settings_row = await get_storage_settings(db)
    return Envelope.of(
        AdminFileStorageSettings(
            attachment_max_upload_bytes=settings_row.attachment_max_upload_bytes,
            trip_attachment_quota_bytes=settings_row.trip_attachment_quota_bytes,
            user_attachment_quota_bytes=settings_row.user_attachment_quota_bytes,
        )
    )


@router.put("/files", response_model=Envelope[AdminFileStorageSettings])
async def update_file_settings(
    body: AdminFileStorageSettingsUpdateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminFileStorageSettings]:
    settings_row, before_state = await set_attachment_storage_settings(
        db,
        attachment_max_upload_bytes=body.attachment_max_upload_bytes,
        trip_attachment_quota_bytes=body.trip_attachment_quota_bytes,
        user_attachment_quota_bytes=body.user_attachment_quota_bytes,
    )
    after_state = storage_settings_state(settings_row)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="settings.files_update",
        resource_type="storage_settings",
        resource_id="files",
        before_state=before_state,
        after_state=after_state,
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(settings_row)
    return Envelope.of(
        AdminFileStorageSettings(
            attachment_max_upload_bytes=settings_row.attachment_max_upload_bytes,
            trip_attachment_quota_bytes=settings_row.trip_attachment_quota_bytes,
            user_attachment_quota_bytes=settings_row.user_attachment_quota_bytes,
        )
    )
