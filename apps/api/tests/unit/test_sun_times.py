"""astral 일출·일몰 계산(2026-11-16 소유자 요청 18) — KASI 고시값과 분 단위로 맞는지."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.sun_times import compute_sun_times, sun_rise_set_dict

KST = ZoneInfo("Asia/Seoul")


def _hm(value: datetime | None) -> str | None:
    return value.astimezone(KST).strftime("%H:%M") if value is not None else None


@pytest.mark.parametrize(
    ("lon", "lat", "on", "sunrise", "sunset"),
    [
        # KASI 출몰시각 고시값(서울·부산, 하지 무렵·동지 무렵).
        (126.978, 37.5665, date(2026, 6, 10), "05:11", "19:52"),
        (126.978, 37.5665, date(2026, 12, 22), "07:44", "17:17"),
        (129.118, 35.153, date(2026, 6, 10), "05:09", "19:37"),
    ],
)
def test_matches_kasi_to_the_minute(
    lon: float, lat: float, on: date, sunrise: str, sunset: str
) -> None:
    times = compute_sun_times(longitude=lon, latitude=lat, on=on)
    assert _hm(times.sunrise_at) == sunrise
    assert _hm(times.sunset_at) == sunset
    assert times.sunrise_at is not None and times.sunrise_at.tzinfo is not None
    assert times.sunrise_at.astimezone(KST).date() == on  # KST 민간일 기준


def test_rounds_to_the_nearest_minute() -> None:
    times = compute_sun_times(longitude=126.978, latitude=37.5665, on=date(2026, 6, 10))
    assert times.sunrise_at is not None
    assert times.sunrise_at.second == 0 and times.sunrise_at.microsecond == 0


def test_polar_day_has_no_sunset_and_is_failed_not_crash() -> None:
    times = compute_sun_times(longitude=15.0, latitude=78.2, on=date(2026, 6, 21))
    assert times.sunrise_at is None and times.sunset_at is None
    result = sun_rise_set_dict(locdate=date(2026, 6, 21), coord=(15.0, 78.2))
    assert result["status"] == "failed"


def test_pending_states_follow_missing_input() -> None:
    now = datetime(2026, 11, 16, tzinfo=UTC)
    assert sun_rise_set_dict(locdate=None, coord=(127.0, 37.5), now=now)["status"] == "pending_date"
    no_coord = sun_rise_set_dict(locdate=date(2026, 11, 16), coord=None, now=now)
    assert no_coord["status"] == "pending_coord"
    assert no_coord["sunrise_at"] is None
    assert no_coord["updated_at"] == now


def test_success_shape_keeps_kasi_moon_and_no_fetched_at() -> None:
    moonrise = datetime(2026, 11, 16, 1, 0, tzinfo=UTC)
    result = sun_rise_set_dict(
        locdate=date(2026, 11, 16),
        coord=(126.978, 37.5665),
        moon={"moonrise_at": moonrise, "moonset_at": None},
    )
    assert result["status"] == "success"
    assert result["fetched_at"] is None
    assert result["moonrise_at"] == moonrise
    assert result["locdate"] == date(2026, 11, 16)
    assert _hm(result["sunrise_at"]) is not None and _hm(result["sunset_at"]) is not None
