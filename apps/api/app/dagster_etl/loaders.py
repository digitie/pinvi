from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.etl_config import get_etl_dataset_config
from app.dagster_etl.runtime import (
    DagsterEtlRun,
    TripMateEtlSkip,
    resolve_download_dir,
    resolve_log_dir,
)


def load_legal_dong_code_standard(session: Session, run: DagsterEtlRun) -> Any:
    _ = run
    from app.etl.vworld.legal_dong_code_loader import (
        DATA_GO_LEGAL_DONG_PAGE_URL,
        load_latest_legal_dong_code_from_data_go,
    )

    result = load_latest_legal_dong_code_from_data_go(
        session,
        resolve_download_dir("legal-dong-code-standard"),
    )
    return {
        **result.__dict__,
        "page_url": DATA_GO_LEGAL_DONG_PAGE_URL,
        "download_dir": resolve_download_dir("legal-dong-code-standard"),
    }


def load_juso_monthly_address(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.juso.pipeline import download_and_load_juso_address_dataset

    result = download_and_load_juso_address_dataset(
        session,
        resolve_download_dir("juso-address"),
        source_year_month=run.run_key,
    )
    return {
        **result.__dict__,
        "download_dir": resolve_download_dir("juso-address"),
        "source_year_month_override": run.op_config.get("source_year_month"),
    }


def load_opinet_region_codes(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.opinet.client import OpiNetApiClient, OpiNetApiError
    from app.etl.opinet.loader import load_opinet_region_codes as load_region_codes

    try:
        return load_region_codes(session, OpiNetApiClient(), collected_at=run.collected_at)
    except OpiNetApiError as exc:
        cache_status = _fresh_opinet_region_cache_status(session, run.collected_at, exc)
        if cache_status is not None:
            raise TripMateEtlSkip(
                "OpiNet areaCode.do returned zero rows; "
                f"using {cache_status['active_region_count']} cached region code rows "
                f"collected at {cache_status['latest_collected_at']}."
            ) from exc
        raise


def _fresh_opinet_region_cache_status(
    session: Session,
    reference_time: datetime,
    error: BaseException,
) -> dict[str, object] | None:
    if "areaCode.do returned zero" not in str(error):
        return None

    from app.models.fuel import FuelServingOpiNetRegionCode

    active_region_count = session.scalar(
        select(func.count())
        .select_from(FuelServingOpiNetRegionCode)
        .where(FuelServingOpiNetRegionCode.is_active.is_(True))
    )
    if not active_region_count:
        return None

    latest_collected_at = session.scalar(
        select(func.max(FuelServingOpiNetRegionCode.collected_at)).where(
            FuelServingOpiNetRegionCode.is_active.is_(True)
        )
    )
    if not isinstance(latest_collected_at, datetime):
        return None

    freshness_target_minutes = get_etl_dataset_config("fuel_region_code").freshness_target_minutes
    if freshness_target_minutes is not None:
        comparable_latest = _align_timezone(latest_collected_at, reference_time)
        if comparable_latest < reference_time - timedelta(minutes=freshness_target_minutes):
            return None

    return {
        "active_region_count": active_region_count,
        "latest_collected_at": latest_collected_at.isoformat(),
    }


def _align_timezone(value: datetime, reference: datetime) -> datetime:
    if value.tzinfo is None and reference.tzinfo is not None:
        return value.replace(tzinfo=reference.tzinfo)
    if value.tzinfo is not None and reference.tzinfo is not None:
        return value.astimezone(reference.tzinfo)
    return value


def load_opinet_avg_prices(session: Session, run: DagsterEtlRun) -> Any:
    _ = run
    from app.etl.opinet.client import OpiNetApiClient
    from app.etl.opinet.loader import load_opinet_avg_prices

    return load_opinet_avg_prices(session, OpiNetApiClient())


def load_opinet_lowest_stations(session: Session, run: DagsterEtlRun) -> Any:
    _ = run
    from app.etl.opinet.client import OpiNetApiClient
    from app.etl.opinet.loader import (
        list_opinet_sigungu_region_codes_for_periodic_collection,
        load_opinet_lowest_stations,
    )

    provider_region_codes = list_opinet_sigungu_region_codes_for_periodic_collection(session)
    if not provider_region_codes:
        raise RuntimeError(
            "OpiNet 최저가 주유소 수집 대상 시군구가 없습니다. "
            "fuel_region_code ETL을 먼저 성공시켜야 합니다."
        )
    return load_opinet_lowest_stations(
        session,
        OpiNetApiClient(),
        provider_region_codes=provider_region_codes,
    )


def load_rest_area_master_dataset(session: Session, run: DagsterEtlRun) -> Any:
    _ = run
    from app.core.kex import build_kex_client
    from app.etl.rest_area.loader import load_rest_area_master

    return load_rest_area_master(session, build_kex_client(), collected_at=run.collected_at)


def load_rest_area_oil_prices_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.core.kex import build_kex_client
    from app.etl.rest_area.loader import load_rest_area_oil_prices

    return load_rest_area_oil_prices(
        session,
        build_kex_client(),
        collected_at=run.collected_at,
        fk_mismatch_log_dir=_rest_area_fk_mismatch_log_dir(),
        run_id=run.run_key,
    )


def load_rest_area_services_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.core.kex import build_kex_client
    from app.etl.rest_area.loader import load_rest_area_services

    return load_rest_area_services(
        session,
        build_kex_client(),
        collected_at=run.collected_at,
        fk_mismatch_log_dir=_rest_area_fk_mismatch_log_dir(),
        run_id=run.run_key,
    )


def load_weather_short_term(session: Session, run: DagsterEtlRun) -> Any:
    from app.core.config import get_settings
    from app.etl.weather.client import KmaWeatherApiClient
    from app.etl.weather.loader import (
        build_sigungu_weather_grid_mappings_from_boundaries,
        load_short_term_weather_for_active_mappings,
    )
    from app.models.weather import WeatherShortTermGridMapping

    existing_count = session.query(WeatherShortTermGridMapping).filter_by(is_active=True).count()
    if existing_count == 0:
        build_sigungu_weather_grid_mappings_from_boundaries(session)
    settings = get_settings()
    return load_short_term_weather_for_active_mappings(
        session,
        KmaWeatherApiClient(
            request_delay_seconds=settings.kma_short_term_request_delay_seconds,
            rate_limit_max_retries=settings.kma_short_term_rate_limit_max_retries,
            rate_limit_retry_backoff_seconds=settings.kma_short_term_rate_limit_backoff_seconds,
        ),
        collected_at=run.collected_at,
    )


def load_weather_alerts(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.client import KmaWeatherApiClient
    from app.etl.weather.loader import load_kma_alerts

    to_date = run.collected_at.date()
    return load_kma_alerts(
        session,
        KmaWeatherApiClient(),
        from_date=to_date - timedelta(days=1),
        to_date=to_date,
        collected_at=run.collected_at,
    )


def load_weather_mid_term(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.client import KmaWeatherApiClient
    from app.etl.weather.loader import load_mid_term_weather

    return load_mid_term_weather(session, KmaWeatherApiClient(), collected_at=run.collected_at)


def load_air_quality_stations_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.client import AirKoreaApiClient
    from app.etl.weather.loader import load_air_quality_stations

    return load_air_quality_stations(session, AirKoreaApiClient(), collected_at=run.collected_at)


def load_air_quality_forecasts_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.client import AirKoreaApiClient
    from app.etl.weather.loader import load_air_quality_forecasts

    return load_air_quality_forecasts(session, AirKoreaApiClient(), collected_at=run.collected_at)


def load_air_quality_measurements_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.client import AirKoreaApiClient
    from app.etl.weather.loader import load_air_quality_sido_measurements

    return load_air_quality_sido_measurements(
        session,
        AirKoreaApiClient(),
        collected_at=run.collected_at,
    )


def load_kma_tour_course_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.tour.kma_tour_course import load_kma_tour_course_file

    source_path = os.environ.get("TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH")
    if not source_path:
        raise TripMateEtlSkip(
            "TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH is not configured. "
            "Upload or place the KMA tour course ZIP/CSV before running this job."
        )
    return load_kma_tour_course_file(session, source_path, collected_at=run.collected_at)


def load_kma_beach_catalog_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.beach import KmaBeachWeatherClient, load_beach_catalog

    return load_beach_catalog(session, KmaBeachWeatherClient(), collected_at=run.collected_at)


def load_kma_beach_ultra_short(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.beach import KMA_BEACH_ULTRA_SHORT_ENDPOINT

    return _load_kma_beach_weather_endpoint(session, run, KMA_BEACH_ULTRA_SHORT_ENDPOINT)


def load_kma_beach_village(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.beach import KMA_BEACH_VILLAGE_ENDPOINT

    return _load_kma_beach_weather_endpoint(session, run, KMA_BEACH_VILLAGE_ENDPOINT)


def load_kma_beach_wave(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.beach import KMA_BEACH_WAVE_ENDPOINT

    return _load_kma_beach_weather_endpoint(session, run, KMA_BEACH_WAVE_ENDPOINT)


def load_kma_beach_water_temperature(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.weather.beach import KMA_BEACH_WATER_TEMP_ENDPOINT

    return _load_kma_beach_weather_endpoint(session, run, KMA_BEACH_WATER_TEMP_ENDPOINT)


def load_kma_beach_tide_sun(session: Session, run: DagsterEtlRun) -> dict[str, Any]:
    from app.etl.weather.beach import KMA_BEACH_SUN_ENDPOINT, KMA_BEACH_TIDE_ENDPOINT

    tide = _load_kma_beach_weather_endpoint(session, run, KMA_BEACH_TIDE_ENDPOINT)
    sun = _load_kma_beach_weather_endpoint(session, run, KMA_BEACH_SUN_ENDPOINT)
    return {"tide": tide, "sun": sun}


def load_khoa_beach_observations_dataset(session: Session, run: DagsterEtlRun) -> Any:
    if not os.environ.get("TRIPMATE_KHOA_API_KEY"):
        raise TripMateEtlSkip("TRIPMATE_KHOA_API_KEY가 없어 KHOA 관측 ETL을 건너뜁니다.")

    from app.etl.beach.sources import KhoaBeachObservationClient, load_khoa_beach_observations

    return load_khoa_beach_observations(
        session,
        KhoaBeachObservationClient(),
        collected_at=run.collected_at,
    )


def load_khoa_beach_index_forecasts_dataset(session: Session, run: DagsterEtlRun) -> Any:
    if not _has_khoa_or_data_go_key():
        raise TripMateEtlSkip("KHOA/data.go.kr 인증키가 없어 KHOA 해수욕지수 ETL을 건너뜁니다.")

    from app.etl.beach.sources import KhoaBeachIndexClient, load_khoa_beach_index_forecasts

    return load_khoa_beach_index_forecasts(
        session,
        KhoaBeachIndexClient(),
        collected_at=run.collected_at,
        req_date=run.collected_at.date(),
    )


def load_mof_beach_info_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.beach.sources import MofBeachInfoClient, load_mof_beach_info

    return load_mof_beach_info(session, MofBeachInfoClient(), collected_at=run.collected_at)


def load_mof_beach_water_quality_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.beach.sources import MofBeachWaterQualityClient, load_mof_beach_water_quality

    client = MofBeachWaterQualityClient()
    current_year = load_mof_beach_water_quality(
        session,
        client,
        year=run.collected_at.year,
        collected_at=run.collected_at,
    )
    previous_year = load_mof_beach_water_quality(
        session,
        client,
        year=run.collected_at.year - 1,
        collected_at=run.collected_at,
    )
    return {"current_year": current_year, "previous_year": previous_year}


def load_khoa_ocean_index_dataset_by_key(session: Session, run: DagsterEtlRun) -> Any:
    if not _has_khoa_or_data_go_key():
        raise TripMateEtlSkip("KHOA/data.go.kr 인증키가 없어 해양지수 ETL을 건너뜁니다.")

    from app.etl.ocean.khoa_indices import KhoaOceanIndexClient, load_khoa_ocean_index_dataset

    return load_khoa_ocean_index_dataset(
        session,
        run.dataset_key,
        KhoaOceanIndexClient(),
        collected_at=run.collected_at,
        req_date=run.collected_at.date(),
    )


def load_public_cultural_festival_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.tour.public_cultural_festival import (
        DataGoPublicCulturalFestivalClient,
        load_public_cultural_festivals,
    )

    return load_public_cultural_festivals(
        session,
        DataGoPublicCulturalFestivalClient(),
        collected_at=run.collected_at,
    )


def load_public_place_dataset_by_key(session: Session, run: DagsterEtlRun) -> Any:
    from app.etl.places.public_data_places import (
        CompositePublicPlaceClient,
        load_public_place_dataset,
    )

    return load_public_place_dataset(
        session,
        run.dataset_key,
        CompositePublicPlaceClient(),
        collected_at=run.collected_at,
    )


def load_krforest_outdoor_feature_dataset(session: Session, run: DagsterEtlRun) -> Any:
    if not _has_krforest_key():
        raise TripMateEtlSkip(
            "KRFOREST/TRIPMATE_DATA_GO service key가 없어 산림 feature ETL을 건너뜁니다."
        )

    from krforest import ForestClient

    from app.etl.outdoor.forest_features import load_default_krforest_outdoor_features

    return load_default_krforest_outdoor_features(
        session,
        ForestClient.from_env(),
        collected_at=run.collected_at,
    )


def load_krmois_outdoor_license_dataset(session: Session, run: DagsterEtlRun) -> Any:
    from mois import LocalDataFileClient

    from app.etl.outdoor.forest_features import load_default_mois_outdoor_license_features

    return load_default_mois_outdoor_license_features(
        session,
        LocalDataFileClient(),
        collected_at=run.collected_at,
    )


def _load_kma_beach_weather_endpoint(session: Session, run: DagsterEtlRun, endpoint: str) -> Any:
    from app.etl.weather.beach import KmaBeachWeatherClient, load_beach_weather_for_active_locations
    from app.models.weather import WeatherBeachLocation

    client = KmaBeachWeatherClient()
    existing_count = session.query(WeatherBeachLocation).filter_by(is_active=True).count()
    if existing_count == 0:
        load_kma_beach_catalog_dataset(session, run)
    return load_beach_weather_for_active_locations(
        session,
        client,
        endpoint=endpoint,
        collected_at=run.collected_at,
    )


def _has_khoa_or_data_go_key() -> bool:
    return bool(
        os.environ.get("TRIPMATE_KHOA_API_KEY") or os.environ.get("TRIPMATE_DATA_GO_SERVICE_KEY")
    )


def _has_krforest_key() -> bool:
    return bool(
        os.environ.get("KRFOREST_SERVICE_KEY")
        or os.environ.get("PYKRFOREST_SERVICE_KEY")
        or os.environ.get("KFS_SERVICE_KEY")
        or os.environ.get("FOREST_SERVICE_KEY")
        or os.environ.get("DATA_GO_SERVICE_KEY")
        or os.environ.get("TRIPMATE_DATA_GO_SERVICE_KEY")
    )


def _rest_area_fk_mismatch_log_dir() -> Any:
    return resolve_log_dir() / "etl" / "rest_area_fk_mismatch"


def _settings_value(name: str) -> str | None:
    value = getattr(get_settings(), name)
    return str(value) if value else None
