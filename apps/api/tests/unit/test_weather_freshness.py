"""선택된 Map weather 사실의 수집 상태를 카드에 보존한다."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.models.weather_location_link import WeatherLocationLink
from app.services import trip_weather_batch as tw
from app.services import weather_map_resolver as mr
from app.services import weather_map_state as st
from app.services.weather_location_resolver import WeatherLocationFound
from tests import weather_map_fixtures as fx


@pytest.mark.parametrize("section_name", ["current", "short", "external", "daily"])
@pytest.mark.parametrize("signal", ["sla", "source"])
def test_section_freshness_attaches_to_only_its_facts(section_name: str, signal: str) -> None:
    body = fx.kma_bundle()
    body["forecasts"]["external"] = fx.forecast_section(
        "external", groups=[fx.forecast_group({"TEMP": [15.0]}, provider="weatherapi")]
    )
    section = (
        body["current"]
        if section_name == "current"
        else body["daily_summaries"]
        if section_name == "daily"
        else body["forecasts"][section_name]
    )
    section["freshness"]["stale"] = signal == "sla"
    section["freshness"]["source_status"] = "stale" if signal == "source" else "ok"
    # 위치 목록의 오래됨은 개별 관측·예보의 수집 상태가 아니다.
    body["location_freshness"]["stale"] = True
    day = datetime.now(fx.KST).date() - timedelta(days=1)
    rows = st.bundle_values(st.parse_bundle(body), daily_dates=[day])
    selected = {
        "current": lambda v: v.forecast_style == "observed",
        "short": lambda v: v.forecast_style == "short" and v.provider == "python-kma-api",
        "external": lambda v: v.provider == "weatherapi",
        "daily": lambda v: v.forecast_style == "daily_summary",
    }[section_name]
    assert any(selected(row) for row in rows)
    for row in rows:
        assert getattr(row, "source_stale", False) is selected(row)


def _daily(day: Any, *, stale: bool, provider: str = "python-kma-api") -> list[st.MapWeatherValue]:
    body = fx.bundle(
        daily=fx.daily_section(slots=[fx.daily_slot(day, source_providers=[provider])])
    )
    body["daily_summaries"]["freshness"]["stale"] = stale
    return st.bundle_values(st.parse_bundle(body), daily_dates=[day])


def _project(values: list[st.MapWeatherValue], days: list[Any]) -> dict[int, Any]:
    pending = tw._Pending(
        {i: {} for i in range(len(days))},
        {i: {} for i in range(len(days))},
        feature_days={"feature": list(enumerate(days))},
    )
    bundles = tw._Bundles({fx.LOC_KMA: {fx.LOC_KMA}}, [fx.LOC_KMA], days)
    tw._project(
        pending,
        {"feature": WeatherLocationFound(fx.LOC_KMA, (fx.LOC_KMA,))},
        bundles,
        {fx.LOC_KMA: values},
        {},
    )
    return pending.weather_cards_by_day_index


def test_card_freshness_isolated_by_trip_day() -> None:
    today = datetime.now(fx.KST).date()
    yesterday = today - timedelta(days=1)
    cards = _project(_daily(yesterday, stale=False) + _daily(today, stale=True), [yesterday, today])
    assert cards[0][fx.LOC_KMA]["is_stale"] is False
    assert cards[1][fx.LOC_KMA]["is_stale"] is True


def test_discarded_provider_staleness_does_not_taint_selected_card() -> None:
    day = datetime.now(fx.KST).date()
    cards = _project(
        _daily(day, stale=False) + _daily(day, stale=True, provider="openweathermap"), [day]
    )
    assert cards[0][fx.LOC_KMA]["is_stale"] is False


def test_legacy_selection_cache_is_not_reused() -> None:
    now = datetime.now(UTC)
    row = WeatherLocationLink(
        feature_id="freshness-fixture",
        lat=37.5,
        lon=127.0,
        location_id=fx.LOC_KMA,
        source_location_ids=[fx.LOC_KMA],
        resolved_at=now,
        stale=False,
        measurement_point={"resolved_via": "kor_travel_map"},
    )
    assert mr.cache_hit(row, lat=37.5, lon=127.0, now=now) is None


@pytest.mark.parametrize(
    ("age", "stale", "hit"),
    [
        (timedelta(), False, True),
        (timedelta(days=8), False, False),
        (timedelta(minutes=10), True, True),
        (timedelta(minutes=16), True, False),
    ],
)
def test_current_selection_cache_keeps_ttl_and_retry_policy(age, stale, hit) -> None:
    now = datetime.now(UTC)
    row = WeatherLocationLink(
        feature_id="versioned-freshness-fixture",
        lat=37.5,
        lon=127.0,
        location_id=fx.LOC_KMA,
        source_location_ids=[fx.LOC_KMA],
        resolved_at=now - age,
        stale=stale,
        measurement_point={"resolved_via": "kor_travel_map", "selection_version": 2},
    )
    assert mr.written_by_map(row)
    assert (mr.cache_hit(row, lat=37.5, lon=127.0, now=now) is not None) is hit
