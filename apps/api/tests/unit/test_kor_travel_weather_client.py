"""`kor-travel-weather` client 계약 테스트 (httpx.MockTransport, T-360/P1)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_weather import (
    KorTravelWeatherBadRequest,
    KorTravelWeatherClient,
    KorTravelWeatherContractError,
    KorTravelWeatherNotFound,
    KorTravelWeatherUnavailable,
    create_kor_travel_weather_client,
    kor_travel_weather_timeout,
)
from app.core.config import Settings

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


async def test_nearby_sends_lat_lon_radius_limit_and_decodes() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json=_envelope(
                [
                    {
                        **_LOCATION,
                        "distance_km": 1.2,
                        "measurement_point": None,
                        "latest": [_WEATHER_VALUE],
                        "forecast": [],
                        "alerts": [],
                    }
                ]
            ),
        )

    client = _client(handler)
    result = await client.nearby(lat=37.5665, lon=126.978, radius_km=10, limit=30)
    assert seen["path"] == "/v1/weather/nearby"
    assert seen["params"] == {"lat": "37.5665", "lon": "126.978", "radius_km": "10", "limit": "30"}
    assert result[0].location_id == "airkorea-station-abc"
    assert result[0].distance_km == 1.2
    assert result[0].latest[0].metric_key == "TMP"
    await client.aclose()


async def test_nearby_rejects_out_of_range_params_before_request() -> None:
    called = {"value": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["value"] = True
        return httpx.Response(200, json=_envelope([]))

    client = _client(handler)
    with pytest.raises(ValueError):
        await client.nearby(lat=50.0, lon=126.0)
    with pytest.raises(ValueError):
        await client.nearby(lat=37.0, lon=126.0, radius_km=501)
    with pytest.raises(ValueError):
        await client.nearby(lat=37.0, lon=126.0, limit=101)
    with pytest.raises(ValueError):
        await client.nearby(lat=37.0, lon=126.0, limit=0)
    assert called["value"] is False
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


# ── ADR-074 결정 4: connect 분리 + 회로차단 (`kor-travel-weather.md` §8.3 "대응") ──────────
#
# 수용 전제는 **SYN을 버리는 호스트**다 — RST 호스트(연결 거부)는 변경 전에도 즉시 예외라
# 검사가 되지 않는다. 아래 `_syn_drop_handler`는 요청에 실린 connect timeout만큼 기다린 뒤
# `ConnectTimeout`을 낸다(커널이 SYN 재전송 끝에 포기하는 모양). MockTransport는 timeout을
# 집행하지 않으므로 handler가 그 몫을 한다.


def _syn_drop_handler(calls: list[float]) -> Callable[[httpx.Request], Any]:
    async def handler(request: httpx.Request) -> httpx.Response:
        connect = request.extensions["timeout"]["connect"]
        calls.append(connect)
        await asyncio.sleep(connect)
        raise httpx.ConnectTimeout("SYN dropped", request=request)

    return handler


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_settings_timeout_splits_connect_from_read() -> None:
    """기본 connect 2.0 s·read 10 s — `httpx.Timeout(10.0, connect=2.0)`."""
    app_settings = Settings()
    assert app_settings.pinvi_kor_travel_weather_connect_timeout_seconds == 2.0
    assert kor_travel_weather_timeout(app_settings) == httpx.Timeout(10.0, connect=2.0)


async def test_factory_client_carries_split_timeout() -> None:
    client = create_kor_travel_weather_client(
        Settings(
            pinvi_kor_travel_weather_timeout_seconds=10.0,
            pinvi_kor_travel_weather_connect_timeout_seconds=2.0,
        )
    )
    try:
        assert client._http.timeout == httpx.Timeout(10.0, connect=2.0)
    finally:
        await client.aclose()


async def test_syn_drop_call_is_bounded_by_connect_timeout_not_read() -> None:
    """회로 닫힘 첫 호출: attempt마다 connect 상한만 기다린다(read 상한이 아니다).

    실제 수치(connect 2 s, read 10 s)를 1/10로 줄여 잰다 — attempt ≤ connect, 호출 ≤
    attempts x connect + backoff. 단일 timeout이면 attempt마다 read 값(1.0)을 기다린다.
    """
    calls: list[float] = []
    http = httpx.AsyncClient(
        base_url="http://kor-travel-weather.test",
        transport=httpx.MockTransport(_syn_drop_handler(calls)),
        timeout=kor_travel_weather_timeout(
            Settings(
                pinvi_kor_travel_weather_timeout_seconds=1.0,
                pinvi_kor_travel_weather_connect_timeout_seconds=0.2,
            )
        ),
    )
    client = KorTravelWeatherClient(http, max_attempts=3, backoff_base_seconds=0.0)
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(KorTravelWeatherUnavailable):
        await client.latest("loc-1")
    elapsed = loop.time() - started
    assert calls == [0.2, 0.2, 0.2]
    assert elapsed < 3 * 0.2 + 0.3
    await client.aclose()


async def test_circuit_opens_after_three_failed_logical_calls() -> None:
    """단위는 논리 호출(attempt 아님): 3회 연속 실패 → open 동안 transport 0회·즉시 Unavailable."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, json={"code": "UPSTREAM"})

    clock = _FakeClock()
    client = _client(handler, max_attempts=2, clock=clock)
    for _ in range(2):
        with pytest.raises(KorTravelWeatherUnavailable):
            await client.latest("loc-1")
    # 논리 호출 2회 = attempt 4회. attempt 수로 셌다면 이미 열렸을 것이다.
    assert attempts["n"] == 4
    with pytest.raises(KorTravelWeatherUnavailable):
        await client.latest("loc-1")
    assert attempts["n"] == 6

    # open: transport를 부르지 않고 즉시 실패한다 — 모든 엔드포인트가 같은 회로를 공유한다.
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.latest("loc-1")
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.resolve(lat=37.5, lon=127.0)
    clock.now += 29.9
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.markers(["loc-1"])
    assert attempts["n"] == 6
    await client.aclose()


