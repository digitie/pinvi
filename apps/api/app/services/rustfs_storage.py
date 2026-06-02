"""RustFS presigned PUT URL 발급 + 첨부 메타 등록 — `docs/api/storage.md`."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.schemas.storage import AttachmentPurpose, UploadUrlResponse


def _allowed_content_types() -> set[str]:
    raw = (
        settings.tripmate_rustfs_allowed_content_types
        if hasattr(settings, "tripmate_rustfs_allowed_content_types")
        else None
    )
    if not raw:
        return {
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
            "video/mp4",
            "application/pdf",
        }
    if isinstance(raw, list):
        return set(raw)
    try:
        return set(json.loads(raw))
    except json.JSONDecodeError:
        return {raw}


class StorageError(Exception):
    code: str = "SERVICE_UNAVAILABLE"


class MimeNotAllowedError(StorageError):
    code = "MIME_NOT_ALLOWED"


class FileTooLargeError(StorageError):
    code = "FILE_TOO_LARGE"


def build_storage_key(
    *,
    purpose: AttachmentPurpose,
    user_id: uuid.UUID,
    filename: str,
) -> str:
    now = datetime.now(UTC)
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    object_uuid = uuid.uuid4().hex
    return f"user-uploads/{purpose}/{user_id}/{now.year:04d}/{now.month:02d}/{object_uuid}.{suffix}"


def make_upload_url(
    *,
    purpose: AttachmentPurpose,
    user_id: uuid.UUID,
    filename: str,
    content_type: str,
    content_length: int,
) -> UploadUrlResponse:
    """presigned PUT URL 응답을 만들어 반환.

    Sprint 2 시점에는 실제 RustFS S3 서명 없이 placeholder URL을 생성.
    Sprint 4~5 활성화 시 `aioboto3` 또는 `botocore`로 실서명.
    """
    max_bytes = getattr(settings, "tripmate_rustfs_max_upload_bytes", 10_485_760)
    if content_length > max_bytes:
        raise FileTooLargeError(f"최대 {max_bytes} bytes")
    allowed = _allowed_content_types()
    if content_type not in allowed:
        raise MimeNotAllowedError(f"허용 MIME: {sorted(allowed)}")

    bucket = getattr(settings, "tripmate_rustfs_bucket", "tripmate-media")
    public_endpoint = getattr(
        settings, "tripmate_rustfs_public_endpoint_url", "http://127.0.0.1:9003"
    )
    storage_key = build_storage_key(purpose=purpose, user_id=user_id, filename=filename)
    expires = datetime.now(UTC) + timedelta(
        seconds=getattr(settings, "tripmate_rustfs_presigned_url_expires_seconds", 900)
    )
    upload_url = f"{public_endpoint}/{bucket}/{storage_key}?X-Amz-Signature=PLACEHOLDER"
    return UploadUrlResponse(
        bucket=bucket,
        storage_key=storage_key,
        upload_url=upload_url,
        headers={"Content-Type": content_type, "x-amz-content-sha256": "UNSIGNED-PAYLOAD"},
        expires_at=expires,
        max_upload_bytes=max_bytes,
        public_url=None,
    )
