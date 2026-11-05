"""요청 밖 bucket 청소 task의 종료·실패 격리."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app.middleware.rate_limit as module


@pytest.mark.parametrize("kind", ["database", "timeout"])
async def test_cleanup_recovers_on_next_tick_without_exposing_database_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, kind: str
) -> None:
    calls = 0
    recovered = asyncio.Event()

    async def cleanup(**_: Any) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            if kind == "database":
                raise SQLAlchemyError("fixture-private-sql-param")
            await asyncio.Event().wait()
        recovered.set()
        return 0

    monkeypatch.setattr(module, "cleanup_expired_rate_limit_buckets", cleanup)
    worker = module.RateLimitBucketCleanup(interval_seconds=0.001, timeout_seconds=0.01)
    worker.start()
    try:
        await asyncio.wait_for(recovered.wait(), timeout=1)
    finally:
        await worker.stop()
    assert calls >= 2
    records = [r for r in caplog.records if r.message == "rate_limit.cleanup_failed"]
    assert len(records) == 1
    assert records[0].error_type == ("SQLAlchemyError" if kind == "database" else "TimeoutError")
    assert "fixture-private-sql-param" not in str(records[0].__dict__)


async def test_cleanup_stop_cancels_inflight_session_and_allows_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    closed = asyncio.Event()
    calls = 0

    class Session:
        async def __aenter__(self) -> Session:
            nonlocal calls
            calls += 1
            return self

        async def __aexit__(self, *_: Any) -> None:
            closed.set()

        async def execute(self, *_: Any, **__: Any) -> None:
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(module.db_session, "async_session_factory", Session)
    worker = module.RateLimitBucketCleanup(interval_seconds=0.001)
    worker.start()
    worker.start()
    await asyncio.wait_for(entered.wait(), timeout=1)
    await worker.stop()
    assert closed.is_set()
    assert calls == 1
    await worker.stop()
    entered.clear()
    closed.clear()
    worker.start()
    await asyncio.wait_for(entered.wait(), timeout=1)
    await worker.stop()
    assert closed.is_set()
    assert calls == 2


async def test_cleanup_cancellation_propagates_and_closes_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    closed = asyncio.Event()

    class Session:
        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *_: Any) -> None:
            closed.set()

        async def execute(self, *_: Any, **__: Any) -> None:
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(module.db_session, "async_session_factory", Session)
    task = asyncio.create_task(module.cleanup_expired_rate_limit_buckets())
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.parametrize("kwargs", [{"interval_seconds": 0}, {"timeout_seconds": -1}])
def test_cleanup_rejects_invalid_lifecycle_intervals(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        module.RateLimitBucketCleanup(**kwargs)


async def test_cleanup_rejects_invalid_batch_without_opening_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected() -> Iterator[None]:
        raise AssertionError("DB must not be opened")

    monkeypatch.setattr(module.db_session, "async_session_factory", unexpected)
    with pytest.raises(ValueError):
        await module.cleanup_expired_rate_limit_buckets(batch_size=0)
