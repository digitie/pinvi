"""email_queue SKIP LOCKED worker 통합 테스트."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.clients.resend import ResendClient
from app.core.config import settings
from app.models.email_deliverability import EmailSuppression
from app.models.email_queue import EmailQueue
from app.models.user import User
from app.services import email_service
from app.services.email_deliverability import email_hash
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


async def test_process_pending_email_batch_skips_suppressed_user_status(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    now = datetime.now(UTC)

    async def fail_send(row: EmailQueue) -> str | None:
        raise AssertionError("suppressed user must not call Resend")

    monkeypatch.setattr(email_service, "_send_email_row", fail_send)
    async with session_factory() as db:
        user = User(
            email="bounced-user@pinvi.test",
            status="active",
            email_status="bounced",
            email_verified_at=now,
        )
        db.add(user)
        await db.flush()
        db.add(
            EmailQueue(
                user_id=user.user_id,
                to_email=user.email,
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
    assert result.sent == 0
    assert result.suppressed == 1

    async with session_factory() as db:
        row = await db.scalar(
            select(EmailQueue).where(EmailQueue.to_email == "bounced-user@pinvi.test")
        )
        assert row is not None
        assert row.status == "bounced"
        assert row.last_error == "suppressed:user_email_status:bounced"


async def test_process_pending_email_batch_skips_active_suppression_source(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    now = datetime.now(UTC)

    async def fail_send(row: EmailQueue) -> str | None:
        raise AssertionError("active suppression must not call Resend")

    monkeypatch.setattr(email_service, "_send_email_row", fail_send)
    async with session_factory() as db:
        db.add(
            EmailSuppression(
                email_hash=email_hash("blocked@pinvi.test"),
                reason="complaint",
                source="resend",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        db.add(
            EmailQueue(
                to_email="Blocked@Pinvi.Test",
                subject="Pinvi 초대",
                template="trip_invite",
                payload={
                    "invite_url": "https://pinvi.test/invite",
                    "trip_title": "서울",
                },
                scheduled_at=now,
            )
        )
        await db.commit()

    async with session_factory() as db:
        result = await process_pending_email_batch(db, now=now)

    assert result.claimed == 1
    assert result.suppressed == 1

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.to_email == "Blocked@Pinvi.Test"))
        assert row is not None
        assert row.status == "suppressed"
        assert row.last_error == "suppressed:suppression:complaint"


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


def _mock_resend(
    monkeypatch: pytest.MonkeyPatch, status: int, body: dict[str, object]
) -> list[int]:
    """`create_resend_client`를 MockTransport로 바꾼다. 반환 목록은 Resend 호출 횟수다."""

    calls: list[int] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json=body, request=request)

    @asynccontextmanager
    async def _factory() -> AsyncIterator[ResendClient]:
        async with httpx.AsyncClient(
            base_url="https://api.resend.test",
            transport=httpx.MockTransport(_handler),
        ) as http:
            yield ResendClient(http)

    monkeypatch.setattr(settings, "pinvi_resend_api_key", "re_worker_test_key")
    monkeypatch.setattr(email_service, "create_resend_client", _factory)
    return calls


async def _enqueue_invite(session_factory, to_email: str, now: datetime) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        db.add(
            EmailQueue(
                to_email=to_email,
                subject="Pinvi 여행 초대: 서울",
                template="trip_invite",
                payload={"invite_url": "https://pinvi.test/trips/x", "trip_title": "서울"},
                scheduled_at=now,
            )
        )
        await db.commit()


@pytest.mark.parametrize(
    ("status", "name", "message"),
    [
        (403, "validation_error", "The send.pinvi.local domain is not verified."),
        (422, "invalid_from_address", "Invalid `from` field."),
    ],
)
async def test_resend_permanent_rejection_fails_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    status: int,
    name: str,
    message: str,
) -> None:
    """#720 — 미검증 발신 도메인 403·from 형식 422는 5회 backoff 없이 첫 시도에 failed."""

    now = datetime.now(UTC)
    to_email = f"permanent-{status}@pinvi.test"
    calls = _mock_resend(
        monkeypatch, status, {"statusCode": status, "name": name, "message": message}
    )
    await _enqueue_invite(session_factory, to_email, now)

    async with session_factory() as db:
        result = await process_pending_email_batch(db, now=now)

    assert result.claimed == 1
    assert result.failed == 1
    assert result.retried == 0
    assert len(calls) == 1

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.to_email == to_email))
        assert row is not None
        assert row.status == "failed"
        assert row.attempts == 1
        assert row.last_error == f"resend_permanent:{status}:{name}:{message}"
        assert "re_worker_test_key" not in (row.last_error or "")

    # 닫힌 row는 다음 batch가 다시 집지 않는다.
    async with session_factory() as db:
        again = await process_pending_email_batch(db, now=now + timedelta(days=1))
    assert again.claimed == 0
    assert len(calls) == 1


