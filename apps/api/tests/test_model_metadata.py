from typing import cast

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    Table,
    UniqueConstraint,
)

from app.db.base import Base
from app.models import (
    AddressCodeStandard,
    AddressRawJusoRelatedJibun,
    AddressRawJusoRoadAddress,
    AddressRawLegalDongCode,
    AddressServingJusoRelatedJibun,
    AddressServingJusoRoadAddress,
    AdminAuditLog,
    AdminNotification,
    AirQualityRawForecast,
    AirQualityRawSidoMeasurement,
    AirQualityRawStation,
    AirQualityServingForecast,
    AirQualityServingSidoMeasurement,
    AirQualityServingStation,
    ApiCallLog,
    AreaDetail,
    BeachIndexForecast,
    BeachObservation,
    BeachProfile,
    BeachProviderRef,
    BeachSourceRecord,
    BeachWaterQualityMeasurement,
    BjdLookup,
    ContentFeatureLink,
    ContentItem,
    ContentMedia,
    ContentSourceLink,
    ContentTag,
    EmailQueue,
    EmailVerificationToken,
    EtlRunLog,
    EventDetail,
    Feature,
    FeatureMappingCandidate,
    FuelRawAvgPrice,
    FuelRawLowestStation,
    FuelRawOpiNetRegionCode,
    FuelRegionLegalDongMapping,
    FuelServingAvgPrice,
    FuelServingLowestStation,
    FuelServingOpiNetRegionCode,
    KmaRecommendedTourCourse,
    MapFeature,
    MapFeatureMedia,
    MapFeatureOverride,
    MapFeatureProviderRef,
    MapFeatureSourceLink,
    MapFeatureTag,
    MapFeatureWeatherValue,
    MapFeatureWebLink,
    MediaAsset,
    NoticeDetail,
    OceanActivityIndexForecast,
    OceanActivityIndexLocation,
    OceanActivityIndexSourceRecord,
    PlaceCategory,
    PlaceDetail,
    PricePoint,
    PriceValue,
    ProviderSyncState,
    RefreshToken,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
    RestAreaRawMaster,
    RestAreaRawOilPrice,
    RestAreaRawService,
    RestAreaServingMaster,
    RestAreaServingOilPrice,
    RestAreaServingService,
    RouteDetail,
    RouteWaypoint,
    SourceRecord,
    Tag,
    TelegramSystemNotificationOutbox,
    TourCourseRawKmaPoint,
    TourCourseRawKmaSpotWeather,
    TourCourseServingKmaSpotWeather,
    TourRawPublicCulturalFestival,
    TourServingPublicCulturalFestival,
    Trip,
    TripDay,
    TripMember,
    TripPlanItem,
    TripPoi,
    TripShareToken,
    User,
    UserConsent,
    UserSession,
    WeatherBeachLocation,
    WeatherKmaAlertStationCode,
    WeatherMidForecastRegion,
    WeatherMidRegionAddressMapping,
    WeatherObservation,
    WeatherRawBeach,
    WeatherRawKmaAlert,
    WeatherRawMidTerm,
    WeatherRawShortTerm,
    WeatherServingBeach,
    WeatherServingKmaAlert,
    WeatherServingMidTerm,
    WeatherServingShortTerm,
    WeatherShortTermGridMapping,
)


