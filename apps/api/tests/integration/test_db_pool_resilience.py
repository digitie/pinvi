"""소유 PG에서 대기·만료·취소가 실제 acquisition metric에 반영된다."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db_pool import DB_POOL_WAIT_SECONDS, ObservedAsyncQueuePool


def sample(outcome: str, suffix: str) -> float:
    for metric in DB_POOL_WAIT_SECONDS.collect():
        for item in metric.samples:
            if item.name.endswith(suffix) and item.labels == {"outcome": outcome}:
                return item.value
    return 0.0


async def test_owned_pool_observes_wait_timeout_and_cancellation(_database_url) -> None:
    before_wait = sample("acquired", "_sum")
    before_timeout = sample("timeout", "_count")
    before_cancel = sample("cancelled", "_count")
    engine = create_async_engine(
        _database_url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.08,
        poolclass=ObservedAsyncQueuePool,
    )

    async def query() -> int:
        async with engine.connect() as conn:
            return await conn.scalar(text("SELECT 1"))

    try:
        async with engine.connect():
            waiting = asyncio.create_task(query())
            await asyncio.sleep(0.03)
            assert not waiting.done()
        assert await waiting == 1
        assert sample("acquired", "_sum") - before_wait >= 0.025

        async with engine.connect():
            with pytest.raises(PoolTimeout):
                await query()
        assert sample("timeout", "_count") == before_timeout + 1

        async with engine.connect():
            cancelled = asyncio.create_task(query())
            await asyncio.sleep(0.01)
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled
        assert sample("cancelled", "_count") == before_cancel + 1
        assert await query() == 1
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()
