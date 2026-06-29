"""Admin retention execution API integration tests — T-276."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select, text

from app.models.audit import AdminAuditLog, LocationAccessLog, LocationAuditOutbox
from app.models.oauth_identity import OAuthLoginState, OAuthMobileExchange, UserOAuthIdentity
from app.models.session import UserSession
from app.models.user import User
from app.models.user_email_verification import UserEmailVerification
from app.services import admin_retention as admin_retention_service
from app.services.location_audit import append_location_log

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    roles: list[str],
    email_prefix: str,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="운영자",
            status="active",
            roles=roles,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _seed_retention_candidates(session_factory: Any) -> tuple[uuid.UUID, uuid.UUID]:
    now = datetime.now(UTC)
    async with session_factory() as db:
        deleted_user = User(
            email="retention-deleted@example.com",
            password_hash="hash",
            nickname="삭제대상",
            status="deleted",
            roles=["user"],
            is_active=False,
            deleted_at=now - timedelta(days=31),
            email_verified_at=now - timedelta(days=60),
            gender="female",
            birth_year_month="199001",
            residence_sigungu_code="11110",
        )
        active_user = User(
            email="retention-active@example.com",
            password_hash="hash",
            nickname="활성사용자",
            status="active",
            roles=["user"],
            email_verified_at=now,
        )
        db.add_all([deleted_user, active_user])
        await db.flush()

        await append_location_log(
            db,
            user_id=active_user.user_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("37.123456"),
            lng=Decimal("127.123456"),
            request_id=uuid.uuid4(),
            ip_hash="a" * 64,
            occurred_at=now - timedelta(days=200),
            commit=False,
        )
        await append_location_log(
            db,
            user_id=active_user.user_id,
            endpoint="/features/in-bounds",
            purpose="viewport_query",
            lat=None,
            lng=None,
            request_id=uuid.uuid4(),
            ip_hash="b" * 64,
            occurred_at=now - timedelta(days=1),
            commit=False,
        )
        db.add_all(
            [
                UserOAuthIdentity(
                    user_id=deleted_user.user_id,
                    provider="google",
                    provider_user_id="retention-deleted-subject",
                    provider_email="retention-deleted@example.com",
                    provider_email_verified=True,
                    display_name_snapshot="삭제대상",
                    linked_at=now - timedelta(days=45),
                ),
                UserEmailVerification(
                    user_id=active_user.user_id,
                    token_hash="retention-expired-signup",
                    purpose="signup",
                    expires_at=now - timedelta(hours=1),
                ),
                UserEmailVerification(
                    user_id=active_user.user_id,
                    token_hash="retention-expired-reset",
                    purpose="password_reset",
                    expires_at=now - timedelta(hours=1),
                ),
                UserSession(
                    user_id=active_user.user_id,
                    session_token_hash="retention-old-revoked",
                    expires_at=now - timedelta(days=40),
                    revoked_at=now - timedelta(days=31),
                    user_agent="old revoked",
                    ip_address="127.0.0.1",
                ),
                UserSession(
                    user_id=active_user.user_id,
                    session_token_hash="retention-old-expired",
                    expires_at=now - timedelta(days=31),
                    user_agent="old expired",
                    ip_address="127.0.0.1",
                ),
                OAuthLoginState(
                    state_hash="retention-expired-oauth-state",
                    nonce_hash="nonce",
                    pkce_code_verifier_hash="pkce",
                    provider="google",
                    mode="login",
                    expires_at=now - timedelta(minutes=10),
                    created_at=now - timedelta(hours=1),
                ),
                OAuthMobileExchange(
                    code_hash="retention-expired-mobile-exchange",
                    user_id=active_user.user_id,
                    expires_at=now - timedelta(minutes=10),
                    created_at=now - timedelta(hours=1),
                ),
                LocationAuditOutbox(
                    user_id=active_user.user_id,
                    occurred_at=now - timedelta(days=1),
                    endpoint="/features/in-bounds",
                    purpose="viewport_query",
                    lat=None,
                    lng=None,
                    request_id=uuid.uuid4(),
                    ip_hash="c" * 64,
                    processed_at=None,
                ),
                AdminAuditLog(
                    actor_user_id=active_user.user_id,
                    action="reveal_email",
                    resource_type="user",
                    resource_id=str(deleted_user.user_id),
                    before_state=None,
                    after_state=None,
                    access_reason="retention test seed",
                    target_pii_fields=["email"],
                    ip_hash="d" * 64,
                    user_agent="retention-test",
                    request_id=uuid.uuid4(),
                    prev_hash="e" * 64,
                    content_hash="f" * 64,
                    occurred_at=now - timedelta(days=200),
                ),
            ]
        )
        await db.commit()
        return deleted_user.user_id, active_user.user_id


async def test_retention_dry_run_records_audit_and_execute_requires_kill_switch(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory,
        roles=["user", "admin"],
        email_prefix="retention-admin",
    )

    summary = await client.get(
        "/admin/retention/summary",
        cookies=auth_cookies(str(admin_id)),
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["data"]["execute_enabled"] is False

    dry_run = await client.post(
        "/admin/retention/dry-run",
        json={"scope": "all", "access_reason": "보존기간 후보 점검"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert dry_run.status_code == 200, dry_run.text
    assert dry_run.json()["data"]["status"] == "dry_run"

    execute = await client.post(
        "/admin/retention/execute",
        json={
            "scope": "all",
            "access_reason": "kill-switch 차단 확인",
            "confirm_phrase": "EXECUTE RETENTION",
        },
        cookies=auth_cookies(str(admin_id)),
    )
    assert execute.status_code == 409
    assert execute.json()["error"]["code"] == "RETENTION_KILL_SWITCH_DISABLED"

    async with session_factory() as db:
        actions = list((await db.scalars(select(AdminAuditLog.action))).all())

    assert actions == ["retention.dry_run"]


async def test_retention_execute_anonymizes_pii_and_archives_location_logs(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cpo_id = await _create_user(
        session_factory,
        roles=["user", "cpo"],
        email_prefix="retention-cpo",
    )
    deleted_user_id, active_user_id = await _seed_retention_candidates(session_factory)
    monkeypatch.setattr(
        admin_retention_service,
        "get_settings",
        lambda: SimpleNamespace(
            pinvi_retention_execute_enabled=True,
            pinvi_retention_execute_confirm_phrase="EXECUTE RETENTION",
        ),
    )

    execute = await client.post(
        "/admin/retention/execute",
        json={
            "scope": "all",
            "access_reason": "보존기간 만료 데이터 정리",
            "confirm_phrase": "EXECUTE RETENTION",
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert execute.status_code == 200, execute.text
    run = execute.json()["data"]
    assert run["status"] == "completed"
    assert run["result"]["pii"]["anonymized_users"] == 1
    assert run["result"]["pii"]["deleted_oauth_identities"] == 1
    assert run["result"]["location"]["archived_rows"] == 1
    assert run["result"]["location"]["deleted_active_rows"] == 1
    assert run["result"]["skipped_admin_audit_pii_over_retention"] == 1
    assert run["candidate_snapshot"]["pii_retention"]["total_candidates"] == 8
    assert run["candidate_snapshot"]["audit_retention"]["policy"] == "append_only_cold_storage"
    assert run["candidate_snapshot"]["audit_retention"]["admin_audit_pii_over_retention"] == 1
    assert run["candidate_snapshot"]["location_log_archive"]["total_candidates"] == 1

    async with session_factory() as db:
        deleted_user = await db.get(User, deleted_user_id)
        assert deleted_user is not None
        assert deleted_user.email == f"deleted+{deleted_user_id}@deleted.pinvi.local"
        assert deleted_user.password_hash is None
        assert deleted_user.nickname is None
        assert deleted_user.email_status == "suppressed"
        assert deleted_user.gender is None
        assert deleted_user.birth_year_month is None
        assert deleted_user.residence_sigungu_code is None

        assert (
            await db.scalar(
                select(func.count())
                .select_from(UserOAuthIdentity)
                .where(UserOAuthIdentity.user_id == deleted_user_id)
            )
        ) == 0
        assert await db.scalar(select(func.count()).select_from(UserEmailVerification)) == 0
        assert await db.scalar(select(func.count()).select_from(UserSession)) == 0
        assert await db.scalar(select(func.count()).select_from(OAuthLoginState)) == 0
        assert await db.scalar(select(func.count()).select_from(OAuthMobileExchange)) == 0

        active_logs = list(
            (
                await db.scalars(select(LocationAccessLog).order_by(LocationAccessLog.log_id.asc()))
            ).all()
        )
        archive_count = await db.scalar(
            text("SELECT count(*) FROM app.location_access_log_archive")
        )
        archive_user_id = await db.scalar(
            text("SELECT user_id FROM app.location_access_log_archive LIMIT 1")
        )
        actions = list(
            (await db.scalars(select(AdminAuditLog.action).order_by(AdminAuditLog.log_id))).all()
        )

    assert len(active_logs) == 1
    assert active_logs[0].user_id == active_user_id
    assert active_logs[0].purpose == "viewport_query"
    assert archive_count == 1
    assert archive_user_id == active_user_id
    assert actions == ["reveal_email", "retention.execute"]


async def test_retention_execute_blocks_location_archive_when_old_outbox_is_pending(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cpo_id = await _create_user(
        session_factory,
        roles=["user", "cpo"],
        email_prefix="retention-blocked-cpo",
    )
    _, active_user_id = await _seed_retention_candidates(session_factory)
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            LocationAuditOutbox(
                user_id=active_user_id,
                occurred_at=now - timedelta(days=200),
                endpoint="/features/nearby",
                purpose="nearby_attractions",
                lat=Decimal("37.000000"),
                lng=Decimal("127.000000"),
                request_id=uuid.uuid4(),
                ip_hash="g" * 64,
                processed_at=None,
            )
        )
        await db.commit()

    monkeypatch.setattr(
        admin_retention_service,
        "get_settings",
        lambda: SimpleNamespace(
            pinvi_retention_execute_enabled=True,
            pinvi_retention_execute_confirm_phrase="EXECUTE RETENTION",
        ),
    )

    execute = await client.post(
        "/admin/retention/execute",
        json={
            "scope": "location",
            "access_reason": "오래된 pending outbox 차단 확인",
            "confirm_phrase": "EXECUTE RETENTION",
        },
        cookies=auth_cookies(str(cpo_id)),
    )

    assert execute.status_code == 409
    assert execute.json()["error"]["code"] == "RETENTION_PRECHECK_FAILED"
    async with session_factory() as db:
        run_count = await db.scalar(text("SELECT count(*) FROM app.retention_runs"))
        active_log_count = await db.scalar(select(func.count()).select_from(LocationAccessLog))
        archive_count = await db.scalar(
            text("SELECT count(*) FROM app.location_access_log_archive")
        )

    assert run_count == 0
    assert active_log_count == 2
    assert archive_count == 0
