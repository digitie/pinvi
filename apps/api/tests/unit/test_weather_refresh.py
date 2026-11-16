"""날씨 새로고침 속도 제한 계산(요청 15) — DB·Map 없이 보는 부분."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.services.weather_refresh import (
    MAX_REFRESH_FEATURES,
    REFRESH_COOLDOWN,
    WeatherRefreshResult,
    _remaining_cooldown,
    refresh_weather_locations,
)

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def _row(age: timedelta) -> Any:
    return SimpleNamespace(resolved_at=NOW - age)


def test_cooldown_is_sixty_seconds_from_last_resolution() -> None:
    assert REFRESH_COOLDOWN == timedelta(seconds=60)
    assert _remaining_cooldown(None, now=NOW) is None
    assert _remaining_cooldown(_row(timedelta(seconds=10)), now=NOW) == timedelta(seconds=50)
    assert _remaining_cooldown(_row(timedelta(seconds=60)), now=NOW) is None
    assert _remaining_cooldown(_row(timedelta(days=1)), now=NOW) is None


def test_retry_after_is_the_longest_remaining_wait_rounded_up() -> None:
    result = WeatherRefreshResult()
    result.note_cooldown("a", timedelta(seconds=12.2))
    result.note_cooldown("b", timedelta(seconds=40.0))
    result.note_cooldown("c", timedelta(milliseconds=10))
    assert result.cooldown == ["a", "b", "c"]
    assert result.retry_after_seconds == 40


async def test_rejects_more_than_one_day_of_targets() -> None:
    coords = {f"f{i}": (37.5, 127.0) for i in range(MAX_REFRESH_FEATURES + 1)}
    with pytest.raises(ValueError, match="까지"):
        await refresh_weather_locations(cast(Any, object()), coords, map_client=None)


async def test_no_targets_is_a_noop() -> None:
    result = await refresh_weather_locations(cast(Any, object()), {}, map_client=None)
    assert (result.refreshed, result.cooldown, result.retry_after_seconds) == ([], [], None)
