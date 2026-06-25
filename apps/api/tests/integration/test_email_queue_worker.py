"""email_queue SKIP LOCKED worker 통합 테스트."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import settings
from app.models.email_queue import EmailQueue
from app.services import email_service
from app.services.email_service import process_pending_email_batch

pytestmark = pytest.mark.asyncio


async def test_process_pending_email_batch_marks_console_mode_sent(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_api_key", "")
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            EmailQueue(
                to_email="worker@pinvi.test",
                subject="Pinvi 이메일 인증",
                template="verify_email",
                payload={"verify_url": "https://pinvi.test/verify?token=x"},
                scheduled_at=now,
            )
        )
        await db.commit()

    async with session_factory() as db:
        result = await process_pending_email_batch(db, now=now)

    assert result.claimed == 1
    assert result.sent == 1

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.to_email == "worker@pinvi.test"))
        assert row is not None
        assert row.status == "sent"
        assert row.attempts == 1
        assert row.sent_at == now


async def test_process_pending_email_batch_retries_render_failure(session_factory) -> None:
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            EmailQueue(
                to_email="retry@pinvi.test",
                subject="Pinvi 이메일 인증",
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
        row = await db.scalar(select(EmailQueue).where(EmailQueue.to_email == "retry@pinvi.test"))
        assert row is not None
        assert row.status == "pending"
        assert row.attempts == 1
        assert row.last_error is not None
        assert row.scheduled_at > now


async def test_email_outbox_worker_lifespan_starts_and_cancels_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_email_outbox_worker_enabled", True)
    monkeypatch.setattr(settings, "pinvi_email_outbox_drain_interval_seconds", 0.01)
    monkeypatch.setattr(settings, "pinvi_email_outbox_batch_size", 7)

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_drain_loop(interval: float, batch_size: int) -> None:
        assert interval == 0.01
        assert batch_size == 7
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(email_service, "_drain_loop", fake_drain_loop)
    app = FastAPI()

    async with email_service.email_outbox_worker_lifespan(app):
        await asyncio.wait_for(started.wait(), timeout=1)
        assert app.state.email_outbox_worker.get_name() == "email-outbox-drain"

    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert app.state.email_outbox_worker is None


async def test_email_outbox_worker_lifespan_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_email_outbox_worker_enabled", False)
    app = FastAPI()

    async with email_service.email_outbox_worker_lifespan(app):
        assert not hasattr(app.state, "email_outbox_worker")
