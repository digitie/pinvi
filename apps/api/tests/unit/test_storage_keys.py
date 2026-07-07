"""storage key + MIME 검증 단위 테스트."""

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings, settings
from app.services.rustfs_storage import (
    FileTooLargeError,
    MimeNotAllowedError,
    build_storage_key,
    make_download_url,
    make_upload_url,
)


def test_build_storage_key_pattern() -> None:
    user_id = uuid.uuid4()
    key = build_storage_key(purpose="trip_attachment", user_id=user_id, filename="photo.jpg")
    assert key.startswith(f"user-uploads/trip_attachment/{user_id}/")
    assert key.endswith(".jpg")


def test_make_upload_url_basic() -> None:
    user_id = uuid.uuid4()
    response = make_upload_url(
        purpose="trip_attachment",
        user_id=user_id,
        filename="photo.jpg",
        content_type="image/jpeg",
        content_length=1024,
    )
    assert response.method == "PUT"
    assert "image/jpeg" in response.headers["Content-Type"]
    assert response.max_upload_bytes > 0


def test_make_upload_url_is_really_signed() -> None:
    user_id = uuid.uuid4()
    response = make_upload_url(
        purpose="trip_attachment",
        user_id=user_id,
        filename="photo.jpg",
        content_type="image/jpeg",
        content_length=1024,
    )
    url = response.upload_url
    # 실서명 — placeholder 가 아니라 SigV4 query auth 파라미터를 포함.
    assert "PLACEHOLDER" not in url
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Credential=" in url
    assert "X-Amz-Expires=" in url
    # path-style addressing — public endpoint host + bucket + key 가 경로에.
    assert settings.pinvi_rustfs_public_endpoint_url in url
    assert f"/{settings.pinvi_rustfs_bucket}/" in url
    assert response.storage_key in url


def test_make_download_url_is_really_signed() -> None:
    response = make_download_url(
        bucket=settings.pinvi_rustfs_bucket,
        storage_key="user-uploads/trip_attachment/x/2026/06/abc.jpg",
        public_url=None,
    )
    url = response.download_url
    assert response.method == "GET"
    assert "PLACEHOLDER" not in url
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "user-uploads/trip_attachment/x/2026/06/abc.jpg" in url


def test_make_upload_url_rejects_unknown_mime() -> None:
    user_id = uuid.uuid4()
    with pytest.raises(MimeNotAllowedError) as exc_info:
        make_upload_url(
            purpose="trip_attachment",
            user_id=user_id,
            filename="strange.bin",
            content_type="application/x-executable",
            content_length=1024,
        )
    message = str(exc_info.value)
    assert "업로드 가능한 파일 형식" in message
    assert "[" not in message
    assert "image/jpeg" not in message


def test_make_upload_url_can_return_api_proxy_url() -> None:
    user_id = uuid.uuid4()
    response = make_upload_url(
        purpose="trip_attachment",
        user_id=user_id,
        filename="photo.JPG",
        content_type="IMAGE/JPEG",
        content_length=1024,
        public_api_base_url="https://api.example.test",
    )

    assert response.upload_url.startswith("https://api.example.test/storage/uploads/")
    assert "127.0.0.1" not in response.upload_url
    assert response.headers["Content-Type"] == "image/jpeg"


def test_make_download_url_can_return_api_proxy_url() -> None:
    response = make_download_url(
        bucket=settings.pinvi_rustfs_bucket,
        storage_key="user-uploads/trip_attachment/x/2026/06/abc.jpg",
        public_url=None,
        public_api_base_url="https://api.example.test",
    )

    assert response.download_url.startswith("https://api.example.test/storage/downloads/")
    assert "127.0.0.1" not in response.download_url


def test_make_upload_url_rejects_too_large() -> None:
    user_id = uuid.uuid4()
    with pytest.raises(FileTooLargeError):
        make_upload_url(
            purpose="trip_attachment",
            user_id=user_id,
            filename="photo.jpg",
            content_type="image/jpeg",
            content_length=10**12,
        )


def test_make_upload_url_accepts_scope_specific_limits() -> None:
    user_id = uuid.uuid4()
    response = make_upload_url(
        purpose="avatar",
        user_id=user_id,
        filename="face.webp",
        content_type="image/webp",
        content_length=2048,
        max_upload_bytes=4096,
        allowed_content_types={"image/webp"},
    )

    assert response.max_upload_bytes == 4096
    assert response.storage_key.startswith(f"user-uploads/avatar/{user_id}/")


def test_make_upload_url_rejects_scope_specific_mime() -> None:
    user_id = uuid.uuid4()
    with pytest.raises(MimeNotAllowedError):
        make_upload_url(
            purpose="avatar",
            user_id=user_id,
            filename="doc.pdf",
            content_type="application/pdf",
            content_length=1024,
            max_upload_bytes=4096,
            allowed_content_types={"image/jpeg"},
        )


def test_settings_reads_rustfs_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PINVI_RUSTFS_ENDPOINT_URL", "http://127.0.0.1:12101")
    monkeypatch.setenv("PINVI_RUSTFS_BUCKET", "pinvi-test")
    monkeypatch.setenv("PINVI_RUSTFS_ACCESS_KEY_ID", "rustfsadmin")
    monkeypatch.setenv("PINVI_RUSTFS_SECRET_ACCESS_KEY", "rustfsadmin")
    monkeypatch.setenv("PINVI_RUSTFS_ALLOWED_CONTENT_TYPES", '["text/plain"]')

    loaded = Settings(_env_file=None)

    assert loaded.pinvi_rustfs_endpoint_url == "http://127.0.0.1:12101"
    assert loaded.pinvi_rustfs_bucket == "pinvi-test"
    assert loaded.pinvi_rustfs_access_key_id == "rustfsadmin"
    assert loaded.pinvi_rustfs_secret_access_key == "rustfsadmin"
    assert loaded.pinvi_rustfs_allowed_content_types == ["text/plain"]
