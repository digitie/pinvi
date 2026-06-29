"""ETL raw SQL smoke tests against the migrated app schema.

Two layers of protection (PR #327 / T-291, issue #348/#349):

1. ``test_etl_raw_sql_statements_execute_against_alembic_schema`` — every
   extracted statement *parses and runs* against the real Alembic-migrated
   ``app`` schema with an empty dataset (catches table/column/grammar drift the
   dialect-compile smoke in ``apps/etl/tests`` cannot see).
2. ``test_etl_raw_sql_statements_return_expected_counts_with_seeded_rows`` —
   seeds representative rows and asserts the count/window/FILTER logic returns
   the *expected* numbers, including the API-only ``_AUDIT_RETENTION_SUMMARY_SQL``
   and a ``status='pending_delete'`` row that locks the widened ``deleted_users``
   filter in ``PII_RETENTION_SUMMARY_SQL``.
"""

from __future__ import annotations

import importlib
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.models.audit import AdminAuditLog
from app.models.email_queue import EmailQueue
from app.models.oauth_identity import (
    OAuthLoginState,
    OAuthMobileExchange,
    UserOAuthIdentity,
)
from app.models.session import UserSession
from app.models.telegram_outbox import TelegramNotificationOutbox
from app.models.user import User
from app.models.user_email_verification import UserEmailVerification
from app.services.admin_etl import _AUDIT_RETENTION_SUMMARY_SQL
from app.services.location_audit import append_location_log

pytestmark = pytest.mark.asyncio


def _load_etl_sql_modules() -> tuple[Any, Any]:
    apps_dir = Path(__file__).resolve().parents[3]
    etl_dir = apps_dir / "etl"
    if str(etl_dir) not in sys.path:
        sys.path.insert(0, str(etl_dir))
    return (
        importlib.import_module("pinvi.etl.sql.outbox"),
        importlib.import_module("pinvi.etl.sql.retention"),
    )


def _params(now: datetime) -> dict[str, Any]:
    return {
        "now": now,
        "stuck_before": now - timedelta(minutes=15),
        "max_attempts": 5,
        "template_window_start": now - timedelta(hours=24),
        "template_limit": 10,
        "category_window_start": now - timedelta(hours=24),
        "category_limit": 10,
        "user_pii_cutoff": now - timedelta(days=30),
        "session_cutoff": now - timedelta(days=30),
        "archive_cutoff": now - timedelta(days=180),
        "purpose_limit": 10,
        "audit_cutoff": now - timedelta(days=90),
    }


async def test_etl_raw_sql_statements_execute_against_alembic_schema(
    session_factory: Any,
) -> None:
    outbox_sql, retention_sql = _load_etl_sql_modules()
    now = datetime(2026, 6, 29, 4, 30, tzinfo=UTC)
    params = _params(now)
    statements = [
        outbox_sql.EMAIL_OUTBOX_SUMMARY_SQL,
        outbox_sql.EMAIL_OUTBOX_TEMPLATE_SQL,
        outbox_sql.TELEGRAM_OUTBOX_SUMMARY_SQL,
        outbox_sql.TELEGRAM_OUTBOX_CATEGORY_SQL,
        retention_sql.PII_RETENTION_SUMMARY_SQL,
        retention_sql.LOCATION_LOG_ARCHIVE_SUMMARY_SQL,
        retention_sql.LOCATION_LOG_ARCHIVE_PURPOSE_SQL,
        # API-only summary — exercised here so an empty-schema run also guards it.
        _AUDIT_RETENTION_SUMMARY_SQL,
    ]

    async with session_factory() as db:
        for statement in statements:
            await db.execute(statement, params)


