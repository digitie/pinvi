from pathlib import Path


def test_initial_migration_keeps_session_tokens_hashed() -> None:
    migration = Path("alembic/versions/20260418_0001_initial_core.py").read_text(encoding="utf-8")

    assert "session_token_hash" in migration
    assert 'session_token"' not in migration


def test_initial_migration_creates_postgis_extension() -> None:
    migration = Path("alembic/versions/20260418_0001_initial_core.py").read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS postgis" in migration


def test_juso_migration_creates_raw_and_code_tables() -> None:
    migration = Path("alembic/versions/20260424_0002_juso_legal_dong_tables.py").read_text(
        encoding="utf-8"
    )

    assert "address_raw_juso_road_address" in migration
    assert "address_code_standard" in migration


def test_juso_address_serving_migration_creates_serving_and_related_jibun_tables() -> None:
    migration = Path(
        "alembic/versions/20260425_0003_juso_address_serving_and_related_jibun.py"
    ).read_text(encoding="utf-8")

    assert "address_serving_juso_road_address" in migration
    assert "address_raw_juso_related_jibun" in migration
    assert "address_serving_juso_related_jibun" in migration


def test_vworld_boundary_migration_creates_raw_and_serving_tables() -> None:
    migration = Path("alembic/versions/20260425_0004_vworld_region_boundaries.py").read_text(
        encoding="utf-8"
    )

    assert "region_boundary_import_batch" in migration
    assert "region_raw_vworld_boundary" in migration
    assert "region_serving_boundary" in migration
    assert "srid=5179" in migration
    assert "srid=4326" in migration


def test_legal_dong_code_csv_migration_preserves_fk_target_rows() -> None:
    migration = Path("alembic/versions/20260425_0005_legal_dong_code_csv_standard.py").read_text(
        encoding="utf-8"
    )

    assert "address_raw_legal_dong_code" in migration
    assert "source_provider" in migration
    assert "is_discontinued" in migration
    assert "fk_asjra_legal_code" in migration
    assert "fk_asjrj_legal_code" in migration
    assert "DELETE FROM address_code_standard" not in migration


def test_data_go_legal_dong_fields_migration_preserves_code_primary_key() -> None:
    migration = Path("alembic/versions/20260425_0006_data_go_legal_dong_fields.py").read_text(
        encoding="utf-8"
    )

    assert "source_created_date" in migration
    assert "source_deleted_date" in migration
    assert "previous_legal_dong_code" in migration
    assert "source_sort_order" in migration
    assert "DROP TABLE address_code_standard" not in migration
    assert "DELETE FROM address_code_standard" not in migration


def test_etl_runtime_migration_adds_logs_notifications_and_user_flags() -> None:
    migration = Path("alembic/versions/20260426_0007_etl_runtime_logs_and_user_flags.py").read_text(
        encoding="utf-8"
    )

    assert "is_admin" in migration
    assert "is_privileged" in migration
    assert "etl_run_logs" in migration
    assert "admin_notifications" in migration
    assert "telegram_system_notification_outbox" in migration
    assert "fk_admin_notifications_etl_run" in migration
    assert "fk_tg_sys_outbox_etl_run" in migration


def test_opinet_fuel_migration_links_provider_regions_to_address_standard() -> None:
    migration = Path("alembic/versions/20260426_0008_opinet_fuel_tables.py").read_text(
        encoding="utf-8"
    )

    assert "fuel_raw_opinet_region_code" in migration
    assert "fuel_serving_opinet_region_code" in migration
    assert "fuel_region_legal_dong_mapping" in migration
    assert "fuel_raw_avg_price" in migration
    assert "fuel_serving_avg_price" in migration
    assert "fuel_raw_lowest_station" in migration
    assert "fuel_serving_lowest_station" in migration
    assert "fk_fsorc_address_code_standard" in migration
    assert "fk_frlm_legal_dong_code" in migration
    assert "fk_fsls_legal_dong_code" in migration
    assert "uq_fsap_region_trade_fuel" in migration
    assert "uq_fsls_region_fuel_station_timestamp" in migration


def test_rest_area_migration_keeps_raw_and_serving_layers_separate() -> None:
    migration = Path("alembic/versions/20260426_0009_rest_area_tables.py").read_text(
        encoding="utf-8"
    )

    assert "rest_area_raw_master" in migration
    assert "rest_area_serving_master" in migration
    assert "rest_area_raw_oil_price" in migration
    assert "rest_area_serving_oil_price" in migration
    assert "rest_area_raw_service" in migration
    assert "rest_area_serving_service" in migration
    assert "fk_rasop_svar_cd" in migration
    assert "fk_rass_svar_cd" in migration
    assert "uq_rasop_svar_fuel_collected_at" in migration
    assert "uq_rass_svar_service_snapshot" in migration


def test_weather_air_quality_tour_migration_links_to_address_standard() -> None:
    migration = Path("alembic/versions/20260426_0010_weather_air_quality_tour_tables.py").read_text(
        encoding="utf-8"
    )

    assert "weather_short_term_grid_mapping" in migration
    assert "weather_raw_short_term" in migration
    assert "weather_serving_short_term" in migration
    assert "weather_kma_alert_station_code" in migration
    assert "weather_raw_kma_alert" in migration
    assert "weather_serving_kma_alert" in migration
    assert "air_quality_raw_station" in migration
    assert "air_quality_serving_station" in migration
    assert "air_quality_raw_forecast" in migration
    assert "air_quality_serving_forecast" in migration
    assert "air_quality_raw_sido_measurement" in migration
    assert "air_quality_serving_sido_measurement" in migration
    assert "tour_course_raw_kma_point" in migration
    assert "kma_recommended_tour_course" in migration
    assert "fk_wstgm_legal_dong_code" in migration
    assert "fk_aqss_legal_dong_code" in migration
    assert "fk_krt_legal_dong_code" in migration
    assert "uq_wsst_endpoint_grid_time_category" in migration
    assert "uq_krt_course_file_spot" in migration


def test_mid_term_weather_migration_keeps_provider_codes_separate_from_address_codes() -> None:
    migration = Path(
        "alembic/versions/20260426_0011_weather_mid_term_and_tour_weather.py"
    ).read_text(encoding="utf-8")

    assert "weather_mid_forecast_region" in migration
    assert "weather_mid_region_address_mapping" in migration
    assert "weather_raw_mid_term" in migration
    assert "weather_serving_mid_term" in migration
    assert "provider_region_id" in migration
    assert "sido_code" in migration
    assert "sigungu_code" in migration
    assert "legal_dong_code_prefix" in migration
    assert "fk_wmram_forecast_region" in migration
    assert "tour_course_raw_kma_spot_weather" in migration
    assert "tour_course_serving_kma_spot_weather" in migration
    assert "no2_grade" in migration
    assert "pm10_flag" in migration
    assert migration.count("postgresql_nulls_not_distinct=True") == 2