def test_initial_core_tables_are_registered() -> None:
    expected_tables = {
        AddressCodeStandard.__tablename__,
        AddressRawLegalDongCode.__tablename__,
        AddressRawJusoRelatedJibun.__tablename__,
        AddressRawJusoRoadAddress.__tablename__,
        AddressServingJusoRelatedJibun.__tablename__,
        AddressServingJusoRoadAddress.__tablename__,
        AdminAuditLog.__tablename__,
        AdminNotification.__tablename__,
        ApiCallLog.__tablename__,
        BeachIndexForecast.__tablename__,
        BeachObservation.__tablename__,
        BeachProfile.__tablename__,
        BeachProviderRef.__tablename__,
        BeachSourceRecord.__tablename__,
        BeachWaterQualityMeasurement.__tablename__,
        BjdLookup.__tablename__,
        EmailQueue.__tablename__,
        EmailVerificationToken.__tablename__,
        EtlRunLog.__tablename__,
        Feature.__tablename__,
        FuelRawAvgPrice.__tablename__,
        FuelRawLowestStation.__tablename__,
        FuelRawOpiNetRegionCode.__tablename__,
        FuelRegionLegalDongMapping.__tablename__,
        FuelServingAvgPrice.__tablename__,
        FuelServingLowestStation.__tablename__,
        FuelServingOpiNetRegionCode.__tablename__,
        KmaRecommendedTourCourse.__tablename__,
        AreaDetail.__tablename__,
        ContentFeatureLink.__tablename__,
        ContentItem.__tablename__,
        ContentMedia.__tablename__,
        ContentSourceLink.__tablename__,
        ContentTag.__tablename__,
        EventDetail.__tablename__,
        FeatureMappingCandidate.__tablename__,
        MapFeature.__tablename__,
        MapFeatureMedia.__tablename__,
        MapFeatureOverride.__tablename__,
        MapFeatureProviderRef.__tablename__,
        MapFeatureSourceLink.__tablename__,
        MapFeatureTag.__tablename__,
        MapFeatureWeatherValue.__tablename__,
        MapFeatureWebLink.__tablename__,
        MediaAsset.__tablename__,
        NoticeDetail.__tablename__,
        OceanActivityIndexForecast.__tablename__,
        OceanActivityIndexLocation.__tablename__,
        OceanActivityIndexSourceRecord.__tablename__,
        PlaceCategory.__tablename__,
        PlaceDetail.__tablename__,
        ProviderSyncState.__tablename__,
        PricePoint.__tablename__,
        PriceValue.__tablename__,
        RefreshToken.__tablename__,
        RouteDetail.__tablename__,
        RouteWaypoint.__tablename__,
        SourceRecord.__tablename__,
        Tag.__tablename__,
        RestAreaRawMaster.__tablename__,
        RestAreaRawOilPrice.__tablename__,
        RestAreaRawService.__tablename__,
        RestAreaServingMaster.__tablename__,
        RestAreaServingOilPrice.__tablename__,
        RestAreaServingService.__tablename__,
        RegionBoundaryImportBatch.__tablename__,
        RegionRawVWorldBoundary.__tablename__,
        RegionServingBoundary.__tablename__,
        TelegramSystemNotificationOutbox.__tablename__,
        TourCourseRawKmaPoint.__tablename__,
        TourCourseRawKmaSpotWeather.__tablename__,
        TourCourseServingKmaSpotWeather.__tablename__,
        TourRawPublicCulturalFestival.__tablename__,
        TourServingPublicCulturalFestival.__tablename__,
        User.__tablename__,
        UserSession.__tablename__,
        Trip.__tablename__,
        TripDay.__tablename__,
        TripMember.__tablename__,
        TripPlanItem.__tablename__,
        TripPoi.__tablename__,
        TripShareToken.__tablename__,
        UserConsent.__tablename__,
        WeatherBeachLocation.__tablename__,
        WeatherObservation.__tablename__,
        WeatherKmaAlertStationCode.__tablename__,
        WeatherRawBeach.__tablename__,
        WeatherRawKmaAlert.__tablename__,
        WeatherRawShortTerm.__tablename__,
        WeatherServingBeach.__tablename__,
        WeatherServingKmaAlert.__tablename__,
        WeatherMidForecastRegion.__tablename__,
        WeatherMidRegionAddressMapping.__tablename__,
        WeatherRawMidTerm.__tablename__,
        WeatherServingMidTerm.__tablename__,
        WeatherServingShortTerm.__tablename__,
        WeatherShortTermGridMapping.__tablename__,
        AirQualityRawForecast.__tablename__,
        AirQualityRawSidoMeasurement.__tablename__,
        AirQualityRawStation.__tablename__,
        AirQualityServingForecast.__tablename__,
        AirQualityServingSidoMeasurement.__tablename__,
        AirQualityServingStation.__tablename__,
    }

    assert expected_tables <= set(Base.metadata.tables)


