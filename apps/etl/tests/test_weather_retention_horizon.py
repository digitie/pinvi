"""T-367 kor-travel-weather 보존 지평 가드 helper 테스트 (네트워크 없이)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from pinvi.etl.assets.pinvi_weather_retention_horizon import (
    DEFAULT_MIN_RETENTION_DAYS,
    WeatherRetentionGuardError,
    compute_oldest_known_at,
    evaluate_retention_horizon,
    fetch_oldest_surviving_values,
    resolve_reference_location,
)


def test_compute_oldest_known_at_prefers_known_at_over_collected_at() -> None:
    values = [
        {"known_at": "2026-09-01T00:00:00Z", "collected_at": "2026-09-05T00:00:00Z"},
        {"known_at": "2026-09-03T00:00:00Z", "collected_at": "2026-09-04T00:00:00Z"},
    ]

    oldest = compute_oldest_known_at(values)

    assert oldest == datetime(2026, 9, 1, tzinfo=UTC)


def test_compute_oldest_known_at_falls_back_to_collected_at() -> None:
    values = [{"known_at": None, "collected_at": "2026-09-02T00:00:00Z"}]

    oldest = compute_oldest_known_at(values)

    assert oldest == datetime(2026, 9, 2, tzinfo=UTC)


def test_compute_oldest_known_at_empty_input_returns_none() -> None:
    assert compute_oldest_known_at([]) is None


def test_evaluate_retention_horizon_passes_when_above_threshold() -> None:
    now = datetime(2026, 9, 30, tzinfo=UTC)
    oldest = datetime(2026, 9, 1, tzinfo=UTC)  # 29일 전

    result = evaluate_retention_horizon(location_id="e2e-seoul", oldest_known_at=oldest, now=now)

    assert result.passed is True
    assert result.effective_retention_days == pytest.approx(29.0)
    assert result.min_retention_days == DEFAULT_MIN_RETENTION_DAYS


def test_evaluate_retention_horizon_fails_when_below_threshold() -> None:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    oldest = datetime(2026, 9, 17, tzinfo=UTC)  # 1일 전 — 현재 실제 보존 2일 시나리오

    result = evaluate_retention_horizon(location_id="e2e-seoul", oldest_known_at=oldest, now=now)

    assert result.passed is False
    assert result.effective_retention_days == pytest.approx(1.0)


def test_evaluate_retention_horizon_fails_when_no_data_at_all() -> None:
    result = evaluate_retention_horizon(
        location_id="e2e-seoul",
        oldest_known_at=None,
        now=datetime(2026, 9, 18, tzinfo=UTC),
    )

    assert result.passed is False
    assert result.effective_retention_days == 0.0
    assert result.oldest_known_at is None


def test_evaluate_retention_horizon_honors_custom_threshold() -> None:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    oldest = datetime(2026, 9, 10, tzinfo=UTC)  # 8일 전

    result = evaluate_retention_horizon(
        location_id="e2e-seoul", oldest_known_at=oldest, now=now, min_retention_days=7
    )

    assert result.passed is True


@pytest.mark.asyncio
async def test_resolve_reference_location_extracts_location_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/weather/resolve"
        return httpx.Response(
            200, json={"data": {"location": {"location_id": "e2e-seoul"}}, "meta": {}}
        )

    async with httpx.AsyncClient(
        base_url="http://weather.invalid", transport=httpx.MockTransport(handler)
    ) as client:
        location_id = await resolve_reference_location(client, lat=37.5665, lon=126.9780)

    assert location_id == "e2e-seoul"


@pytest.mark.asyncio
async def test_resolve_reference_location_raises_on_missing_location_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"location": {}}, "meta": {}})

    async with httpx.AsyncClient(
        base_url="http://weather.invalid", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(WeatherRetentionGuardError):
            await resolve_reference_location(client, lat=37.5665, lon=126.9780)


@pytest.mark.asyncio
async def test_fetch_oldest_surviving_values_omits_from_and_passes_limit() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/weather/locations/e2e-seoul/forecast"
        captured.update(dict(request.url.params))
        assert "from" not in request.url.params
        return httpx.Response(
            200,
            json={
                "data": [
                    {"known_at": "2026-09-16T00:00:00Z", "collected_at": "2026-09-16T00:00:00Z"}
                ],
                "meta": {},
            },
        )

    async with httpx.AsyncClient(
        base_url="http://weather.invalid", transport=httpx.MockTransport(handler)
    ) as client:
        values = await fetch_oldest_surviving_values(
            client, "e2e-seoul", now=datetime(2026, 9, 18, tzinfo=UTC), limit=50
        )

    assert captured["limit"] == "50"
    assert captured["history"] == "true"
    assert len(values) == 1
    assert values[0]["known_at"] == "2026-09-16T00:00:00Z"
