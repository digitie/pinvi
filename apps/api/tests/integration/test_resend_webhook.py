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
from app.models.email_queue import EmailQueue

pytestmark = pytest.mark.asyncio

_WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"tripmate-test-webhook-secret").decode().rstrip("=")


@pytest.fixture(autouse=True)
def _clear_resend_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tripmate_resend_webhook_secret", "")


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


def _payload(body: dict[str, Any]) -> bytes:
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()


def _secret_key(secret: str) -> bytes:
    secret_value = secret.removeprefix("whsec_")
    padding = "=" * (-len(secret_value) % 4)
    return base64.b64decode(f"{secret_value}{padding}", altchars=b"-_")


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


async def test_signed_delivered_updates_status(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "tripmate_resend_webhook_secret", _WEBHOOK_SECRET)
    email_id = await _seed_email(session_factory)
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


async def test_signed_webhook_rejects_missing_signature_headers(
    client,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "tripmate_resend_webhook_secret", _WEBHOOK_SECRET)
    email_id = await _seed_email(session_factory)
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
    monkeypatch.setattr(settings, "tripmate_resend_webhook_secret", _WEBHOOK_SECRET)
    email_id = await _seed_email(session_factory)
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
    monkeypatch.setattr(settings, "tripmate_resend_webhook_secret", _WEBHOOK_SECRET)
    email_id = await _seed_email(session_factory)
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
