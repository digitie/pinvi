"""비밀번호 재설정 API + email_queue 흐름."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models.email_queue import EmailQueue
from app.models.session import UserSession
from app.models.user import User
from app.models.user_email_verification import UserEmailVerification

pytestmark = pytest.mark.asyncio


async def _seed_password_user(session_factory) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    user_id = uuid.uuid4()
    email = f"reset_{uuid.uuid4().hex[:8]}@example.com"
    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=email,
                password_hash=hash_password("old-secret-pw-12345"),
                nickname="reset-user",
                status="active",
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.flush()
        db.add(
            UserSession(
                user_id=user_id,
                session_token_hash=uuid.uuid4().hex,
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        await db.commit()
    return str(user_id), email


async def test_password_reset_request_is_enumeration_safe(client, session_factory) -> None:
    resp = await client.post(
        "/auth/password/reset-request",
        json={"email": "missing@example.com"},
    )

    assert resp.status_code == 200
    assert resp.json()["data"] == {"accepted": True}

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue))
        assert row is None


async def test_password_reset_updates_password_and_revokes_sessions(
    client,
    session_factory,
) -> None:
    user_id, email = await _seed_password_user(session_factory)

    request_resp = await client.post("/auth/password/reset-request", json={"email": email})

    assert request_resp.status_code == 200
    assert request_resp.json()["data"] == {"accepted": True}

    async with session_factory() as db:
        queue_row = await db.scalar(
            select(EmailQueue).where(
                EmailQueue.user_id == uuid.UUID(user_id),
                EmailQueue.template == "reset_password",
            )
        )
        assert queue_row is not None
        token = parse_qs(urlparse(str(queue_row.payload["reset_url"])).query)["token"][0]

    reset_resp = await client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": "new-secret-pw-67890"},
    )

    assert reset_resp.status_code == 200
    assert reset_resp.json()["data"]["email"] == email
    assert "tripmate_access=" in reset_resp.headers["set-cookie"]

    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.user_id == uuid.UUID(user_id)))
        assert user is not None
        assert user.password_hash is not None
        assert verify_password("new-secret-pw-67890", user.password_hash)

        session = await db.scalar(select(UserSession).where(UserSession.user_id == user.user_id))
        assert session is not None
        assert session.revoked_at is not None

        verification = await db.scalar(
            select(UserEmailVerification).where(
                UserEmailVerification.user_id == user.user_id,
                UserEmailVerification.purpose == "password_reset",
            )
        )
        assert verification is not None
        assert verification.used_at is not None


async def test_password_reset_rejects_invalid_token(client) -> None:
    resp = await client.post(
        "/auth/password/reset",
        json={"token": "x" * 43, "new_password": "new-secret-pw-67890"},
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
