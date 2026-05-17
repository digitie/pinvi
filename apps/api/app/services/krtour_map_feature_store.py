from __future__ import annotations

from typing import Any

from krtour_map.db import (
    FeatureDbContext,
    FeatureDbSettings,
    data_integrity_violations,
    dedup_review_queue,
    feature_db_settings_from_object,
    feature_overrides,
    feature_weather_values,
    initialize_feature_db,
    price_point_from_row,
    price_point_to_row,
    price_points,
    price_value_from_row,
    price_value_to_row,
    price_values,
    provider_sync_state,
    provider_sync_state_from_row,
    provider_sync_state_to_row,
    weather_value_to_row,
)
from krtour_map.db import (
    metadata as feature_metadata,
)
from krtour_map.models import PricePoint, PriceValue, ProviderSyncState, WeatherValue

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


def price_point_insert_values(value: PricePoint) -> dict[str, Any]:
    """Build an insert/update payload for the library-owned price point table."""

    return price_point_to_row(value)


def price_value_insert_values(value: PriceValue) -> dict[str, Any]:
    """Build an insert/update payload for the library-owned price value table."""

    return price_value_to_row(value)


def provider_sync_state_insert_values(value: ProviderSyncState) -> dict[str, Any]:
    """Build an insert/update payload for the library-owned provider sync table."""

    return provider_sync_state_to_row(value)


__all__ = [
    "feature_weather_values",
    "price_points",
    "price_values",
    "provider_sync_state",
    "feature_overrides",
    "dedup_review_queue",
    "data_integrity_violations",
    "initialize_krtour_map_feature_db",
    "krtour_map_feature_db_settings",
    "krtour_map_feature_metadata",
    "price_point_from_row",
    "price_point_insert_values",
    "price_value_from_row",
    "price_value_insert_values",
    "provider_sync_state_from_row",
    "provider_sync_state_insert_values",
    "weather_insert_values",
]
