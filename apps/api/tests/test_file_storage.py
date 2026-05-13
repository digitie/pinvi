from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.services.file_storage import FileStorageError, RustfsStorage


def test_rustfs_storage_generates_presigned_upload_url() -> None:
    storage = _build_storage()

    upload = storage.create_presigned_upload(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        filename="beach photo.JPG",
        content_type="image/jpeg",
        content_length=1024,
        purpose="media_asset",
    )

    assert upload.bucket == "tripmate-media"
    assert upload.storage_key.startswith(
        "user-uploads/media_asset/11111111-1111-1111-1111-111111111111/"
    )
    assert upload.storage_key.endswith(".jpg")
    assert upload.upload_url.startswith("http://127.0.0.1:19000/tripmate-media/")
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in upload.upload_url
    assert "X-Amz-Signature=" in upload.upload_url
    assert "X-Amz-SignedHeaders=content-type%3Bhost" in upload.upload_url
    assert upload.headers == {"Content-Type": "image/jpeg"}
    assert upload.public_url == "https://cdn.example.test/" + upload.storage_key


def test_rustfs_storage_rejects_disallowed_content_type() -> None:
    storage = _build_storage()

    with pytest.raises(FileStorageError):
        storage.create_presigned_upload(
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
            filename="payload.exe",
            content_type="application/x-msdownload",
            content_length=1024,
        )


def test_rustfs_storage_rejects_oversized_upload() -> None:
    storage = _build_storage(max_upload_bytes=100)

    with pytest.raises(FileStorageError):
        storage.create_presigned_upload(
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
            filename="large.png",
            content_type="image/png",
            content_length=101,
        )


def test_rustfs_storage_builds_content_type_extension_fallback() -> None:
    storage = _build_storage()

    key = storage.build_user_upload_key(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        purpose="avatar",
        filename="profile",
        content_type="image/webp",
        now=datetime(2026, 5, 13, tzinfo=UTC),
    )

    assert key.startswith("user-uploads/avatar/11111111-1111-1111-1111-111111111111/2026/05/")
    assert key.endswith(".webp")


def _build_storage(*, max_upload_bytes: int = 10_000) -> RustfsStorage:
    return RustfsStorage(
        endpoint_url="http://rustfs:9000",
        public_endpoint_url="http://127.0.0.1:19000",
        public_base_url="https://cdn.example.test",
        region="us-east-1",
        bucket="tripmate-media",
        access_key_id="test-access",
        secret_access_key="test-secret",
        upload_url_expires_seconds=900,
        max_upload_bytes=max_upload_bytes,
        allowed_content_types=["image/jpeg", "image/png", "image/webp"],
    )
