"""T-367 kor-travel-weather 보존 지평 가드 helper 테스트 (네트워크 없이)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from dagster import Backoff, Failure, Jitter, build_asset_context

from pinvi.etl.assets.pinvi_weather_retention_horizon import (
    DEFAULT_MIN_RETENTION_DAYS,
    DEFAULT_REFERENCE_LOCATION_ID,
    RESOLVE_TIMEOUT_SECONDS,
    WeatherRetentionGuardError,
    compute_oldest_known_at,
    evaluate_retention_horizon,
    fetch_oldest_surviving_values,
    fetch_reference_values,
    pinvi_weather_retention_horizon_guard,
    resolve_reference_location,
)
from pinvi.etl.resources import KorTravelWeatherResource


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
    oldest = datetime(2026, 9, 17, tzinfo=UTC)  # 1일 전 — 보존이 기본 2일로 되돌아간 시나리오

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


def test_default_min_retention_days_matches_owner_decision() -> None:
    # ADR-073(2026-10-13): kor-travel-weather 보존 16일 → 7일, 가드 임계 15일 → 6일
    # (보존 7일에 하루 여유 — KST 05:00 측정의 거짓 실패 방지).
    assert DEFAULT_MIN_RETENTION_DAYS == 6


def test_evaluate_retention_horizon_passes_at_exact_threshold() -> None:
    now = datetime(2026, 10, 13, tzinfo=UTC)
    oldest = datetime(2026, 10, 7, tzinfo=UTC)  # 정확히 6일 전

    result = evaluate_retention_horizon(location_id="e2e-seoul", oldest_known_at=oldest, now=now)

    assert result.passed is True
    assert result.effective_retention_days == pytest.approx(6.0)


def test_evaluate_retention_horizon_fails_just_below_threshold() -> None:
    now = datetime(2026, 10, 13, tzinfo=UTC)
    oldest = datetime(2026, 10, 7, 1, tzinfo=UTC)  # 5일 23시간 전

    result = evaluate_retention_horizon(location_id="e2e-seoul", oldest_known_at=oldest, now=now)

    assert result.passed is False
    assert result.min_retention_days == 6


def test_evaluate_retention_horizon_honors_custom_threshold() -> None:
    now = datetime(2026, 9, 18, tzinfo=UTC)
    oldest = datetime(2026, 9, 10, tzinfo=UTC)  # 8일 전 — 기본 임계 6일은 통과

    result = evaluate_retention_horizon(
        location_id="e2e-seoul", oldest_known_at=oldest, now=now, min_retention_days=10
    )

    assert result.passed is False
    assert result.min_retention_days == 10


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


# --- 2026-11-24: 수집 실패 감사 §1.3 — `/resolve` 10초 timeout으로 14회 중 13회 실패 ---

SEOUL = DEFAULT_REFERENCE_LOCATION_ID
OLD_ROW = {"known_at": "2026-11-16T15:08:34Z", "collected_at": "2026-11-16T15:08:34Z"}


def _client(handler) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(
        base_url="http://weather.invalid", transport=httpx.MockTransport(handler)
    )


@pytest.mark.asyncio
async def test_fixed_reference_location_skips_resolve() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"data": [OLD_ROW], "meta": {}})

    async with _client(handler) as client:
        location_id, values = await fetch_reference_values(
            client, location_id=SEOUL, lat=37.5665, lon=126.978, now=datetime.now(UTC)
        )

    assert location_id == SEOUL
    assert values == [OLD_ROW]
    assert paths == [f"/v1/weather/locations/{SEOUL}/forecast"]


@pytest.mark.parametrize("missing", ["404", "empty"])
@pytest.mark.asyncio
async def test_missing_reference_location_falls_back_to_resolve_with_long_timeout(
    missing: str,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == f"/v1/weather/locations/{SEOUL}/forecast":
            if missing == "404":
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json={"data": [], "meta": {}})
        if request.url.path == "/v1/weather/resolve":
            return httpx.Response(200, json={"data": {"location": {"location_id": "moved"}}})
        assert request.url.path == "/v1/weather/locations/moved/forecast"
        return httpx.Response(200, json={"data": [OLD_ROW], "meta": {}})

    async with _client(handler) as client:
        location_id, values = await fetch_reference_values(
            client, location_id=SEOUL, lat=37.5665, lon=126.978, now=datetime.now(UTC)
        )

    assert location_id == "moved" and values == [OLD_ROW]
    resolve = next(r for r in seen if r.url.path == "/v1/weather/resolve")
    assert resolve.extensions["timeout"]["read"] == RESOLVE_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_empty_reference_location_id_always_resolves() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/v1/weather/resolve":
            return httpx.Response(200, json={"data": {"location": {"location_id": "e2e"}}})
        return httpx.Response(200, json={"data": [OLD_ROW], "meta": {}})

    async with _client(handler) as client:
        location_id, _ = await fetch_reference_values(
            client, location_id="", lat=37.5665, lon=126.978, now=datetime.now(UTC)
        )

    assert location_id == "e2e"
    assert paths == ["/v1/weather/resolve", "/v1/weather/locations/e2e/forecast"]


@pytest.mark.asyncio
async def test_server_error_stays_retryable_but_client_error_does_not() -> None:
    # 5xx·timeout은 RetryPolicy가 다시 부른다. 4xx·계약 위반은 바로 실패한다.
    async with _client(lambda request: httpx.Response(503, json={})) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_oldest_surviving_values(client, SEOUL, now=datetime.now(UTC))
    async with _client(lambda request: httpx.Response(422, json={})) as client:
        with pytest.raises(WeatherRetentionGuardError) as error:
            await fetch_oldest_surviving_values(client, SEOUL, now=datetime.now(UTC))
    assert error.value.allow_retries is False


def test_threshold_breach_is_not_retried() -> None:
    error = WeatherRetentionGuardError("실효 보존 1.0일 < 임계 6일")
    assert isinstance(error, Failure)
    assert error.allow_retries is False


def test_retry_policy_backs_off_with_jitter() -> None:
    policy = pinvi_weather_retention_horizon_guard.op.retry_policy
    assert policy is not None
    assert policy.max_retries == 3
    assert policy.backoff == Backoff.EXPONENTIAL
    assert policy.jitter == Jitter.PLUS_MINUS


def test_weather_resource_timeout_covers_measured_forecast_latency() -> None:
    # n150 실측 forecast 2.4~6.8초 — 10초는 여유가 없었다.
    assert KorTravelWeatherResource(base_url="http://weather.invalid").timeout >= 30


@pytest.mark.asyncio
async def test_guard_asset_reads_fixed_location_without_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"data": [OLD_ROW], "meta": {}})

    monkeypatch.setattr(KorTravelWeatherResource, "create_client", lambda self: _client(handler))
    resource = KorTravelWeatherResource(base_url="http://weather.invalid")
    with build_asset_context(asset_config={}) as context:
        result = await pinvi_weather_retention_horizon_guard(context, resource)

    assert paths == [f"/v1/weather/locations/{SEOUL}/forecast"]
    assert result["location_id"] == SEOUL
    assert result["passed"] is True
