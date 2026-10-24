"""지도 weather marker — Map 경로 (ADR-077, `build_weather_markers_in_bounds_via_map`)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient, KorTravelMapError
from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient
from app.schemas.feature import BBox
from app.services.weather_map_markers import build_weather_markers_in_bounds_via_map
from tests import weather_map_fixtures as fx

pytestmark = pytest.mark.asyncio

_SEOUL = BBox(lng_min=126.9, lat_min=37.4, lng_max=127.1, lat_max=37.6)


def _client(handler: Any) -> tuple[KorTravelMapWeatherClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        response: httpx.Response = handler(request)
        return response

    map_client = KorTravelMapClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(record)),
        service_token="svc",
        max_attempts=1,
    )
    return KorTravelMapWeatherClient(map_client), seen


async def test_markers_use_bbox_with_include_current() -> None:
    body = fx.list_body(
        [
            fx.location(
                observations=[
                    fx.observation("T1H", 12.5, unit="deg_c"),
                    fx.observation("RN1", 1.5, unit="mm"),
                ]
            ),
            # 관측 부분을 못 읽은 위치 — 온도가 없으니 빠진다.
            fx.location(fx.LOC_AIR, include_observations=True),
            # 좌표 없는 위치는 지도에 놓을 수 없다.
            fx.location(fx.LOC_EXT, lon=None, lat=None, observations=[fx.observation("T1H", 3)]),
        ]
    )
    client, seen = _client(lambda r: httpx.Response(200, json=body))
    markers = await build_weather_markers_in_bounds_via_map(
        bbox=_SEOUL, zoom=10, limit=100, map_client=client
    )
    assert [(m.location_id, m.temperature_c, m.condition, m.provider) for m in markers] == [
        (fx.LOC_KMA, 12.5, "rainy", "python-kma-api")
    ]
    [request] = seen
    assert request.url.path == "/v1/service/weather/locations"
    params = request.url.params
    assert params["include_current"] == "true"
    assert (params["min_lon"], params["min_lat"], params["max_lon"], params["max_lat"]) == (
        "126.9",
        "37.4",
        "127.1",
        "37.6",
    )
    assert params["limit"] == "100"


async def test_below_min_zoom_or_outside_korea_makes_no_call() -> None:
    client, seen = _client(lambda r: httpx.Response(500))
    assert (
        await build_weather_markers_in_bounds_via_map(
            bbox=_SEOUL, zoom=7, limit=100, map_client=client
        )
        == []
    )
    # 서비스 범위(위도 39 이하) 밖 — BBox 검증은 통과하지만 국내 범위와 교차가 없다.
    north = BBox(lng_min=126.0, lat_min=40.0, lng_max=127.0, lat_max=41.0)
    assert (
        await build_weather_markers_in_bounds_via_map(
            bbox=north, zoom=10, limit=100, map_client=client
        )
        == []
    )
    assert seen == []


async def test_map_failure_propagates_for_the_route_to_503() -> None:
    client, _ = _client(
        lambda r: httpx.Response(503, json=fx.problem_body(503, "WEATHER_STATE_NOT_LOADED"))
    )
    with pytest.raises(KorTravelMapError):
        await build_weather_markers_in_bounds_via_map(
            bbox=_SEOUL, zoom=10, limit=100, map_client=client
        )
