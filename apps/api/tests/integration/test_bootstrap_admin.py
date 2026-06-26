"""Bootstrap admin 계정 보장 흐름."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.session import UserSession
from app.models.user import User
from app.services.bootstrap_admin import ensure_bootstrap_admin

pytestmark = pytest.mark.asyncio


async def test_bootstrap_admin_skips_without_password(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    monkeypatch.setattr(settings, "pinvi_bootstrap_admin_email", "admin@ad.min")
    monkeypatch.setattr(settings, "pinvi_bootstrap_admin_password", "")

    result = await ensure_bootstrap_admin()

    assert result.action == "skipped"
    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.email == "admin@ad.min"))
        assert user is None


async def test_bootstrap_admin_creates_active_admin(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    monkeypatch.setattr(settings, "pinvi_bootstrap_admin_email", "admin@ad.min")
    monkeypatch.setattr(settings, "pinvi_bootstrap_admin_password", "admin")

    result = await ensure_bootstrap_admin()

    assert result.action == "created"
    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.email == "admin@ad.min"))
        assert user is not None
        assert user.status == "active"
        assert user.email_verified_at is not None
        assert user.is_active is True
        assert {"user", "admin"}.issubset(set(user.roles))
        assert user.password_hash is not None
        assert verify_password("admin", user.password_hash)


async def test_bootstrap_admin_repairs_existing_user_and_revokes_sessions(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    monkeypatch.setattr(settings, "pinvi_bootstrap_admin_email", "admin@ad.min")
    monkeypatch.setattr(settings, "pinvi_bootstrap_admin_password", "admin")
    async with session_factory() as db:
        user = User(
            email="admin@ad.min",
            password_hash=hash_password("old-password"),
            nickname=None,
            status="disabled",
            roles=["user"],
            email_verified_at=None,
            is_active=False,
            deleted_at=datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        session = UserSession(
            user_id=user.user_id,
            session_token_hash="old-session",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db.add(session)
        await db.commit()

    result = await ensure_bootstrap_admin()

    assert result.action == "updated"
    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.email == "admin@ad.min"))
        assert user is not None
        assert user.status == "active"
        assert user.email_verified_at is not None
        assert user.is_active is True
        assert user.deleted_at is None
        assert {"user", "admin"}.issubset(set(user.roles))
        assert user.password_hash is not None
        assert verify_password("admin", user.password_hash)
        session = await db.scalar(
            select(UserSession).where(UserSession.session_token_hash == "old-session")
        )
        assert session is not None
        assert session.revoked_at is not None


async def test_bootstrap_admin_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    monkeypatch.setattr(settings, "pinvi_bootstrap_admin_email", "admin@ad.min")
    monkeypatch.setattr(settings, "pinvi_bootstrap_admin_password", "admin")

    first = await ensure_bootstrap_admin()
    second = await ensure_bootstrap_admin()

    assert first.action == "created"
    assert second.action == "unchanged"
