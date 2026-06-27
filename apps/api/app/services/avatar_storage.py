"""사용자 아바타 RustFS 메타데이터 관리."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage_settings import StorageSettings
from app.models.user import User
from app.schemas.storage import AVATAR_CONTENT_TYPES, AvatarApplyRequest, AvatarInfo
from app.services.rustfs_storage import (
    FileTooLargeError,
    InvalidStorageRefError,
    MimeNotAllowedError,
    validate_attachment_storage_ref,
)

DEFAULT_AVATAR_MAX_UPLOAD_BYTES = 2 * 1024 * 1024


async def get_storage_settings(db: AsyncSession) -> StorageSettings:
    row = await db.scalar(select(StorageSettings).where(StorageSettings.settings_id == 1))
    if row is not None:
        return row
    row = StorageSettings(
        settings_id=1,
        avatar_max_upload_bytes=DEFAULT_AVATAR_MAX_UPLOAD_BYTES,
    )
    db.add(row)
    await db.flush()
    return row


async def set_avatar_max_upload_bytes(
    db: AsyncSession,
    *,
    avatar_max_upload_bytes: int,
) -> tuple[StorageSettings, dict[str, int]]:
    row = await get_storage_settings(db)
    before_state = {"avatar_max_upload_bytes": row.avatar_max_upload_bytes}
    row.avatar_max_upload_bytes = avatar_max_upload_bytes
    await db.flush()
    return row, before_state


def avatar_info(user: User) -> AvatarInfo:
    return AvatarInfo(
        avatar_kind=user.avatar_kind,
        avatar_url=user.avatar_url,
        avatar_content_type=user.avatar_content_type,
        avatar_byte_size=user.avatar_byte_size,
        avatar_updated_at=user.avatar_updated_at,
        has_avatar=bool(user.avatar_bucket and user.avatar_storage_key),
    )


def avatar_state(user: User) -> dict[str, object | None]:
    return {
        "avatar_kind": user.avatar_kind,
        "avatar_bucket": user.avatar_bucket,
        "avatar_storage_key": user.avatar_storage_key,
        "avatar_content_type": user.avatar_content_type,
        "avatar_byte_size": user.avatar_byte_size,
        "avatar_updated_at": user.avatar_updated_at.isoformat() if user.avatar_updated_at else None,
        "avatar_url": user.avatar_url,
    }


def validate_avatar_apply(
    body: AvatarApplyRequest,
    *,
    user_id: uuid.UUID,
    max_upload_bytes: int,
) -> None:
    if body.content_type not in AVATAR_CONTENT_TYPES:
        raise MimeNotAllowedError(f"허용 MIME: {sorted(AVATAR_CONTENT_TYPES)}")
    if body.byte_size > max_upload_bytes:
        raise FileTooLargeError(f"최대 {max_upload_bytes} bytes")
    validate_attachment_storage_ref(
        bucket=body.bucket,
        storage_key=body.storage_key,
        purpose="avatar",
        user_id=user_id,
    )


def apply_avatar(user: User, body: AvatarApplyRequest) -> None:
    user.avatar_bucket = body.bucket
    user.avatar_storage_key = body.storage_key
    user.avatar_content_type = body.content_type
    user.avatar_byte_size = body.byte_size
    user.avatar_url = body.public_url
    user.avatar_kind = "upload"
    user.avatar_updated_at = datetime.now(UTC)


def clear_avatar(user: User) -> tuple[str | None, str | None]:
    bucket = user.avatar_bucket
    storage_key = user.avatar_storage_key
    user.avatar_bucket = None
    user.avatar_storage_key = None
    user.avatar_content_type = None
    user.avatar_byte_size = None
    user.avatar_url = None
    user.avatar_kind = "default"
    user.avatar_updated_at = datetime.now(UTC)
    return bucket, storage_key


__all__ = [
    "AVATAR_CONTENT_TYPES",
    "InvalidStorageRefError",
    "apply_avatar",
    "avatar_info",
    "avatar_state",
    "clear_avatar",
    "get_storage_settings",
    "set_avatar_max_upload_bytes",
    "validate_avatar_apply",
]
