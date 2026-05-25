"""storage key + MIME 검증 단위 테스트."""

from __future__ import annotations

import uuid

import pytest

from app.services.rustfs_storage import (
    FileTooLargeError,
    MimeNotAllowedError,
    build_storage_key,
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


def test_make_upload_url_rejects_unknown_mime() -> None:
    user_id = uuid.uuid4()
    with pytest.raises(MimeNotAllowedError):
        make_upload_url(
            purpose="trip_attachment",
            user_id=user_id,
            filename="strange.bin",
            content_type="application/x-executable",
            content_length=1024,
        )


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
