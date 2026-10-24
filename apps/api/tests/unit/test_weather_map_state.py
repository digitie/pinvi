"""Map weather 묶음 해석·평탄화·배치 청크 (ADR-077, `app/services/weather_map_state.py`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient
from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient
from app.clients.kor_travel_weather import KorTravelWeatherUnavailable, WeatherMarkerOut
from app.core.time import KST
from app.services import weather_map_state as st
from app.services.weather_metrics import dedupe_by_provider_priority, to_weather_metric
from tests import weather_map_fixtures as fx

def _map_client(handler: Any) -> tuple[KorTravelMapWeatherClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        response: httpx.Response = handler(request)
        return response

    client = KorTravelMapClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(record)),
        service_token="svc",
        max_attempts=1,
    )
    return KorTravelMapWeatherClient(client), seen


# ── 평탄화 ────────────────────────────────────────────────────────────────────────────


def test_forecast_columns_flatten_to_rows_and_drop_null_slots() -> None:
    times = [fx.hours_from_now(1), fx.hours_from_now(2), fx.hours_from_now(3)]
    group = st.MapWeatherForecastGroup.model_validate(
        fx.forecast_group({"TMP": [15.0, None, 16], "SKY": ["1", "3", None]}, target_at=times)
    )
    rows = st.forecast_values(fx.LOC_KMA, "short", [group])
    got = {(r.metric_key, r.target_at.isoformat(), r.value_number, r.value_text) for r in rows}
    assert got == {
        ("TMP", times[0], 15.0, None),
        ("TMP", times[2], 16.0, None),
        ("SKY", times[0], None, "1"),
        ("SKY", times[1], None, "3"),
    }
    tmp = next(r for r in rows if r.metric_key == "TMP")
    # KMA 고정 단위·이름표(weather providers/kma.py)로 채운다 — 직접 경로와 같은 값.
    assert (tmp.unit, tmp.metric_name, tmp.forecast_style) == ("deg_c", "기온", "short")
    assert tmp.valid_at == tmp.target_at
    assert tmp.issued_at == group.published_at
    assert all(r.location_id == fx.LOC_KMA for r in rows)


def test_misaligned_forecast_group_is_a_contract_error() -> None:
    body = fx.kma_bundle()
    body["forecasts"]["short"]["groups"][0]["metrics"]["TMP"].append(1.0)
    with pytest.raises(st.MapWeatherContractError):
        st.parse_bundle(body)


def test_external_forecast_becomes_short_and_drops_unitless_wind_speed() -> None:
    group = st.MapWeatherForecastGroup.model_validate(
        fx.forecast_group({"TEMP": [14.0], "WIND_SPEED": [36.0]}, provider="openweathermap")
    )
    rows = st.forecast_values(fx.LOC_EXT, "external", [group])
    assert [(r.metric_key, r.forecast_style, r.unit) for r in rows] == [("TEMP", "short", None)]
    # 정규화 규칙은 직접 경로와 같다 — TEMP(short) → TMP, 단위 기본값 deg_c.
    metric = to_weather_metric(rows[0])
    assert (metric.metric_key, metric.unit, metric.weather_domain) == ("TMP", "deg_c", None)


def test_kma_wind_speed_forecast_keeps_its_fixed_unit() -> None:
    group = st.MapWeatherForecastGroup.model_validate(fx.forecast_group({"WSD": [3.2]}))
    [row] = st.forecast_values(fx.LOC_KMA, "short", [group])
    assert (row.metric_key, row.unit) == ("WSD", "m/s")


def test_observations_keep_unit_and_mark_observed_at() -> None:
    obs = [
        st.MapWeatherObservation.model_validate(fx.observation("T1H", 12.5, unit="deg_c")),
        st.MapWeatherObservation.model_validate(
            fx.observation("TEMP", 11, provider="weatherapi", forecast_style="nowcast")
        ),
        st.MapWeatherObservation.model_validate(fx.observation("PM10", None)),
    ]
    rows = st.observation_values(fx.LOC_AIR, obs)
    assert [(r.metric_key, r.forecast_style) for r in rows] == [
        ("T1H", "observed"),
        ("TEMP", "nowcast"),
    ]
    assert rows[0].observed_at == rows[0].target_at
    assert rows[1].observed_at is None
    assert rows[1].value_number == 11.0
    assert rows[0].metric_name == "현재 기온"


def test_provider_priority_dedupe_runs_on_flattened_rows() -> None:
    at = fx.hours_from_now(2)
    kma = st.MapWeatherForecastGroup.model_validate(
        fx.forecast_group({"TMP": [15.0]}, target_at=[at])
    )
    other = st.MapWeatherForecastGroup.model_validate(
        fx.forecast_group({"TMP": [99.0]}, provider="open_meteo", target_at=[at])
    )
    rows = st.forecast_values(fx.LOC_KMA, "short", [other, kma])
    [kept] = dedupe_by_provider_priority(rows)
    assert (kept.provider, kept.value_number) == ("python-kma-api", 15.0)


def test_daily_slots_project_only_requested_dates_and_keep_vs_previous_day() -> None:
    bundle = st.parse_bundle(fx.kma_bundle())
    daily = bundle.daily_summaries
    assert daily is not None
    today = datetime.now(KST).date()
    yesterday = today - timedelta(days=1)
    # vs_previous_day는 Map 값 그대로(PinVi가 다시 계산하지 않는다) — partial이면 Map이 준 null.
    by_date = {slot.date: slot for slot in daily.slots}
    delta = by_date[yesterday].vs_previous_day
    assert delta is not None
    assert (delta.previous_date, delta.temp_min_delta, delta.humidity_avg_delta) == (
        today - timedelta(days=2),
        -1.5,
        3.0,
    )
    assert by_date[today].partial is True
    assert by_date[today].vs_previous_day is None

    rows = st.daily_values(fx.LOC_KMA, daily, dates=[yesterday])
    assert {r.target_at.date() for r in rows} == {yesterday}
    keys = [(r.metric_key, r.metric_name) for r in rows]
    assert keys[:2] == [("TMN", "아침 최저기온"), ("TMX", "아침 최고기온")]
    first = rows[0]
    assert first.forecast_style == "observed"
    assert first.timeline_bucket == "morning"
    assert first.valid_from == datetime(
        yesterday.year, yesterday.month, yesterday.day, 5, tzinfo=KST
    )
    assert first.valid_until == datetime(
        yesterday.year, yesterday.month, yesterday.day, 11, tzinfo=KST
    )


def test_daily_slots_without_samples_are_skipped() -> None:
    today = datetime.now(KST).date()
    section = st.MapWeatherDailySection.model_validate(
        fx.daily_section(slots=[fx.daily_slot(today, sample_count=0)])
    )
    assert st.daily_values(fx.LOC_KMA, section, dates=[today]) == []


def test_nearest_bundle_sources_and_section_failure() -> None:
    bundle = st.parse_bundle(fx.nearest_split_bundle())
    # 대표 위치 먼저, 부분별 source 위치를 순서 보존 dedupe.
    assert bundle.section_location_ids() == [fx.LOC_AIR, fx.LOC_KMA, fx.LOC_EXT]
    assert bundle.any_section_failed() is True  # ultra_short not_loaded·daily unavailable
    rows = st.bundle_values(bundle)
    assert {(r.location_id, r.metric_key) for r in rows} == {
        (fx.LOC_AIR, "PM10"),
        (fx.LOC_KMA, "TMP"),
        (fx.LOC_EXT, "TEMP"),
    }


def test_bundle_with_only_ok_or_no_data_sections_is_not_failed() -> None:
    bundle = st.parse_bundle(fx.bundle(current=fx.current_section("no_data")))
    assert bundle.any_section_failed() is False
    assert st.bundle_values(bundle) == []


# ── 배치 청크 ──────────────────────────────────────────────────────────────────────────


async def test_batch_chunks_over_50_and_isolates_a_failed_chunk() -> None:
    ids = [f"loc-{i:03d}" for i in range(120)]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        chunk = body["location_ids"]
        if "loc-060" in chunk:
            return httpx.Response(503, json=fx.problem_body(503, "WEATHER_STATE_UNAVAILABLE"))
        items = [fx.bundle(loc) for loc in chunk if loc != "loc-001"]
        missing = [fx.missing("loc-001")] if "loc-001" in chunk else []
        return httpx.Response(200, json=fx.batch_body(items, missing))

    client, seen = _map_client(handler)
    now = datetime.now(UTC)
    result = await st.fetch_location_bundles(
        client,
        ids,
        sections=("current", "forecasts"),
        forecast_from=now,
        forecast_to=now + timedelta(days=1),
    )
    sizes = sorted(len(json.loads(r.content)["location_ids"]) for r in seen)
    assert sizes == [20, 50, 50]
    assert result.failed == {f"loc-{i:03d}" for i in range(50, 100)}
    assert result.missing == {"loc-001"}
    assert len(result.bundles) == 120 - 50 - 1
    assert all("forecast_to" in json.loads(r.content) for r in seen)


async def test_batch_without_forecasts_sends_no_window() -> None:
    client, seen = _map_client(lambda r: httpx.Response(200, json=fx.batch_body([fx.bundle()])))
    now = datetime.now(UTC)
    await st.fetch_location_bundles(
        client, [fx.LOC_KMA], sections=("current",), forecast_from=now, forecast_to=now
    )
    body = json.loads(seen[0].content)
    assert "forecast_from" not in body
    assert "forecast_to" not in body


async def test_contract_violation_marks_chunk_failed() -> None:
    broken = fx.batch_body([fx.kma_bundle()])
    del broken["data"]["items"][0]["location"]["location_id"]
    client, _ = _map_client(lambda r: httpx.Response(200, json=broken))
    result = await st.fetch_location_bundles(client, [fx.LOC_KMA], sections=("current",))
    assert result.failed == {fx.LOC_KMA}
    assert result.bundles == {}


async def test_empty_id_list_makes_no_call() -> None:
    client, seen = _map_client(lambda r: httpx.Response(500))
    result = await st.fetch_location_bundles(client, [], sections=("current",))
    assert result.bundles == {} and result.failed == set()
    assert seen == []


class _AlertWeather:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[str]] = []

    async def markers(self, location_ids: list[str]) -> tuple[WeatherMarkerOut, ...]:
        self.calls.append(list(location_ids))
        if self.fail:
            raise KorTravelWeatherUnavailable("down")
        return (WeatherMarkerOut(location_id=location_ids[0], alerts=()),)


async def test_alerts_are_optional_and_failure_is_swallowed() -> None:
    assert await st.fetch_alerts(None, [fx.LOC_KMA]) == {}
    failing = _AlertWeather(fail=True)
    assert await st.fetch_alerts(failing, [fx.LOC_KMA]) == {}  # type: ignore[arg-type]
    assert failing.calls == [[fx.LOC_KMA]]