def test_session_model_does_not_store_plain_token_column() -> None:
    session_columns = set(UserSession.__table__.columns.keys())

    assert "session_token_hash" in session_columns
    assert "session_token" not in session_columns


def test_etl_datetime_columns_are_timezone_aware() -> None:
    started_at_type = EtlRunLog.__table__.c.started_at.type
    finished_at_type = EtlRunLog.__table__.c.finished_at.type
    sent_at_type = TelegramSystemNotificationOutbox.__table__.c.sent_at.type
    fuel_avg_timestamp_type = FuelServingAvgPrice.__table__.c.timestamp.type
    fuel_station_timestamp_type = FuelServingLowestStation.__table__.c.timestamp.type
    weather_collected_at_type = WeatherServingShortTerm.__table__.c.collected_at.type
    weather_mid_collected_at_type = WeatherServingMidTerm.__table__.c.collected_at.type
    weather_beach_location_collected_at_type = WeatherBeachLocation.__table__.c.collected_at.type
    weather_raw_beach_collected_at_type = WeatherRawBeach.__table__.c.collected_at.type
    weather_serving_beach_collected_at_type = WeatherServingBeach.__table__.c.collected_at.type
    air_quality_collected_at_type = AirQualityServingSidoMeasurement.__table__.c.collected_at.type
    tour_collected_at_type = KmaRecommendedTourCourse.__table__.c.collected_at.type
    tour_weather_collected_at_type = TourCourseServingKmaSpotWeather.__table__.c.collected_at.type
    public_festival_collected_at_type = (
        TourServingPublicCulturalFestival.__table__.c.collected_at.type
    )
    place_first_seen_at_type = MapFeature.__table__.c.first_seen_at.type
    place_source_collected_at_type = SourceRecord.__table__.c.imported_at.type
    email_token_expires_at_type = EmailVerificationToken.__table__.c.expires_at.type
    trip_item_starts_at_type = TripPlanItem.__table__.c.starts_at.type
    trip_item_ends_at_type = TripPlanItem.__table__.c.ends_at.type
    beach_profile_collected_at_type = BeachProfile.__table__.c.collected_at.type
    beach_source_collected_at_type = BeachSourceRecord.__table__.c.collected_at.type
    beach_observation_collected_at_type = BeachObservation.__table__.c.collected_at.type
    beach_index_collected_at_type = BeachIndexForecast.__table__.c.collected_at.type
    beach_quality_collected_at_type = BeachWaterQualityMeasurement.__table__.c.collected_at.type
    ocean_location_collected_at_type = OceanActivityIndexLocation.__table__.c.collected_at.type
    ocean_source_collected_at_type = OceanActivityIndexSourceRecord.__table__.c.collected_at.type
    ocean_forecast_collected_at_type = OceanActivityIndexForecast.__table__.c.collected_at.type
    ocean_forecast_start_at_type = OceanActivityIndexForecast.__table__.c.activity_start_at.type
    ocean_forecast_end_at_type = OceanActivityIndexForecast.__table__.c.activity_end_at.type
    spec_v3_datetime_types = [
        UserConsent.__table__.c.agreed_at.type,
        UserConsent.__table__.c.withdrawn_at.type,
        RefreshToken.__table__.c.issued_at.type,
        RefreshToken.__table__.c.expires_at.type,
        RefreshToken.__table__.c.revoked_at.type,
        Feature.__table__.c.created_at.type,
        Feature.__table__.c.updated_at.type,
        Feature.__table__.c.deleted_at.type,
        PriceValue.__table__.c.observed_at.type,
        WeatherObservation.__table__.c.issued_at.type,
        WeatherObservation.__table__.c.valid_at.type,
        Trip.__table__.c.deleted_at.type,
        TripMember.__table__.c.invited_at.type,
        TripMember.__table__.c.joined_at.type,
        TripPoi.__table__.c.feature_link_broken_at.type,
        TripShareToken.__table__.c.expires_at.type,
        TripShareToken.__table__.c.revoked_at.type,
        TripShareToken.__table__.c.last_used_at.type,
        TripShareToken.__table__.c.created_at.type,
        ApiCallLog.__table__.c.occurred_at.type,
        EmailQueue.__table__.c.queued_at.type,
        EmailQueue.__table__.c.sent_at.type,
        AdminAuditLog.__table__.c.occurred_at.type,
        MapFeatureOverride.__table__.c.reviewed_at.type,
        MapFeatureOverride.__table__.c.created_at.type,
        MapFeatureOverride.__table__.c.updated_at.type,
        MapFeatureWeatherValue.__table__.c.issued_at.type,
        MapFeatureWeatherValue.__table__.c.valid_at.type,
        MapFeatureWeatherValue.__table__.c.observed_at.type,
        MapFeatureWeatherValue.__table__.c.collected_at.type,
        ProviderSyncState.__table__.c.last_success_at.type,
        ProviderSyncState.__table__.c.last_attempt_at.type,
        ProviderSyncState.__table__.c.next_run_after.type,
        ProviderSyncState.__table__.c.last_error_at.type,
        ProviderSyncState.__table__.c.created_at.type,
        ProviderSyncState.__table__.c.updated_at.type,
    ]

    assert isinstance(started_at_type, DateTime)
    assert isinstance(finished_at_type, DateTime)
    assert isinstance(sent_at_type, DateTime)
    assert isinstance(fuel_avg_timestamp_type, DateTime)
    assert isinstance(fuel_station_timestamp_type, DateTime)
    assert isinstance(weather_collected_at_type, DateTime)
    assert isinstance(weather_mid_collected_at_type, DateTime)
    assert isinstance(weather_beach_location_collected_at_type, DateTime)
    assert isinstance(weather_raw_beach_collected_at_type, DateTime)
    assert isinstance(weather_serving_beach_collected_at_type, DateTime)
    assert isinstance(air_quality_collected_at_type, DateTime)
    assert isinstance(tour_collected_at_type, DateTime)
    assert isinstance(tour_weather_collected_at_type, DateTime)
    assert isinstance(public_festival_collected_at_type, DateTime)
    assert isinstance(place_first_seen_at_type, DateTime)
    assert isinstance(place_source_collected_at_type, DateTime)
    assert isinstance(email_token_expires_at_type, DateTime)
    assert isinstance(trip_item_starts_at_type, DateTime)
    assert isinstance(trip_item_ends_at_type, DateTime)
    assert isinstance(beach_profile_collected_at_type, DateTime)
    assert isinstance(beach_source_collected_at_type, DateTime)
    assert isinstance(beach_observation_collected_at_type, DateTime)
    assert isinstance(beach_index_collected_at_type, DateTime)
    assert isinstance(beach_quality_collected_at_type, DateTime)
    assert isinstance(ocean_location_collected_at_type, DateTime)
    assert isinstance(ocean_source_collected_at_type, DateTime)
    assert isinstance(ocean_forecast_collected_at_type, DateTime)
    assert isinstance(ocean_forecast_start_at_type, DateTime)
    assert isinstance(ocean_forecast_end_at_type, DateTime)
    assert started_at_type.timezone is True
    assert finished_at_type.timezone is True
    assert sent_at_type.timezone is True
    assert fuel_avg_timestamp_type.timezone is True
    assert fuel_station_timestamp_type.timezone is True
    assert weather_collected_at_type.timezone is True
    assert weather_mid_collected_at_type.timezone is True
    assert weather_beach_location_collected_at_type.timezone is True
    assert weather_raw_beach_collected_at_type.timezone is True
    assert weather_serving_beach_collected_at_type.timezone is True
    assert air_quality_collected_at_type.timezone is True
    assert tour_collected_at_type.timezone is True
    assert tour_weather_collected_at_type.timezone is True
    assert public_festival_collected_at_type.timezone is True
    assert place_first_seen_at_type.timezone is True
    assert place_source_collected_at_type.timezone is True
    assert email_token_expires_at_type.timezone is True
    assert trip_item_starts_at_type.timezone is True
    assert trip_item_ends_at_type.timezone is True
    assert beach_profile_collected_at_type.timezone is True
    assert beach_source_collected_at_type.timezone is True
    assert beach_observation_collected_at_type.timezone is True
    assert beach_index_collected_at_type.timezone is True
    assert beach_quality_collected_at_type.timezone is True
    assert ocean_location_collected_at_type.timezone is True
    assert ocean_source_collected_at_type.timezone is True
    assert ocean_forecast_collected_at_type.timezone is True
    assert ocean_forecast_start_at_type.timezone is True
    assert ocean_forecast_end_at_type.timezone is True
    for datetime_type in spec_v3_datetime_types:
        assert isinstance(datetime_type, DateTime)
        assert datetime_type.timezone is True