async def _seed_rows(session_factory: Any, now: datetime) -> uuid.UUID:
    """Seed representative rows for every ETL summary statement.

    Returns the ``active_user`` id (FK target for location/audit rows).
    """
    in_window = now - timedelta(hours=1)
    out_of_window = now - timedelta(hours=48)
    old = now - timedelta(days=200)
    grace_expired = now - timedelta(days=31)

    async with session_factory() as db:
        active_user = User(
            email=f"etl-active-{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="활성",
            status="active",
            roles=["user"],
            email_verified_at=now,
        )
        # Eligible PII candidates: a fully 'deleted' account AND a 'pending_delete'
        # account whose grace window has lapsed. The pending_delete row LOCKS the
        # widened `status IN ('pending_delete','deleted')` filter — if the filter
        # regressed to `status = 'deleted'` the candidate count would drop to 1.
        deleted_user = User(
            email=f"etl-deleted-{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="삭제대상",
            status="deleted",
            roles=["user"],
            is_active=False,
            deleted_at=grace_expired,
            email_verified_at=old,
        )
        pending_delete_user = User(
            email=f"etl-pending-{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="탈퇴진행",
            status="pending_delete",
            roles=["user"],
            is_active=False,
            deleted_at=grace_expired,
            email_verified_at=old,
        )
        # Privileged deleted account — excluded from anonymization candidates.
        privileged_user = User(
            email=f"etl-cpo-{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="보호대상",
            status="deleted",
            roles=["user", "cpo"],
            is_active=False,
            deleted_at=grace_expired,
            email_verified_at=old,
        )
        db.add_all([active_user, deleted_user, pending_delete_user, privileged_user])
        await db.flush()

        # --- email_queue: 8 in-window rows (2 templates) + 1 out-of-window row.
        email_rows = [
            ("welcome", "pending"),
            ("welcome", "sent"),
            ("welcome", "delivered"),
            ("welcome", "delivery_delayed"),
            ("welcome", "suppressed"),
            ("reset", "failed"),
            ("reset", "bounced"),
            ("reset", "complained"),
        ]
        for template, status in email_rows:
            db.add(
                EmailQueue(
                    to_email="x@pinvi.test",
                    template=template,
                    subject="s",
                    status=status,
                    scheduled_at=now,
                    created_at=in_window,
                )
            )
        # Out-of-window row: excluded by the template window, counted by summary.
        db.add(
            EmailQueue(
                to_email="x@pinvi.test",
                template="welcome",
                subject="s",
                status="sent",
                scheduled_at=now,
                created_at=out_of_window,
            )
        )

        # --- telegram outbox: 6 in-window rows (2 categories) + 1 out-of-window.
        telegram_rows = [
            ("system_alert", "pending"),
            ("system_alert", "sent"),
            ("system_alert", "skipped"),
            ("system_alert", "failed"),
            ("trip_created", "sent"),
            ("trip_created", "sent"),
        ]
        for category, status in telegram_rows:
            db.add(
                TelegramNotificationOutbox(
                    category=category,
                    status=status,
                    scheduled_at=now,
                    created_at=in_window,
                )
            )
        db.add(
            TelegramNotificationOutbox(
                category="system_alert",
                status="sent",
                scheduled_at=now,
                created_at=out_of_window,
            )
        )

        # --- location_access_log: 2 archive candidates (<= cutoff) + 1 active.
        await append_location_log(
            db,
            user_id=active_user.user_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("37.123456"),
            lng=Decimal("127.123456"),
            request_id=uuid.uuid4(),
            ip_hash="a" * 64,
            occurred_at=old,
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
            occurred_at=old,
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
            ip_hash="c" * 64,
            occurred_at=now - timedelta(days=1),
            commit=False,
        )

        # --- PII retention satellites.
        db.add_all(
            [
                UserOAuthIdentity(
                    user_id=deleted_user.user_id,
                    provider="google",
                    provider_user_id="etl-deleted-subject",
                    provider_email="etl-deleted@example.com",
                    provider_email_verified=True,
                    display_name_snapshot="삭제대상",
                    linked_at=old,
                ),
                UserOAuthIdentity(
                    user_id=pending_delete_user.user_id,
                    provider="google",
                    provider_user_id="etl-pending-subject",
                    provider_email="etl-pending@example.com",
                    provider_email_verified=True,
                    display_name_snapshot="탈퇴진행",
                    linked_at=old,
                ),
                UserEmailVerification(
                    user_id=active_user.user_id,
                    token_hash="etl-signup-1",
                    purpose="signup",
                    expires_at=now - timedelta(hours=1),
                ),
                UserEmailVerification(
                    user_id=active_user.user_id,
                    token_hash="etl-signup-2",
                    purpose="signup",
                    expires_at=now - timedelta(hours=2),
                ),
                UserEmailVerification(
                    user_id=active_user.user_id,
                    token_hash="etl-reset-1",
                    purpose="password_reset",
                    expires_at=now - timedelta(hours=1),
                ),
                UserSession(
                    user_id=active_user.user_id,
                    session_token_hash="etl-old-revoked",
                    expires_at=grace_expired,
                    revoked_at=grace_expired,
                    user_agent="old revoked",
                    ip_address="127.0.0.1",
                ),
                UserSession(
                    user_id=active_user.user_id,
                    session_token_hash="etl-old-expired",
                    expires_at=grace_expired,
                    user_agent="old expired",
                    ip_address="127.0.0.1",
                ),
                OAuthLoginState(
                    state_hash="etl-expired-oauth-state",
                    nonce_hash="nonce",
                    pkce_code_verifier_hash="pkce",
                    provider="google",
                    mode="login",
                    expires_at=now - timedelta(minutes=10),
                    created_at=now - timedelta(hours=1),
                ),
                OAuthMobileExchange(
                    code_hash="etl-expired-mobile-exchange",
                    user_id=active_user.user_id,
                    expires_at=now - timedelta(minutes=10),
                    created_at=now - timedelta(hours=1),
                ),
            ]
        )

        # --- admin_audit_log: 2 over-retention PII rows + 2 that must NOT count.
        db.add_all(
            [
                AdminAuditLog(
                    actor_user_id=active_user.user_id,
                    action="reveal_email",
                    resource_type="user",
                    resource_id=str(deleted_user.user_id),
                    access_reason="seed",
                    target_pii_fields=["email"],
                    ip_hash="d" * 64,
                    user_agent="audit-old-pii",
                    request_id=uuid.uuid4(),
                    prev_hash="1" * 64,
                    content_hash="a1" + "0" * 62,
                    occurred_at=old,
                ),
                AdminAuditLog(
                    actor_user_id=active_user.user_id,
                    action="view",
                    resource_type="user",
                    resource_id=str(active_user.user_id),
                    access_reason="seed",
                    target_pii_fields=None,
                    ip_hash="e" * 64,
                    user_agent="audit-old-ua-only",
                    request_id=uuid.uuid4(),
                    prev_hash="2" * 64,
                    content_hash="a2" + "0" * 62,
                    occurred_at=old,
                ),
                # Recent → after cutoff → not counted.
                AdminAuditLog(
                    actor_user_id=active_user.user_id,
                    action="reveal_email",
                    resource_type="user",
                    resource_id=str(active_user.user_id),
                    access_reason="seed",
                    target_pii_fields=["email"],
                    ip_hash="f" * 64,
                    user_agent="audit-recent",
                    request_id=uuid.uuid4(),
                    prev_hash="3" * 64,
                    content_hash="a3" + "0" * 62,
                    occurred_at=now - timedelta(days=1),
                ),
                # Old but no PII fields and no user_agent → not counted.
                AdminAuditLog(
                    actor_user_id=active_user.user_id,
                    action="view",
                    resource_type="user",
                    resource_id=str(active_user.user_id),
                    access_reason="seed",
                    target_pii_fields=None,
                    ip_hash="9" * 64,
                    user_agent=None,
                    request_id=uuid.uuid4(),
                    prev_hash="4" * 64,
                    content_hash="a4" + "0" * 62,
                    occurred_at=old,
                ),
            ]
        )

        await db.commit()
        return active_user.user_id


