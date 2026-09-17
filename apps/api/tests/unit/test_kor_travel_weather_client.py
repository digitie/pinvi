"""`kor-travel-weather` client 계약 테스트 (httpx.MockTransport, T-360/P1)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.clients.kor_travel_weather import (
    KorTravelWeatherBadRequest,
    KorTravelWeatherClient,
    KorTravelWeatherContractError,
    KorTravelWeatherNotFound,
    KorTravelWeatherUnavailable,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, **kwargs: object) -> KorTravelWeatherClient:
    http = httpx.AsyncClient(
        base_url="http://kor-travel-weather.test",
        transport=httpx.MockTransport(handler),
    )
    params: dict[str, object] = {"max_attempts": 2, "backoff_base_seconds": 0.0}
    params.update(kwargs)
    return KorTravelWeatherClient(http, **params)  # type: ignore[arg-type]


def _envelope(data: object) -> dict[str, object]:
    return {
        "data": data,
        "meta": {"request_id": "r1", "generated_at": "2026-09-17T00:00:00+09:00", "duration_ms": 1},
    }


_LOCATION = {
    "location_id": "airkorea-station-abc",
    "name": "중구",
    "latitude": 37.5,
    "longitude": 126.9,
    "nx": None,
    "ny": None,
    "region_code": None,
    "enabled": True,
    "metadata": {},
}

_WEATHER_VALUE = {
    "value_id": "wv1",
    "location_id": "airkorea-station-abc",
    "provider": "python-kma-api",
    "dataset_key": "kma_short_forecast",
    "weather_domain": "weather",
    "forecast_style": "short",
    "metric_key": "TMP",
    "metric_name": None,
    "source_metric_key": None,
    "source_metric_name": None,
    "value_number": 21.0,
    "value_text": None,
    "unit": "deg_c",
    "severity": None,
    "issued_at": None,
    "valid_at": None,
    "valid_from": None,
    "valid_until": None,
    "observed_at": None,
    "target_at": "2026-09-17T12:00:00+09:00",
    "known_at": "2026-09-17T00:00:00+09:00",
    "normalization_version": "kma-v1",
    "collected_at": "2026-09-17T00:00:00+09:00",
    "source_record_key": "sr1",
}


async def test_resolve_sends_lat_lon_radius_and_decodes() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json=_envelope(
                {
                    "requested": {"latitude": 37.5665, "longitude": 126.978},
                    "location": _LOCATION,
                    "distance_km": 0.27,
                    "measurement_point": None,
                    "source_locations": [_LOCATION],
                    "latest": [_WEATHER_VALUE],
                    "forecast": [],
                    "alerts": [],
                }
            ),
        )

    client = _client(handler)
    result = await client.resolve(lat=37.5665, lon=126.978, radius_km=30)
    assert seen["path"] == "/v1/weather/resolve"
    assert seen["params"] == {"lat": "37.5665", "lon": "126.978", "radius_km": "30"}
    assert result.location.location_id == "airkorea-station-abc"
    assert len(result.source_locations) == 1
    assert result.latest[0].metric_key == "TMP"
    assert result.latest[0].target_at.tzinfo is not None
    await client.aclose()


async def test_resolve_rejects_out_of_range_coordinates_before_request() -> None:
    called = {"value": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["value"] = True
        return httpx.Response(200, json=_envelope({}))

    client = _client(handler)
    with pytest.raises(ValueError):
        await client.resolve(lat=50.0, lon=126.0)
    with pytest.raises(ValueError):
        await client.resolve(lat=37.0, lon=200.0)
    with pytest.raises(ValueError):
        await client.resolve(lat=37.0, lon=126.0, radius_km=501)
    assert called["value"] is False
    await client.aclose()


async def test_markers_sends_repeated_location_id_query() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["ids"] = request.url.params.get_list("location_id")
        return httpx.Response(
            200,
            json=_envelope(
                [{"location_id": "a", "measurement_point": None, "latest": [], "alerts": []}]
            ),
        )

    client = _client(handler)
    result = await client.markers(["a", "b"])
    assert seen["path"] == "/v1/weather/markers"
    assert seen["ids"] == ["a", "b"]
    assert result[0].location_id == "a"
    await client.aclose()


async def test_markers_rejects_empty_and_over_cap_before_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([]))

    client = _client(handler)
    with pytest.raises(ValueError):
        await client.markers([])
    with pytest.raises(ValueError):
        await client.markers([f"loc-{i}" for i in range(501)])
    await client.aclose()


async def test_latest_builds_path_and_decodes_list() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["limit"] = request.url.params.get("limit")
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    client = _client(handler)
    result = await client.latest("loc-1", limit=50)
    assert seen["path"] == "/v1/weather/locations/loc-1/latest"
    assert seen["limit"] == "50"
    assert len(result) == 1
    await client.aclose()


async def test_forecast_requires_aware_datetime() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([]))

    client = _client(handler)
    with pytest.raises(ValueError):
        await client.forecast("loc-1", from_=datetime(2026, 9, 17))  # naive
    await client.aclose()


async def test_forecast_sends_from_to_dataset_and_metric() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    client = _client(handler)
    start = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 18, 0, 0, tzinfo=UTC)
    await client.forecast(
        "loc-1", from_=start, to=end, dataset_key="kma_short_forecast", metric_key="TMP"
    )
    params = seen["params"]
    assert isinstance(params, dict)
    assert params["from"] == start.isoformat()
    assert params["to"] == end.isoformat()
    assert params["dataset_key"] == "kma_short_forecast"
    assert params["metric_key"] == "TMP"
    assert "history" not in params  # False는 생략된다
    await client.aclose()


async def test_404_raises_not_found_with_problem_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "type": "about:blank",
                "title": "찾을 수 없음",
                "status": 404,
                "detail": "location을 찾을 수 없습니다.",
                "code": "HTTP_ERROR",
                "request_id": "r1",
            },
        )

    client = _client(handler)
    with pytest.raises(KorTravelWeatherNotFound) as exc:
        await client.latest("missing")
    assert exc.value.status_code == 404
    assert exc.value.code == "HTTP_ERROR"
    assert exc.value.detail == "location을 찾을 수 없습니다."
    await client.aclose()


async def test_422_raises_bad_request_with_problem_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "type": "about:blank",
                "title": "요청 검증 실패",
                "status": 422,
                "detail": "요청 값이 API 계약에 맞지 않습니다.",
                "code": "VALIDATION_ERROR",
                "request_id": "r1",
                "errors": [{"loc": ["query", "lat"], "msg": "too big", "type": "less_than_equal"}],
            },
        )

    client = _client(handler)
    with pytest.raises(KorTravelWeatherBadRequest) as exc:
        await client.latest("loc-1")
    assert exc.value.status_code == 422
    assert exc.value.code == "VALIDATION_ERROR"
    await client.aclose()


async def test_5xx_retries_then_unavailable() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, json={"code": "UPSTREAM"})

    client = _client(handler, max_attempts=3)
    with pytest.raises(KorTravelWeatherUnavailable):
        await client.latest("loc-1")
    assert attempts["n"] == 3
    await client.aclose()


async def test_transport_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    with pytest.raises(KorTravelWeatherUnavailable):
        await client.latest("loc-1")
    await client.aclose()


async def test_missing_field_raises_contract_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        broken = dict(_WEATHER_VALUE)
        del broken["target_at"]
        return httpx.Response(200, json=_envelope([broken]))

    client = _client(handler)
    with pytest.raises(KorTravelWeatherContractError):
        await client.latest("loc-1")
    await client.aclose()


async def test_unexpected_extra_field_raises_contract_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        broken = dict(_WEATHER_VALUE)
        broken["unexpected_new_field"] = "surprise"
        return httpx.Response(200, json=_envelope([broken]))

    client = _client(handler)
    with pytest.raises(KorTravelWeatherContractError):
        await client.latest("loc-1")
    await client.aclose()


async def test_missing_data_key_raises_contract_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {}})

    client = _client(handler)
    with pytest.raises(KorTravelWeatherContractError):
        await client.latest("loc-1")
    await client.aclose()
