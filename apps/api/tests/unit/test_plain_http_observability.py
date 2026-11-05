"""서비스 실제 factory의 실패·취소·중복·관측 DB 격리를 검증한다."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.clients.kor_travel_map_cache_target import CacheTargetNetworkError
from app.clients.kor_travel_map_feature_reference_reconciliation import (
    FeatureReferenceReconciliationUnavailable,
)
from app.clients.telegram import TelegramError
from app.middleware.api_call_logging import close_api_call_logs
from tests.plain_http_fixtures import (
    CASES,
    FIXTURE_BOT,
    RecordingFactory,
    Scenario,
    exercise,
    install_transport,
)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize(
    "mode,error", [("connect", "ConnectError"), ("timeout", "ReadTimeout"), ("body", "ReadError")]
)
async def test_factory_failure_is_observed_and_redacted(monkeypatch, tmp_path, case, mode, error):
    factory = RecordingFactory()
    scenario = Scenario(case, mode)
    install_transport(monkeypatch, scenario, factory)
    try:
        try:
            await exercise(monkeypatch, tmp_path, case)
        except (
            httpx.HTTPError,
            TelegramError,
            CacheTargetNetworkError,
            FeatureReferenceReconciliationUnavailable,
        ):
            pass
    finally:
        await close_api_call_logs(factory)
    assert scenario.requests
    assert len(factory.rows) == len(scenario.requests), "transport failure has no response hook"
    assert all(row["error_class"] == error for row in factory.rows)
    assert all(row["status_code"] is None for row in factory.rows)
    assert all(row["provider"] != "unknown" for row in factory.rows)
    assert "fixture-private" not in repr(factory.rows)
    assert FIXTURE_BOT not in repr(factory.rows)


@pytest.mark.parametrize("case", CASES)
async def test_factory_cancellation_is_observed_and_still_propagates(monkeypatch, tmp_path, case):
    factory = RecordingFactory()
    scenario = Scenario(case, "cancel")
    install_transport(monkeypatch, scenario, factory)
    pending = asyncio.create_task(exercise(monkeypatch, tmp_path, case))
    try:
        await asyncio.wait_for(scenario.entered.wait(), 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, 1)
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await close_api_call_logs(factory)
    assert len(factory.rows) == len(scenario.requests)
    assert factory.rows
    assert all(row["error_class"] == "CancelledError" for row in factory.rows)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("db_failed", [False, True])
async def test_factory_response_is_not_duplicated_or_blocked_by_log_database(
    monkeypatch,
    tmp_path,
    case,
    db_failed,
):
    factory = RecordingFactory()
    factory.fail = db_failed
    scenario = Scenario(case, "success")
    install_transport(monkeypatch, scenario, factory)
    try:
        result = await asyncio.wait_for(exercise(monkeypatch, tmp_path, case), 1)
        if case == "oauth":
            assert result.provider_user_id == "fixture-user"
        elif case == "dagster":
            assert result.status == "degraded"
        elif case.startswith("cache") or case == "reconciliation":
            assert result.status_code == 200
    finally:
        await close_api_call_logs(factory)
    assert scenario.requests
    assert len(factory.rows) == (0 if db_failed else len(scenario.requests))
    if not db_failed:
        assert all(row["status_code"] in {200, 503} for row in factory.rows)
        assert "fixture-private" not in repr(factory.rows)
        assert FIXTURE_BOT not in repr(factory.rows)
