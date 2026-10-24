"""Map 경로 위치 집합 규칙 (ADR-077, `app/services/weather_map_resolver.py`) — DB 없는 부분."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient
from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient
from app.services import weather_map_resolver as mr
from tests import weather_map_fixtures as fx

#: kor-travel-weather `src/kortravelweather/providers/*.py` 중 위치에 `measurement_point`(station_name)를 붙이는
#: provider와 그 location_id 접두어(`location_id=f"<prefix>-{suffix}"`). weather에 측정소 provider가 늘면 이 표와
#: `STATION_LOCATION_PREFIXES`를 함께 고친다(Map 위치에는 측정소 표시가 없어 접두어가 유일한 신호다).
_WEATHER_STATION_PROVIDERS: dict[str, str] = {
    "airkorea.py": "airkorea-",
    "khoa.py": "khoa-",
    "krex.py": "krex-",
    "krforest.py": "krforest-",
    "krforest_dust.py": "krforest-dust-",
}


def test_station_prefixes_cover_every_weather_station_provider() -> None:
    for module, prefix in _WEATHER_STATION_PROVIDERS.items():
        assert mr.is_station(f"{prefix}0001"), module
    # 목록에 군더더기가 없다 — 각 접두어가 어떤 provider를 덮는다.
    for prefix in mr.STATION_LOCATION_PREFIXES:
        assert any(p.startswith(prefix) for p in _WEATHER_STATION_PROVIDERS.values()), prefix


@pytest.mark.parametrize(
    "location_id",
    ["kma-grid-60-127", "openweathermap-seoul", "open_meteo-37.5-126.9", "e2e-seoul"],
)
def test_non_station_locations(location_id: str) -> None:
    assert not mr.is_station(location_id)


def _client(near: list[tuple[str, float]], nearest: dict[str, Any]) -> KorTravelMapWeatherClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/nearest"):
            return httpx.Response(200, json=fx.bundle_body(nearest))
        return httpx.Response(
            200,
            json=fx.list_body(
                [fx.location(loc, distance_m=d) for loc, d in near], with_current=False
            ),
        )

    return KorTravelMapWeatherClient(
        KorTravelMapClient(
            httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
            service_token="svc",
            max_attempts=1,
        )
    )


async def test_krforest_station_is_the_anchor_when_nearest() -> None:
    """산악기상 측정소(krforest-)가 가장 가까우면 대표다 — KMA 격자가 아니라. 다른 측정소는 둘레에서 빠진다."""
    near = [
        ("krforest-mt-0042", 600.0),
        (fx.LOC_KMA, 900.0),
        ("krforest-dust-0007", 1500.0),
        (fx.LOC_AIR, 2500.0),
    ]
    resolved = await mr.nearest_location_set(_client(near, fx.kma_bundle()), lat=37.6, lon=127.0)
    assert resolved is not None
    assert resolved.location_id == "krforest-mt-0042"
    assert resolved.source_location_ids == ("krforest-mt-0042", fx.LOC_KMA)
    assert resolved.distance_km == pytest.approx(0.6)
