"""Google OAuth 안전 매칭 (G-4) 통합 — login / safe-link / no-link / new (SPRINT-2 DoD).

`resolve_google_login` 의 핵심 분기를 실제 DB 에 대해 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.oauth_identity import UserOAuthIdentity
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


async def test_providers_endpoint(client) -> None:
    resp = await client.get("/auth/oauth/providers")
    assert resp.status_code == 200
    providers = {p["provider"] for p in resp.json()["data"]["providers"]}
    assert providers == {"google", "naver", "kakao"}


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
