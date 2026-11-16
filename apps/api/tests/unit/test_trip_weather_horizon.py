"""받은 예보의 마지막 KST 날짜(`forecast_horizon`) — 예보 범위 밖 안내의 근거(2026-11-17 결정 3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.trip_weather_batch import forecast_horizon
from app.services.weather_map_state import MapWeatherBundle, parse_bundle
from tests import weather_map_fixtures as fx


def _bundle(*target_at: datetime, status: str = "ok") -> MapWeatherBundle:
    data = fx.bundle(
        fx.LOC_KMA,
        current=fx.current_section("no_data"),
        forecasts={
            "mid": fx.forecast_section(
                "mid",
                status,
                groups=[
                    fx.forecast_group(
                        {"TMN": [1.0] * len(target_at)},
                        target_at=[t.isoformat() for t in target_at],
                    )
                ],
            )
        },
    )
    return parse_bundle(data)


def test_horizon_is_latest_target_in_kst() -> None:
    # 2026-11-27 15:30 UTC = 11-28 00:30 KST — 날짜는 KST로 센다.
    late = datetime(2026, 11, 27, 15, 30, tzinfo=UTC)
    early = late - timedelta(days=3)
    horizon = forecast_horizon([_bundle(early), _bundle(late)])
    assert horizon is not None and horizon.isoformat() == "2026-11-28"


def test_no_forecast_means_unknown_horizon() -> None:
    assert forecast_horizon([]) is None
    failed = _bundle(datetime(2026, 11, 27, tzinfo=UTC), status="not_loaded")
    assert forecast_horizon([failed]) is None
