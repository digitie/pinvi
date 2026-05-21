from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from krtour_map import (
    PricePoint,
    PriceValue,
    WeatherValue,
    make_source_record_key,
)
from krtour_map import (
    ProviderSyncState as KrtourProviderSyncState,
)
from sqlalchemy import CheckConstraint

from app.core.config import Settings
from app.core.krtour_map_contract import (
    FORECAST_STYLE_VALUES,
    MAP_FEATURE_TYPE_VALUES,
    SOURCE_ROLE_VALUES,
    WEATHER_DOMAIN_VALUES,
)
from app.models.etl import ProviderSyncState
from app.models.place import MapFeature, MapFeatureSourceLink, SourceRecord
from app.services.krtour_map import feature_to_tripmate_snapshot
from app.services.krtour_map_contract import (
    map_feature_to_krtour_feature,
    provider_sync_state_to_krtour_state,
    raw_ref_from_source_record,
    source_record_to_krtour_source,
)
from app.services.krtour_map_feature_store import (
    data_integrity_violations,
    dedup_review_queue,
    feature_overrides,
    feature_weather_values,
    initialize_krtour_map_feature_db,
    krtour_map_feature_db_settings,
    krtour_map_feature_metadata,
    price_point_insert_values,
    price_points,
    price_value_insert_values,
    price_values,
    provider_sync_state,
    provider_sync_state_insert_values,
    weather_insert_values,
)


def test_map_feature_constraints_follow_krtour_map_contract_values() -> None:
    feature_type_constraint = _check_constraint_sql(MapFeature, "ck_map_features_feature_type")
    source_role_constraint = _check_constraint_sql(
        MapFeatureSourceLink, "ck_map_feature_source_links_role"
    )

    for value in MAP_FEATURE_TYPE_VALUES:
        assert f"'{value}'" in feature_type_constraint
    for value in SOURCE_ROLE_VALUES:
        assert f"'{value}'" in source_role_constraint
    assert "feature_weather_values" in krtour_map_feature_metadata().tables
    assert "price_points" in krtour_map_feature_metadata().tables
    assert "price_values" in krtour_map_feature_metadata().tables
    assert "provider_sync_state" in krtour_map_feature_metadata().tables
    assert "feature_overrides" in krtour_map_feature_metadata().tables
    assert "dedup_review_queue" in krtour_map_feature_metadata().tables
    assert "data_integrity_violations" in krtour_map_feature_metadata().tables
    assert "map_feature_weather_values" not in krtour_map_feature_metadata().tables
    assert WEATHER_DOMAIN_VALUES
    assert FORECAST_STYLE_VALUES


