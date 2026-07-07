"""RustFS 업로드/다운로드 URL 발급 + 첨부 메타 등록 — `docs/api/storage.md`.

presigned URL 은 boto3 `generate_presigned_url`(SigV4 query auth)로 실서명한다. 서명은
순수 로컬 연산(네트워크 호출 없음)이라 async 핸들러에서 동기 호출해도 블로킹이 없다.
서명 host 는 **public endpoint**(브라우저가 접근하는 host) — 서버→RustFS 내부 endpoint 가
아니라 — 를 써야 서명이 유효하다. RustFS/MinIO 계열은 path-style addressing 필수.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from binascii import Error as BinasciiError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Literal

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
        settings.pinvi_rustfs_public_endpoint_url,
        settings.pinvi_rustfs_access_key_id,
        settings.pinvi_rustfs_secret_access_key,
    )


def _storage_client() -> Any:
    return _presign_client(
        settings.pinvi_rustfs_endpoint_url,
        settings.pinvi_rustfs_access_key_id,
        settings.pinvi_rustfs_secret_access_key,
    )


def _allowed_content_types() -> set[str]:
    raw = settings.pinvi_rustfs_allowed_content_types
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


def _normalize_content_type(content_type: str) -> str:
    return content_type.strip().lower()


_CONTENT_TYPE_LABELS = {
    "image/jpeg": "JPG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
    "video/mp4": "MP4",
    "application/pdf": "PDF",
}


def _allowed_content_type_message(allowed: set[str]) -> str:
    labels = [_CONTENT_TYPE_LABELS.get(value, value) for value in sorted(allowed)]
    return f"업로드 가능한 파일 형식은 {', '.join(labels)}입니다."


class StorageError(Exception):
    code: str = "SERVICE_UNAVAILABLE"


class MimeNotAllowedError(StorageError):
    code = "MIME_NOT_ALLOWED"


class FileTooLargeError(StorageError):
    code = "FILE_TOO_LARGE"


class InvalidStorageRefError(StorageError):
    code = "INVALID_ATTACHMENT_STORAGE_REF"


class InvalidStorageProxyTokenError(StorageError):
    code = "INVALID_STORAGE_TOKEN"


@dataclass(frozen=True)
class StorageProxyRef:
    op: Literal["put", "get"]
    bucket: str
    storage_key: str
    expires_at: datetime
    content_type: str | None = None
    content_length: int | None = None
    max_upload_bytes: int | None = None


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign_proxy_payload(payload: str) -> str:
    digest = hmac.new(
        settings.pinvi_jwt_secret_key.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _make_storage_proxy_token(
    *,
    op: Literal["put", "get"],
    bucket: str,
    storage_key: str,
    expires_at: datetime,
    content_type: str | None = None,
    content_length: int | None = None,
    max_upload_bytes: int | None = None,
) -> str:
    payload = {
        "v": 1,
        "op": op,
        "bucket": bucket,
        "key": storage_key,
        "exp": int(expires_at.timestamp()),
    }
    if content_type is not None:
        payload["ct"] = content_type
    if content_length is not None:
        payload["len"] = content_length
    if max_upload_bytes is not None:
        payload["max"] = max_upload_bytes

    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{encoded}.{_sign_proxy_payload(encoded)}"


def parse_storage_proxy_token(token: str, *, expected_op: Literal["put", "get"]) -> StorageProxyRef:
    try:
        payload_part, signature_part = token.split(".", 1)
    except ValueError as exc:
        raise InvalidStorageProxyTokenError("저장소 접근 토큰 형식이 올바르지 않습니다.") from exc

    expected_signature = _sign_proxy_payload(payload_part)
    if not hmac.compare_digest(signature_part, expected_signature):
        raise InvalidStorageProxyTokenError("저장소 접근 토큰이 올바르지 않습니다.")

    try:
        payload = json.loads(_b64decode(payload_part))
    except (BinasciiError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidStorageProxyTokenError("저장소 접근 토큰을 읽을 수 없습니다.") from exc

    if payload.get("op") != expected_op:
        raise InvalidStorageProxyTokenError("저장소 접근 토큰 용도가 올바르지 않습니다.")
    bucket = payload.get("bucket")
    storage_key = payload.get("key")
    exp = payload.get("exp")
    if not isinstance(bucket, str) or not isinstance(storage_key, str) or not isinstance(exp, int):
        raise InvalidStorageProxyTokenError("저장소 접근 토큰 내용이 올바르지 않습니다.")
    expires_at = datetime.fromtimestamp(exp, UTC)
    if expires_at <= datetime.now(UTC):
        raise InvalidStorageProxyTokenError("저장소 접근 토큰이 만료되었습니다.")

    content_type = payload.get("ct")
    content_length = payload.get("len")
    max_upload_bytes = payload.get("max")
    return StorageProxyRef(
        op=expected_op,
        bucket=bucket,
        storage_key=storage_key,
        expires_at=expires_at,
        content_type=content_type if isinstance(content_type, str) else None,
        content_length=content_length if isinstance(content_length, int) else None,
        max_upload_bytes=max_upload_bytes if isinstance(max_upload_bytes, int) else None,
    )


def _proxy_url(public_api_base_url: str, path: str) -> str:
    return f"{public_api_base_url.rstrip('/')}{path}"


def put_storage_object(*, ref: StorageProxyRef, body: bytes, content_type: str | None) -> None:
    if ref.op != "put":
        raise InvalidStorageProxyTokenError("저장소 접근 토큰 용도가 올바르지 않습니다.")
    if ref.content_type and _normalize_content_type(content_type or "") != ref.content_type:
        raise MimeNotAllowedError("업로드 요청의 Content-Type이 발급된 값과 다릅니다.")
    if ref.content_length is not None and len(body) != ref.content_length:
        raise FileTooLargeError("업로드 파일 크기가 발급된 값과 다릅니다.")
    if ref.max_upload_bytes is not None and len(body) > ref.max_upload_bytes:
        raise FileTooLargeError(f"최대 {ref.max_upload_bytes} bytes")
    _storage_client().put_object(
        Bucket=ref.bucket,
        Key=ref.storage_key,
        Body=body,
        ContentType=ref.content_type or content_type or "application/octet-stream",
    )


def get_storage_object(*, ref: StorageProxyRef) -> tuple[bytes, str]:
    if ref.op != "get":
        raise InvalidStorageProxyTokenError("저장소 접근 토큰 용도가 올바르지 않습니다.")
    obj = _storage_client().get_object(Bucket=ref.bucket, Key=ref.storage_key)
    body = obj["Body"].read()
    content_type = obj.get("ContentType") or "application/octet-stream"
    return body, content_type


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
    max_upload_bytes: int | None = None,
    allowed_content_types: set[str] | None = None,
    public_api_base_url: str | None = None,
) -> UploadUrlResponse:
    """업로드 URL 응답을 만들어 반환한다.

    `public_api_base_url` 이 있으면 브라우저가 접근 가능한 API 프록시 URL을 반환한다.
    없으면 기존 S3 presigned PUT URL을 반환해 단위 테스트·내부 호출 호환성을 유지한다.
    """
    max_bytes = max_upload_bytes or settings.pinvi_rustfs_max_upload_bytes
    if content_length > max_bytes:
        raise FileTooLargeError(f"최대 {max_bytes} bytes")
    content_type = _normalize_content_type(content_type)
    allowed = {
        _normalize_content_type(value)
        for value in (allowed_content_types or _allowed_content_types())
    }
    if content_type not in allowed:
        raise MimeNotAllowedError(_allowed_content_type_message(allowed))

    bucket = settings.pinvi_rustfs_bucket
    storage_key = build_storage_key(purpose=purpose, user_id=user_id, filename=filename)
    expires_seconds = settings.pinvi_rustfs_presigned_url_expires_seconds
    expires = datetime.now(UTC) + timedelta(seconds=expires_seconds)
    if public_api_base_url:
        token = _make_storage_proxy_token(
            op="put",
            bucket=bucket,
            storage_key=storage_key,
            expires_at=expires,
            content_type=content_type,
            content_length=content_length,
            max_upload_bytes=max_bytes,
        )
        upload_url = _proxy_url(public_api_base_url, f"/storage/uploads/{token}")
    else:
        upload_url = _presigner().generate_presigned_url(
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
    *,
    bucket: str,
    storage_key: str,
    public_url: str | None = None,
    public_api_base_url: str | None = None,
) -> DownloadUrlResponse:
    """다운로드 URL 응답(private 첨부 접근, T-105).

    public_url이 있으면 함께 반환해 공개 버킷은 그대로 직접 접근하게 한다.
    """
    expires_seconds = settings.pinvi_rustfs_presigned_url_expires_seconds
    expires = datetime.now(UTC) + timedelta(seconds=expires_seconds)
    if public_api_base_url:
        token = _make_storage_proxy_token(
            op="get",
            bucket=bucket,
            storage_key=storage_key,
            expires_at=expires,
        )
        download_url = _proxy_url(public_api_base_url, f"/storage/downloads/{token}")
    else:
        download_url = _presigner().generate_presigned_url(
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
    if bucket != settings.pinvi_rustfs_bucket:
        raise InvalidStorageRefError("첨부 bucket은 서버가 발급한 RustFS bucket이어야 합니다.")
    expected_prefix = f"user-uploads/{purpose}/{user_id}/"
    if not isinstance(storage_key, str) or not storage_key.startswith(expected_prefix):
        raise InvalidStorageRefError(
            "첨부 storage_key는 현재 사용자의 presigned 업로드 경로여야 합니다."
        )
