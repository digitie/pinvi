"""Resend webhook 통합 — Svix 서명 검증 + email_queue 갱신."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.email_deliverability import EmailSuppression, ResendWebhookEvent
from app.models.email_queue import EmailQueue
from app.models.user import User

pytestmark = pytest.mark.asyncio

_WEBHOOK_SECRET_KEY = b"\xff\xee\xdd\xcc\xbb\xaa\x99\x88pinvi-test-webhook-secret"
_WEBHOOK_SECRET = "whsec_" + base64.b64encode(_WEBHOOK_SECRET_KEY).decode().rstrip("=")
_URLSAFE_WEBHOOK_SECRET = "whsec_" + base64.urlsafe_b64encode(_WEBHOOK_SECRET_KEY).decode().rstrip(
    "="
)


@pytest.fixture(autouse=True)
def _clear_resend_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pinvi_environment", "development")
    monkeypatch.setattr(settings, "pinvi_resend_webhook_secret", "")
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", False)


async def _seed_email(session_factory, *, with_user: bool = False) -> tuple[str, str | None]:
    """email_queue row 1건 seed 후 email_id(UUID 문자열) 반환."""
    email_id = uuid.uuid4()
    user_id = None
    async with session_factory() as db:
        if with_user:
            user = User(
                email="x@pinvi.test",
                status="active",
                email_status="active",
                email_verified_at=datetime.now(UTC),
            )
            db.add(user)
            await db.flush()
            user_id = user.user_id
        db.add(
            EmailQueue(
                email_id=email_id,
                user_id=user_id,
                to_email="x@pinvi.test",
                subject="인증",
                template="verify_email",
                status="sent",
                scheduled_at=datetime.now(UTC),
            )
        )
        await db.commit()
    return str(email_id), None if user_id is None else str(user_id)


def _payload(body: dict[str, Any]) -> bytes:
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()


def _secret_key(secret: str) -> bytes:
    secret_value = secret.removeprefix("whsec_")
    padding = "=" * (-len(secret_value) % 4)
    return base64.b64decode(f"{secret_value}{padding}", validate=True)


def _signed_headers(
    payload: bytes,
    *,
    secret: str = _WEBHOOK_SECRET,
    message_id: str = "msg_test",
    timestamp: int | None = None,
) -> dict[str, str]:
    timestamp_value = int(time.time()) if timestamp is None else timestamp
    signed_content = f"{message_id}.{timestamp_value}.".encode() + payload
    signature = base64.b64encode(
        hmac.new(_secret_key(secret), signed_content, hashlib.sha256).digest()
    ).decode()
    return {
        "content-type": "application/json",
        "svix-id": message_id,
        "svix-timestamp": str(timestamp_value),
        "svix-signature": f"v1,{signature}",
    }


async def test_unsigned_webhook_rejects_missing_secret_without_local_opt_in(
    client,
    session_factory,
) -> None:
    email_id, _ = await _seed_email(session_factory)
    resp = await client.post(
        "/webhooks/resend",
        json={
            "type": "email.delivered",
            "data": {"headers": {"X-Entity-Ref-ID": email_id}},
        },
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WEBHOOK_SIGNATURE_NOT_CONFIGURED"

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id)))
        assert row is not None
        assert row.status == "sent"
        assert row.delivered_at is None


async def test_unsigned_delivered_updates_status_with_local_opt_in(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", True)
    email_id, _ = await _seed_email(session_factory)
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


async def test_unsigned_webhook_rejects_missing_secret_in_production(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_environment", "production")
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", True)
    email_id, _ = await _seed_email(session_factory)

    resp = await client.post(
        "/webhooks/resend",
        json={
            "type": "email.delivered",
            "data": {"headers": {"X-Entity-Ref-ID": email_id}},
        },
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WEBHOOK_SIGNATURE_NOT_CONFIGURED"

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id)))
        assert row is not None
        assert row.status == "sent"
        assert row.delivered_at is None


async def test_signed_delivered_updates_status(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_secret", _WEBHOOK_SECRET)
    email_id, _ = await _seed_email(session_factory)
    payload = _payload(
        {
            "type": "email.delivered",
            "data": {"headers": {"X-Entity-Ref-ID": email_id}},
        }
    )

    resp = await client.post(
        "/webhooks/resend",
        content=payload,
        headers=_signed_headers(payload),
    )
    assert resp.status_code == 200

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id)))
        assert row is not None
        assert row.status == "delivered"
        assert row.delivered_at is not None


async def test_signed_webhook_rejects_urlsafe_secret_config(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_environment", "production")
    monkeypatch.setattr(settings, "pinvi_resend_webhook_secret", _URLSAFE_WEBHOOK_SECRET)
    email_id, _ = await _seed_email(session_factory)
    payload = _payload(
        {
            "type": "email.delivered",
            "data": {"headers": {"X-Entity-Ref-ID": email_id}},
        }
    )

    resp = await client.post(
        "/webhooks/resend",
        content=payload,
        headers=_signed_headers(payload),
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WEBHOOK_SIGNATURE_NOT_CONFIGURED"

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id)))
        assert row is not None
        assert row.status == "sent"
        assert row.delivered_at is None


async def test_signed_webhook_rejects_missing_signature_headers(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_secret", _WEBHOOK_SECRET)
    email_id, _ = await _seed_email(session_factory)
    payload = _payload(
        {
            "type": "email.delivered",
            "data": {"headers": {"X-Entity-Ref-ID": email_id}},
        }
    )

    resp = await client.post(
        "/webhooks/resend",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id)))
        assert row is not None
        assert row.status == "sent"
        assert row.delivered_at is None


async def test_signed_webhook_rejects_invalid_signature(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_secret", _WEBHOOK_SECRET)
    email_id, _ = await _seed_email(session_factory)
    payload = _payload(
        {
            "type": "email.delivered",
            "data": {"headers": {"X-Entity-Ref-ID": email_id}},
        }
    )
    headers = _signed_headers(payload)
    headers["svix-signature"] = "v1,invalid"

    resp = await client.post("/webhooks/resend", content=payload, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id)))
        assert row is not None
        assert row.status == "sent"


async def test_signed_webhook_rejects_old_timestamp(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_secret", _WEBHOOK_SECRET)
    email_id, _ = await _seed_email(session_factory)
    payload = _payload(
        {
            "type": "email.delivered",
            "data": {"headers": {"X-Entity-Ref-ID": email_id}},
        }
    )

    resp = await client.post(
        "/webhooks/resend",
        content=payload,
        headers=_signed_headers(payload, timestamp=int(time.time()) - 600),
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id)))
        assert row is not None
        assert row.status == "sent"


async def test_unsigned_bounced_updates_status_with_local_opt_in(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", True)
    email_id, _ = await _seed_email(session_factory)
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


async def test_unsigned_missing_entity_ref_is_ok_with_local_opt_in(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", True)
    resp = await client.post(
        "/webhooks/resend",
        json={"type": "email.delivered", "data": {"headers": {}}},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_unsigned_bounced_updates_user_status_and_suppression(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", True)
    email_id, user_id = await _seed_email(session_factory, with_user=True)
    assert user_id is not None

    resp = await client.post(
        "/webhooks/resend",
        json={
            "id": "evt_bounce_user",
            "type": "email.bounced",
            "created_at": "2026-06-28T10:00:00Z",
            "data": {
                "id": "email_resend_1",
                "headers": {"X-Entity-Ref-ID": email_id},
                "bounce": {"type": "hard", "message": "mailbox unavailable"},
            },
        },
    )

    assert resp.status_code == 200
    async with session_factory() as db:
        queue = await db.scalar(
            select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id))
        )
        user = await db.scalar(select(User).where(User.user_id == uuid.UUID(user_id)))
        suppression = await db.scalar(select(EmailSuppression))
        event = await db.scalar(
            select(ResendWebhookEvent).where(ResendWebhookEvent.event_id == "evt_bounce_user")
        )
        assert queue is not None
        assert queue.status == "bounced"
        assert queue.last_provider_event_id == "evt_bounce_user"
        assert user is not None
        assert user.email_status == "bounced"
        assert suppression is not None
        assert suppression.reason == "hard_bounce"
        assert suppression.released_at is None
        assert event is not None
        assert event.resend_email_id == "email_resend_1"


async def test_unsigned_duplicate_event_is_idempotent(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", True)
    email_id, _ = await _seed_email(session_factory)
    body = {
        "id": "evt_duplicate",
        "type": "email.delivery_delayed",
        "created_at": "2026-06-28T10:00:00Z",
        "data": {
            "headers": {"X-Entity-Ref-ID": email_id},
            "message": "temporary provider delay",
        },
    }

    first = await client.post("/webhooks/resend", json=body)
    second = await client.post("/webhooks/resend", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    async with session_factory() as db:
        events = list((await db.execute(select(ResendWebhookEvent))).scalars())
        queue = await db.scalar(
            select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id))
        )
        assert len(events) == 1
        assert queue is not None
        assert queue.status == "delivery_delayed"
        assert queue.attempts == 0


async def test_unsigned_delivered_after_bounce_does_not_revert_terminal_status(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", True)
    email_id, _ = await _seed_email(session_factory)
    bounce = {
        "id": "evt_terminal_bounce",
        "type": "email.bounced",
        "created_at": "2026-06-28T10:00:00Z",
        "data": {
            "headers": {"X-Entity-Ref-ID": email_id},
            "bounce": {"type": "hard"},
        },
    }
    delivered = {
        "id": "evt_terminal_delivered",
        "type": "email.delivered",
        "created_at": "2026-06-28T10:05:00Z",
        "data": {"headers": {"X-Entity-Ref-ID": email_id}},
    }

    assert (await client.post("/webhooks/resend", json=bounce)).status_code == 200
    assert (await client.post("/webhooks/resend", json=delivered)).status_code == 200

    async with session_factory() as db:
        queue = await db.scalar(
            select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id))
        )
        assert queue is not None
        assert queue.status == "bounced"
        assert queue.last_provider_event_id == "evt_terminal_bounce"


async def test_unsigned_bounce_after_complaint_does_not_downgrade_terminal_status(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_webhook_allow_unsigned", True)
    email_id, _ = await _seed_email(session_factory)
    complaint = {
        "id": "evt_terminal_complaint",
        "type": "email.complained",
        "created_at": "2026-06-28T10:00:00Z",
        "data": {"headers": {"X-Entity-Ref-ID": email_id}},
    }
    bounce = {
        "id": "evt_terminal_bounce_after_complaint",
        "type": "email.bounced",
        "created_at": "2026-06-28T10:05:00Z",
        "data": {
            "headers": {"X-Entity-Ref-ID": email_id},
            "bounce": {"type": "hard"},
        },
    }

    assert (await client.post("/webhooks/resend", json=complaint)).status_code == 200
    assert (await client.post("/webhooks/resend", json=bounce)).status_code == 200

    async with session_factory() as db:
        queue = await db.scalar(
            select(EmailQueue).where(EmailQueue.email_id == uuid.UUID(email_id))
        )
        suppression = await db.scalar(select(EmailSuppression))
        assert queue is not None
        assert queue.status == "complained"
        assert queue.last_provider_event_id == "evt_terminal_complaint"
        assert suppression is not None
        assert suppression.reason == "complaint"
        assert suppression.provider_event_id == "evt_terminal_complaint"
