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


def _client(handler: Handler, *, token: str = "svc") -> tuple[KorTravelMapWeatherClient, list[httpx.Request]]:
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
    invalid, _ = _client(lambda r: httpx.Response(422, json=fx.problem_body(422, "VALIDATION_ERROR")))
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
    data = await client.list_locations(bbox=(126.0, 37.0, 127.0, 38.0), include_current=True, limit=50)
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
