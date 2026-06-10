"""RustFS presigned PUT URL 발급 + 첨부 메타 등록 — `docs/api/storage.md`."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.schemas.storage import AttachmentPurpose, DownloadUrlResponse, UploadUrlResponse


def _allowed_content_types() -> set[str]:
    raw = settings.tripmate_rustfs_allowed_content_types
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


class InvalidStorageRefError(StorageError):
    code = "INVALID_ATTACHMENT_STORAGE_REF"


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
    max_bytes = settings.tripmate_rustfs_max_upload_bytes
    if content_length > max_bytes:
        raise FileTooLargeError(f"최대 {max_bytes} bytes")
    allowed = _allowed_content_types()
    if content_type not in allowed:
        raise MimeNotAllowedError(f"허용 MIME: {sorted(allowed)}")

    bucket = settings.tripmate_rustfs_bucket
    public_endpoint = settings.tripmate_rustfs_public_endpoint_url
    storage_key = build_storage_key(purpose=purpose, user_id=user_id, filename=filename)
    expires = datetime.now(UTC) + timedelta(
        seconds=settings.tripmate_rustfs_presigned_url_expires_seconds
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


def make_download_url(
    *, bucket: str, storage_key: str, public_url: str | None = None
) -> DownloadUrlResponse:
    """presigned GET URL 응답(private 첨부 접근, T-105).

    Sprint 2 시점에는 실서명 없이 placeholder URL을 생성(make_upload_url과 동일 패턴).
    public_url이 있으면 함께 반환해 공개 버킷은 그대로 직접 접근하게 한다.
    """
    public_endpoint = settings.tripmate_rustfs_public_endpoint_url
    expires = datetime.now(UTC) + timedelta(
        seconds=settings.tripmate_rustfs_presigned_url_expires_seconds
    )
    download_url = f"{public_endpoint}/{bucket}/{storage_key}?X-Amz-Signature=PLACEHOLDER"
    return DownloadUrlResponse(
        bucket=bucket,
        storage_key=storage_key,
        download_url=download_url,
        expires_at=expires,
        public_url=public_url,
    )


def validate_attachment_storage_ref(
    *,
    bucket: str | None,
    storage_key: str | None,
    purpose: str,
    user_id: uuid.UUID,
) -> None:
    """첨부 metadata가 서버가 발급한 presigned upload ref를 가리키는지 검증한다."""
    if bucket != settings.tripmate_rustfs_bucket:
        raise InvalidStorageRefError("첨부 bucket은 서버가 발급한 RustFS bucket이어야 합니다.")
    expected_prefix = f"user-uploads/{purpose}/{user_id}/"
    if not isinstance(storage_key, str) or not storage_key.startswith(expected_prefix):
        raise InvalidStorageRefError(
            "첨부 storage_key는 현재 사용자의 presigned 업로드 경로여야 합니다."
        )
