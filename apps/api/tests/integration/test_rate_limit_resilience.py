"""요청 한 번의 한도 결정·카운터 저장과 요청 밖 만료 정리."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

from app.core.config import settings
from app.middleware.rate_limit import RateLimitMiddleware
from app.models.rate_limit import RateLimitBucket

pytestmark = pytest.mark.asyncio


async def test_request_checks_override_and_counter_in_one_statement_without_cleanup(
    session_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setattr(settings, "pinvi_rate_limit_enabled", True)
    monkeypatch.setitem(settings.__dict__, "pinvi_rate_limit_user_limit_overrides", {})
    old_key = "e" * 64
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            RateLimitBucket(
                bucket_hash=old_key,
                window_start=now - timedelta(minutes=3),
                limit_name="authenticated_default",
                count=1,
                expires_at=now - timedelta(minutes=1),
            )
        )
        await db.commit()

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/trips")
    async def trips() -> dict[str, bool]:
        return {"ok": True}

    statements: list[str] = []
    engine = session_factory.kw["bind"]

    def capture(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "after_cursor_execute", capture)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://fixture"
        ) as client:
            response = await client.get("/trips")
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", capture)

    assert response.status_code == 200, response.text
    assert len(statements) == 1, statements
    async with session_factory() as db:
        assert (
            await db.scalar(
                select(RateLimitBucket.count).where(RateLimitBucket.bucket_hash == old_key)
            )
            == 1
        )


async def test_cleanup_removes_only_bounded_expired_unlocked_rows(session_factory: Any) -> None:
    import asyncio

    from app.middleware.rate_limit import cleanup_expired_rate_limit_buckets

    now = datetime.now(UTC)
    async with session_factory() as db:
        for index in range(4):
            db.add(
                RateLimitBucket(
                    bucket_hash=str(index) * 64,
                    window_start=now - timedelta(minutes=3),
                    limit_name="authenticated_default",
                    count=1,
                    expires_at=now + timedelta(minutes=1)
                    if index == 3
                    else now - timedelta(minutes=1),
                )
            )
        await db.commit()

    async with session_factory() as locked:
        await locked.execute(
            select(RateLimitBucket).where(RateLimitBucket.bucket_hash == "0" * 64).with_for_update()
        )
        removed = await asyncio.wait_for(
            cleanup_expired_rate_limit_buckets(batch_size=1), timeout=2
        )
        assert removed == 1
        async with session_factory() as db:
            rows = (await db.scalars(select(RateLimitBucket))).all()
            assert len(rows) == 3
            assert {"0" * 64, "3" * 64} <= {r.bucket_hash for r in rows}
        assert await cleanup_expired_rate_limit_buckets(batch_size=2) == 1
        await locked.rollback()

    assert await cleanup_expired_rate_limit_buckets(batch_size=2) == 1
    assert await cleanup_expired_rate_limit_buckets() == 0
    async with session_factory() as db:
        rows = (await db.scalars(select(RateLimitBucket))).all()
        assert len(rows) == 1 and rows[0].bucket_hash == "3" * 64


async def test_periodic_cleanup_runs_and_stops_without_a_request(session_factory: Any) -> None:
    import asyncio

    from app.middleware.rate_limit import RateLimitBucketCleanup

    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            RateLimitBucket(
                bucket_hash="a" * 64,
                window_start=now - timedelta(minutes=3),
                limit_name="authenticated_default",
                count=1,
                expires_at=now - timedelta(minutes=1),
            )
        )
        await db.commit()

    worker = RateLimitBucketCleanup(interval_seconds=0.01)
    engine = session_factory.kw["bind"]
    cleaned = asyncio.Event()

    def observe(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        if "DELETE FROM app.rate_limit_buckets" in statement:
            cleaned.set()

    event.listen(engine.sync_engine, "after_cursor_execute", observe)
    worker.start()
    try:
        await asyncio.wait_for(cleaned.wait(), timeout=2)

        # after_cursor_execute는 COMMIT 전이다. 다음 읽기에서 반영될 때까지 확인한다.
        async def wait_until_committed() -> None:
            while True:
                async with session_factory() as db:
                    if await db.scalar(select(RateLimitBucket.bucket_hash)) is None:
                        return
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_until_committed(), timeout=2)
    finally:
        await worker.stop()
        event.remove(engine.sync_engine, "after_cursor_execute", observe)


async def test_postgres_check_cancellation_does_not_increment_waiting_bucket(
    session_factory: Any,
) -> None:
    import asyncio

    from sqlalchemy import text

    from app.middleware.rate_limit import PostgresRateLimitBackend

    now = datetime.now(UTC)
    window = now.replace(second=0, microsecond=0)
    key = "c" * 64
    async with session_factory() as db:
        db.add(
            RateLimitBucket(
                bucket_hash=key,
                window_start=window,
                limit_name="authenticated_default",
                count=1,
                expires_at=now + timedelta(minutes=2),
            )
        )
        await db.commit()

    backend = PostgresRateLimitBackend()
    async with session_factory() as locked:
        await locked.execute(
            select(RateLimitBucket).where(RateLimitBucket.bucket_hash == key).with_for_update()
        )
        task = asyncio.create_task(
            backend.check(
                bucket_hash=key,
                limit_name="authenticated_default",
                window_start=window,
                expires_at=now + timedelta(minutes=2),
                now=now,
            )
        )
        try:

            async def wait_for_db_lock() -> None:
                while True:
                    async with session_factory() as db:
                        waiting = await db.scalar(
                            text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE datname = current_database() "
                                "AND pid <> pg_backend_pid() AND wait_event_type = 'Lock' "
                                "AND query LIKE '%WITH active_override AS MATERIALIZED%'"
                            )
                        )
                    if waiting:
                        return
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_db_lock(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            await locked.rollback()

    result = await asyncio.wait_for(
        backend.check(
            bucket_hash=key,
            limit_name="authenticated_default",
            window_start=window,
            expires_at=now + timedelta(minutes=2),
            now=now,
        ),
        timeout=2,
    )
    assert result.count == 2
    async with session_factory() as db:
        assert (
            await db.scalar(select(RateLimitBucket.count).where(RateLimitBucket.bucket_hash == key))
            == 2
        )


async def test_expired_and_revoked_overrides_cannot_bypass_or_block_counting(
    session_factory: Any,
) -> None:
    import uuid

    from app.middleware.rate_limit import PostgresRateLimitBackend
    from app.models.rate_limit import RateLimitOverride
    from app.models.user import User

    now = datetime.now(UTC)
    key = "d" * 64
    async with session_factory() as db:
        user = User(
            user_id=uuid.uuid4(),
            email="limiter-fixture@example.invalid",
            nickname="한도 fixture",
            password_hash=None,
            status="active",
        )
        db.add(user)
        await db.flush()
        for action, expired, revoked in (
            ("blocked", True, False),
            ("allowed", True, False),
            ("blocked", False, True),
            ("allowed", False, True),
        ):
            db.add(
                RateLimitOverride(
                    bucket_hash=key,
                    limit_name="authenticated_default",
                    identity_kind="user",
                    identity_fingerprint=key,
                    identity_label="fixture",
                    action=action,
                    reason="fixture",
                    created_by_user_id=user.user_id,
                    expires_at=now + timedelta(minutes=-1 if expired else 1),
                    revoked_at=now if revoked else None,
                )
            )
        await db.commit()

    result = await PostgresRateLimitBackend().check(
        bucket_hash=key,
        limit_name="authenticated_default",
        window_start=now.replace(second=0, microsecond=0),
        expires_at=now + timedelta(minutes=2),
        now=now,
        prefer_blocked=True,
    )
    assert result.override is None and result.count == 1


async def test_periodic_cleanup_drains_backlog_in_one_tick_and_preserves_locked_and_live_rows(
    session_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    import app.middleware.rate_limit as module

    now = datetime.now(UTC)
    locked_key = f"{0:064x}"
    live_key = f"{2502:064x}"
    async with session_factory() as db:
        db.add_all(
            [
                RateLimitBucket(
                    bucket_hash=f"{index:064x}",
                    window_start=now - timedelta(minutes=3),
                    limit_name="authenticated_default",
                    count=1,
                    expires_at=now - timedelta(minutes=1),
                )
                for index in range(2502)
            ]
            + [
                RateLimitBucket(
                    bucket_hash=live_key,
                    window_start=now,
                    limit_name="authenticated_default",
                    count=1,
                    expires_at=now + timedelta(minutes=2),
                )
            ]
        )
        await db.commit()

    original_sleep = asyncio.sleep
    original_cleanup = module.cleanup_expired_rate_limit_buckets
    cycle_finished = asyncio.Event()
    second_tick_gate = asyncio.Event()
    delete_counts: list[int] = []
    tick_sleeps = 0
    worker = module.RateLimitBucketCleanup()

    async def controlled_sleep(seconds: float, result: Any = None) -> Any:
        nonlocal tick_sleeps
        # 실제 60초를 기다리지 않고 두 번째 tick 직전에 첫 주기의 종료를 포착한다.
        # DB driver·다른 task·주기 안 yield의 sleep은 원래 구현으로 보낸다.
        if asyncio.current_task() is worker._task and seconds == 60:
            tick_sleeps += 1
            if tick_sleeps == 1:
                return await original_sleep(0, result)
            cycle_finished.set()
            await second_tick_gate.wait()
            return result
        return await original_sleep(seconds, result)

    async def observe_cleanup(**kwargs: Any) -> int:
        removed = await original_cleanup(**kwargs)
        delete_counts.append(removed)
        return removed

    monkeypatch.setattr(module.asyncio, "sleep", controlled_sleep)
    monkeypatch.setattr(module, "cleanup_expired_rate_limit_buckets", observe_cleanup)
    async with session_factory() as locked:
        await locked.execute(
            select(RateLimitBucket)
            .where(RateLimitBucket.bucket_hash == locked_key)
            .with_for_update()
        )
        worker.start()
        try:
            await asyncio.wait_for(cycle_finished.wait(), timeout=10)
            # 각 호출은 실제 PG에서 COMMIT된 별도 transaction이다. 한 주기에
            # 1000행 상한을 유지하며 2501개 unlocked 만료행을 모두 처리해야 한다.
            assert delete_counts == [1000, 1000, 501]
            async with session_factory() as db:
                remaining = set(await db.scalars(select(RateLimitBucket.bucket_hash)))
            assert remaining == {locked_key, live_key}
            assert tick_sleeps == 2
        finally:
            await worker.stop()
            await locked.rollback()
