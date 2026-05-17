from __future__ import annotations

from typing import Any

from krtour_map.db import (
    FeatureDbContext,
    FeatureDbSettings,
    feature_weather_values,
    feature_db_settings_from_object,
    initialize_feature_db,
    metadata as feature_metadata,
    weather_value_to_row,
)
from krtour_map.models import WeatherValue

from app.core.config import Settings, get_settings


def krtour_map_feature_metadata() -> Any:
    """Return the feature DB metadata owned by python-krtour-map."""

    return feature_metadata


def krtour_map_feature_db_settings(settings: Settings | None = None) -> FeatureDbSettings:
    """Build python-krtour-map DB settings from TripMate settings."""

    return feature_db_settings_from_object(settings or get_settings())


def initialize_krtour_map_feature_db(
    settings: Settings | None = None,
    *,
    create_schema: bool = True,
) -> FeatureDbContext:
    """Initialize the library-owned feature DB using TripMate DB settings."""

    return initialize_feature_db(
        krtour_map_feature_db_settings(settings),
        create_schema=create_schema,
    )


def weather_insert_values(value: WeatherValue) -> dict[str, Any]:
    """Build an insert/update payload for the library-owned weather table."""

    return weather_value_to_row(value)


__all__ = [
    "feature_weather_values",
    "initialize_krtour_map_feature_db",
    "krtour_map_feature_db_settings",
    "krtour_map_feature_metadata",
    "weather_insert_values",
]
