from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from app.core.config import get_settings


@dataclass(frozen=True)
class EtlDatasetRuntimeConfig:
    dataset_key: str
    schedule: str
    retry_interval_seconds: int
    retry_max_attempts: int
    failure_admin_notification_enabled: bool
    failure_telegram_notification_enabled: bool
    freshness_target_minutes: int | None = None


DEFAULT_ETL_DATASET_CONFIGS: dict[str, EtlDatasetRuntimeConfig] = {
    "legal_dong_code_standard": EtlDatasetRuntimeConfig(
        dataset_key="legal_dong_code_standard",
        schedule="30 4 15 2,5,8,11 *",
        retry_interval_seconds=300,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=131400,
    ),
    "juso_road_address_korean": EtlDatasetRuntimeConfig(
        dataset_key="juso_road_address_korean",
        schedule="0 4 10-31 * *",
        retry_interval_seconds=300,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=44640,
    ),
    "vworld_boundary_upload": EtlDatasetRuntimeConfig(
        dataset_key="vworld_boundary_upload",
        schedule="manual",
        retry_interval_seconds=300,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=None,
    ),
    "fuel_region_code": EtlDatasetRuntimeConfig(
        dataset_key="fuel_region_code",
        schedule="0 4 1 1,4,7,10 *",
        retry_interval_seconds=1800,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=131400,
    ),
    "fuel_avg_price": EtlDatasetRuntimeConfig(
        dataset_key="fuel_avg_price",
        schedule="20 5,13,21 * * *",
        retry_interval_seconds=300,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=720,
    ),
    "fuel_lowest_station": EtlDatasetRuntimeConfig(
        dataset_key="fuel_lowest_station",
        schedule="40 5,13,21 * * *",
        retry_interval_seconds=300,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=720,
    ),
    "rest_area_master": EtlDatasetRuntimeConfig(
        dataset_key="rest_area_master",
        schedule="10 4 1 * *",
        retry_interval_seconds=1800,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=44640,
    ),
    "rest_area_oil_price": EtlDatasetRuntimeConfig(
        dataset_key="rest_area_oil_price",
        schedule="10 6,18 * * *",
        retry_interval_seconds=600,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=1440,
    ),
    "rest_area_svcs": EtlDatasetRuntimeConfig(
        dataset_key="rest_area_svcs",
        schedule="30 4 1 * *",
        retry_interval_seconds=1800,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=44640,
    ),
    "weather_short_term": EtlDatasetRuntimeConfig(
        dataset_key="weather_short_term",
        schedule="*/30 * * * *",
        retry_interval_seconds=300,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=60,
    ),
    "weather_kma_alert": EtlDatasetRuntimeConfig(
        dataset_key="weather_kma_alert",
        schedule="*/30 * * * *",
        retry_interval_seconds=300,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=60,
    ),
    "weather_mid_term": EtlDatasetRuntimeConfig(
        dataset_key="weather_mid_term",
        schedule="20 6,18 * * *",
        retry_interval_seconds=600,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=1440,
    ),
    "air_quality_station": EtlDatasetRuntimeConfig(
        dataset_key="air_quality_station",
        schedule="20 4 * * *",
        retry_interval_seconds=1800,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=10080,
    ),
    "air_quality_forecast": EtlDatasetRuntimeConfig(
        dataset_key="air_quality_forecast",
        schedule="15 5,11,17,23 * * *",
        retry_interval_seconds=600,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=720,
    ),
    "air_quality_sido_measurement": EtlDatasetRuntimeConfig(
        dataset_key="air_quality_sido_measurement",
        schedule="25 * * * *",
        retry_interval_seconds=600,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=120,
    ),
    "kma_recommended_tour_course": EtlDatasetRuntimeConfig(
        dataset_key="kma_recommended_tour_course",
        schedule="0 5 1 3 *",
        retry_interval_seconds=1800,
        retry_max_attempts=3,
        failure_admin_notification_enabled=True,
        failure_telegram_notification_enabled=True,
        freshness_target_minutes=525600,
    ),
}


