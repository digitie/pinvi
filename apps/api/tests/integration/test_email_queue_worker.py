"""email_queue SKIP LOCKED worker 통합 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.email_queue import EmailQueue
from app.services.email_service import process_pending_email_batch

pytestmark = pytest.mark.asyncio


async def test_process_pending_email_batch_marks_console_mode_sent(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    monkeypatch.setattr(settings, "tripmate_resend_api_key", "")
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            EmailQueue(
                to_email="worker@tripmate.test",
                subject="TripMate 이메일 인증",
                template="verify_email",
                payload={"verify_url": "https://tripmate.test/verify?token=x"},
                scheduled_at=now,
            )
        )
        await db.commit()

    async with session_factory() as db:
        result = await process_pending_email_batch(db, now=now)

    assert result.claimed == 1
    assert result.sent == 1

    async with session_factory() as db:
        row = await db.scalar(
            select(EmailQueue).where(EmailQueue.to_email == "worker@tripmate.test")
        )
        assert row is not None
        assert row.status == "sent"
        assert row.attempts == 1
        assert row.sent_at == now


async def test_process_pending_email_batch_retries_render_failure(session_factory) -> None:
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            EmailQueue(
                to_email="retry@tripmate.test",
                subject="TripMate 이메일 인증",
                template="verify_email",
                payload={},
                scheduled_at=now,
            )
        )
        await db.commit()

    async with session_factory() as db:
        result = await process_pending_email_batch(db, now=now)

    assert result.claimed == 1
    assert result.retried == 1

    async with session_factory() as db:
        row = await db.scalar(
            select(EmailQueue).where(EmailQueue.to_email == "retry@tripmate.test")
        )
        assert row is not None
        assert row.status == "pending"
        assert row.attempts == 1
        assert row.last_error is not None
        assert row.scheduled_at > now
