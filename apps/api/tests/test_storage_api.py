from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app
from app.models.mixins import kst_now
from app.models.user import User
from app.services.admin_auth import hash_password, issue_auth_tokens


def test_create_storage_upload_url_requires_authenticated_user(db_session: Session) -> None:
    client = _build_client(db_session)

    response = client.post(
        "/storage/upload-urls",
        json={
            "filename": "photo.jpg",
            "content_type": "image/jpeg",
            "content_length": 1024,
        },
    )

    assert response.status_code == 401


def test_create_storage_upload_url_returns_rustfs_presigned_put(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRIPMATE_RUSTFS_ENDPOINT_URL", "http://rustfs:9000")
    monkeypatch.setenv("TRIPMATE_RUSTFS_PUBLIC_ENDPOINT_URL", "http://127.0.0.1:19000")
    monkeypatch.setenv("TRIPMATE_RUSTFS_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("TRIPMATE_RUSTFS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("TRIPMATE_RUSTFS_BUCKET", "tripmate-media")
    get_settings.cache_clear()

    user = _add_active_user(db_session)
    settings = get_settings()
    tokens = issue_auth_tokens(
        db_session,
        user_id=user.id,
        secret_key=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        access_token_minutes=settings.access_token_minutes,
        refresh_token_days=settings.refresh_token_days,
    )
    db_session.commit()
    client = _build_client(db_session)
    client.cookies.set(settings.access_token_cookie_name, tokens.access_token)
    client.cookies.set(settings.refresh_token_cookie_name, tokens.refresh_token)

    response = client.post(
        "/storage/upload-urls",
        json={
            "filename": "photo.jpg",
            "content_type": "image/jpeg",
            "content_length": 1024,
            "purpose": "avatar",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["method"] == "PUT"
    assert payload["bucket"] == "tripmate-media"
    assert payload["storage_key"].startswith(f"user-uploads/avatar/{user.id}/")
    assert payload["storage_key"].endswith(".jpg")
    assert payload["upload_url"].startswith("http://127.0.0.1:19000/tripmate-media/")
    assert "X-Amz-Signature=" in payload["upload_url"]
    assert payload["headers"] == {"Content-Type": "image/jpeg"}
    assert payload["max_upload_bytes"] == 10 * 1024 * 1024

    get_settings.cache_clear()


def test_create_storage_upload_url_rejects_disallowed_type(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRIPMATE_RUSTFS_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("TRIPMATE_RUSTFS_SECRET_ACCESS_KEY", "test-secret")
    get_settings.cache_clear()

    user = _add_active_user(db_session)
    settings = get_settings()
    tokens = issue_auth_tokens(
        db_session,
        user_id=user.id,
        secret_key=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        access_token_minutes=settings.access_token_minutes,
        refresh_token_days=settings.refresh_token_days,
    )
    db_session.commit()
    client = _build_client(db_session)
    client.cookies.set(settings.access_token_cookie_name, tokens.access_token)
    client.cookies.set(settings.refresh_token_cookie_name, tokens.refresh_token)

    response = client.post(
        "/storage/upload-urls",
        json={
            "filename": "payload.exe",
            "content_type": "application/x-msdownload",
            "content_length": 1024,
        },
    )

    assert response.status_code == 422

    get_settings.cache_clear()


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _add_active_user(db_session: Session) -> User:
    user = User(
        email="planner@example.com",
        password_hash=hash_password("strong-password-1"),
        display_name="여행자",
        email_verified_at=kst_now(),
        account_status="active",
        system_role="planner",
        nickname="여행자",
        name="홍길동",
        is_active=True,
        is_admin=False,
        is_privileged=False,
    )
    db_session.add(user)
    db_session.flush()
    return user
