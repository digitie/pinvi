"""Resend webhook 통합 — delivered / bounced / complained → email_queue 갱신.

SPRINT-2 DoD (Svix 서명 실검증은 Sprint 5 — `docs/integrations/resend.md` §6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.email_queue import EmailQueue

pytestmark = pytest.mark.asyncio


async def _seed_email(session_factory) -> str:
    """email_queue row 1건 seed 후 email_id(UUID 문자열) 반환."""
    email_id = uuid.uuid4()
    async with session_factory() as db:
        db.add(
            EmailQueue(
                email_id=email_id,
                to_email="x@tripmate.test",
                subject="인증",
                template="verify_email",
                status="sent",
                scheduled_at=datetime.now(UTC),
            )
        )
        await db.commit()
    return str(email_id)


async def test_delivered_updates_status(client, session_factory) -> None:
    email_id = await _seed_email(session_factory)
    resp = await client.post(
        "/webhooks/resend",
        json={
            "type": "email.delivered",
            "data": {"headers": {"X-Entity-Ref-ID": email_id}},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id)))
        assert row is not None
        assert row.status == "delivered"
        assert row.delivered_at is not None


async def test_bounced_updates_status(client, session_factory) -> None:
    email_id = await _seed_email(session_factory)
    resp = await client.post(
        "/webhooks/resend",
        json={
            "type": "email.bounced",
            "data": {
                "headers": {"X-Entity-Ref-ID": email_id},
                "bounce": {"type": "hard"},
            },
        },
    )
    assert resp.status_code == 200

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id)))
        assert row is not None
        assert row.status == "bounced"
        assert row.bounce_type == "hard"
        assert row.bounced_at is not None


async def test_missing_entity_ref_is_ok(client) -> None:
    resp = await client.post(
        "/webhooks/resend",
        json={"type": "email.delivered", "data": {"headers": {}}},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