def get_etl_dataset_config(dataset_key: str) -> EtlDatasetRuntimeConfig:
    configs = load_etl_dataset_configs()
    try:
        return configs[dataset_key]
    except KeyError as exc:
        supported = ", ".join(sorted(configs))
        raise KeyError(f"Unknown ETL dataset key {dataset_key!r}. Supported: {supported}") from exc


@lru_cache
def load_etl_dataset_configs() -> dict[str, EtlDatasetRuntimeConfig]:
    config_path = os.environ.get("TRIPMATE_ETL_CONFIG_PATH", get_settings().etl_config_path)
    if not config_path:
        return DEFAULT_ETL_DATASET_CONFIGS

    path = Path(config_path)
    if not path.exists():
        return DEFAULT_ETL_DATASET_CONFIGS

    raw_config = json.loads(path.read_text(encoding="utf-8"))
    raw_datasets = cast(dict[str, Any], raw_config.get("datasets", {}))
    merged = dict(DEFAULT_ETL_DATASET_CONFIGS)
    for dataset_key, values in raw_datasets.items():
        if not isinstance(values, dict):
            raise ValueError(f"ETL config for {dataset_key!r} must be an object.")
        default = merged.get(
            dataset_key,
            EtlDatasetRuntimeConfig(
                dataset_key=dataset_key,
                schedule="manual",
                retry_interval_seconds=300,
                retry_max_attempts=3,
                failure_admin_notification_enabled=True,
                failure_telegram_notification_enabled=True,
            ),
        )
        merged[dataset_key] = _build_config(dataset_key, default, values)
    return merged


def _build_config(
    dataset_key: str,
    default: EtlDatasetRuntimeConfig,
    values: dict[str, Any],
) -> EtlDatasetRuntimeConfig:
    schedule = str(values.get("schedule", default.schedule)).strip()
    if not schedule:
        raise ValueError(f"{dataset_key}: schedule cannot be empty.")

    retry_interval_seconds = _read_non_negative_int(
        dataset_key,
        values,
        "retry_interval_seconds",
        default.retry_interval_seconds,
    )
    retry_max_attempts = _read_non_negative_int(
        dataset_key,
        values,
        "retry_max_attempts",
        default.retry_max_attempts,
    )

    freshness_value = values.get("freshness_target_minutes", default.freshness_target_minutes)
    freshness_target_minutes = (
        None
        if freshness_value is None
        else _coerce_non_negative_int(dataset_key, "freshness_target_minutes", freshness_value)
    )

    return EtlDatasetRuntimeConfig(
        dataset_key=dataset_key,
        schedule=schedule,
        retry_interval_seconds=retry_interval_seconds,
        retry_max_attempts=retry_max_attempts,
        failure_admin_notification_enabled=_read_bool(
            dataset_key,
            values,
            "failure_admin_notification_enabled",
            default.failure_admin_notification_enabled,
        ),
        failure_telegram_notification_enabled=_read_bool(
            dataset_key,
            values,
            "failure_telegram_notification_enabled",
            default.failure_telegram_notification_enabled,
        ),
        freshness_target_minutes=freshness_target_minutes,
    )


def _read_non_negative_int(
    dataset_key: str,
    values: dict[str, Any],
    key: str,
    default: int,
) -> int:
    return _coerce_non_negative_int(dataset_key, key, values.get(key, default))


def _coerce_non_negative_int(dataset_key: str, key: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{dataset_key}: {key} must be an integer, not boolean.")
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{dataset_key}: {key} must be an integer.") from exc
    if resolved < 0:
        raise ValueError(f"{dataset_key}: {key} must be >= 0.")
    return resolved


def _read_bool(
    dataset_key: str,
    values: dict[str, Any],
    key: str,
    default: bool,
) -> bool:
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{dataset_key}: {key} must be a boolean.")
    return value
