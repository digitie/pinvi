"""Google OAuth 안전 매칭 (G-4) 통합 — login / safe-link / no-link / new (SPRINT-2 DoD).

`resolve_google_login` 의 핵심 분기를 실제 DB 에 대해 검증.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.oauth_identity import OAuthLoginState, UserOAuthIdentity
from app.models.user import User
from app.services.oauth_google import (
    GoogleClaims,
    consume_login_state,
    issue_login_state,
    resolve_google_login,
)

pytestmark = pytest.mark.asyncio


def _claims(*, sub: str, email: str | None, verified: bool) -> GoogleClaims:
    return GoogleClaims(
        provider_user_id=sub,
        email=email,
        email_verified=verified,
        display_name="구글 사용자",
    )


async def test_new_user_created(session_factory) -> None:
    async with session_factory() as db:
        result = await resolve_google_login(
            db, claims=_claims(sub="g-1", email="new@gmail.com", verified=True)
        )
        assert result.created_user is True
        assert result.linked_existing is False
        assert result.user.email == "new@gmail.com"
        assert result.user.email_verified_at is not None
        assert result.user.status == "active"


async def test_existing_identity_logs_in(session_factory) -> None:
    # 1차 로그인 → identity 생성
    async with session_factory() as db:
        first = await resolve_google_login(
            db, claims=_claims(sub="g-2", email="repeat@gmail.com", verified=True)
        )
        first_user_id = first.user.user_id

    # 2차 로그인 → 같은 사용자, 신규 생성 X
    async with session_factory() as db:
        second = await resolve_google_login(
            db, claims=_claims(sub="g-2", email="repeat@gmail.com", verified=True)
        )
        assert second.created_user is False
        assert second.linked_existing is False
        assert second.user.user_id == first_user_id

    async with session_factory() as db:
        identities = list(
            (
                await db.execute(
                    select(UserOAuthIdentity).where(UserOAuthIdentity.provider_user_id == "g-2")
                )
            ).scalars()
        )
        assert len(identities) == 1


async def test_safe_link_when_email_verified(session_factory) -> None:
    """Google email_verified=true + 같은 이메일 로컬 계정 → 안전 연결."""
    async with session_factory() as db:
        local = User(
            email="local@gmail.com",
            password_hash="x",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(local)
        await db.commit()
        await db.refresh(local)
        local_id = local.user_id

    async with session_factory() as db:
        result = await resolve_google_login(
            db, claims=_claims(sub="g-3", email="local@gmail.com", verified=True)
        )
        assert result.linked_existing is True
        assert result.created_user is False
        assert result.user.user_id == local_id


async def test_no_link_when_email_unverified(session_factory) -> None:
    """Google email_verified=false → 자동 연결 금지 (계정 탈취 방지) → 신규 생성."""
    async with session_factory() as db:
        local = User(
            email="victim@gmail.com",
            password_hash="x",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(local)
        await db.commit()
        await db.refresh(local)
        local_id = local.user_id

    async with session_factory() as db:
        result = await resolve_google_login(
            db, claims=_claims(sub="g-4", email="victim@gmail.com", verified=False)
        )
        # 기존 계정에 연결되지 않아야 한다
        assert result.linked_existing is False
        assert result.user.user_id != local_id

    # victim 계정에는 google identity 가 붙지 않았어야 한다
    async with session_factory() as db:
        linked = await db.scalar(
            select(UserOAuthIdentity).where(UserOAuthIdentity.user_id == local_id)
        )
        assert linked is None


async def test_providers_endpoint_exposes_google_only_for_now(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "tripmate_google_oauth_client_id", "google-client")
    monkeypatch.setattr(settings, "tripmate_naver_oauth_client_id", "naver-client")
    monkeypatch.setattr(settings, "tripmate_kakao_oauth_rest_api_key", "kakao-client")

    resp = await client.get("/auth/oauth/providers")

    assert resp.status_code == 200
    providers = resp.json()["data"]["providers"]
    assert providers == [{"provider": "google", "enabled": True}]


async def test_me_returns_linked_oauth_identities(
    client,
    session_factory,
    verified_user,
    auth_cookies,
) -> None:
    user_id, email = verified_user
    linked_at = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            UserOAuthIdentity(
                user_id=uuid.UUID(user_id),
                provider="google",
                provider_user_id="me-linked-google",
                provider_email=email,
                provider_email_verified=True,
                display_name_snapshot="Google User",
                linked_at=linked_at,
                last_login_at=linked_at,
            )
        )
        await db.commit()

    resp = await client.get("/auth/me", cookies=auth_cookies(user_id))

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["email"] == email
    assert data["has_password"] is False
    assert data["oauth_identities"] == [
        {
            "provider": "google",
            "provider_email": email,
            "provider_email_verified": True,
            "display_name": "Google User",
            "linked_at": linked_at.isoformat().replace("+00:00", "Z"),
            "last_login_at": linked_at.isoformat().replace("+00:00", "Z"),
        }
    ]


async def test_google_start_returns_enveloped_authorize_url(client, monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "tripmate_google_oauth_client_id",
        "test-client.apps.googleusercontent.com",
    )

    resp = await client.post(
        "/auth/oauth/google/start",
        json={"return_to": "/trips", "mode": "login"},
    )

    assert resp.status_code == 200
    authorize_url = resp.json()["data"]["authorize_url"]
    parsed = urlparse(authorize_url)
    params = parse_qs(parsed.query)
    assert parsed.netloc == "accounts.google.com"
    assert params["client_id"] == ["test-client.apps.googleusercontent.com"]
    assert params["redirect_uri"] == ["http://localhost:9021/auth/oauth/google/callback"]
    assert params["response_type"] == ["code"]
    assert params["state"][0]
    assert params["code_challenge"][0]
    assert params["code_challenge_method"] == ["S256"]


async def test_google_start_rejects_link_mode_without_authenticated_link_endpoint(client) -> None:
    resp = await client.post(
        "/auth/oauth/google/start",
        json={"return_to": "/profile", "mode": "link"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OAUTH_LINK_REQUIRES_AUTH"


async def test_google_link_stores_user_bound_link_state(
    client,
    session_factory,
    verified_user,
    auth_cookies,
    monkeypatch,
) -> None:
    user_id, _email = verified_user
    monkeypatch.setattr(
        settings,
        "tripmate_google_oauth_client_id",
        "test-client.apps.googleusercontent.com",
    )

    resp = await client.post(
        "/auth/oauth/google/link",
        json={"return_to": "/profile"},
        cookies=auth_cookies(user_id),
    )

    assert resp.status_code == 200
    authorize_url = resp.json()["data"]["authorize_url"]
    state = parse_qs(urlparse(authorize_url).query)["state"][0]
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()

    async with session_factory() as db:
        row = await db.scalar(
            select(OAuthLoginState).where(OAuthLoginState.state_hash == state_hash)
        )
        assert row is not None
        assert row.mode == "link"
        assert row.return_to_path == "/profile"
        assert row.user_id == uuid.UUID(user_id)


async def test_login_state_replays_pkce_code_verifier(session_factory) -> None:
    async with session_factory() as db:
        state, _nonce, code_verifier = await issue_login_state(
            db,
            mode="login",
            return_to="/trips",
        )
        consumed = await consume_login_state(db, state=state)

    assert consumed.code_verifier == code_verifier
    assert consumed.mode == "login"
    assert consumed.return_to_path == "/trips"


async def test_unlink_google_requires_password(
    client,
    session_factory,
    verified_user,
    auth_cookies,
) -> None:
    user_id, email = verified_user
    async with session_factory() as db:
        db.add(
            UserOAuthIdentity(
                user_id=uuid.UUID(user_id),
                provider="google",
                provider_user_id="unlink-blocked-google",
                provider_email=email,
                provider_email_verified=True,
                display_name_snapshot="Google User",
                linked_at=datetime.now(UTC),
                last_login_at=datetime.now(UTC),
            )
        )
        await db.commit()

    resp = await client.delete("/auth/oauth/google", cookies=auth_cookies(user_id))

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "OAUTH_UNLINK_PASSWORD_REQUIRED"
    async with session_factory() as db:
        identity = await db.scalar(
            select(UserOAuthIdentity).where(
                UserOAuthIdentity.provider_user_id == "unlink-blocked-google"
            )
        )
        assert identity is not None


async def test_unlink_google_deletes_identity_when_password_exists(
    client,
    session_factory,
    auth_cookies,
) -> None:
    user = User(
        email="unlink-google@example.com",
        password_hash="hash",
        nickname="unlink",
        status="active",
        email_verified_at=datetime.now(UTC),
    )
    async with session_factory() as db:
        db.add(user)
        await db.flush()
        db.add(
            UserOAuthIdentity(
                user_id=user.user_id,
                provider="google",
                provider_user_id="unlink-ok-google",
                provider_email=user.email,
                provider_email_verified=True,
                display_name_snapshot="Google User",
                linked_at=datetime.now(UTC),
                last_login_at=datetime.now(UTC),
            )
        )
        await db.commit()
        user_id = str(user.user_id)

    resp = await client.delete("/auth/oauth/google", cookies=auth_cookies(user_id))

    assert resp.status_code == 204
    async with session_factory() as db:
        identity = await db.scalar(
            select(UserOAuthIdentity).where(
                UserOAuthIdentity.provider_user_id == "unlink-ok-google"
            )
        )
        assert identity is None


async def test_callback_invalid_state_redirects_to_login(client) -> None:
    resp = await client.get(
        "/auth/oauth/google/callback?code=test-code&state=invalid-state",
        follow_redirects=False,
    )

    assert resp.status_code == 303
    location = resp.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "http://localhost:9022/login"
    assert params["error"] == ["OAUTH_STATE_INVALID"]


async def test_callback_provider_denied_redirects_to_login(client) -> None:
    resp = await client.get(
        "/auth/oauth/google/callback?error=access_denied&error_description=cancelled",
        follow_redirects=False,
    )

    assert resp.status_code == 303
    location = resp.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "http://localhost:9022/login"
    assert params["error"] == ["OAUTH_PROVIDER_DENIED"]
