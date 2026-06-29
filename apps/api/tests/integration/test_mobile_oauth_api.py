"""모바일 Google OAuth — 딥링크 1회용 code 발급(callback) + 토큰 교환(exchange).

웹 callback과 같은 state/PKCE/안전 매칭을 쓰되, `return_to`가 앱 딥링크면 쿠키 대신
`pinvi://oauth?code=`로 리다이렉트하고 앱이 그 code를 토큰과 교환한다.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User
from app.services.oauth_google import (
    GoogleClaims,
    OAuthStateInvalidError,
    consume_mobile_exchange,
    issue_login_state,
    mint_mobile_exchange,
)

pytestmark = pytest.mark.asyncio


def _claims(*, sub: str, email: str, verified: bool = True) -> GoogleClaims:
    return GoogleClaims(
        provider_user_id=sub, email=email, email_verified=verified, display_name="구글 사용자"
    )


async def _seed_user(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    user = User(
        email=f"oauth_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("pw-123456789"),
        nickname="모바일",
        status="active",
        email_verified_at=datetime.now(UTC),
    )
    async with session_factory() as db:
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def test_mobile_callback_redirects_to_app_deeplink_with_code(
    client, session_factory, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        state, _nonce, _verifier = await issue_login_state(
            db, mode="login", return_to=settings.pinvi_mobile_oauth_redirect
        )
        await db.commit()

    async def fake_exchange(**_kwargs) -> GoogleClaims:  # type: ignore[no-untyped-def]
        return _claims(sub="mob-google-1", email="mob-new@gmail.com")

    monkeypatch.setattr("app.api.v1.oauth.exchange_code_for_claims", fake_exchange)

    resp = await client.get(
        f"/auth/oauth/google/callback?code=test-code&state={state}", follow_redirects=False
    )
    assert resp.status_code == 303
    parsed = urlparse(resp.headers["location"])
    assert parsed.scheme == "pinvi"
    code = parse_qs(parsed.query).get("code")
    assert code and code[0]
    # 모바일 흐름은 쿠키를 세팅하지 않는다(토큰은 exchange 시점 발급).
    assert resp.cookies.get("pinvi_access") is None

    # 발급된 code로 토큰 교환이 동작한다.
    exchanged = await client.post("/mobile/auth/oauth/exchange", json={"code": code[0]})
    assert exchanged.status_code == 200, exchanged.text
    data = exchanged.json()["data"]
    assert data["user"]["email"] == "mob-new@gmail.com"
    assert data["access_token"] and data["refresh_token"]


async def test_mobile_exchange_returns_tokens_and_bearer_works(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    user_id = await _seed_user(session_factory)
    async with session_factory() as db:
        code = await mint_mobile_exchange(db, user_id=user_id)

    resp = await client.post("/mobile/auth/oauth/exchange", json={"code": code})
    assert resp.status_code == 200, resp.text
    access = resp.json()["data"]["access_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200, me.text
    assert me.json()["data"]["user_id"] == str(user_id)


async def test_mobile_exchange_rejects_invalid_code(client) -> None:  # type: ignore[no-untyped-def]
    resp = await client.post("/mobile/auth/oauth/exchange", json={"code": "not-a-real-code"})
    assert resp.status_code == 401


async def test_mobile_exchange_rejects_reused_code(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    user_id = await _seed_user(session_factory)
    async with session_factory() as db:
        code = await mint_mobile_exchange(db, user_id=user_id)

    first = await client.post("/mobile/auth/oauth/exchange", json={"code": code})
    assert first.status_code == 200, first.text
    second = await client.post("/mobile/auth/oauth/exchange", json={"code": code})
    assert second.status_code == 401


async def test_mobile_callback_error_redirects_to_app_deeplink(
    client, session_factory, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    # 같은 이메일의 기존 로컬 계정 → resolve가 OAUTH_ACCOUNT_LINK_REQUIRED.
    async with session_factory() as db:
        db.add(
            User(
                email="mob-existing@example.com",
                password_hash=hash_password("pw-123456789"),
                nickname="기존",
                status="active",
                email_verified_at=datetime.now(UTC),
            )
        )
        state, _nonce, _verifier = await issue_login_state(
            db, mode="login", return_to=settings.pinvi_mobile_oauth_redirect
        )
        await db.commit()

    async def fake_exchange(**_kwargs) -> GoogleClaims:  # type: ignore[no-untyped-def]
        return _claims(sub="mob-google-2", email="mob-existing@example.com")

    monkeypatch.setattr("app.api.v1.oauth.exchange_code_for_claims", fake_exchange)

    resp = await client.get(
        f"/auth/oauth/google/callback?code=test-code&state={state}", follow_redirects=False
    )
    assert resp.status_code == 303
    parsed = urlparse(resp.headers["location"])
    assert parsed.scheme == "pinvi"
    assert parse_qs(parsed.query).get("error") == ["OAUTH_ACCOUNT_LINK_REQUIRED"]


async def test_mobile_oauth_start_returns_authorize_url(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        settings, "pinvi_google_oauth_client_id", "test-client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "pinvi_google_oauth_client_secret", "test-secret")
    resp = await client.post("/mobile/auth/oauth/google/start")
    assert resp.status_code == 200, resp.text
    url = resp.json()["data"]["authorize_url"]
    params = parse_qs(urlparse(url).query)
    assert params["client_id"] == ["test-client.apps.googleusercontent.com"]
    assert params["redirect_uri"] == ["http://localhost:12801/auth/oauth/google/callback"]


async def test_mobile_oauth_start_503_when_unconfigured(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_google_oauth_client_id", "")
    monkeypatch.setattr(settings, "pinvi_google_oauth_client_secret", "test-secret")
    resp = await client.post("/mobile/auth/oauth/google/start")
    assert resp.status_code == 503


async def test_mobile_callback_provider_error_redirects_to_app_deeplink(
    client, session_factory
) -> None:  # type: ignore[no-untyped-def]
    # provider가 error를 실어 보낸 모바일 흐름 → 앱 딥링크로 라우팅(웹 /login 아님).
    async with session_factory() as db:
        state, _nonce, _verifier = await issue_login_state(
            db, mode="login", return_to=settings.pinvi_mobile_oauth_redirect
        )
        await db.commit()

    resp = await client.get(
        f"/auth/oauth/google/callback?error=access_denied&error_description=denied&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    parsed = urlparse(resp.headers["location"])
    assert parsed.scheme == "pinvi"
    assert parse_qs(parsed.query).get("error") == ["OAUTH_PROVIDER_DENIED"]


async def test_web_callback_provider_error_redirects_to_login(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    # 웹 흐름(non-mobile return_to) → 웹 /login 으로 라우팅(딥링크 아님).
    async with session_factory() as db:
        state, _nonce, _verifier = await issue_login_state(db, mode="login", return_to="/")
        await db.commit()

    resp = await client.get(
        f"/auth/oauth/google/callback?error=access_denied&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert urlparse(location).scheme != "pinvi"
    assert location.startswith(settings.pinvi_web_base_url)
    assert "error=OAUTH_PROVIDER_DENIED" in location


async def test_mobile_exchange_rejects_expired_code(client, session_factory, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # 음수 TTL로 발급 → 만료된 code → exchange 401.
    user_id = await _seed_user(session_factory)
    monkeypatch.setattr(settings, "pinvi_mobile_oauth_exchange_ttl_seconds", -10)
    async with session_factory() as db:
        code = await mint_mobile_exchange(db, user_id=user_id)

    resp = await client.post("/mobile/auth/oauth/exchange", json={"code": code})
    assert resp.status_code == 401


async def test_mobile_exchange_concurrent_only_one_wins(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    # 같은 code를 동시에 두 번 소비 → 정확히 하나만 성공(1회용 원자성).
    user_id = await _seed_user(session_factory)
    async with session_factory() as db:
        code = await mint_mobile_exchange(db, user_id=user_id)

    async def _consume(factory, code):  # type: ignore[no-untyped-def]
        async with factory() as db:
            return await consume_mobile_exchange(db, code=code)

    results = await asyncio.gather(
        _consume(session_factory, code),
        _consume(session_factory, code),
        return_exceptions=True,
    )
    successes = [r for r in results if isinstance(r, uuid.UUID)]
    failures = [r for r in results if isinstance(r, OAuthStateInvalidError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert successes[0] == user_id
