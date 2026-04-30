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


def test_database_architecture_index_migration_adds_missing_fk_indexes() -> None:
    migration = Path("alembic/versions/20260427_0012_database_architecture_indexes.py").read_text(
        encoding="utf-8"
    )

    assert "ix_admin_notifications_etl_run_log_id" in migration
    assert "ix_tg_sys_outbox_etl_run_log_id" in migration
    assert "ix_rsb_address_code_standard_code" in migration
    assert "ix_rsb_import_batch_id" in migration
    assert "ix_rsb_raw_boundary_id" in migration
    assert "ix_wska_stn_id" in migration


def test_default_admin_seed_migration_uses_hashed_password_and_admin_flags() -> None:
    migration = Path("alembic/versions/20260427_0013_seed_default_admin.py").read_text(
        encoding="utf-8"
    )

    assert "admin@ad.min" in migration
    assert "pbkdf2_sha256" in migration
    assert "is_admin" in migration
    assert "is_privileged" in migration
    assert "password_hash" in migration
    assert "VALUES ('admin'" not in migration


def test_place_canonical_migration_creates_public_data_place_tables() -> None:
    migration = Path("alembic/versions/20260427_0015_place_canonical_tables.py").read_text(
        encoding="utf-8"
    )

    assert 'down_revision: str | None = "20260427_0013"' in migration
    assert "place_categories" in migration
    assert "places" in migration
    assert "place_source_records" in migration
    assert "place_source_links" in migration
    assert "place_provider_refs" in migration
    assert "place_web_links" in migration
    assert "source_specific_attributes" in migration
    assert "fk_places_legal_dong_code" in migration
    assert "fk_places_primary_category_code" in migration
    assert "uq_place_provider_refs_provider_dataset_place" in migration
    assert "postgresql_nulls_not_distinct=True" in migration
    assert "03030201" in migration
    assert "01040201" in migration
    assert "ix_places_geom" in migration


def test_user_registration_migration_adds_profile_and_email_tokens() -> None:
    migration = Path("alembic/versions/20260427_0016_user_registration_profile.py").read_text(
        encoding="utf-8"
    )

    assert "email_verification_tokens" in migration
    assert "account_status" in migration
    assert "system_role" in migration
    assert "birth_year_month" in migration
    assert "residence_sigungu_code" in migration
    assert "fk_users_residence_sigungu_code" in migration
    assert "fk_users_created_by_user_id" in migration
    assert "token_hash" in migration
    assert "token_value" not in migration
    assert "plain_token" not in migration


def test_public_cultural_festival_migration_keeps_raw_serving_and_address_keys() -> None:
    migration = Path("alembic/versions/20260428_0017_public_cultural_festival.py").read_text(
        encoding="utf-8"
    )

    assert "tour_raw_public_cultural_festival" in migration
    assert "tour_serving_public_cultural_festival" in migration
    assert "uq_trpcf_provider_source_hash" in migration
    assert "uq_tspcf_provider_source_record" in migration
    assert "place_join_key" in migration
    assert "road_name_code" in migration
    assert "road_address_management_no" in migration
    assert "fk_tspcf_legal_dong_code" in migration
    assert "POINT" in migration
    assert "srid=4326" in migration
    assert "ix_tspcf_geom" in migration


def test_map_feature_replacement_migration_links_trip_items_to_features() -> None:
    migration = Path("alembic/versions/20260429_0021_map_feature_schema.py").read_text(
        encoding="utf-8"
    )

    assert "trip_plan_items" in migration
    assert "resource_type" in migration
    assert "map_feature_id" in migration
    assert "festival_id" in migration
    assert "fk_tpi_map_feature_id" in migration
    assert "ck_tpi_resource_type" in migration
    assert "ck_tpi_map_feature_type_match" in migration
    assert "ck_tpi_single_fk_resource" in migration


def test_map_feature_replacement_migration_links_beach_weather_to_features() -> None:
    migration = Path("alembic/versions/20260429_0021_map_feature_schema.py").read_text(
        encoding="utf-8"
    )

    assert "weather_beach_location" in migration
    assert "weather_serving_beach" in migration
    assert "map_features" in migration
    assert "fk_wbl_map_feature_id" in migration
    assert "fk_wsb_map_feature_id" in migration
    assert "ix_wbl_map_feature_id" in migration
    assert "ix_wsb_map_feature_id" in migration


def test_integrated_beach_source_migration_keeps_profile_refs_and_measurements() -> None:
    migration = Path("alembic/versions/20260428_0020_beach_domain_tables.py").read_text(
        encoding="utf-8"
    )

    assert "beach_profiles" in migration
    assert "beach_provider_refs" in migration
    assert "beach_source_records" in migration
    assert "beach_observations" in migration
    assert "beach_index_forecasts" in migration
    assert "beach_water_quality_measurements" in migration
    assert "fk_beach_profiles_legal_dong_code" in migration
    assert "uq_beach_provider_refs_provider_dataset_id" in migration
    assert "uq_beach_source_records_provider_dataset_record_hash" in migration
    assert "uq_beach_observations_provider_beach_time" in migration
    assert "uq_beach_index_forecasts_provider_beach_date_slot" in migration
    assert "uq_beach_water_quality_measurements_provider_source_key" in migration
    assert "POINT" in migration
    assert "srid=4326" in migration
    assert "ix_beach_profiles_geom" in migration


def test_map_feature_replacement_migration_retargets_beach_profiles() -> None:
    migration = Path("alembic/versions/20260429_0021_map_feature_schema.py").read_text(
        encoding="utf-8"
    )

    assert "beach_profiles" in migration
    assert "map_feature_id" in migration
    assert "fk_beach_profiles_map_feature_id" in migration
    assert "ix_beach_profiles_map_feature_id" in migration


def test_ocean_activity_index_migration_keeps_raw_location_and_forecast_layers() -> None:
    migration = Path("alembic/versions/20260429_0022_ocean_activity_index_tables.py").read_text(
        encoding="utf-8"
    )

    assert "ocean_activity_index_locations" in migration
    assert "ocean_activity_index_source_records" in migration
    assert "ocean_activity_index_forecasts" in migration
    assert "fk_oail_legal_dong_code" in migration
    assert "fk_oaif_location_id" in migration
    assert "fk_oaif_source_record_id" in migration
    assert "uq_oail_provider_dataset_location" in migration
    assert "uq_oaisr_provider_dataset_record_hash" in migration
    assert "uq_oaif_provider_location_date_slot_time" in migration
    assert "POINT" in migration
    assert "srid=4326" in migration
    assert "ix_oail_geom" in migration