def test_nullable_unique_constraints_use_postgresql_nulls_not_distinct() -> None:
    weather_mapping_table = WeatherMidRegionAddressMapping.__table__
    tour_weather_table = TourCourseServingKmaSpotWeather.__table__
    map_feature_weather_table = MapFeatureWeatherValue.__table__

    assert isinstance(weather_mapping_table, Table)
    assert isinstance(tour_weather_table, Table)
    assert isinstance(map_feature_weather_table, Table)

    weather_mapping_constraint = next(
        constraint
        for constraint in weather_mapping_table.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_wmram_provider_region_address_scope"
    )
    tour_weather_constraint = next(
        constraint
        for constraint in tour_weather_table.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_tcskw_course_spot_time_category"
    )
    map_feature_weather_constraint = next(
        constraint
        for constraint in map_feature_weather_table.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_map_feature_weather_values_feature_provider_time"
    )

    assert weather_mapping_constraint.dialect_options["postgresql"]["nulls_not_distinct"] is True
    assert tour_weather_constraint.dialect_options["postgresql"]["nulls_not_distinct"] is True
    assert (
        map_feature_weather_constraint.dialect_options["postgresql"]["nulls_not_distinct"] is True
    )


def test_geometry_columns_have_explicit_srid_and_gist_index() -> None:
    for table in Base.metadata.tables.values():
        geometry_columns = [column for column in table.c if isinstance(column.type, Geometry)]

        for column in geometry_columns:
            geometry_type = column.type
            assert isinstance(geometry_type, Geometry)
            assert geometry_type.srid in {4326, 5179}
            assert geometry_type.spatial_index is False
            assert any(
                column.name in index.columns
                and index.dialect_options["postgresql"].get("using") == "gist"
                for index in table.indexes
            ), f"{table.name}.{column.name} needs an explicit GiST index"


def test_foreign_key_columns_have_covering_indexes() -> None:
    for table in Base.metadata.tables.values():
        covering_column_sets = [
            tuple(column.name for column in index.columns) for index in table.indexes
        ]
        covering_column_sets.extend(
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, PrimaryKeyConstraint | UniqueConstraint)
        )

        for constraint in table.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue

            fk_columns = tuple(column.name for column in constraint.columns)
            assert any(
                indexed_columns[: len(fk_columns)] == fk_columns
                for indexed_columns in covering_column_sets
            ), f"{table.name}.{constraint.name} needs a covering index"


def test_place_check_constraint_names_match_migration_contract() -> None:
    category_table = cast(Table, PlaceCategory.__table__)
    place_table = cast(Table, MapFeature.__table__)
    category_checks = {
        constraint.name
        for constraint in category_table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    place_checks = {
        constraint.name
        for constraint in place_table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_place_category_code_format" in category_checks
    assert "ck_map_features_not_self_parent" in place_checks
