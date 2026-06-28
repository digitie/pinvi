"""Admin rate-limit / abuse surface (T-282)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.middleware.rate_limit import rate_limit_bucket_hash, rate_limit_identity_key
from app.models.audit import AdminAuditLog
from app.models.rate_limit import RateLimitBucket, RateLimitOverride
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    email: str,
    roles: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash="x",
            status="active",
            roles=roles or ["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _seed_bucket(
    session_factory: Any,
    *,
    limit_name: str,
    raw_key: str,
    count: int,
) -> str:
    now = datetime.now(UTC)
    bucket_hash = rate_limit_bucket_hash(limit_name, raw_key)
    async with session_factory() as db:
        db.add(
            RateLimitBucket(
                bucket_hash=bucket_hash,
                window_start=now.replace(second=0, microsecond=0),
                limit_name=limit_name,
                count=count,
                expires_at=now + timedelta(minutes=2),
                updated_at=now,
            )
        )
        await db.commit()
    return bucket_hash


async def test_admin_abuse_summary_lists_buckets_and_suspicious_activity(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.settings.pinvi_rate_limit_backend", "postgres")
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    bucket_hash = await _seed_bucket(
        session_factory,
        limit_name="auth_low",
        raw_key=rate_limit_identity_key(
            "ip_email",
            ip="127.0.0.1",
            email="blocked@example.com",
        ),
        count=9,
    )

    resp = await client.get("/admin/abuse", cookies=auth_cookies(str(admin_id)))

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["backend"]["effective_backend"] == "postgres"
    assert data["backend"]["store_status"] == "ok"
    assert data["backend"]["fail_closed"] is True
    assert data["rate_limited_bucket_count"] >= 1
    assert any(item["bucket_hash_prefix"] == bucket_hash[:16] for item in data["buckets"])
    assert any(item["signal"] == "auth_low_repeated_attempt" for item in data["suspicious"])


async def test_admin_creates_and_rolls_back_rate_limit_override_with_audit(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    request_id = uuid.uuid4()

    create = await client.post(
        "/admin/abuse/overrides",
        json={
            "limit_name": "auth_low",
            "identity_kind": "ip_email",
            "ip": "127.0.0.1",
            "email": "blocked@example.com",
            "action": "blocked",
            "ttl_minutes": 30,
            "access_reason": "login abuse burst",
        },
        headers={"X-Request-Id": str(request_id)},
        cookies=auth_cookies(str(admin_id)),
    )

    assert create.status_code == 201, create.text
    created = create.json()["data"]
    assert created["identity_label"].startswith("ip_email_hash:")
    assert "blocked@example.com" not in create.text
    assert created["status"] == "blocked"

    rollback = await client.post(
        f"/admin/abuse/overrides/{created['override_id']}/rollback",
        json={"access_reason": "false positive", "rollback_reason": "support confirmed"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["data"]["status"] == "revoked"
    async with session_factory() as db:
        row = await db.get(RateLimitOverride, uuid.UUID(created["override_id"]))
        audits = list(
            (await db.scalars(select(AdminAuditLog.action).order_by(AdminAuditLog.log_id))).all()
        )
    assert row is not None
    assert row.revoked_at is not None
    assert row.revoked_reason == "support confirmed"
    assert audits == ["rate_limit_override.create", "rate_limit_override.rollback"]


async def test_block_override_is_enforced_by_rate_limit_middleware(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.settings.pinvi_rate_limit_backend", "postgres")
    monkeypatch.setattr("app.core.config.settings.pinvi_rate_limit_auth_per_minute", 100)
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    create = await client.post(
        "/admin/abuse/overrides",
        json={
            "limit_name": "auth_low",
            "identity_kind": "ip_email",
            "ip": "127.0.0.1",
            "email": "blocked@example.com",
            "action": "blocked",
            "ttl_minutes": 30,
            "access_reason": "credential stuffing",
        },
        cookies=auth_cookies(str(admin_id)),
    )
    assert create.status_code == 201, create.text

    blocked = await client.post(
        "/auth/login",
        json={"email": "blocked@example.com", "password": "not-valid"},
    )

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMIT_BLOCKED"
