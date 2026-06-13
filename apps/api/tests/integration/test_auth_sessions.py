"""Auth refresh session persistence + rotation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.session import UserSession
from app.models.user import User
from app.services.auth_session import (
    RefreshTokenExpiredError,
    RefreshTokenInvalidError,
    hash_session_token,
    refresh_user_session,
)

pytestmark = pytest.mark.asyncio


async def _seed_active_user(session_factory) -> tuple[str, str, str]:
    email = f"session_{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pw-12345"
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash=hash_password(password),
            nickname="session-user",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.user_id), email, password


async def test_login_persists_refresh_session_hash(client, session_factory) -> None:
    user_id, email, password = await _seed_active_user(session_factory)

    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"user-agent": "pinvi-test-agent"},
    )

    assert resp.status_code == 200
    refresh_token = resp.cookies.get("pinvi_refresh")
    assert refresh_token is not None
    async with session_factory() as db:
        session = await db.scalar(
            select(UserSession).where(UserSession.user_id == uuid.UUID(user_id))
        )
        assert session is not None
        assert session.session_token_hash == hash_session_token(refresh_token)
        assert session.session_token_hash != refresh_token
        assert session.revoked_at is None
        assert session.user_agent == "pinvi-test-agent"


async def test_refresh_rotates_refresh_session(client, session_factory) -> None:
    user_id, email, password = await _seed_active_user(session_factory)
    login_resp = await client.post("/auth/login", json={"email": email, "password": password})
    old_refresh = login_resp.cookies["pinvi_refresh"]
    client.cookies.clear()

    refresh_resp = await client.post("/auth/refresh", cookies={"pinvi_refresh": old_refresh})

    assert refresh_resp.status_code == 200
    new_refresh = refresh_resp.cookies.get("pinvi_refresh")
    assert new_refresh is not None
    assert new_refresh != old_refresh
    assert refresh_resp.json()["data"]["email"] == email

    async with session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(UserSession)
                    .where(UserSession.user_id == uuid.UUID(user_id))
                    .order_by(UserSession.created_at.asc())
                )
            ).scalars()
        )
        assert len(rows) == 2
        assert rows[0].session_token_hash == hash_session_token(old_refresh)
        assert rows[0].revoked_at is not None
        assert rows[1].session_token_hash == hash_session_token(new_refresh)
        assert rows[1].revoked_at is None

    client.cookies.clear()
    replay_resp = await client.post("/auth/refresh", cookies={"pinvi_refresh": old_refresh})
    assert replay_resp.status_code == 401
    assert replay_resp.json()["error"]["code"] == "TOKEN_EXPIRED"


async def test_refresh_rotation_is_single_use_under_race(client, session_factory) -> None:
    user_id, email, password = await _seed_active_user(session_factory)
    login_resp = await client.post("/auth/login", json={"email": email, "password": password})
    old_refresh = login_resp.cookies["pinvi_refresh"]
    client.cookies.clear()

    async def rotate_once() -> str:
        async with session_factory() as db:
            try:
                refreshed = await refresh_user_session(db, refresh_token=old_refresh)
            except (RefreshTokenExpiredError, RefreshTokenInvalidError) as exc:
                return exc.code
            return refreshed.issue.refresh_token

    results = await asyncio.gather(rotate_once(), rotate_once())

    successes = [result for result in results if result not in {"TOKEN_EXPIRED", "TOKEN_INVALID"}]
    failures = [result for result in results if result in {"TOKEN_EXPIRED", "TOKEN_INVALID"}]
    assert len(successes) == 1
    assert len(failures) == 1
    assert successes[0] != old_refresh

    async with session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(UserSession)
                    .where(UserSession.user_id == uuid.UUID(user_id))
                    .order_by(UserSession.created_at.asc())
                )
            ).scalars()
        )
        assert len(rows) == 2
        assert sum(row.revoked_at is None for row in rows) == 1
        assert rows[0].session_token_hash == hash_session_token(old_refresh)
        assert rows[0].revoked_at is not None


async def test_refresh_rejects_expired_session_and_revokes_it(client, session_factory) -> None:
    user_id, _email, _password = await _seed_active_user(session_factory)
    expired_refresh = "expired-refresh-token"
    async with session_factory() as db:
        db.add(
            UserSession(
                user_id=uuid.UUID(user_id),
                session_token_hash=hash_session_token(expired_refresh),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await db.commit()

    resp = await client.post("/auth/refresh", cookies={"pinvi_refresh": expired_refresh})

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TOKEN_EXPIRED"
    async with session_factory() as db:
        session = await db.scalar(
            select(UserSession).where(
                UserSession.session_token_hash == hash_session_token(expired_refresh)
            )
        )
        assert session is not None
        assert session.revoked_at is not None


async def test_logout_revokes_refresh_session_and_clears_cookies(client, session_factory) -> None:
    user_id, email, password = await _seed_active_user(session_factory)
    login_resp = await client.post("/auth/login", json={"email": email, "password": password})
    refresh_token = login_resp.cookies["pinvi_refresh"]
    client.cookies.clear()

    resp = await client.post("/auth/logout", cookies={"pinvi_refresh": refresh_token})

    assert resp.status_code == 204
    set_cookie_headers = resp.headers.get_list("set-cookie")
    assert any("pinvi_access=" in header and "Max-Age=0" in header for header in set_cookie_headers)
    assert any(
        "pinvi_refresh=" in header and "Max-Age=0" in header for header in set_cookie_headers
    )

    async with session_factory() as db:
        session = await db.scalar(
            select(UserSession).where(UserSession.user_id == uuid.UUID(user_id))
        )
        assert session is not None
        assert session.revoked_at is not None
