"""최외곽 client lifespan이 관측 큐와 rate-limit 청소 task를 소유한다."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.core.config import settings
from app.db import session as db_session
from app.middleware.api_call_logging import close_api_call_logs
from app.middleware.rate_limit import RateLimitBucketCleanup, effective_rate_limit_backend_name


@asynccontextmanager
async def outbound_resilience_lifespan() -> AsyncIterator[None]:
    # main의 Map client lifespan은 다른 client/업무 worker보다 먼저 열리고 나중에 닫힌다.
    # startup runtime/계약 guard를 통과한 뒤에만 이 context에 들어온다.
    factory = db_session.async_session_factory
    cleanup = RateLimitBucketCleanup()
    if settings.pinvi_rate_limit_enabled and effective_rate_limit_backend_name() == "postgres":
        cleanup.start()
    try:
        yield
    finally:
        try:
            await cleanup.stop()
        finally:
            await close_api_call_logs(factory)
