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
    KorTravelWeatherDeadlineExhausted,
    KorTravelWeatherNotFound,
    KorTravelWeatherUnavailable,
    create_kor_travel_weather_client,
    kor_travel_weather_call_deadline,
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

    # open: transport를 부르지 않고 즉시 실패한다 — 같은 엔드포인트(location_id 무관)는 같은 회로다.
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.latest("loc-1")
    clock.now += 29.9
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.latest("loc-2")
    assert attempts["n"] == 6
    # 회로는 엔드포인트마다다(T-378) — 다른 엔드포인트는 여전히 transport에 닿는다.
    with pytest.raises(KorTravelWeatherUnavailable) as exc_info:
        await client.markers(["loc-1"])
    assert "회로 열림" not in str(exc_info.value)
    assert attempts["n"] == 8
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
    # 시험 호출이 진행 중이면 다른 호출은 transport에 닿지 않는다(닿으면 handler가 멈추므로
    # 상한을 둔다 — 회귀가 hang이 아니라 실패로 보이게).
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        async with asyncio.timeout(2.0):
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
    async with asyncio.timeout(2.0):
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


async def test_late_non_trial_failure_does_not_free_half_open_slot() -> None:
    """회로가 열리기 전에 출발한 옛 호출의 늦은 실패가 진행 중인 시험 자리를 비우면 안 된다."""
    release_old = asyncio.Event()
    attempts = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        n = attempts["n"]
        if n == 1:  # 옛 호출 A — 회로가 닫혀 있을 때 출발, 나중에 실패
            await release_old.wait()
            return httpx.Response(503, json={"code": "UPSTREAM"})
        if n <= 4:  # 연속 실패 3회 → open
            return httpx.Response(503, json={"code": "UPSTREAM"})
        if n == 5:  # half-open 시험 호출 T — 끝나지 않는다
            await asyncio.Event().wait()
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    clock = _FakeClock()
    client = _client(handler, max_attempts=1, clock=clock)
    old_call = asyncio.create_task(client.latest("loc-1"))
    for _ in range(5):
        await asyncio.sleep(0)
    for _ in range(3):
        with pytest.raises(KorTravelWeatherUnavailable):
            await client.latest("loc-1")
    clock.now += 30.0
    trial = asyncio.create_task(client.latest("loc-1"))
    for _ in range(5):
        await asyncio.sleep(0)
    assert attempts["n"] == 5

    release_old.set()
    with pytest.raises(KorTravelWeatherUnavailable):
        await old_call
    clock.now += 30.0
    # 시험 T가 아직 진행 중이므로 두 번째 시험은 허가되지 않는다.
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        async with asyncio.timeout(2.0):
            await client.latest("loc-1")
    assert attempts["n"] == 5
    trial.cancel()
    with pytest.raises(asyncio.CancelledError):
        await trial
    await client.aclose()


def _hanging_handler(read_waits: list[float]) -> Callable[[httpx.Request], Any]:
    """연결은 받고 응답하지 않는 피호출자 — 요청의 read timeout만큼 기다린 뒤 `ReadTimeout`."""

    async def handler(request: httpx.Request) -> httpx.Response:
        read = request.extensions["timeout"]["read"]
        read_waits.append(read)
        await asyncio.sleep(read)
        raise httpx.ReadTimeout("no response", request=request)

    return handler


async def test_call_deadline_caps_attempt_timeout_and_counts_as_failure() -> None:
    """호출자 deadline 안에서는 attempt timeout이 남은 시간으로 깎여 **실패로 끝난다**.

    바깥 `asyncio.timeout` 취소는 회로 실패로 세지 않으므로, 이것이 없으면 응답하지 않는
    피호출자(read 10 s x 3회)는 trip view 예산(10 s)에 늘 취소돼 회로를 열지 못한다. attempt
    예산(0.15 s)이 정상 read(0.2 s)의 절반 이상이라 "의미 있는 예산"으로 센다.
    """
    read_waits: list[float] = []
    http = httpx.AsyncClient(
        base_url="http://kor-travel-weather.test",
        transport=httpx.MockTransport(_hanging_handler(read_waits)),
        timeout=httpx.Timeout(0.2, connect=0.2),
    )
    client = KorTravelWeatherClient(http, max_attempts=3, backoff_base_seconds=0.0)
    loop = asyncio.get_running_loop()
    for _ in range(3):
        started = loop.time()
        with kor_travel_weather_call_deadline(started + 0.15):
            with pytest.raises(KorTravelWeatherUnavailable):
                await client.latest("loc-1")
        assert loop.time() - started < 0.15 + 0.1
    # attempt 하나가 남은 시간(≤0.15 s)까지만 기다렸고 재시도 없이 끝났다(남은 시간 0).
    assert len(read_waits) == 3
    assert all(wait <= 0.15 for wait in read_waits)
    # 세 번의 논리 호출 실패로 회로가 열렸다 — 다음 호출은 transport에 닿지 않는다.
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.latest("loc-1")
    assert len(read_waits) == 3
    await client.aclose()


