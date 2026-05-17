from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from krtour_map import make_source_record_key
from sqlalchemy import CheckConstraint

from app.core.krtour_map_contract import (
    FORECAST_STYLE_VALUES,
    MAP_FEATURE_TYPE_VALUES,
    SOURCE_ROLE_VALUES,
    WEATHER_DOMAIN_VALUES,
)
from app.models.etl import ProviderSyncState
from app.models.place import MapFeature, MapFeatureSourceLink, MapFeatureWeatherValue, SourceRecord
from app.services.krtour_map_contract import (
    map_feature_to_krtour_feature,
    provider_sync_state_to_krtour_state,
    raw_ref_from_source_record,
    source_record_to_krtour_source,
    weather_value_to_krtour_value,
)


def test_map_feature_constraints_follow_krtour_map_contract_values() -> None:
    feature_type_constraint = _check_constraint_sql(MapFeature, "ck_map_features_feature_type")
    source_role_constraint = _check_constraint_sql(
        MapFeatureSourceLink, "ck_map_feature_source_links_role"
    )
    weather_domain_constraint = _check_constraint_sql(
        MapFeatureWeatherValue, "ck_map_feature_weather_values_domain"
    )
    forecast_style_constraint = _check_constraint_sql(
        MapFeatureWeatherValue, "ck_map_feature_weather_values_style"
    )

    for value in MAP_FEATURE_TYPE_VALUES:
        assert f"'{value}'" in feature_type_constraint
    for value in SOURCE_ROLE_VALUES:
        assert f"'{value}'" in source_role_constraint
    for value in WEATHER_DOMAIN_VALUES:
        assert f"'{value}'" in weather_domain_constraint
    for value in FORECAST_STYLE_VALUES:
        assert f"'{value}'" in forecast_style_constraint


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
    assert exported.address.bjd_code == "1117010100"
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


def test_weather_and_sync_state_export_to_krtour_contracts() -> None:
    now = datetime(2026, 5, 17, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    weather = MapFeatureWeatherValue(
        provider="kma",
        weather_domain="kma_short_forecast",
        forecast_style="short",
        metric_key="TMP",
        metric_name="기온",
        value_number=Decimal("22.5"),
        unit="C",
        issued_at=now,
        valid_at=now,
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

    exported_weather = weather_value_to_krtour_value(weather, feature_id="place-001")
    exported_state = provider_sync_state_to_krtour_state(sync_state)

    assert exported_weather.provider == "python-kma-api"
    assert exported_weather.identity()[0] == "place-001"
    assert exported_state.provider == "python-kma-api"
    assert exported_state.identity() == ("python-kma-api", "short_forecast", "grid:60,127")


def _check_constraint_sql(model: type[object], constraint_name: str) -> str:
    constraint = next(
        constraint
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == constraint_name
    )
    return str(constraint.sqltext)
