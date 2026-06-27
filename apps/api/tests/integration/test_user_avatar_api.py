"""사용자 아바타 RustFS 업로드/삭제 API 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        user = User(
            email=f"avatar-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
            nickname="아바타",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def test_user_avatar_upload_apply_download_and_delete(
    client,
    session_factory,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _create_user(session_factory)

    upload = await client.post(
        "/users/me/avatar/upload-url",
        json={
            "filename": "face.jpg",
            "content_type": "image/jpeg",
            "content_length": 1024,
        },
        cookies=auth_cookies(str(user_id)),
    )

    assert upload.status_code == 200, upload.text
    upload_data = upload.json()["data"]
    assert upload_data["max_upload_bytes"] == 2 * 1024 * 1024
    assert upload_data["storage_key"].startswith(f"user-uploads/avatar/{user_id}/")

    applied = await client.put(
        "/users/me/avatar",
        json={
            "bucket": upload_data["bucket"],
            "storage_key": upload_data["storage_key"],
            "content_type": "image/jpeg",
            "byte_size": 1024,
            "public_url": None,
        },
        cookies=auth_cookies(str(user_id)),
    )

    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["has_avatar"] is True

    me = await client.get("/auth/me", cookies=auth_cookies(str(user_id)))
    assert me.status_code == 200
    assert me.json()["data"]["avatar_kind"] == "upload"
    assert me.json()["data"]["has_avatar"] is True

    download = await client.get(
        "/users/me/avatar/download-url",
        cookies=auth_cookies(str(user_id)),
    )

    assert download.status_code == 200
    assert download.json()["data"]["bucket"] == settings.pinvi_rustfs_bucket
    assert "X-Amz-Signature=" in download.json()["data"]["download_url"]

    deleted_keys: list[str] = []

    async def _delete_object(*, key: str) -> None:
        deleted_keys.append(key)

    import app.api.v1.users as users_router

    monkeypatch.setattr(users_router, "delete_object", _delete_object)

    deleted = await client.delete("/users/me/avatar", cookies=auth_cookies(str(user_id)))

    assert deleted.status_code == 200
    assert deleted.json()["data"]["has_avatar"] is False
    assert deleted_keys == [upload_data["storage_key"]]

    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.user_id == user_id))

    assert user is not None
    assert user.avatar_storage_key is None
    assert user.avatar_kind == "default"


async def test_user_avatar_rejects_non_image_and_too_large(
    client,
    session_factory,
    auth_cookies,
) -> None:
    user_id = await _create_user(session_factory)

    bad_mime = await client.post(
        "/users/me/avatar/upload-url",
        json={
            "filename": "doc.pdf",
            "content_type": "application/pdf",
            "content_length": 1024,
        },
        cookies=auth_cookies(str(user_id)),
    )

    assert bad_mime.status_code == 422
    assert bad_mime.json()["error"]["code"] == "MIME_NOT_ALLOWED"

    too_large = await client.post(
        "/users/me/avatar/upload-url",
        json={
            "filename": "face.jpg",
            "content_type": "image/jpeg",
            "content_length": 2 * 1024 * 1024 + 1,
        },
        cookies=auth_cookies(str(user_id)),
    )

    assert too_large.status_code == 422
    assert too_large.json()["error"]["code"] == "FILE_TOO_LARGE"
