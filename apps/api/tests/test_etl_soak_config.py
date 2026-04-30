from __future__ import annotations

from pathlib import Path

import pytest

from app.core import etl_config


def test_soak_config_shortens_long_running_dataset_schedules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    config_path = repo_root / "config" / "etl-datasets.soak.json"

    monkeypatch.setenv("TRIPMATE_ETL_CONFIG_PATH", str(config_path))
    etl_config.load_etl_dataset_configs.cache_clear()

    try:
        assert etl_config.get_etl_dataset_config("legal_dong_code_standard").schedule == (
            "5 * * * *"
        )
        assert etl_config.get_etl_dataset_config("juso_road_address_korean").schedule == (
            "10 * * * *"
        )
        assert etl_config.get_etl_dataset_config("fuel_region_code").schedule == "15 * * * *"
        assert etl_config.get_etl_dataset_config("rest_area_master").schedule == "20 * * * *"
        assert etl_config.get_etl_dataset_config("air_quality_station").schedule == (
            "35 * * * *"
        )
        assert etl_config.get_etl_dataset_config("kma_recommended_tour_course").schedule == (
            "45 * * * *"
        )
        assert etl_config.get_etl_dataset_config("kma_beach_catalog").schedule == ("15 * * * *")
        assert etl_config.get_etl_dataset_config("kma_beach_ultra_short_forecast").schedule == (
            "45 */6 * * *"
        )
        assert etl_config.get_etl_dataset_config("kma_beach_tide_sun").schedule == ("10 * * * *")
        assert etl_config.get_etl_dataset_config("khoa_beach_observation").schedule == (
            "20 */6 * * *"
        )
        assert etl_config.get_etl_dataset_config("khoa_beach_index_forecast").schedule == (
            "30 */12 * * *"
        )
        assert (
            etl_config.get_etl_dataset_config("khoa_beach_index_forecast").retry_max_attempts == 0
        )
        assert etl_config.get_etl_dataset_config("mof_beach_info").schedule == ("12 * * * *")
        assert etl_config.get_etl_dataset_config("mof_beach_water_quality").schedule == (
            "22 * * * *"
        )
        assert etl_config.get_etl_dataset_config("public_arboretum_basic").schedule == (
            "55 * * * *"
        )
        assert etl_config.get_etl_dataset_config("public_recreation_forest").schedule == (
            "0 * * * *"
        )
        assert etl_config.get_etl_dataset_config("public_museum_art_gallery").schedule == (
            "5 * * * *"
        )
        assert etl_config.get_etl_dataset_config("public_campground").schedule == ("10 * * * *")
    finally:
        etl_config.load_etl_dataset_configs.cache_clear()


def test_docker_compose_allows_soak_config_and_dataset_mount() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    compose_text = (repo_root / "infra" / "docker-compose.yml").read_text(encoding="utf-8")

    assert (
        "TRIPMATE_ETL_CONFIG_PATH: "
        "${TRIPMATE_ETL_CONFIG_PATH:-/opt/tripmate/config/etl-datasets.json}"
    ) in compose_text
    assert "../dataset:/opt/tripmate/dataset:ro" in compose_text