async def test_circuit_half_open_trial_closes_on_success_and_reopens_on_failure() -> None:
    fail = {"on": True}
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if fail["on"]:
            return httpx.Response(503, json={"code": "UPSTREAM"})
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    clock = _FakeClock()
    client = _client(handler, max_attempts=1, clock=clock)
    for _ in range(3):
        with pytest.raises(KorTravelWeatherUnavailable):
            await client.latest("loc-1")
    assert attempts["n"] == 3

    # 30 s 뒤 half-open 시험 1회 — 실패면 다시 30 s open.
    clock.now += 30.0
    with pytest.raises(KorTravelWeatherUnavailable):
        await client.latest("loc-1")
    assert attempts["n"] == 4
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.latest("loc-1")
    assert attempts["n"] == 4

    # 다시 30 s 뒤 시험이 성공하면 닫히고 이후 호출은 정상이다.
    clock.now += 30.0
    fail["on"] = False
    assert len(await client.latest("loc-1")) == 1
    assert len(await client.latest("loc-1")) == 1
    assert attempts["n"] == 6
    await client.aclose()


async def test_circuit_half_open_admits_only_one_trial_at_a_time() -> None:
    release = asyncio.Event()
    attempts = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] <= 3:
            return httpx.Response(503, json={"code": "UPSTREAM"})
        await release.wait()
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    clock = _FakeClock()
    client = _client(handler, max_attempts=1, clock=clock)
    for _ in range(3):
        with pytest.raises(KorTravelWeatherUnavailable):
            await client.latest("loc-1")
    clock.now += 30.0
    trial = asyncio.create_task(client.latest("loc-1"))
    for _ in range(5):
        await asyncio.sleep(0)
    # 시험 호출이 진행 중이면 다른 호출은 transport에 닿지 않는다.
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.latest("loc-1")
    release.set()
    assert len(await trial) == 1
    assert attempts["n"] == 4
    await client.aclose()


async def test_cancelled_trial_releases_half_open_slot() -> None:
    """결과 없이 취소된 시험 호출은 회로 상태를 바꾸지 않고 시험 자리만 돌려준다."""
    attempts = {"n": 0}
    hang = {"on": True}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] <= 3:
            return httpx.Response(503, json={"code": "UPSTREAM"})
        if hang["on"]:
            await asyncio.Event().wait()
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    clock = _FakeClock()
    client = _client(handler, max_attempts=1, clock=clock)
    for _ in range(3):
        with pytest.raises(KorTravelWeatherUnavailable):
            await client.latest("loc-1")
    clock.now += 30.0
    trial = asyncio.create_task(client.latest("loc-1"))
    for _ in range(5):
        await asyncio.sleep(0)
    trial.cancel()
    with pytest.raises(asyncio.CancelledError):
        await trial
    hang["on"] = False
    assert len(await client.latest("loc-1")) == 1
    await client.aclose()


async def test_4xx_is_not_a_circuit_failure() -> None:
    """404/422는 피호출자가 살아 있다는 뜻이다 — 회로 실패로 세지 않는다."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(404, json={"code": "NOT_FOUND"})

    client = _client(handler, clock=_FakeClock())
    for _ in range(5):
        with pytest.raises(KorTravelWeatherNotFound):
            await client.latest("loc-1")
    assert attempts["n"] == 5
    await client.aclose()


async def test_success_resets_consecutive_failure_count() -> None:
    script = iter([503, 503, 200, 503, 503, 200])
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        code = next(script)
        if code == 200:
            return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))
        return httpx.Response(code, json={"code": "UPSTREAM"})

    client = _client(handler, max_attempts=1, clock=_FakeClock())
    for expect_ok in (False, False, True, False, False, True):
        if expect_ok:
            await client.latest("loc-1")
        else:
            with pytest.raises(KorTravelWeatherUnavailable):
                await client.latest("loc-1")
    assert attempts["n"] == 6
    await client.aclose()
