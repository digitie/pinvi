from __future__ import annotations

from typing import Any

from krtour_map.db import (
    feature_weather_values,
    metadata as feature_metadata,
    weather_value_to_row,
)
from krtour_map.models import WeatherValue


def krtour_map_feature_metadata() -> Any:
    """Return the feature DB metadata owned by python-krtour-map."""

    return feature_metadata


def weather_insert_values(value: WeatherValue) -> dict[str, Any]:
    """Build an insert/update payload for the library-owned weather table."""

    return weather_value_to_row(value)


__all__ = [
    "feature_weather_values",
    "krtour_map_feature_metadata",
    "weather_insert_values",
]
