"""astral 해·달 출몰 계산(2026-11-16 요청 18, 11-17 달 이관) — KASI 고시값과 분 단위로 맞는지."""

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


# KASI 출몰시각(운영 `trip_day_rise_sets` 성공 행, 2026-11-17 표본 25건 모두 ±1분)에서 고른 값.
@pytest.mark.parametrize(
    ("lon", "lat", "on", "expected"),
    [
        (128.5289, 36.5503, date(2026, 11, 8), ("06:56", "17:23", "05:47", "16:24")),
        (128.4974, 38.1638, date(2026, 11, 19), ("07:11", "17:11", "13:52", "00:56")),
        (128.5309, 36.8400, date(2026, 11, 5), ("06:53", "17:25", "02:36", "15:05")),
        (128.5289, 36.5503, date(2026, 11, 16), ("07:05", "17:17", "12:34", "22:56")),
    ],
)
def test_sun_and_moon_match_kasi_within_a_minute(
    lon: float, lat: float, on: date, expected: tuple[str, str, str, str]
) -> None:
    times = compute_sun_times(longitude=lon, latitude=lat, on=on)
    got = (times.sunrise_at, times.sunset_at, times.moonrise_at, times.moonset_at)
    for value, want in zip(got, expected, strict=True):
        assert value is not None
        assert value.astimezone(KST).date() == on
        minutes = value.astimezone(KST).hour * 60 + value.astimezone(KST).minute
        want_minutes = int(want[:2]) * 60 + int(want[3:])
        assert abs(minutes - want_minutes) <= 1, (on, value, want)


def test_moon_event_before_9am_kst_is_found() -> None:
    """astral moonset(tzinfo=KST)은 UTC 날짜만 봐서 서울 2026-05-06 08시대 월몰을 놓친다(ValueError)."""
    times = compute_sun_times(longitude=127.1, latitude=37.5, on=date(2026, 5, 6))
    assert _hm(times.moonset_at) == "08:08"
    assert _hm(times.moonrise_at) == "23:51"


def test_day_without_moonset_is_none_not_neighbouring_day() -> None:
    # 서울 2026-11-17: 13:10에 떠서 자정을 넘겨 진다 — 그날 월몰은 없다(다음날 값을 끌어오지 않는다).
    times = compute_sun_times(longitude=126.978, latitude=37.5665, on=date(2026, 11, 17))
    assert _hm(times.moonrise_at) == "13:10"
    assert times.moonset_at is None


def test_success_shape_has_computed_moon_and_no_fetched_at() -> None:
    result = sun_rise_set_dict(locdate=date(2026, 6, 10), coord=(129.118, 35.153))
    assert result["status"] == "success"
    assert result["fetched_at"] is None
    assert _hm(result["moonrise_at"]) == "01:12"
    assert _hm(result["moonset_at"]) == "14:07"
    assert result["locdate"] == date(2026, 6, 10)


def test_pending_states_have_no_moon() -> None:
    assert sun_rise_set_dict(locdate=None, coord=(127.0, 37.5))["moonrise_at"] is None
    assert sun_rise_set_dict(locdate=date(2026, 6, 10), coord=None)["moonset_at"] is None
