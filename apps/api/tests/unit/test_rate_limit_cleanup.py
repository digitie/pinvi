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


@pytest.mark.parametrize("error_type", [ConnectionRefusedError, OSError])
async def test_connection_creation_error_recovers_on_next_tick_and_stops_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error_type: type[OSError],
) -> None:
    calls = 0
    recovered = asyncio.Event()

    class Result:
        def all(self) -> list[tuple[()]]:
            return []

    class Session:
        async def __aenter__(self) -> Session:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise error_type("fixture-private-database-address")
            return self

        async def __aexit__(self, *_: Any) -> None:
            pass

        async def execute(self, *_: Any, **__: Any) -> Result:
            recovered.set()
            return Result()

        async def commit(self) -> None:
            pass

    monkeypatch.setattr(module.db_session, "async_session_factory", Session)
    worker = module.RateLimitBucketCleanup(interval_seconds=0.001, timeout_seconds=0.1)
    worker.start()
    try:
        try:
            await asyncio.wait_for(recovered.wait(), timeout=0.1)
        except TimeoutError:
            pass
    finally:
        stopped = await asyncio.gather(worker.stop(), return_exceptions=True)
    assert recovered.is_set(), "connection creation failure permanently stopped cleanup"
    assert stopped == [None], "expected connection failure leaked through lifecycle stop"
    assert calls >= 2
    errors = [r for r in caplog.records if r.message == "rate_limit.cleanup_failed"]
    assert len(errors) == 1 and errors[0].error_type == error_type.__name__
    assert "fixture-private-database-address" not in str(errors[0].__dict__)


async def test_full_batches_share_one_timeout_budget_and_worker_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    first_cycle_done = asyncio.Event()
    next_tick = asyncio.Event()
    original_sleep = asyncio.sleep
    worker = module.RateLimitBucketCleanup(interval_seconds=60, timeout_seconds=0.02)
    ticks = 0

    async def controlled_sleep(delay: float) -> None:
        nonlocal ticks
        if asyncio.current_task() is worker._task and delay == 60:
            ticks += 1
            if ticks == 1:
                return
            first_cycle_done.set()
            await next_tick.wait()
        else:
            await original_sleep(delay)

    async def full_batch(**kwargs: Any) -> int:
        nonlocal calls
        assert kwargs.get("batch_size", 1000) == 1000
        calls += 1
        if calls == 1:
            return 1000
        # 다음 batch를 멈춰 공통 주기 deadline이 취소하고 다음 tick으로 복귀하는지 본다.
        await asyncio.Event().wait()
        return 1000

    monkeypatch.setattr(module.asyncio, "sleep", controlled_sleep)
    monkeypatch.setattr(module, "cleanup_expired_rate_limit_buckets", full_batch)
    worker.start()
    try:
        await asyncio.wait_for(first_cycle_done.wait(), 1)
        assert calls == 2, "one period must start another batch and bound its wait"
        assert worker._task is not None and not worker._task.done()
    finally:
        await worker.stop()


async def test_external_worker_cancellation_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()

    async def cleanup(**_: Any) -> int:
        entered.set()
        await asyncio.Event().wait()
        return 0

    monkeypatch.setattr(module, "cleanup_expired_rate_limit_buckets", cleanup)
    worker = module.RateLimitBucketCleanup(interval_seconds=0.001)
    worker.start()
    await asyncio.wait_for(entered.wait(), 1)
    task = worker._task
    assert task is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await worker.stop()


async def test_cancellation_survives_connection_error_during_session_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    calls = 0

    async def cleanup(**_: Any) -> int:
        nonlocal calls
        calls += 1
        first = calls == 1
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            if first:
                # 실제 driver가 취소 처리 중 연결 close 오류를 올리는 경우를 모사한다.
                raise ConnectionRefusedError("fixture-private-close-address")
        return 0

    monkeypatch.setattr(module, "cleanup_expired_rate_limit_buckets", cleanup)
    worker = module.RateLimitBucketCleanup(interval_seconds=0.001)
    worker.start()
    await asyncio.wait_for(entered.wait(), 1)
    task = worker._task
    assert task is not None
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(task), 0.1)
    finally:
        await worker.stop()
