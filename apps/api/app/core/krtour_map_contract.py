from __future__ import annotations

from collections.abc import Iterable

from krtour_map import (
    FeatureKind,
    FeatureStatus,
    ForecastStyle,
    SourceRole,
    WeatherDomain,
)

FEATURE_KIND_VALUES = tuple(kind.value for kind in FeatureKind)
FEATURE_STATUS_VALUES = tuple(
    status.value for status in (FeatureStatus.ACTIVE, FeatureStatus.HIDDEN, FeatureStatus.BROKEN)
)
MAP_FEATURE_TYPE_VALUES = tuple(
    kind.value
    for kind in (
        FeatureKind.PLACE,
        FeatureKind.EVENT,
        FeatureKind.ROUTE,
        FeatureKind.AREA,
        FeatureKind.NOTICE,
    )
)
MAP_FEATURE_STATUS_VALUES = (
    FeatureStatus.DRAFT.value,
    FeatureStatus.ACTIVE.value,
    FeatureStatus.INACTIVE.value,
    "temporarily_closed",
    FeatureStatus.DELETED.value,
)
SOURCE_ROLE_VALUES = tuple(role.value for role in SourceRole)
WEATHER_DOMAIN_VALUES = tuple(domain.value for domain in WeatherDomain)
FORECAST_STYLE_VALUES = tuple(style.value for style in ForecastStyle)


def sql_in_values(values: Iterable[str]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"
