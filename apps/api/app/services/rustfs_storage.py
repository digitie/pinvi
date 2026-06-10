"""RustFS presigned PUT/GET URL 발급 + 첨부 메타 등록 — `docs/api/storage.md`.

presigned URL 은 boto3 `generate_presigned_url`(SigV4 query auth)로 실서명한다. 서명은
순수 로컬 연산(네트워크 호출 없음)이라 async 핸들러에서 동기 호출해도 블로킹이 없다.
서명 host 는 **public endpoint**(브라우저가 접근하는 host) — 서버→RustFS 내부 endpoint 가
아니라 — 를 써야 서명이 유효하다. RustFS/MinIO 계열은 path-style addressing 필수.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import settings
from app.schemas.storage import AttachmentPurpose, DownloadUrlResponse, UploadUrlResponse


@lru_cache(maxsize=4)
def _presign_client(endpoint_url: str, access_key: str, secret_key: str) -> Any:
    """public endpoint 에 바인딩된 presign 전용 S3 client(설정 조합별 캐시)."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _presigner() -> Any:
    return _presign_client(
        settings.tripmate_rustfs_public_endpoint_url,
        settings.tripmate_rustfs_access_key_id,
        settings.tripmate_rustfs_secret_access_key,
    )


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
    """presigned PUT URL 응답을 만들어 반환(boto3 SigV4 query auth 실서명).

    `ContentType` 을 서명에 포함하므로 클라이언트는 PUT 시 동일한 `Content-Type` 헤더를
    반드시 보내야 한다(응답 `headers` 그대로). body 는 UNSIGNED-PAYLOAD(query 서명 기본).
    """
    max_bytes = settings.tripmate_rustfs_max_upload_bytes
    if content_length > max_bytes:
        raise FileTooLargeError(f"최대 {max_bytes} bytes")
    allowed = _allowed_content_types()
    if content_type not in allowed:
        raise MimeNotAllowedError(f"허용 MIME: {sorted(allowed)}")

    bucket = settings.tripmate_rustfs_bucket
    storage_key = build_storage_key(purpose=purpose, user_id=user_id, filename=filename)
    expires_seconds = settings.tripmate_rustfs_presigned_url_expires_seconds
    expires = datetime.now(UTC) + timedelta(seconds=expires_seconds)
    upload_url: str = _presigner().generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": storage_key, "ContentType": content_type},
        ExpiresIn=expires_seconds,
    )
    return UploadUrlResponse(
        bucket=bucket,
        storage_key=storage_key,
        upload_url=upload_url,
        headers={"Content-Type": content_type},
        expires_at=expires,
        max_upload_bytes=max_bytes,
        public_url=None,
    )


def make_download_url(
    *, bucket: str, storage_key: str, public_url: str | None = None
) -> DownloadUrlResponse:
    """presigned GET URL 응답(private 첨부 접근, T-105) — boto3 SigV4 query auth 실서명.

    public_url이 있으면 함께 반환해 공개 버킷은 그대로 직접 접근하게 한다.
    """
    expires_seconds = settings.tripmate_rustfs_presigned_url_expires_seconds
    expires = datetime.now(UTC) + timedelta(seconds=expires_seconds)
    download_url: str = _presigner().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": storage_key},
        ExpiresIn=expires_seconds,
    )
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
