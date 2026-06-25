"""미인증 로그인 시 재인증 메일 재발송 + `/auth/verify-email/resend` 흐름."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.email_queue import EmailQueue
from app.models.user import User
from app.models.user_email_verification import UserEmailVerification

pytestmark = pytest.mark.asyncio

_PASSWORD = "verify-secret-pw-12345"


async def _seed_unverified_user(
    session_factory,  # type: ignore[no-untyped-def]
    *,
    signup_token_age: timedelta | None = None,
) -> tuple[uuid.UUID, str]:
    """미인증(pending_verification) 사용자를 생성. signup_token_age를 주면 그 시점의 signup 토큰을 함께 둔다."""
    user_id = uuid.uuid4()
    email = f"reverify_{uuid.uuid4().hex[:8]}@example.com"
    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=email,
                password_hash=hash_password(_PASSWORD),
                nickname="reverify-user",
                status="pending_verification",
                email_verified_at=None,
            )
        )
        await db.flush()
        if signup_token_age is not None:
            created = datetime.now(UTC) - signup_token_age
            db.add(
                UserEmailVerification(
                    user_id=user_id,
                    token_hash=uuid.uuid4().hex,
                    purpose="signup",
                    expires_at=created + timedelta(hours=24),
                    created_at=created,
                )
            )
        await db.commit()
    return user_id, email


async def _verify_email_rows(session_factory, user_id: uuid.UUID) -> list[EmailQueue]:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        return list(
            (
                await db.scalars(
                    select(EmailQueue).where(
                        EmailQueue.user_id == user_id,
                        EmailQueue.template == "verify_email",
                    )
                )
            ).all()
        )


async def test_login_unverified_resends_verification_email(client, session_factory) -> None:
    user_id, email = await _seed_unverified_user(session_factory)

    resp = await client.post("/auth/login", json={"email": email, "password": _PASSWORD})

    assert resp.status_code == 401, resp.text
    error = resp.json()["error"]
    assert error["code"] == "EMAIL_NOT_VERIFIED"
    assert "verification_email_dispatched" in error["details"]

    rows = await _verify_email_rows(session_factory, user_id)
    assert len(rows) == 1
    assert "verify_url" in rows[0].payload

    async with session_factory() as db:
        token = await db.scalar(
            select(UserEmailVerification).where(
                UserEmailVerification.user_id == user_id,
                UserEmailVerification.purpose == "signup",
                UserEmailVerification.used_at.is_(None),
            )
        )
        assert token is not None


async def test_login_unverified_respects_cooldown(client, session_factory) -> None:
    # 방금 발급된 signup 토큰이 있으면 cooldown(기본 60s)에 걸려 재발송하지 않는다.
    user_id, email = await _seed_unverified_user(
        session_factory, signup_token_age=timedelta(seconds=1)
    )

    resp = await client.post("/auth/login", json={"email": email, "password": _PASSWORD})

    assert resp.status_code == 401, resp.text
    assert resp.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

    rows = await _verify_email_rows(session_factory, user_id)
    assert rows == []


async def test_login_wrong_password_does_not_resend(client, session_factory) -> None:
    # 비밀번호가 틀리면 미인증 분기에 도달하지 않으므로 재발송도 없다(소유 미증명).
    user_id, email = await _seed_unverified_user(session_factory)

    resp = await client.post("/auth/login", json={"email": email, "password": "wrong-password-xx"})

    assert resp.status_code == 401, resp.text
    assert resp.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
    assert await _verify_email_rows(session_factory, user_id) == []


async def test_resend_endpoint_dispatches_and_invalidates_old_token(
    client, session_factory
) -> None:
    user_id, email = await _seed_unverified_user(
        session_factory, signup_token_age=timedelta(minutes=10)
    )

    resp = await client.post("/auth/verify-email/resend", json={"email": email})

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"accepted": True}

    rows = await _verify_email_rows(session_factory, user_id)
    assert len(rows) == 1

    async with session_factory() as db:
        tokens = (
            await db.scalars(
                select(UserEmailVerification).where(
                    UserEmailVerification.user_id == user_id,
                    UserEmailVerification.purpose == "signup",
                )
            )
        ).all()
        # 옛 토큰은 used 처리되고, 새 unused 토큰 1개만 살아있다.
        assert sum(t.used_at is None for t in tokens) == 1


async def test_resend_endpoint_is_enumeration_safe(client, session_factory) -> None:
    resp = await client.post("/auth/verify-email/resend", json={"email": "missing@example.com"})

    assert resp.status_code == 200
    assert resp.json()["data"] == {"accepted": True}

    async with session_factory() as db:
        assert await db.scalar(select(EmailQueue)) is None


async def test_resend_endpoint_noop_for_verified_user(client, session_factory) -> None:
    user_id = uuid.uuid4()
    email = f"verified_{uuid.uuid4().hex[:8]}@example.com"
    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=email,
                password_hash=hash_password(_PASSWORD),
                nickname="verified-user",
                status="active",
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.commit()

    resp = await client.post("/auth/verify-email/resend", json={"email": email})

    assert resp.status_code == 200
    assert resp.json()["data"] == {"accepted": True}
    assert await _verify_email_rows(session_factory, user_id) == []
