"""Admin email deliverability API 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.models.email_deliverability import EmailSuppression, ResendWebhookEvent
from app.models.email_queue import EmailQueue
from app.models.user import User
from app.services.email_deliverability import email_hash

pytestmark = pytest.mark.asyncio


async def _create_admin_user(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        user = User(
            email=f"email_admin_{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="관리자",
            status="active",
            roles=["user", "operator"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def test_admin_email_deliverability_reports_degraded_counts(
    client,
    session_factory,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_api_key", "")
    monkeypatch.setattr(settings, "pinvi_resend_from_email", "Pinvi <noreply@send.pinvi.test>")
    monkeypatch.setattr(settings, "pinvi_resend_webhook_secret", "")
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", False)
    admin_id = await _create_admin_user(session_factory)
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add_all(
            [
                EmailQueue(
                    to_email="pending@pinvi.test",
                    subject="대기",
                    template="verify_email",
                    payload={"verify_url": "https://pinvi.test/verify"},
                    status="pending",
                    scheduled_at=now,
                ),
                EmailQueue(
                    to_email="suppressed@pinvi.test",
                    subject="차단",
                    template="trip_invite",
                    payload={"invite_url": "https://pinvi.test/invite", "trip_title": "서울"},
                    status="suppressed",
                    scheduled_at=now,
                ),
                EmailSuppression(
                    email_hash=email_hash("suppressed@pinvi.test"),
                    reason="complaint",
                    source="resend",
                    first_seen_at=now,
                    last_seen_at=now,
                ),
                ResendWebhookEvent(
                    event_id="evt_admin_email_bounce",
                    event_type="email.bounced",
                    event_created_at=now,
                    payload_summary={"has_entity_ref": False},
                ),
            ]
        )
        await db.commit()

    resp = await client.get(
        "/admin/emails/deliverability",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "degraded"
    assert data["resend_api_configured"] is False
    assert data["console_mode"] is True
    assert data["domain"]["from_domain"] == "send.pinvi.test"
    assert data["queue"]["pending"] == 1
    assert data["queue"]["suppressed"] == 1
    assert data["suppression"]["active_suppressions"] == 1
    assert data["webhook"]["recent_events"]["email.bounced"] == 1
    assert "re_test_secret" not in resp.text
