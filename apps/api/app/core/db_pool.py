"""DB 풀 acquisition 대기: checkout 이후의 SQL 실행 시간과 분리한다."""

from __future__ import annotations

import asyncio
from time import perf_counter

from prometheus_client import Histogram
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.pool import AsyncAdaptedQueuePool, ConnectionPoolEntry

DB_POOL_WAIT_SECONDS = Histogram(
    "pinvi_api_db_pool_wait_seconds",
    "SQLAlchemy pool acquisition time, including connection creation when needed.",
    ("outcome",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


class ObservedAsyncQueuePool(AsyncAdaptedQueuePool):
    """실제 queue acquisition을 측정하므로 성공 checkout 이전 대기·timeout·취소도 포함한다."""

    def _do_get(self) -> ConnectionPoolEntry:
        started = perf_counter()
        outcome = "error"
        try:
            record = super()._do_get()
            outcome = "acquired"
            return record
        except PoolTimeout:
            outcome = "timeout"
            raise
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            DB_POOL_WAIT_SECONDS.labels(outcome=outcome).observe(perf_counter() - started)
