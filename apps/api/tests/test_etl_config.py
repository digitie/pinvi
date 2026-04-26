from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import etl_config


def test_etl_dataset_config_uses_checked_in_defaults() -> None:
    config = etl_config.get_etl_dataset_config("juso_road_address_korean")

    assert config.schedule == "0 4 10-31 * *"
    assert config.retry_interval_seconds == 300
    assert config.retry_max_attempts == 3
    assert config.failure_admin_notification_enabled is True
    assert config.failure_telegram_notification_enabled is True


def test_fuel_etl_dataset_configs_have_distinct_retry_and_freshness_targets() -> None:
    region_config = etl_config.get_etl_dataset_config("fuel_region_code")
    average_config = etl_config.get_etl_dataset_config("fuel_avg_price")
    lowest_config = etl_config.get_etl_dataset_config("fuel_lowest_station")

    assert region_config.schedule == "0 4 1 1,4,7,10 *"
    assert region_config.retry_interval_seconds == 1800
    assert region_config.retry_max_attempts == 3
    assert region_config.freshness_target_minutes == 131400
    assert average_config.schedule == "20 5,13,21 * * *"
    assert average_config.retry_interval_seconds == 300
    assert average_config.freshness_target_minutes == 720
    assert lowest_config.schedule == "40 5,13,21 * * *"
    assert lowest_config.retry_interval_seconds == 300
    assert lowest_config.freshness_target_minutes == 720


def test_rest_area_etl_dataset_configs_match_collection_policy() -> None:
    master_config = etl_config.get_etl_dataset_config("rest_area_master")
    oil_config = etl_config.get_etl_dataset_config("rest_area_oil_price")
    service_config = etl_config.get_etl_dataset_config("rest_area_svcs")

    assert master_config.schedule == "10 4 1 * *"
    assert master_config.retry_interval_seconds == 1800
    assert master_config.freshness_target_minutes == 44640
    assert oil_config.schedule == "10 6,18 * * *"
    assert oil_config.retry_interval_seconds == 600
    assert oil_config.freshness_target_minutes == 1440
    assert service_config.schedule == "30 4 1 * *"
    assert service_config.retry_interval_seconds == 1800
    assert service_config.freshness_target_minutes == 44640


def test_weather_and_air_quality_etl_dataset_configs_respect_quota_policy() -> None:
    short_term_config = etl_config.get_etl_dataset_config("weather_short_term")
    alert_config = etl_config.get_etl_dataset_config("weather_kma_alert")
    station_config = etl_config.get_etl_dataset_config("air_quality_station")
    forecast_config = etl_config.get_etl_dataset_config("air_quality_forecast")
    measurement_config = etl_config.get_etl_dataset_config("air_quality_sido_measurement")
    tour_config = etl_config.get_etl_dataset_config("kma_recommended_tour_course")

    assert short_term_config.schedule == "*/30 * * * *"
    assert short_term_config.retry_interval_seconds == 300
    assert short_term_config.freshness_target_minutes == 60
    assert alert_config.schedule == "*/30 * * * *"
    assert alert_config.retry_interval_seconds == 300
    assert alert_config.freshness_target_minutes == 60
    assert station_config.schedule == "20 4 * * *"
    assert station_config.retry_interval_seconds == 1800
    assert station_config.freshness_target_minutes == 10080
    assert forecast_config.schedule == "15 5,11,17,23 * * *"
    assert forecast_config.retry_interval_seconds == 600
    assert forecast_config.freshness_target_minutes == 720
    assert measurement_config.schedule == "25 * * * *"
    assert measurement_config.retry_interval_seconds == 600
    assert measurement_config.freshness_target_minutes == 120
    assert tour_config.schedule == "0 5 1 3 *"
    assert tour_config.retry_interval_seconds == 1800
    assert tour_config.freshness_target_minutes == 525600


def test_etl_dataset_config_can_be_overridden_by_json_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "etl-datasets.json"
    config_path.write_text(
        json.dumps(
            {
                "datasets": {
                    "juso_road_address_korean": {
                        "schedule": "0 5 10-31 * *",
                        "retry_interval_seconds": 600,
                        "retry_max_attempts": 5,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRIPMATE_ETL_CONFIG_PATH", str(config_path))
    etl_config.load_etl_dataset_configs.cache_clear()

    try:
        config = etl_config.get_etl_dataset_config("juso_road_address_korean")
        assert config.schedule == "0 5 10-31 * *"
        assert config.retry_interval_seconds == 600
        assert config.retry_max_attempts == 5
    finally:
        etl_config.load_etl_dataset_configs.cache_clear()


def test_etl_dataset_config_rejects_string_boolean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "etl-datasets.json"
    config_path.write_text(
        json.dumps(
            {
                "datasets": {
                    "juso_road_address_korean": {
                        "failure_admin_notification_enabled": "false",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRIPMATE_ETL_CONFIG_PATH", str(config_path))
    etl_config.load_etl_dataset_configs.cache_clear()

    try:
        with pytest.raises(ValueError, match="must be a boolean"):
            etl_config.get_etl_dataset_config("juso_road_address_korean")
    finally:
        etl_config.load_etl_dataset_configs.cache_clear()


def test_etl_dataset_config_rejects_negative_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "etl-datasets.json"
    config_path.write_text(
        json.dumps(
            {
                "datasets": {
                    "juso_road_address_korean": {
                        "retry_interval_seconds": -1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRIPMATE_ETL_CONFIG_PATH", str(config_path))
    etl_config.load_etl_dataset_configs.cache_clear()

    try:
        with pytest.raises(ValueError, match="must be >= 0"):
            etl_config.get_etl_dataset_config("juso_road_address_korean")
    finally:
        etl_config.load_etl_dataset_configs.cache_clear()
