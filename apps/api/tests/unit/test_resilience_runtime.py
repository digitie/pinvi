"""공용 background task는 guard 뒤 runtime context에서만 생기고 실패 시에도 닫힌다."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.middleware import resilience_runtime as runtime


@pytest.mark.parametrize(
    "backend,enabled,starts",
    [
        ("postgres", True, True),
        ("postgres", False, False),
        ("memory", True, False),
    ],
)
async def test_runtime_owns_cleanup_and_drains_logs_on_failure(
    monkeypatch,
    backend,
    enabled,
    starts,
) -> None:
    events = []

    class Cleanup:
        def start(self):
            events.append("start")

        async def stop(self):
            events.append("stop")

    async def drain(_factory):
        events.append("drain")

    monkeypatch.setattr(runtime, "RateLimitBucketCleanup", Cleanup)
    monkeypatch.setattr(runtime, "effective_rate_limit_backend_name", lambda: backend)
    monkeypatch.setattr(settings, "pinvi_rate_limit_enabled", enabled)
    monkeypatch.setattr(runtime, "close_api_call_logs", drain)
    with pytest.raises(ValueError, match="fixture"):
        async with runtime.outbound_resilience_lifespan():
            events.append("body")
            raise ValueError("fixture")
    assert events == (["start"] if starts else []) + ["body", "stop", "drain"]


async def test_runtime_log_drain_survives_cleanup_stop_failure(monkeypatch) -> None:
    class Cleanup:
        def start(self):
            pass

        async def stop(self):
            raise RuntimeError("stop fixture")

    close = AsyncMock()
    monkeypatch.setattr(runtime, "RateLimitBucketCleanup", Cleanup)
    monkeypatch.setattr(runtime, "close_api_call_logs", close)
    with pytest.raises(RuntimeError, match="stop fixture"):
        async with runtime.outbound_resilience_lifespan():
            pass
    close.assert_awaited_once()
