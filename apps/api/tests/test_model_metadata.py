from sqlalchemy import DateTime, UniqueConstraint

from app.db.base import Base
from app.models import (
    AddressCodeStandard,
    AddressRawJusoRelatedJibun,
    AddressRawJusoRoadAddress,
    AddressRawLegalDongCode,
    AddressServingJusoRelatedJibun,
    AddressServingJusoRoadAddress,
    AdminNotification,
    AirQualityRawForecast,
    AirQualityRawSidoMeasurement,
    AirQualityRawStation,
    AirQualityServingForecast,
    AirQualityServingSidoMeasurement,
    AirQualityServingStation,
    EtlRunLog,
    FuelRawAvgPrice,
    FuelRawLowestStation,
    FuelRawOpiNetRegionCode,
    FuelRegionLegalDongMapping,
    FuelServingAvgPrice,
    FuelServingLowestStation,
    FuelServingOpiNetRegionCode,
    KmaRecommendedTourCourse,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
    RestAreaRawMaster,
    RestAreaRawOilPrice,
    RestAreaRawService,
    RestAreaServingMaster,
    RestAreaServingOilPrice,
    RestAreaServingService,
    TelegramSystemNotificationOutbox,
    TourCourseRawKmaPoint,
    TourCourseRawKmaSpotWeather,
    TourCourseServingKmaSpotWeather,
    Trip,
    TripDay,
    User,
    UserSession,
    WeatherKmaAlertStationCode,
    WeatherMidForecastRegion,
    WeatherMidRegionAddressMapping,
    WeatherRawKmaAlert,
    WeatherRawMidTerm,
    WeatherRawShortTerm,
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
        AdminNotification.__tablename__,
        EtlRunLog.__tablename__,
        FuelRawAvgPrice.__tablename__,
        FuelRawLowestStation.__tablename__,
        FuelRawOpiNetRegionCode.__tablename__,
        FuelRegionLegalDongMapping.__tablename__,
        FuelServingAvgPrice.__tablename__,
        FuelServingLowestStation.__tablename__,
        FuelServingOpiNetRegionCode.__tablename__,
        KmaRecommendedTourCourse.__tablename__,
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
        User.__tablename__,
        UserSession.__tablename__,
        Trip.__tablename__,
        TripDay.__tablename__,
        WeatherKmaAlertStationCode.__tablename__,
        WeatherRawKmaAlert.__tablename__,
        WeatherRawShortTerm.__tablename__,
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
    air_quality_collected_at_type = AirQualityServingSidoMeasurement.__table__.c.collected_at.type
    tour_collected_at_type = KmaRecommendedTourCourse.__table__.c.collected_at.type
    tour_weather_collected_at_type = TourCourseServingKmaSpotWeather.__table__.c.collected_at.type

    assert isinstance(started_at_type, DateTime)
    assert isinstance(finished_at_type, DateTime)
    assert isinstance(sent_at_type, DateTime)
    assert isinstance(fuel_avg_timestamp_type, DateTime)
    assert isinstance(fuel_station_timestamp_type, DateTime)
    assert isinstance(weather_collected_at_type, DateTime)
    assert isinstance(weather_mid_collected_at_type, DateTime)
    assert isinstance(air_quality_collected_at_type, DateTime)
    assert isinstance(tour_collected_at_type, DateTime)
    assert isinstance(tour_weather_collected_at_type, DateTime)
    assert started_at_type.timezone is True
    assert finished_at_type.timezone is True
    assert sent_at_type.timezone is True
    assert fuel_avg_timestamp_type.timezone is True
    assert fuel_station_timestamp_type.timezone is True
    assert weather_collected_at_type.timezone is True
    assert weather_mid_collected_at_type.timezone is True
    assert air_quality_collected_at_type.timezone is True
    assert tour_collected_at_type.timezone is True
    assert tour_weather_collected_at_type.timezone is True


def test_nullable_unique_constraints_use_postgresql_nulls_not_distinct() -> None:
    weather_mapping_constraint = next(
        constraint
        for constraint in WeatherMidRegionAddressMapping.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_wmram_provider_region_address_scope"
    )
    tour_weather_constraint = next(
        constraint
        for constraint in TourCourseServingKmaSpotWeather.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_tcskw_course_spot_time_category"
    )

    assert weather_mapping_constraint.dialect_options["postgresql"]["nulls_not_distinct"] is True
    assert tour_weather_constraint.dialect_options["postgresql"]["nulls_not_distinct"] is True
