"""`KorTravelMapWeatherClient` — 오류 매핑·재시도 없음·요청 구성 (ADR-077)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapClient,
    KorTravelMapContractError,
    KorTravelMapFeatureNotFound,
)
from app.clients.kor_travel_map_weather import (
    KorTravelMapWeatherClient,
    KorTravelMapWeatherCursorExpired,
    KorTravelMapWeatherUnavailable,
)
from tests import weather_map_fixtures as fx

pytestmark = pytest.mark.asyncio

Handler = Callable[[httpx.Request], httpx.Response]


def _client(
    handler: Handler, *, token: str = "svc"
) -> tuple[KorTravelMapWeatherClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    map_client = KorTravelMapClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(record)),
        service_token=token,
        max_attempts=3,
        backoff_base_seconds=0.0,
    )
    return KorTravelMapWeatherClient(map_client), seen


async def test_no_service_token_never_calls_map() -> None:
    client, seen = _client(lambda r: httpx.Response(200, json=fx.batch_body([])), token="")
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await client.batch(location_ids=[fx.LOC_KMA])
    assert info.value.code == "UPSTREAM_AUTH"
    assert seen == []


async def test_503_maps_problem_code_without_retry() -> None:
    client, seen = _client(
        lambda r: httpx.Response(503, json=fx.problem_body(503, "WEATHER_STATE_NOT_LOADED"))
    )
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await client.nearest(lon=126.9, lat=37.5)
    assert info.value.code == "WEATHER_STATE_NOT_LOADED"
    assert len(seen) == 1  # 재시도 없음


async def test_timeout_is_unavailable_without_retry() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    client, seen = _client(boom)
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await client.location(fx.FID_KMA)
    assert info.value.code is None
    assert len(seen) == 1


@pytest.mark.parametrize("status_code", [401, 403])
async def test_auth_rejection_is_upstream_auth(status_code: int) -> None:
    client, _seen = _client(lambda r: httpx.Response(status_code, json={"code": "UNAUTHORIZED"}))
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await client.list_locations(bbox=(126.0, 37.0, 127.0, 38.0))
    assert info.value.code == "UPSTREAM_AUTH"


async def test_not_found_code_is_feature_not_found_but_route_404_is_unavailable() -> None:
    client, _ = _client(lambda r: httpx.Response(404, json=fx.problem_body(404, "NOT_FOUND")))
    with pytest.raises(KorTravelMapFeatureNotFound):
        await client.nearest(lon=126.9, lat=37.5, radius_m=20_000.0)
    old_map, _ = _client(lambda r: httpx.Response(404, json={"detail": "Not Found"}))
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await old_map.nearest(lon=126.9, lat=37.5)
    assert info.value.code == "UPSTREAM_REJECTED"


async def test_409_is_cursor_expired_and_422_is_bad_request() -> None:
    expired, _ = _client(
        lambda r: httpx.Response(409, json=fx.problem_body(409, "WEATHER_STATE_GENERATION_EXPIRED"))
    )
    with pytest.raises(KorTravelMapWeatherCursorExpired):
        await expired.list_locations(cursor="c")
    invalid, _ = _client(
        lambda r: httpx.Response(422, json=fx.problem_body(422, "VALIDATION_ERROR"))
    )
    with pytest.raises(KorTravelMapBadRequest):
        await invalid.batch(location_ids=[fx.LOC_KMA])


async def test_non_json_success_is_contract_error() -> None:
    client, _ = _client(lambda r: httpx.Response(200, content=b"<html>"))
    with pytest.raises(KorTravelMapContractError):
        await client.batch(location_ids=[fx.LOC_KMA])


async def test_batch_sends_json_body_with_service_token() -> None:
    client, seen = _client(lambda r: httpx.Response(200, json=fx.batch_body([fx.kma_bundle()])))
    now = datetime.now(UTC)
    data = await client.batch(
        location_ids=[fx.LOC_KMA, fx.LOC_AIR],
        sections=("current", "forecasts"),
        forecast_from=now,
        forecast_to=now + timedelta(days=1),
    )
    assert data["items"][0]["location"]["location_id"] == fx.LOC_KMA
    [request] = seen
    assert request.method == "POST"
    assert request.url.path == "/v1/service/weather/locations/batch"
    assert request.headers["X-Kor-Travel-Map-Service-Token"] == "svc"
    body = json.loads(request.content)
    assert body["location_ids"] == [fx.LOC_KMA, fx.LOC_AIR]
    assert body["sections"] == ["current", "forecasts"]
    assert body["forecast_from"] == now.isoformat()
    assert "feature_ids" not in body


async def test_batch_rejects_more_than_50_and_duplicates_before_calling() -> None:
    client, seen = _client(lambda r: httpx.Response(200, json=fx.batch_body([])))
    with pytest.raises(ValueError):
        await client.batch(location_ids=[f"loc-{i}" for i in range(51)])
    with pytest.raises(ValueError):
        await client.batch(location_ids=["a", "a"])
    with pytest.raises(ValueError):
        await client.batch()
    assert seen == []


async def test_naive_datetime_is_rejected() -> None:
    client, seen = _client(lambda r: httpx.Response(200, json=fx.bundle_body(fx.kma_bundle())))
    with pytest.raises(ValueError):
        await client.location(fx.FID_KMA, from_=datetime(2026, 10, 24, 9, 0))
    assert seen == []


async def test_list_query_and_repeated_section_params() -> None:
    client, seen = _client(lambda r: httpx.Response(200, json=fx.list_body([fx.location()])))
    data = await client.list_locations(
        bbox=(126.0, 37.0, 127.0, 38.0), include_current=True, limit=50
    )
    assert data["next_cursor"] is None
    params = seen[0].url.params
    assert params["include_current"] == "true"
    assert (params["min_lon"], params["max_lat"], params["limit"]) == ("126.0", "38.0", "50")
    with pytest.raises(ValueError):
        await client.list_locations(bbox=(126.0, 37.0, 127.0, 38.0), near=(126.0, 37.0, 10.0))

    client2, seen2 = _client(lambda r: httpx.Response(200, json=fx.bundle_body(fx.kma_bundle())))
    await client2.nearest(
        lon=126.9, lat=37.5, sections=("current", "forecasts"), forecast_styles=("short",)
    )
    assert seen2[0].url.params.get_list("sections") == ["current", "forecasts"]
    assert seen2[0].url.params.get_list("forecast_styles") == ["short"]
    with pytest.raises(ValueError):
        await client2.nearest(lon=126.9, lat=37.5, radius_m=200_000.0)


# ── 회로차단·timeout (ADR-077 리뷰 반영) ─────────────────────────────────────────────


def _clocked(
    handler: Handler,
) -> tuple[KorTravelMapWeatherClient, list[httpx.Request], list[float]]:
    now = [1000.0]
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    map_client = KorTravelMapClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(record)),
        service_token="svc",
        max_attempts=1,
    )
    client = KorTravelMapWeatherClient(
        map_client, timeout_seconds=2.0, connect_timeout_seconds=0.5, clock=lambda: now[0]
    )
    return client, seen, now


async def test_circuit_opens_after_three_failures_and_fails_fast() -> None:
    client, seen, now = _clocked(
        lambda r: httpx.Response(503, json=fx.problem_body(503, "WEATHER_STATE_UNAVAILABLE"))
    )
    for _ in range(3):
        with pytest.raises(KorTravelMapWeatherUnavailable):
            await client.nearest(lon=126.9, lat=37.5)
    assert len(seen) == 3
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await client.nearest(lon=126.9, lat=37.5)
    assert info.value.code == "CIRCUIT_OPEN"
    assert len(seen) == 3  # 열린 동안 부르지 않는다

    # 같은 Map client를 감싼 새 래퍼(요청마다 만든다)도 같은 회로를 본다.
    other = KorTravelMapWeatherClient(client._map, clock=lambda: now[0])
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await other.batch(location_ids=[fx.LOC_KMA])
    assert info.value.code == "CIRCUIT_OPEN"

    # open 시간이 지나면 시험 호출 하나 — 실패하면 다시 열린다.
    now[0] += 31.0
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await client.nearest(lon=126.9, lat=37.5)
    assert info.value.code == "WEATHER_STATE_UNAVAILABLE"
    assert len(seen) == 4
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await client.nearest(lon=126.9, lat=37.5)
    assert info.value.code == "CIRCUIT_OPEN"


async def test_circuit_closes_after_a_successful_trial() -> None:
    responses = [httpx.Response(503, json={"code": "X"})] * 3 + [
        httpx.Response(200, json=fx.bundle_body(fx.kma_bundle()))
    ] * 2
    client, seen, now = _clocked(lambda r: responses[len(seen) - 1])
    for _ in range(3):
        with pytest.raises(KorTravelMapWeatherUnavailable):
            await client.nearest(lon=126.9, lat=37.5)
    now[0] += 31.0
    await client.nearest(lon=126.9, lat=37.5)
    await client.nearest(lon=126.9, lat=37.5)
    assert len(seen) == 5


async def test_not_loaded_and_4xx_do_not_open_the_circuit() -> None:
    client, seen, _ = _clocked(
        lambda r: httpx.Response(503, json=fx.problem_body(503, "WEATHER_STATE_NOT_LOADED"))
    )
    for _ in range(5):
        with pytest.raises(KorTravelMapWeatherUnavailable) as info:
            await client.nearest(lon=126.9, lat=37.5)
        assert info.value.code == "WEATHER_STATE_NOT_LOADED"
    assert len(seen) == 5
    client_404, seen_404, _ = _clocked(
        lambda r: httpx.Response(404, json=fx.problem_body(404, "NOT_FOUND"))
    )
    for _ in range(5):
        with pytest.raises(KorTravelMapFeatureNotFound):
            await client_404.nearest(lon=126.9, lat=37.5)
    assert len(seen_404) == 5


async def test_per_call_timeout_is_short() -> None:
    client, seen, _ = _clocked(lambda r: httpx.Response(200, json=fx.bundle_body(fx.kma_bundle())))
    await client.nearest(lon=126.9, lat=37.5)
    timeout = seen[0].extensions["timeout"]
    assert timeout == {"connect": 0.5, "read": 2.0, "write": 2.0, "pool": 2.0}


def test_settings_reject_weather_flag_without_service_token() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            pinvi_environment="test",
            pinvi_kor_travel_map_weather_enabled=True,
            pinvi_kor_travel_map_service_token=" ",
        )
    ok = Settings(  # type: ignore[call-arg]
        _env_file=None,
        pinvi_environment="test",
        pinvi_kor_travel_map_weather_enabled=True,
        pinvi_kor_travel_map_service_token="svc-token",
    )
    assert ok.pinvi_kor_travel_map_weather_enabled is True


def test_breaker_ignores_results_of_calls_started_before_a_state_change() -> None:
    """열리기 전에 출발한 호출의 늦은 실패는 열린 시간을 늘리지 않고, 늦은 성공은 half-open 시험보다 먼저 닫지 않는다."""
    from app.clients.kor_travel_map_weather import _CircuitBreaker

    now = [0.0]
    breaker = _CircuitBreaker(failure_threshold=3, open_seconds=30.0, clock=lambda: now[0])
    in_flight = [breaker.acquire() for _ in range(5)]  # 모두 닫힌 회로에서 출발
    for trial, generation in in_flight[:3]:
        breaker.record_failure(trial=trial, generation=generation)
    assert breaker.is_open

    # 열린 뒤 25초에 옛 호출이 실패해도 열린 시각은 0초 그대로 — 30초에 시험 호출이 허가된다.
    now[0] = 25.0
    trial, generation = in_flight[3]
    breaker.record_failure(trial=trial, generation=generation)
    now[0] = 30.5
    trial_call = breaker.acquire()
    assert trial_call[0] is True

    # 시험 호출이 진행 중일 때 옛 호출의 성공은 회로를 닫지 않는다.
    trial, generation = in_flight[4]
    breaker.record_success(trial=trial, generation=generation)
    assert breaker.is_open
    with pytest.raises(KorTravelMapWeatherUnavailable):
        breaker.acquire()  # 시험 자리는 아직 차 있다

    # 시험 호출 자신의 성공은 닫는다.
    breaker.record_success(trial=trial_call[0], generation=trial_call[1])
    assert not breaker.is_open
    assert breaker.acquire()[0] is False