async def test_resend_server_error_still_backs_off(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    now = datetime.now(UTC)
    to_email = "transient-503@pinvi.test"
    calls = _mock_resend(monkeypatch, 503, {"name": "internal_server_error", "message": "down"})
    await _enqueue_invite(session_factory, to_email, now)

    async with session_factory() as db:
        result = await process_pending_email_batch(db, now=now)

    assert result.retried == 1
    assert result.failed == 0
    assert len(calls) == 1

    async with session_factory() as db:
        row = await db.scalar(select(EmailQueue).where(EmailQueue.to_email == to_email))
        assert row is not None
        assert row.status == "pending"
        assert row.attempts == 1
        assert row.scheduled_at > now
        assert "503" in (row.last_error or "")


async def test_account_level_rejection_pauses_sending_and_keeps_the_rest_pending(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    """403(발신 도메인)은 계정 수준 — 맞은 row만 failed, 나머지는 pending 그대로, 정지가 풀리면 나간다."""

    now = datetime.now(UTC)
    responses = [
        (
            403,
            {"name": "validation_error", "message": "The send.pinvi.local domain is not verified."},
        ),
        (200, {"id": "email_after_fix"}),
    ]
    calls: list[int] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        status, body = responses[min(len(calls), len(responses) - 1)]
        calls.append(status)
        return httpx.Response(status, json=body, request=request)

    @asynccontextmanager
    async def _factory() -> AsyncIterator[ResendClient]:
        async with httpx.AsyncClient(
            base_url="https://api.resend.test", transport=httpx.MockTransport(_handler)
        ) as http:
            yield ResendClient(http)

    monkeypatch.setattr(settings, "pinvi_resend_api_key", "re_worker_test_key")
    monkeypatch.setattr(email_service, "create_resend_client", _factory)
    await _enqueue_invite(session_factory, "first@pinvi.test", now)
    await _enqueue_invite(session_factory, "second@pinvi.test", now + timedelta(seconds=1))
    later = now + timedelta(seconds=2)

    async with session_factory() as db:
        result = await process_pending_email_batch(db, now=later)
    assert (result.claimed, result.failed, result.retried, result.sent) == (2, 1, 0, 0)
    assert calls == [403]

    async with session_factory() as db:
        rows = {row.to_email: row for row in (await db.scalars(select(EmailQueue))).all()}
    assert rows["first@pinvi.test"].status == "failed"
    assert rows["second@pinvi.test"].status == "pending"
    assert rows["second@pinvi.test"].attempts == 0
    assert rows["second@pinvi.test"].last_error is None

    # 정지 중에는 Resend를 부르지 않는다.
    async with session_factory() as db:
        paused = await process_pending_email_batch(db, now=later + timedelta(seconds=60))
    assert paused.claimed == 0
    assert calls == [403]

    # 정지가 끝나면(또는 재기동하면) 대기 메일이 나간다.
    resumed_at = later + timedelta(seconds=email_service.PROVIDER_PAUSE_SECONDS + 1)
    async with session_factory() as db:
        resumed = await process_pending_email_batch(db, now=resumed_at)
    assert (resumed.claimed, resumed.sent) == (1, 1)
    assert calls == [403, 200]


async def test_row_level_rejection_does_not_pause_the_queue(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    """422는 그 메일만의 문제 — 다음 메일은 그대로 시도한다."""

    now = datetime.now(UTC)
    calls = _mock_resend(
        monkeypatch, 422, {"name": "validation_error", "message": "Invalid `to` field."}
    )
    await _enqueue_invite(session_factory, "a-422@pinvi.test", now)
    await _enqueue_invite(session_factory, "b-422@pinvi.test", now)

    async with session_factory() as db:
        result = await process_pending_email_batch(db, now=now)

    assert (result.claimed, result.failed) == (2, 2)
    assert len(calls) == 2
