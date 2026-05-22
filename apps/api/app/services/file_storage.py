from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import SplitResult, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import UUID, uuid4
from xml.etree import ElementTree

from app.core.config import Settings

StorageUploadPurpose = Literal[
    "media_asset",
    "avatar",
    "trip_attachment",
    "plan_attachment",
    "poi_attachment",
    "notice_plan_attachment",
    "notice_poi_attachment",
]

_SAFE_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_SAFE_EXTENSION_RE = re.compile(r"^[A-Za-z0-9]{1,12}$")
_FALLBACK_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "application/pdf": ".pdf",
}


class FileStorageError(ValueError):
    """Raised when a file storage request is invalid."""


class FileStorageConfigurationError(RuntimeError):
    """Raised when RustFS storage is not configured."""


class FileStorageHttpError(RuntimeError):
    """Raised when RustFS returns an unusable S3-compatible response."""


@dataclass(frozen=True)
class PresignedUpload:
    bucket: str
    storage_key: str
    upload_url: str
    headers: dict[str, str]
    expires_at: datetime
    public_url: str | None


@dataclass(frozen=True)
class RustfsObject:
    key: str
    size: int | None = None
    last_modified: datetime | None = None
    etag: str | None = None
    storage_class: str | None = None


@dataclass(frozen=True)
class RustfsObjectListing:
    bucket: str
    prefix: str
    objects: tuple[RustfsObject, ...]
    is_truncated: bool
    next_continuation_token: str | None


class RustfsStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str | None,
        public_base_url: str | None,
        region: str,
        bucket: str,
        access_key_id: str | None,
        secret_access_key: str | None,
        upload_url_expires_seconds: int,
        max_upload_bytes: int,
        allowed_content_types: list[str],
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.public_endpoint_url = (public_endpoint_url or endpoint_url).rstrip("/")
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self.region = region
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.upload_url_expires_seconds = upload_url_expires_seconds
        self.max_upload_bytes = max_upload_bytes
        self.allowed_content_types = frozenset(allowed_content_types)

    @classmethod
    def from_settings(cls, settings: Settings) -> RustfsStorage:
        return cls(
            endpoint_url=settings.rustfs_endpoint_url,
            public_endpoint_url=settings.rustfs_public_endpoint_url,
            public_base_url=settings.rustfs_public_base_url,
            region=settings.rustfs_region,
            bucket=settings.rustfs_bucket,
            access_key_id=settings.rustfs_access_key_id,
            secret_access_key=settings.rustfs_secret_access_key,
            upload_url_expires_seconds=settings.rustfs_presigned_url_expires_seconds,
            max_upload_bytes=settings.rustfs_max_upload_bytes,
            allowed_content_types=settings.rustfs_allowed_content_types,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key)

    def create_presigned_upload(
        self,
        *,
        user_id: UUID,
        filename: str,
        content_type: str,
        content_length: int,
        purpose: StorageUploadPurpose = "media_asset",
    ) -> PresignedUpload:
        self._ensure_configured()
        self._validate_bucket()
        self._validate_upload(content_type=content_type, content_length=content_length)

        now = datetime.now(UTC)
        storage_key = self.build_user_upload_key(
            user_id=user_id,
            purpose=purpose,
            filename=filename,
            content_type=content_type,
            now=now,
        )
        expires_at = now + timedelta(seconds=self.upload_url_expires_seconds)
        headers = {"Content-Type": content_type}
        upload_url = self._presign_url(
            method="PUT",
            storage_key=storage_key,
            headers=headers,
            expires_seconds=self.upload_url_expires_seconds,
            now=now,
        )
        return PresignedUpload(
            bucket=self.bucket,
            storage_key=storage_key,
            upload_url=upload_url,
            headers=headers,
            expires_at=expires_at,
            public_url=self.public_object_url(storage_key),
        )

    def build_user_upload_key(
        self,
        *,
        user_id: UUID,
        purpose: StorageUploadPurpose,
        filename: str,
        content_type: str,
        now: datetime,
    ) -> str:
        extension = _safe_extension(filename) or _FALLBACK_EXTENSIONS.get(content_type, "")
        return f"user-uploads/{purpose}/{user_id}/{now:%Y/%m}/{uuid4().hex}{extension.lower()}"

    def public_object_url(self, storage_key: str) -> str | None:
        if not self.public_base_url:
            return None
        return f"{self.public_base_url}/{quote(storage_key, safe='/')}"

    def list_objects(
        self,
        *,
        prefix: str = "",
        max_keys: int = 100,
        continuation_token: str | None = None,
        bucket: str | None = None,
    ) -> RustfsObjectListing:
        self._ensure_configured()
        self._validate_bucket()
        if max_keys <= 0 or max_keys > 1000:
            raise FileStorageError("max_keys must be between 1 and 1000.")

        target_bucket = bucket or self.bucket
        query = {
            "list-type": "2",
            "max-keys": str(max_keys),
        }
        if prefix:
            query["prefix"] = prefix
        if continuation_token:
            query["continuation-token"] = continuation_token

        body = self._request("GET", f"/{quote(target_bucket, safe='')}", query=query)
        return _parse_list_objects(body, bucket=target_bucket, prefix=prefix)

    def delete_object(self, storage_key: str, *, bucket: str | None = None) -> None:
        self._ensure_configured()
        self._validate_bucket()
        normalized_key = storage_key.strip().lstrip("/")
        if not normalized_key:
            raise FileStorageError("storage_key is required.")
        target_bucket = bucket or self.bucket
        self._request(
            "DELETE",
            f"/{quote(target_bucket, safe='')}/{quote(normalized_key, safe='/')}",
        )

    def _ensure_configured(self) -> None:
        if not self.is_configured:
            raise FileStorageConfigurationError("RustFS access key and secret key are required.")

    def _validate_bucket(self) -> None:
        if not _SAFE_BUCKET_RE.fullmatch(self.bucket):
            raise FileStorageConfigurationError("RustFS bucket name is invalid.")

    def _validate_upload(self, *, content_type: str, content_length: int) -> None:
        if content_type not in self.allowed_content_types:
            raise FileStorageError(f"Unsupported upload content type: {content_type}")
        if content_length <= 0:
            raise FileStorageError("Upload content length must be greater than zero.")
        if content_length > self.max_upload_bytes:
            raise FileStorageError(f"Upload content length exceeds {self.max_upload_bytes} bytes.")

    def _presign_url(
        self,
        *,
        method: str,
        storage_key: str,
        headers: dict[str, str],
        expires_seconds: int,
        now: datetime,
    ) -> str:
        if self.access_key_id is None or self.secret_access_key is None:
            raise FileStorageConfigurationError("RustFS credentials are required.")

        endpoint = urlsplit(self.public_endpoint_url)
        if not endpoint.scheme or not endpoint.netloc:
            raise FileStorageConfigurationError("RustFS endpoint URL must include scheme and host.")

        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        host = endpoint.netloc
        signed_header_values = {"host": host, **{k.lower(): v for k, v in headers.items()}}
        signed_headers = ";".join(sorted(signed_header_values))
        query_parameters = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key_id}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires_seconds),
            "X-Amz-SignedHeaders": signed_headers,
        }

        canonical_uri = _canonical_object_path(endpoint.path, self.bucket, storage_key)
        canonical_query = _canonical_query_string(query_parameters)
        canonical_headers = "".join(
            f"{name}:{_normalize_header_value(value)}\n"
            for name, value in sorted(signed_header_values.items())
        )
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_query,
                canonical_headers,
                signed_headers,
                "UNSIGNED-PAYLOAD",
            ]
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _signature_key(
            secret_access_key=self.secret_access_key,
            date_stamp=date_stamp,
            region=self.region,
        )
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        signed_query = _canonical_query_string({**query_parameters, "X-Amz-Signature": signature})
        return urlunsplit((endpoint.scheme, endpoint.netloc, canonical_uri, signed_query, ""))

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
    ) -> bytes:
        if self.access_key_id is None or self.secret_access_key is None:
            raise FileStorageConfigurationError("RustFS credentials are required.")

        endpoint = urlsplit(self.endpoint_url)
        if not endpoint.scheme or not endpoint.netloc:
            raise FileStorageConfigurationError("RustFS endpoint URL must include scheme and host.")

        normalized_path = f"{endpoint.path.rstrip('/')}{path}" if endpoint.path else path
        query_dict = dict(query or {})
        url = urlunsplit(
            (endpoint.scheme, endpoint.netloc, normalized_path, urlencode(query_dict), "")
        )
        request = Request(url, method=method)
        for key, value in self._signed_headers(
            method=method,
            endpoint=endpoint,
            path=normalized_path,
            query=query_dict,
        ).items():
            request.add_header(key, value)

        try:
            with urlopen(request, timeout=10.0) as response:  # noqa: S310
                body: bytes = response.read()
                return body
        except OSError as exc:
            raise FileStorageHttpError(str(exc)) from exc

    def _signed_headers(
        self,
        *,
        method: str,
        endpoint: SplitResult,
        path: str,
        query: Mapping[str, str],
    ) -> dict[str, str]:
        if self.access_key_id is None or self.secret_access_key is None:
            raise FileStorageConfigurationError("RustFS credentials are required.")

        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        headers = {
            "host": endpoint.netloc,
            "x-amz-content-sha256": "UNSIGNED-PAYLOAD",
            "x-amz-date": amz_date,
        }
        signed_headers = ";".join(sorted(headers))
        canonical_request = "\n".join(
            [
                method,
                quote(path, safe="/"),
                _canonical_query_string(query),
                "".join(f"{name}:{headers[name]}\n" for name in sorted(headers)),
                signed_headers,
                "UNSIGNED-PAYLOAD",
            ]
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _signature_key(
            secret_access_key=self.secret_access_key,
            date_stamp=date_stamp,
            region=self.region,
        )
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {**headers, "authorization": authorization}


def _safe_extension(filename: str) -> str:
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in name:
        return ""
    extension = name.rsplit(".", 1)[-1]
    if not _SAFE_EXTENSION_RE.fullmatch(extension):
        return ""
    return f".{extension}"


def _canonical_object_path(endpoint_path: str, bucket: str, storage_key: str) -> str:
    base_path = endpoint_path.rstrip("/")
    encoded_bucket = quote(bucket, safe="")
    encoded_key = quote(storage_key, safe="/")
    return (
        f"{base_path}/{encoded_bucket}/{encoded_key}"
        if base_path
        else f"/{encoded_bucket}/{encoded_key}"
    )


def _canonical_query_string(parameters: Mapping[str, str]) -> str:
    return "&".join(
        f"{quote(str(key), safe='-_.~')}={quote(str(value), safe='-_.~')}"
        for key, value in sorted(parameters.items())
    )


def _normalize_header_value(value: str) -> str:
    return " ".join(value.strip().split())


def _signature_key(*, secret_access_key: str, date_stamp: str, region: str) -> bytes:
    date_key = _sign(("AWS4" + secret_access_key).encode("utf-8"), date_stamp)
    date_region_key = _sign(date_key, region)
    date_region_service_key = _sign(date_region_key, "s3")
    return _sign(date_region_service_key, "aws4_request")


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _parse_list_objects(body: bytes, *, bucket: str, prefix: str) -> RustfsObjectListing:
    root = ElementTree.fromstring(body)
    objects: list[RustfsObject] = []
    for node in _findall(root, "Contents"):
        key = _findtext(node, "Key")
        if not key:
            continue
        objects.append(
            RustfsObject(
                key=key,
                size=_int_or_none(_findtext(node, "Size")),
                last_modified=_datetime_or_none(_findtext(node, "LastModified")),
                etag=(_findtext(node, "ETag") or "").strip('"') or None,
                storage_class=_findtext(node, "StorageClass"),
            )
        )
    return RustfsObjectListing(
        bucket=bucket,
        prefix=prefix,
        objects=tuple(objects),
        is_truncated=(_findtext(root, "IsTruncated") or "").lower() == "true",
        next_continuation_token=_findtext(root, "NextContinuationToken"),
    )


def _findall(root: ElementTree.Element, tag: str) -> list[ElementTree.Element]:
    return root.findall(f".//{{*}}{tag}") or root.findall(f".//{tag}")


def _findtext(root: ElementTree.Element, tag: str) -> str | None:
    value = root.findtext(f".//{{*}}{tag}") or root.findtext(f".//{tag}")
    if value is None:
        return None
    text = value.strip()
    return text or None


def _int_or_none(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def _datetime_or_none(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
