"""모바일 /mobile/auth/* — access/refresh 토큰 본문 발급 + Bearer 동작 + refresh 회전/logout 폐기."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.core.security import hash_password
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _seed_user(session_factory) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    email = f"mob_{uuid.uuid4().hex[:8]}@pinvi.test"
    password = "mobile-pw-12345"
    async with session_factory() as db:
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                nickname="모바일",
                status="active",
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.commit()
    return email, password


async def test_mobile_login_returns_tokens_and_bearer_works(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    email, password = await _seed_user(session_factory)

    resp = await client.post("/mobile/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["user"]["email"] == email
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["expires_at"]
    # 모바일 로그인은 cookie를 세팅하지 않는다(본문 토큰만).
    assert resp.cookies.get("pinvi_access") is None

    # 발급된 access_token이 Bearer로 동작한다(인증 dep 확장).
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200, me.text
    assert me.json()["data"]["email"] == email


async def test_mobile_login_bad_credentials(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    email, _ = await _seed_user(session_factory)
    resp = await client.post(
        "/mobile/auth/login", json={"email": email, "password": "wrong-password-xyz"}
    )
    assert resp.status_code == 401


async def test_mobile_refresh_rotates_and_invalidates_old(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    email, password = await _seed_user(session_factory)
    login = await client.post("/mobile/auth/login", json={"email": email, "password": password})
    old_refresh = login.json()["data"]["refresh_token"]

    rotated = await client.post("/mobile/auth/refresh", json={"refresh_token": old_refresh})
    assert rotated.status_code == 200, rotated.text
    new_refresh = rotated.json()["data"]["refresh_token"]
    assert new_refresh != old_refresh

    # 회전된 옛 refresh token은 더 이상 유효하지 않다.
    again = await client.post("/mobile/auth/refresh", json={"refresh_token": old_refresh})
    assert again.status_code == 401


async def test_mobile_logout_revokes_refresh(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    email, password = await _seed_user(session_factory)
    login = await client.post("/mobile/auth/login", json={"email": email, "password": password})
    refresh = login.json()["data"]["refresh_token"]

    out = await client.post("/mobile/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 204

    after = await client.post("/mobile/auth/refresh", json={"refresh_token": refresh})
    assert after.status_code == 401