async def test_etl_raw_sql_statements_return_expected_counts_with_seeded_rows(
    session_factory: Any,
) -> None:
    outbox_sql, retention_sql = _load_etl_sql_modules()
    now = datetime(2026, 6, 29, 4, 30, tzinfo=UTC)
    params = _params(now)

    await _seed_rows(session_factory, now)

    async with session_factory() as db:
        # --- email summary (all rows, no window).
        email_summary = (
            (await db.execute(outbox_sql.EMAIL_OUTBOX_SUMMARY_SQL, params)).mappings().one()
        )
        assert email_summary["total"] == 9
        assert email_summary["pending_total"] == 1
        assert email_summary["failed"] == 1
        assert email_summary["bounced"] == 1
        assert email_summary["complained"] == 1

        # --- email template (windowed) — locks delivery_delayed/suppressed columns
        # and the created_at window (out-of-window 'welcome/sent' row is excluded).
        email_templates = {
            row["template"]: row
            for row in (await db.execute(outbox_sql.EMAIL_OUTBOX_TEMPLATE_SQL, params))
            .mappings()
            .all()
        }
        assert email_templates["welcome"]["total"] == 5
        assert email_templates["welcome"]["pending"] == 1
        assert email_templates["welcome"]["sent"] == 1
        assert email_templates["welcome"]["delivered"] == 1
        assert email_templates["welcome"]["delivery_delayed"] == 1
        assert email_templates["welcome"]["suppressed"] == 1
        assert email_templates["reset"]["total"] == 3
        assert email_templates["reset"]["failed"] == 1
        assert email_templates["reset"]["bounced"] == 1
        assert email_templates["reset"]["complained"] == 1

        # --- telegram summary (all rows).
        tg_summary = (
            (await db.execute(outbox_sql.TELEGRAM_OUTBOX_SUMMARY_SQL, params)).mappings().one()
        )
        assert tg_summary["total"] == 7
        assert tg_summary["pending_total"] == 1
        assert tg_summary["sent"] == 4
        assert tg_summary["skipped"] == 1
        assert tg_summary["failed"] == 1

        # --- telegram category (windowed).
        tg_categories = {
            row["category"]: row
            for row in (await db.execute(outbox_sql.TELEGRAM_OUTBOX_CATEGORY_SQL, params))
            .mappings()
            .all()
        }
        assert tg_categories["system_alert"]["total"] == 4
        assert tg_categories["system_alert"]["pending"] == 1
        assert tg_categories["system_alert"]["sent"] == 1
        assert tg_categories["system_alert"]["skipped"] == 1
        assert tg_categories["system_alert"]["failed"] == 1
        assert tg_categories["trip_created"]["total"] == 2
        assert tg_categories["trip_created"]["sent"] == 2

        # --- PII retention — pending_delete row LOCKS the widened filter (== 2).
        pii = (await db.execute(retention_sql.PII_RETENTION_SUMMARY_SQL, params)).mappings().one()
        assert pii["deleted_user_pii_candidates"] == 2
        assert pii["deleted_user_oauth_identity_candidates"] == 2
        assert pii["excluded_privileged_deleted_users"] == 1
        assert pii["expired_signup_verifications"] == 2
        assert pii["expired_password_reset_tokens"] == 1
        assert pii["old_revoked_sessions"] == 1
        assert pii["old_expired_sessions"] == 1
        assert pii["expired_oauth_login_states"] == 1
        assert pii["expired_mobile_oauth_exchanges"] == 1

        # --- location archive summary + purpose breakdown.
        loc = (
            (await db.execute(retention_sql.LOCATION_LOG_ARCHIVE_SUMMARY_SQL, params))
            .mappings()
            .one()
        )
        assert loc["total_candidates"] == 2
        assert loc["active_rows_after_cutoff"] == 1
        purposes = {
            row["purpose"]: row["total"]
            for row in (await db.execute(retention_sql.LOCATION_LOG_ARCHIVE_PURPOSE_SQL, params))
            .mappings()
            .all()
        }
        assert purposes == {"nearby_attractions": 1, "viewport_query": 1}

        # --- API-only audit retention summary (90-day window, skip-not-delete).
        audit = (await db.execute(_AUDIT_RETENTION_SUMMARY_SQL, params)).mappings().one()
        assert audit["admin_audit_pii_over_retention"] == 2