def test_map_feature_can_export_to_krtour_feature_contract() -> None:
    now = datetime(2026, 5, 17, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    feature = MapFeature(
        public_id="place-001",
        feature_type="place",
        name="서울역",
        display_name="서울역",
        normalized_name="서울역",
        category_name="교통",
        geom="POINT(126.972 37.555)",
        geometry_kind="point",
        centroid="POINT(126.972 37.555)",
        longitude=Decimal("126.97200000"),
        latitude=Decimal("37.55500000"),
        road_address="서울특별시 용산구 한강대로 405",
        legal_dong_code="1117010100",
        website_url="https://example.com/seoul-station",
        status="active",
        is_visible=True,
        extra={"marker_icon": "train", "marker_color": "#155EEF"},
        first_seen_at=now,
    )

    exported = map_feature_to_krtour_feature(feature)

    assert exported.feature_id == "place-001"
    assert exported.kind == "place"
    assert exported.coord.longitude == 126.972
    assert exported.address.legal_dong_code == "1117010100"
    assert exported.urls.homepage is not None
    assert exported.marker_icon == "train"


def test_source_record_contract_normalizes_provider_and_raw_ref() -> None:
    now = datetime(2026, 5, 17, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    record = SourceRecord(
        provider="opinet",
        dataset_key="station_price",
        source_entity_type="station",
        source_entity_id="A001",
        raw_payload_hash="payload-hash",
        raw_name="테스트 주유소",
        raw_data={"price": 1650},
        fetched_at=now,
        imported_at=now,
    )

    exported = source_record_to_krtour_source(record)
    raw_ref = raw_ref_from_source_record(record)
    expected_key = make_source_record_key(
        provider="python-opinet-api",
        dataset_key="station_price",
        source_entity_type="station",
        source_entity_id="A001",
        raw_payload_hash="payload-hash",
    )

    assert exported.provider == "python-opinet-api"
    assert exported.key() == expected_key
    assert raw_ref.provider == "python-opinet-api"
    assert raw_ref.payload_hash == "payload-hash"


def test_weather_uses_krtour_map_feature_db_and_sync_state_exports() -> None:
    now = datetime(2026, 5, 17, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    weather = WeatherValue(
        feature_id="place-001",
        provider="kma",
        weather_domain="kma_short_forecast",
        forecast_style="short",
        timeline_bucket="short",
        metric_key="TMP",
        source_metric_key="TMP",
        source_metric_name="temperature",
        metric_name="기온",
        value_number=Decimal("22.5"),
        unit="C",
        issued_at=now,
        valid_at=now,
        valid_from=now,
        valid_until=now,
        normalization_version="weather-feature-v1",
        payload={"category": "TMP"},
        collected_at=now,
    )
    sync_state = ProviderSyncState(
        provider="kma",
        dataset_key="short_forecast",
        sync_scope="grid:60,127",
        status="active",
        cursor={"base_date": "20260517"},
        updated_at=now,
    )

    row = weather_insert_values(weather)
    exported_state = provider_sync_state_to_krtour_state(sync_state)

    assert feature_weather_values.name == "feature_weather_values"
    assert row["provider"] == "python-kma-api"
    assert row["timeline_bucket"] == "short"
    assert row["source_metric_key"] == "TMP"
    assert row["normalization_version"] == "weather-feature-v1"
    assert exported_state.provider == "python-kma-api"
    assert exported_state.identity() == ("python-kma-api", "short_forecast", "grid:60,127")


def test_latest_krtour_map_tables_are_imported_directly() -> None:
    now = datetime(2026, 5, 17, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    point = PricePoint(feature_id="price-001", price_category="fuel", retention_days=3650)
    price = PriceValue(
        feature_id="price-001",
        item_key="gasoline",
        observed_at=now,
        value=Decimal("1699"),
        payload_hash="price-hash",
    )
    sync_state = KrtourProviderSyncState(
        provider="kma",
        dataset_key="short_forecast",
        sync_scope="grid:60,127",
        cursor={"base_date": "20260517"},
        updated_at=now,
    )

    assert price_points.name == "price_points"
    assert price_values.name == "price_values"
    assert provider_sync_state.name == "provider_sync_state"
    assert feature_overrides.name == "feature_overrides"
    assert dedup_review_queue.name == "dedup_review_queue"
    assert data_integrity_violations.name == "data_integrity_violations"

    assert price_point_insert_values(point)["retention_days"] == 3650
    assert price_value_insert_values(price)["currency"] == "KRW"
    assert provider_sync_state_insert_values(sync_state)["provider"] == "python-kma-api"


def test_feature_db_initializes_from_tripmate_settings() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:")

    feature_settings = krtour_map_feature_db_settings(settings)
    context = initialize_krtour_map_feature_db(settings)
    try:
        assert feature_settings.database_url == settings.database_url
        assert context.engine.dialect.name == "sqlite"
        assert "feature_weather_values" in krtour_map_feature_metadata().tables
    finally:
        context.dispose()


def test_tripmate_krtour_map_adapter_is_function_based_not_rest_client() -> None:
    adapter = Path("app/services/krtour_map.py").read_text(encoding="utf-8")
    docs = Path("../../docs/architecture/krtour-map-library.md").read_text(encoding="utf-8")

    assert "get_feature(feature_id)" in docs
    assert "REST API" in docs
    assert "base_url" not in adapter
    assert "requests" not in adapter
    assert "aiohttp" not in adapter
    assert "httpx" not in adapter


def test_krtour_map_feature_snapshot_conversion_uses_dto_shape() -> None:
    class FeatureDto:
        def model_dump(self, mode: str) -> dict:
            assert mode == "json"
            return {
                "feature_id": "heritage:seoul:1",
                "name": "국가유산",
                "category": "heritage",
                "coord": {"longitude": 126.978, "latitude": 37.566},
                "address": {"road_address": "서울특별시"},
                "marker_icon": "museum",
                "marker_color": "#4466aa",
                "urls": {"homepage": "https://example.test"},
                "detail": {"kind": "tour"},
                "raw_refs": [{"provider": "python-krheritage-api"}],
            }

    snapshot = feature_to_tripmate_snapshot(FeatureDto())

    assert snapshot["source"] == "python-krtour-map"
    assert snapshot["feature_id"] == "heritage:seoul:1"
    assert snapshot["longitude"] == 126.978
    assert snapshot["raw_refs"] == [{"provider": "python-krheritage-api"}]


def _check_constraint_sql(model: type[object], constraint_name: str) -> str:
    constraint = next(
        constraint
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == constraint_name
    )
    return str(constraint.sqltext)
