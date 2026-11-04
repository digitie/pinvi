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


def _freeze_limiter_window(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.middleware.rate_limit as middleware

    fixed = datetime.now(UTC).replace(second=10, microsecond=0)

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return fixed

    monkeypatch.setattr(middleware, "datetime", Clock)


async def _user_override(
    session_factory: Any,
    *,
    admin_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    created_at: datetime | None = None,
) -> RateLimitOverride:
    now = datetime.now(UTC)
    bucket_hash = rate_limit_bucket_hash("authenticated_default", "user:" + str(user_id))
    row = RateLimitOverride(
        limit_name="authenticated_default",
        bucket_hash=bucket_hash,
        identity_kind="user",
        identity_fingerprint=bucket_hash,
        identity_label="fixture-user",
        action=action,
        reason="fixture bounded cap",
        created_by_user_id=admin_id,
        expires_at=now + timedelta(hours=1),
        created_at=created_at or now,
    )
    async with session_factory() as db:
        db.add(row)
        await db.commit()
    return row


@pytest.mark.parametrize("base", [4, 60])
async def test_configured_user_counts_despite_legacy_allowed(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
    base: int,
) -> None:
    from app.core.config import settings

    _freeze_limiter_window(monkeypatch)

    admin_id = await _create_user(
        session_factory, email="cap-admin@example.com", roles=["user", "admin"]
    )
    user_id = await _create_user(session_factory, email="cap-user@example.com")
    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setattr(settings, "pinvi_rate_limit_authenticated_per_minute", base)
    monkeypatch.setitem(
        settings.__dict__, "pinvi_rate_limit_user_limit_overrides", {str(user_id): 4}
    )
    await _user_override(session_factory, admin_id=admin_id, user_id=user_id, action="allowed")
    for _ in range(4):
        assert (await client.get("/auth/me", cookies=auth_cookies(str(user_id)))).status_code == 200
    response = await client.get("/auth/me", cookies=auth_cookies(str(user_id)))
    assert response.status_code == 429
    assert response.json()["error"]["details"]["limit"] == 4
    assert int(response.headers["Retry-After"]) > 0
    summary = await client.get("/admin/abuse", cookies=auth_cookies(str(admin_id)))
    assert summary.status_code == 200
    bucket_hash = rate_limit_bucket_hash("authenticated_default", "user:" + str(user_id))
    row = next(
        r for r in summary.json()["data"]["buckets"] if r["bucket_hash_prefix"] == bucket_hash[:16]
    )
    assert row["limit"] == 4 and row["remaining"] == 0 and row["rate_limited"] is True
    assert row["status"] == "observed"
    assert row["active_override_action"] == "allowed"


@pytest.mark.parametrize("blocked_newer", [False, True])
async def test_configured_user_blocked_wins_both_creation_orders(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
    blocked_newer: bool,
) -> None:
    from app.core.config import settings

    _freeze_limiter_window(monkeypatch)

    admin_id = await _create_user(
        session_factory, email="order-admin@example.com", roles=["user", "admin"]
    )
    user_id = await _create_user(session_factory, email="order-user@example.com")
    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setitem(
        settings.__dict__, "pinvi_rate_limit_user_limit_overrides", {str(user_id): 4}
    )
    now = datetime.now(UTC)
    blocked = await _user_override(
        session_factory,
        admin_id=admin_id,
        user_id=user_id,
        action="blocked",
        created_at=now if blocked_newer else now - timedelta(minutes=1),
    )
    await _user_override(
        session_factory,
        admin_id=admin_id,
        user_id=user_id,
        action="allowed",
        created_at=now - timedelta(minutes=1) if blocked_newer else now,
    )
    response = await client.get("/auth/me", cookies=auth_cookies(str(user_id)))
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_BLOCKED"
    summary = await client.get("/admin/abuse", cookies=auth_cookies(str(admin_id)))
    # Blocked attempts do not need a counter row; seed one to verify admin choice too.
    await _seed_bucket(
        session_factory, limit_name="authenticated_default", raw_key="user:" + str(user_id), count=1
    )
    summary = await client.get("/admin/abuse", cookies=auth_cookies(str(admin_id)))
    assert summary.status_code == 200
    bucket_hash = rate_limit_bucket_hash("authenticated_default", "user:" + str(user_id))
    row = next(
        r for r in summary.json()["data"]["buckets"] if r["bucket_hash_prefix"] == bucket_hash[:16]
    )
    assert row["status"] == "blocked"
    assert row["active_override_id"] == str(blocked.override_id)
    revoked = await client.post(
        f"/admin/abuse/overrides/{blocked.override_id}/rollback",
        json={"access_reason": "fixture resolved", "rollback_reason": "fixture block removed"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert revoked.status_code == 200
    for _ in range(3):
        assert (await client.get("/auth/me", cookies=auth_cookies(str(user_id)))).status_code == 200
    assert (await client.get("/auth/me", cookies=auth_cookies(str(user_id)))).status_code == 429


async def test_admin_counter_summary_uses_configured_cap(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    _freeze_limiter_window(monkeypatch)

    admin_id = await _create_user(
        session_factory, email="summary-cap-admin@example.com", roles=["user", "admin"]
    )
    user_id = await _create_user(session_factory, email="summary-cap-user@example.com")
    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setitem(
        settings.__dict__, "pinvi_rate_limit_user_limit_overrides", {str(user_id): 4}
    )
    bucket_hash = await _seed_bucket(
        session_factory, limit_name="authenticated_default", raw_key="user:" + str(user_id), count=5
    )
    summary = await client.get("/admin/abuse", cookies=auth_cookies(str(admin_id)))
    assert summary.status_code == 200
    data = summary.json()["data"]
    assert data["rate_limited_bucket_count"] >= 1
    row = next(r for r in data["buckets"] if r["bucket_hash_prefix"] == bucket_hash[:16])
    assert row["limit"] == 4 and row["rate_limited"] is True


async def test_unconfigured_user_keeps_legacy_allowed_semantics(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    _freeze_limiter_window(monkeypatch)

    admin_id = await _create_user(
        session_factory, email="old-admin@example.com", roles=["user", "admin"]
    )
    user_id = await _create_user(session_factory, email="old-user@example.com")
    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setattr(settings, "pinvi_rate_limit_authenticated_per_minute", 1)
    monkeypatch.setitem(settings.__dict__, "pinvi_rate_limit_user_limit_overrides", {})
    await _user_override(
        session_factory,
        admin_id=admin_id,
        user_id=user_id,
        action="blocked",
        created_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    await _user_override(session_factory, admin_id=admin_id, user_id=user_id, action="allowed")
    for _ in range(4):
        assert (await client.get("/auth/me", cookies=auth_cookies(str(user_id)))).status_code == 200


async def test_configured_cap_does_not_restore_revoked_authentication(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    _freeze_limiter_window(monkeypatch)

    user_id = await _create_user(session_factory, email="revoked-cap-user@example.com")
    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setitem(
        settings.__dict__, "pinvi_rate_limit_user_limit_overrides", {str(user_id): 4}
    )
    cookies = auth_cookies(str(user_id))
    assert (await client.get("/auth/me", cookies=cookies)).status_code == 200
    async with session_factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.access_token_version += 1
        await db.commit()
    assert (await client.get("/auth/me", cookies=cookies)).status_code == 401


async def test_postgres_configured_counter_is_atomic_across_backends_and_requests(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from sqlalchemy import delete

    import app.middleware.rate_limit as middleware
    from app.core.config import settings

    _freeze_limiter_window(monkeypatch)
    from app.middleware.rate_limit import PostgresRateLimitBackend

    user_id = await _create_user(session_factory, email="atomic-cap-user@example.com")
    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setitem(
        settings.__dict__, "pinvi_rate_limit_user_limit_overrides", {str(user_id): 4}
    )
    fixed = datetime.now(UTC).replace(second=10, microsecond=0)

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return fixed

    monkeypatch.setattr(middleware, "datetime", Clock)
    bucket_hash = rate_limit_bucket_hash("authenticated_default", "user:" + str(user_id))
    backends = [PostgresRateLimitBackend(), PostgresRateLimitBackend()]
    counts = await asyncio.gather(
        *(
            backends[i % 2].hit(
                bucket_hash=bucket_hash,
                limit_name="authenticated_default",
                window_start=fixed.replace(second=0),
                expires_at=fixed.replace(second=0) + timedelta(minutes=2),
            )
            for i in range(12)
        )
    )
    assert sorted(counts) == list(range(1, 13))
    async with session_factory() as db:
        await db.execute(delete(RateLimitBucket).where(RateLimitBucket.bucket_hash == bucket_hash))
        await db.commit()
    results = await asyncio.gather(
        *(client.get("/auth/me", cookies=auth_cookies(str(user_id))) for _ in range(12))
    )
    assert [r.status_code for r in results].count(200) == 4
    assert [r.status_code for r in results].count(429) == 8
    assert all(r.json()["error"]["details"]["limit"] == 4 for r in results if r.status_code == 429)