async def test_exhausted_call_deadline_sends_nothing_and_is_not_a_failure() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    client = _client(handler, clock=_FakeClock())
    past = asyncio.get_running_loop().time() - 1.0
    for _ in range(5):
        with kor_travel_weather_call_deadline(past):
            with pytest.raises(KorTravelWeatherDeadlineExhausted):
                await client.latest("loc-1")
    assert attempts["n"] == 0
    # 예산 소진은 피호출자 장애의 증거가 아니다 — 회로는 닫힌 채다.
    assert len(await client.latest("loc-1")) == 1
    await client.aclose()


async def test_short_budget_timeout_is_exhaustion_not_a_failure() -> None:
    """정상 read의 절반보다 짧은 예산에서 깎인 timeout은 "호출자 예산 소진"이다 — 회로 미집계.

    느리지만 살아 있는 피호출자에서 view 예산 끝의 병렬 forecast가 함께 끊겨도 회로가 열리면 안 된다.
    """
    hang = {"on": True}
    attempts = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if hang["on"]:
            read = request.extensions["timeout"]["read"]
            await asyncio.sleep(read)
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    http = httpx.AsyncClient(
        base_url="http://kor-travel-weather.test",
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(1.0, connect=0.2),
    )
    client = KorTravelWeatherClient(http, max_attempts=3, backoff_base_seconds=0.0)
    loop = asyncio.get_running_loop()
    for _ in range(5):
        with kor_travel_weather_call_deadline(loop.time() + 0.1):
            with pytest.raises(KorTravelWeatherDeadlineExhausted):
                await client.latest("loc-1")
    # 각 호출은 deadline에서 끊긴 attempt 1회로 끝났다(남은 시간 0 — 재시도 없음).
    assert attempts["n"] == 5
    hang["on"] = False
    assert len(await client.latest("loc-1")) == 1
    await client.aclose()


async def test_one_deadline_scope_counts_at_most_one_failure() -> None:
    """한 deadline 범위(trip view 1회)의 병렬 호출 실패는 회로 실패 1회다."""
    fail = {"on": True}
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if fail["on"]:
            return httpx.Response(503, json={"code": "UPSTREAM"})
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    client = _client(handler, max_attempts=1, clock=_FakeClock())
    loop = asyncio.get_running_loop()
    with kor_travel_weather_call_deadline(loop.time() + 5.0):
        results = await asyncio.gather(
            *(client.latest(f"loc-{i}") for i in range(10)), return_exceptions=True
        )
    assert all(isinstance(r, KorTravelWeatherUnavailable) for r in results)
    assert attempts["n"] == 10
    fail["on"] = False
    # 회로는 닫힌 채다 — 다음 호출이 transport에 닿는다.
    assert len(await client.latest("loc-1")) == 1
    await client.aclose()


async def test_trickling_body_is_bounded_by_attempt_total_timeout() -> None:
    """httpx 단계별 timeout은 조각마다 다시 잰다 — 본문이 찔끔찔끔 오면 deadline을 넘는다.
    attempt 전체를 남은 시간으로 묶어야 한다."""

    async def trickle() -> Any:
        for _ in range(40):
            await asyncio.sleep(0.05)
            yield b" "

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=trickle())

    http = httpx.AsyncClient(
        base_url="http://kor-travel-weather.test",
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(0.2, connect=0.2),
    )
    client = KorTravelWeatherClient(http, max_attempts=3, backoff_base_seconds=0.0)
    loop = asyncio.get_running_loop()
    started = loop.time()
    with kor_travel_weather_call_deadline(started + 0.3):
        with pytest.raises(KorTravelWeatherUnavailable) as exc_info:
            async with asyncio.timeout(3.0):
                await client.latest("loc-1")
    assert loop.time() - started < 0.3 + 0.5
    # 예산 0.3 s는 정상 read(0.2 s)의 절반 이상 — 진짜 실패로 센다.
    assert not isinstance(exc_info.value, KorTravelWeatherDeadlineExhausted)
    await client.aclose()


async def test_backoff_longer_than_remaining_stops_and_counts() -> None:
    """backoff가 deadline을 넘으면 자지 않고 멈춘다 — 자다가 바깥 취소(미집계)를 맞지 않게."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, json={"code": "UPSTREAM"})

    clock = _FakeClock()
    client = _client(handler, max_attempts=3, backoff_base_seconds=0.2, clock=clock)
    loop = asyncio.get_running_loop()
    for _ in range(3):
        started = loop.time()
        with kor_travel_weather_call_deadline(started + 0.1):
            with pytest.raises(KorTravelWeatherUnavailable) as exc_info:
                await client.latest("loc-1")
        assert loop.time() - started < 0.1
        assert not isinstance(exc_info.value, KorTravelWeatherDeadlineExhausted)
    assert attempts["n"] == 3
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.latest("loc-1")
    await client.aclose()


async def test_nested_deadline_cannot_widen_budget() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    client = _client(handler, clock=_FakeClock())
    loop = asyncio.get_running_loop()
    with kor_travel_weather_call_deadline(loop.time() - 1.0):
        with kor_travel_weather_call_deadline(loop.time() + 60.0):
            with pytest.raises(KorTravelWeatherDeadlineExhausted):
                await client.latest("loc-1")
    assert attempts["n"] == 0
    await client.aclose()


async def test_nested_scope_shares_counting_state() -> None:
    """중첩 범위는 바깥과 집계 상태를 공유한다 — 안팎에서 실패를 두 번 세지 않는다."""
    fail = {"on": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if fail["on"]:
            return httpx.Response(503, json={"code": "UPSTREAM"})
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    client = _client(handler, max_attempts=1, clock=_FakeClock())
    loop = asyncio.get_running_loop()
    for _ in range(2):
        with kor_travel_weather_call_deadline(loop.time() + 5.0):
            with pytest.raises(KorTravelWeatherUnavailable):
                await client.latest("loc-1")
            with kor_travel_weather_call_deadline(loop.time() + 5.0):
                with pytest.raises(KorTravelWeatherUnavailable):
                    await client.latest("loc-1")
    # 범위 2개 = 실패 2회 < 임계 3 — 회로는 닫힌 채다.
    fail["on"] = False
    assert len(await client.latest("loc-1")) == 1
    await client.aclose()


# ── T-378: 엔드포인트별 성공 관측·연속 실패 ──────────────────────────────────────────────


def _split_handler(forecast: str) -> tuple[Callable[[httpx.Request], Any], dict[str, int]]:
    """`latest`는 늘 응답하고 `forecast`만 `forecast` 방식으로 실패하는 피호출자."""
    calls = {"latest": 0, "forecast": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/forecast"):
            calls["forecast"] += 1
            if forecast == "hang":
                read = request.extensions["timeout"]["read"]
                await asyncio.sleep(read)
                raise httpx.ReadTimeout("no response", request=request)
            return httpx.Response(503, json={"code": "UPSTREAM"})
        calls["latest"] += 1
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    return handler, calls


async def test_forecast_hang_opens_circuit_although_other_endpoint_answers_in_the_view() -> None:
    """한 view에서 latest는 응답하고 forecast만 멈춘다 — forecast hang이 view마다 실패로 세져 3 view 뒤 열린다.

    종전에는 범위 전체의 성공 관측(latest)이 forecast의 deadline timeout을 "소진"으로 바꾸고, latest 성공이
    연속 실패 수를 되돌려 회로가 영영 열리지 않았다(view마다 예산 끝까지 기다림, #584 최종 리뷰).
    """
    handler, calls = _split_handler("hang")
    http = httpx.AsyncClient(
        base_url="http://kor-travel-weather.test",
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(0.2, connect=0.2),
    )
    client = KorTravelWeatherClient(http, max_attempts=3, backoff_base_seconds=0.0)
    loop = asyncio.get_running_loop()
    for _ in range(3):
        with kor_travel_weather_call_deadline(loop.time() + 0.15):
            assert len(await client.latest("loc-1")) == 1
            with pytest.raises(KorTravelWeatherUnavailable) as exc_info:
                await client.forecast("loc-1")
            assert not isinstance(exc_info.value, KorTravelWeatherDeadlineExhausted)
    assert calls == {"latest": 3, "forecast": 3}
    # forecast 연속 실패 3회 — forecast 회로만 열린다. latest는 계속 transport에 닿는다.
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.forecast("loc-2")
    assert len(await client.latest("loc-1")) == 1
    assert calls == {"latest": 4, "forecast": 3}
    await client.aclose()


async def test_same_endpoint_success_still_makes_its_deadline_timeout_exhaustion() -> None:
    """같은 엔드포인트가 그 view에서 이미 응답했으면 그 엔드포인트의 deadline timeout은 소진이다(종전 규칙)."""
    seen = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["n"] += 1
        if request.url.path.startswith("/v1/weather/locations/slow/"):
            read = request.extensions["timeout"]["read"]
            await asyncio.sleep(read)
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    http = httpx.AsyncClient(
        base_url="http://kor-travel-weather.test",
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(0.2, connect=0.2),
    )
    client = KorTravelWeatherClient(http, max_attempts=3, backoff_base_seconds=0.0)
    loop = asyncio.get_running_loop()
    for _ in range(4):
        with kor_travel_weather_call_deadline(loop.time() + 0.15):
            assert len(await client.latest("fast")) == 1
            with pytest.raises(KorTravelWeatherDeadlineExhausted):
                await client.latest("slow")
    # 소진은 세지 않으므로 회로는 닫힌 채다.
    assert len(await client.latest("fast")) == 1
    await client.aclose()


async def test_other_endpoint_success_does_not_reset_failing_endpoint_count() -> None:
    """forecast 실패 사이사이 latest가 성공해도 forecast의 연속 실패는 이어진다 — 3회째에 forecast만 열린다.

    half-open 시험도 엔드포인트마다다: 30 s 뒤 forecast 시험이 실패하면 forecast만 다시 열리고, latest는
    그동안 내내 닫힌 채 응답한다.
    """
    handler, calls = _split_handler("503")
    clock = _FakeClock()
    client = _client(handler, max_attempts=1, clock=clock)
    for _ in range(2):
        with pytest.raises(KorTravelWeatherUnavailable):
            await client.forecast("loc-1")
        assert len(await client.latest("loc-1")) == 1
    with pytest.raises(KorTravelWeatherUnavailable):
        await client.forecast("loc-1")
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.forecast("loc-1")
    assert len(await client.latest("loc-1")) == 1
    assert calls == {"latest": 3, "forecast": 3}

    clock.now += 30.0
    with pytest.raises(KorTravelWeatherUnavailable) as exc_info:
        await client.forecast("loc-1")  # half-open 시험 — 실패해 다시 연다
    assert "회로 열림" not in str(exc_info.value)
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.forecast("loc-1")
    assert len(await client.latest("loc-1")) == 1
    assert calls == {"latest": 4, "forecast": 4}
    await client.aclose()


async def test_circuit_key_is_the_endpoint_not_the_location_id() -> None:
    """회로 key는 호출부의 리터럴 엔드포인트 이름이다 — location_id가 매번 달라도(`/` 포함) 같은 회로에 센다."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, json={"code": "UPSTREAM"})

    client = _client(handler, max_attempts=1, clock=_FakeClock())
    for location_id in ("loc-1", "a/b", "c/d/e"):
        with pytest.raises(KorTravelWeatherUnavailable) as exc_info:
            await client.latest(location_id)
        assert "회로 열림" not in str(exc_info.value)
    assert attempts["n"] == 3
    with pytest.raises(KorTravelWeatherUnavailable, match="회로 열림"):
        await client.latest("never-seen/before")
    assert attempts["n"] == 3
    await client.aclose()


async def test_location_id_is_quoted_as_one_path_segment() -> None:
    """`/`·`?`·`#`가 든 location_id도 경로 세그먼트 하나로 quote돼 나간다(경로를 쪼개거나 바꾸지 않는다)."""
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path.split(b"?", 1)[0])
        return httpx.Response(200, json=_envelope([_WEATHER_VALUE]))

    client = _client(handler, clock=_FakeClock())
    await client.latest("a/b")
    await client.forecast("x/../y?z#w")
    await client.latest("plain-id_1.2")
    assert seen == [
        b"/v1/weather/locations/a%2Fb/latest",
        b"/v1/weather/locations/x%2F..%2Fy%3Fz%23w/forecast",
        b"/v1/weather/locations/plain-id_1.2/latest",
    ]
    await client.aclose()
