from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.etl.weather.client import AirKoreaApiClient, KmaWeatherApiClient
from app.geospatial.kma_grid import wgs84_to_kma_grid
from app.models.address import RegionServingBoundary
from app.models.weather import (
    AirQualityRawForecast,
    AirQualityRawSidoMeasurement,
    AirQualityRawStation,
    AirQualityServingForecast,
    AirQualityServingSidoMeasurement,
    AirQualityServingStation,
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

KMA_ULTRA_SHORT_NOWCAST_ENDPOINT = "getUltraSrtNcst"
KMA_ULTRA_SHORT_FORECAST_ENDPOINT = "getUltraSrtFcst"
KMA_VILLAGE_FORECAST_ENDPOINT = "getVilageFcst"
KMA_WARNING_ENDPOINT = "getWthrWrnList"
KMA_INFO_ENDPOINT = "getWthrInfoList"
KMA_BREAKING_NEWS_ENDPOINT = "getWthrBrkNewsList"
KMA_MID_OUTLOOK_ENDPOINT = "getMidFcst"
KMA_MID_LAND_ENDPOINT = "getMidLandFcst"
KMA_MID_TEMPERATURE_ENDPOINT = "getMidTa"
AIRKOREA_STATION_ENDPOINT = "getMsrstnList"
AIRKOREA_FORECAST_ENDPOINT = "getMinuDustFrcstDspth"
AIRKOREA_SIDO_MEASUREMENT_ENDPOINT = "getCtprvnRltmMesureDnsty"
KST = ZoneInfo("Asia/Seoul")

KST_SIDO_NAMES = [
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
]


@dataclass(frozen=True)
class WeatherGridMappingLoadResult:
    mapping_count: int
    skipped_count: int


@dataclass(frozen=True)
class WeatherShortTermLoadResult:
    requested_grid_count: int
    requested_endpoint_count: int
    raw_row_count: int
    serving_row_count: int
    skipped_row_count: int


@dataclass(frozen=True)
class KmaAlertLoadResult:
    raw_row_count: int
    serving_row_count: int
    station_count: int


@dataclass(frozen=True)
class WeatherMidTermRegionSeedResult:
    region_count: int
    mapping_count: int
    source_version: str


@dataclass(frozen=True)
class WeatherMidTermLoadResult:
    requested_region_count: int
    raw_row_count: int
    serving_row_count: int
    seeded_region_count: int
    seeded_mapping_count: int


@dataclass(frozen=True)
class AirQualityStationLoadResult:
    raw_row_count: int
    serving_row_count: int
    mapped_row_count: int


@dataclass(frozen=True)
class AirQualityForecastLoadResult:
    raw_row_count: int
    serving_row_count: int


@dataclass(frozen=True)
class AirQualitySidoMeasurementLoadResult:
    requested_sido_count: int
    raw_row_count: int
    serving_row_count: int


@dataclass(frozen=True)
class _CategorySpec:
    code: str
    category_name: str
    normalized_category: str
    unit: str | None


SHORT_TERM_CATEGORY_SPECS = {
    "POP": _CategorySpec("POP", "강수확률", "rain_probability", "%"),
    "PCP": _CategorySpec("PCP", "1시간 강수량", "precipitation", "mm"),
    "PTY": _CategorySpec("PTY", "강수형태", "precipitation_type", None),
    "REH": _CategorySpec("REH", "습도", "humidity", "%"),
    "RN1": _CategorySpec("RN1", "1시간 강수량", "rainfall_1h", "mm"),
    "SNO": _CategorySpec("SNO", "1시간 신적설", "snowfall", "cm"),
    "T1H": _CategorySpec("T1H", "기온", "temperature", "deg_c"),
    "TMP": _CategorySpec("TMP", "1시간 기온", "temperature", "deg_c"),
    "TMN": _CategorySpec("TMN", "일 최저기온", "temperature_min", "deg_c"),
    "TMX": _CategorySpec("TMX", "일 최고기온", "temperature_max", "deg_c"),
    "UUU": _CategorySpec("UUU", "동서바람성분", "wind_u", "m/s"),
    "VEC": _CategorySpec("VEC", "풍향", "wind_direction", "deg"),
    "VVV": _CategorySpec("VVV", "남북바람성분", "wind_v", "m/s"),
    "WSD": _CategorySpec("WSD", "풍속", "wind_speed", "m/s"),
    "SKY": _CategorySpec("SKY", "하늘상태", "sky", None),
    "LGT": _CategorySpec("LGT", "낙뢰", "lightning", None),
}


def upsert_weather_grid_mapping(
    session: Session,
    *,
    region_code_type: str,
    region_code: str,
    representative_lon: Decimal | float | str,
    representative_lat: Decimal | float | str,
    legal_dong_code: str | None = None,
    sigungu_code: str | None = None,
    sido_code: str | None = None,
    mapping_method: str = "manual",
    source_boundary_version: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> WeatherShortTermGridMapping:
    lon = _decimal(representative_lon)
    lat = _decimal(representative_lat)
    grid = wgs84_to_kma_grid(latitude=float(lat), longitude=float(lon))
    existing = session.scalar(
        select(WeatherShortTermGridMapping)
        .where(WeatherShortTermGridMapping.region_code_type == region_code_type)
        .where(WeatherShortTermGridMapping.region_code == region_code)
    )
    values = {
        "legal_dong_code": legal_dong_code,
        "sigungu_code": sigungu_code,
        "sido_code": sido_code,
        "representative_lon": lon,
        "representative_lat": lat,
        "nx": grid.nx,
        "ny": grid.ny,
        "mapping_method": mapping_method,
        "source_boundary_version": source_boundary_version,
        "raw_payload": raw_payload or {},
        "is_active": True,
    }
    if existing is None:
        existing = WeatherShortTermGridMapping(
            region_code_type=region_code_type,
            region_code=region_code,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def build_sigungu_weather_grid_mappings_from_boundaries(
    session: Session,
) -> WeatherGridMappingLoadResult:
    rows = session.execute(
        select(
            RegionServingBoundary.region_code,
            RegionServingBoundary.sido_code,
            RegionServingBoundary.sigungu_code,
            RegionServingBoundary.address_code_standard_code,
            RegionServingBoundary.source_file_hash,
            func.ST_X(func.ST_PointOnSurface(RegionServingBoundary.geom)),
            func.ST_Y(func.ST_PointOnSurface(RegionServingBoundary.geom)),
        ).where(RegionServingBoundary.boundary_level == "sigungu")
    ).all()
    mapping_count = 0
    skipped_count = 0
    for row in rows:
        region_code, sido_code, sigungu_code, address_code, source_hash, lon, lat = row
        if not region_code or lon is None or lat is None:
            skipped_count += 1
            continue
        upsert_weather_grid_mapping(
            session,
            region_code_type="sigungu",
            region_code=region_code,
            representative_lon=lon,
            representative_lat=lat,
            legal_dong_code=address_code,
            sigungu_code=sigungu_code,
            sido_code=sido_code,
            mapping_method="postgis_point_on_surface",
            source_boundary_version=source_hash,
            raw_payload={"boundary_level": "sigungu", "region_code": region_code},
        )
        mapping_count += 1
    session.flush()
    return WeatherGridMappingLoadResult(mapping_count=mapping_count, skipped_count=skipped_count)


def load_short_term_weather_for_active_mappings(
    session: Session,
    client: KmaWeatherApiClient,
    *,
    collected_at: datetime | None = None,
    endpoints: tuple[str, ...] | None = None,
) -> WeatherShortTermLoadResult:
    mappings = list(
        session.scalars(
            select(WeatherShortTermGridMapping)
            .where(WeatherShortTermGridMapping.is_active.is_(True))
            .order_by(WeatherShortTermGridMapping.nx, WeatherShortTermGridMapping.ny)
        ).all()
    )
    unique_grids = sorted({(mapping.nx, mapping.ny) for mapping in mappings})
    return load_short_term_weather_for_grids(
        session,
        client,
        grids=unique_grids,
        collected_at=collected_at,
        endpoints=endpoints,
    )


def load_short_term_weather_for_grids(
    session: Session,
    client: KmaWeatherApiClient,
    *,
    grids: list[tuple[int, int]],
    collected_at: datetime | None = None,
    endpoints: tuple[str, ...] | None = None,
) -> WeatherShortTermLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    requested_endpoints = endpoints or (
        KMA_ULTRA_SHORT_NOWCAST_ENDPOINT,
        KMA_ULTRA_SHORT_FORECAST_ENDPOINT,
        KMA_VILLAGE_FORECAST_ENDPOINT,
    )
    raw_count = 0
    serving_count = 0
    skipped_count = 0
    for nx, ny in grids:
        for endpoint, rows in _fetch_short_term_rows(
            client, nx=nx, ny=ny, endpoints=requested_endpoints
        ):
            for row in rows:
                category_code = _optional_text(row, "category")
                if not category_code:
                    skipped_count += 1
                    continue
                base_date = _required_text(row, "baseDate")
                base_time = _required_text(row, "baseTime")
                forecast_date = _optional_text(row, "fcstDate") or base_date
                forecast_time = _optional_text(row, "fcstTime") or base_time
                raw_payload = dict(row)
                session.add(
                    WeatherRawShortTerm(
                        endpoint=endpoint,
                        nx=nx,
                        ny=ny,
                        base_date=base_date,
                        base_time=base_time,
                        forecast_date=forecast_date,
                        forecast_time=forecast_time,
                        category_code=category_code,
                        raw_payload=raw_payload,
                        response_hash=_hash_payload(raw_payload),
                        collected_at=resolved_collected_at,
                    )
                )
                raw_count += 1
                _upsert_serving_short_term(
                    session,
                    endpoint=endpoint,
                    row=raw_payload,
                    nx=nx,
                    ny=ny,
                    base_date=base_date,
                    base_time=base_time,
                    forecast_date=forecast_date,
                    forecast_time=forecast_time,
                    category_code=category_code,
                    collected_at=resolved_collected_at,
                )
                serving_count += 1
    session.flush()
    return WeatherShortTermLoadResult(
        requested_grid_count=len(grids),
        requested_endpoint_count=len(requested_endpoints),
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        skipped_row_count=skipped_count,
    )


def _fetch_short_term_rows(
    client: KmaWeatherApiClient,
    *,
    nx: int,
    ny: int,
    endpoints: tuple[str, ...],
) -> list[tuple[str, list[dict[str, Any]]]]:
    rows: list[tuple[str, list[dict[str, Any]]]] = []
    for endpoint in endpoints:
        if endpoint == KMA_ULTRA_SHORT_NOWCAST_ENDPOINT:
            rows.append((endpoint, client.fetch_ultra_short_nowcast(nx=nx, ny=ny)))
        elif endpoint == KMA_ULTRA_SHORT_FORECAST_ENDPOINT:
            rows.append((endpoint, client.fetch_ultra_short_forecast(nx=nx, ny=ny)))
        elif endpoint == KMA_VILLAGE_FORECAST_ENDPOINT:
            rows.append((endpoint, client.fetch_village_forecast(nx=nx, ny=ny)))
        else:
            raise ValueError(f"Unsupported short-term weather endpoint: {endpoint}")
    return rows


def load_kma_alerts(
    session: Session,
    client: KmaWeatherApiClient,
    *,
    from_date: date,
    to_date: date,
    collected_at: datetime | None = None,
) -> KmaAlertLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    endpoint_rows = [
        (
            KMA_WARNING_ENDPOINT,
            "warning",
            client.fetch_weather_warnings(from_date=from_date, to_date=to_date),
        ),
        (
            KMA_INFO_ENDPOINT,
            "information",
            client.fetch_weather_infos(from_date=from_date, to_date=to_date),
        ),
        (
            KMA_BREAKING_NEWS_ENDPOINT,
            "breaking_news",
            client.fetch_weather_breaking_news(from_date=from_date, to_date=to_date),
        ),
    ]
    raw_count = 0
    serving_count = 0
    seen_station_ids: set[str] = set()
    for endpoint, alert_type, rows in endpoint_rows:
        for row in rows:
            stn_id = _optional_text(row, "stnId")
            if stn_id:
                seen_station_ids.add(stn_id)
                _upsert_alert_station(
                    session, stn_id=stn_id, row=row, collected_at=resolved_collected_at
                )
            raw_payload = dict(row)
            title = _optional_text(row, "title")
            tm_fc = _optional_text(row, "tmFc")
            tm_seq = _optional_text(row, "tmSeq")
            session.add(
                WeatherRawKmaAlert(
                    endpoint=endpoint,
                    alert_type=alert_type,
                    stn_id=stn_id,
                    title=title,
                    tm_fc=tm_fc,
                    tm_seq=tm_seq,
                    raw_payload=raw_payload,
                    response_hash=_hash_payload(raw_payload),
                    collected_at=resolved_collected_at,
                )
            )
            raw_count += 1
            _upsert_serving_alert(
                session,
                alert_type=alert_type,
                stn_id=stn_id,
                title=title,
                tm_fc=tm_fc,
                tm_seq=tm_seq,
                raw_payload=raw_payload,
                collected_at=resolved_collected_at,
            )
            serving_count += 1
    session.flush()
    return KmaAlertLoadResult(
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        station_count=len(seen_station_ids),
    )


def seed_kma_mid_term_regions(
    session: Session,
    *,
    config_path: Path | str | None = None,
    collected_at: datetime | None = None,
) -> WeatherMidTermRegionSeedResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    config = _load_mid_term_region_config(config_path)
    provider = str(config.get("provider") or "kma")
    source_version = str(config.get("source_version") or "unknown")
    region_count = 0
    mapping_count = 0

    for raw_region in _read_config_list(config, "regions"):
        region = {str(key): value for key, value in raw_region.items()}
        endpoint = _required_text(region, "endpoint")
        region_kind = _required_text(region, "region_kind")
        provider_region_id = _required_text(region, "provider_region_id")
        existing = session.scalar(
            select(WeatherMidForecastRegion)
            .where(WeatherMidForecastRegion.provider == provider)
            .where(WeatherMidForecastRegion.endpoint == endpoint)
            .where(WeatherMidForecastRegion.region_kind == region_kind)
            .where(WeatherMidForecastRegion.provider_region_id == provider_region_id)
        )
        values = {
            "region_name": _required_text(region, "region_name"),
            "parent_region_id": _optional_text(region, "parent_region_id"),
            "source_version": source_version,
            "raw_payload": region,
            "collected_at": resolved_collected_at,
            "is_active": True,
        }
        if existing is None:
            session.add(
                WeatherMidForecastRegion(
                    provider=provider,
                    endpoint=endpoint,
                    region_kind=region_kind,
                    provider_region_id=provider_region_id,
                    **values,
                )
            )
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        region_count += 1

    session.flush()

    for raw_mapping in _read_config_list(config, "mappings"):
        mapping = {str(key): value for key, value in raw_mapping.items()}
        endpoint = _required_text(mapping, "endpoint")
        provider_region_kind = _required_text(mapping, "provider_region_kind")
        provider_region_id = _required_text(mapping, "provider_region_id")
        existing = session.scalar(
            select(WeatherMidRegionAddressMapping)
            .where(WeatherMidRegionAddressMapping.provider == provider)
            .where(WeatherMidRegionAddressMapping.endpoint == endpoint)
            .where(WeatherMidRegionAddressMapping.provider_region_kind == provider_region_kind)
            .where(WeatherMidRegionAddressMapping.provider_region_id == provider_region_id)
            .where(WeatherMidRegionAddressMapping.sido_code == _optional_text(mapping, "sido_code"))
            .where(
                WeatherMidRegionAddressMapping.sigungu_code
                == _optional_text(mapping, "sigungu_code")
            )
            .where(
                WeatherMidRegionAddressMapping.legal_dong_code_prefix
                == _optional_text(mapping, "legal_dong_code_prefix")
            )
        )
        values = {
            "sido_code": _optional_text(mapping, "sido_code"),
            "sigungu_code": _optional_text(mapping, "sigungu_code"),
            "legal_dong_code_prefix": _optional_text(mapping, "legal_dong_code_prefix"),
            "mapping_method": _required_text(mapping, "mapping_method"),
            "priority": _optional_int(mapping.get("priority")) or 100,
            "valid_from": _optional_text(mapping, "valid_from"),
            "source_version": source_version,
            "raw_payload": mapping,
            "is_active": True,
        }
        if existing is None:
            session.add(
                WeatherMidRegionAddressMapping(
                    provider=provider,
                    endpoint=endpoint,
                    provider_region_kind=provider_region_kind,
                    provider_region_id=provider_region_id,
                    **values,
                )
            )
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        mapping_count += 1

    session.flush()
    return WeatherMidTermRegionSeedResult(
        region_count=region_count,
        mapping_count=mapping_count,
        source_version=source_version,
    )


def load_mid_term_weather(
    session: Session,
    client: KmaWeatherApiClient,
    *,
    config_path: Path | str | None = None,
    collected_at: datetime | None = None,
) -> WeatherMidTermLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    seed_result = seed_kma_mid_term_regions(
        session,
        config_path=config_path,
        collected_at=resolved_collected_at,
    )
    regions = list(
        session.scalars(
            select(WeatherMidForecastRegion)
            .where(WeatherMidForecastRegion.provider == "kma")
            .where(WeatherMidForecastRegion.is_active.is_(True))
            .order_by(
                WeatherMidForecastRegion.region_kind,
                WeatherMidForecastRegion.provider_region_id,
            )
        )
    )

    raw_count = 0
    serving_count = 0
    for region in regions:
        rows = _fetch_mid_term_rows(client, region)
        for row in rows:
            raw_payload = dict(row)
            tm_fc = _optional_text(raw_payload, "tmFc")
            session.add(
                WeatherRawMidTerm(
                    endpoint=region.endpoint,
                    region_kind=region.region_kind,
                    provider_region_id=region.provider_region_id,
                    tm_fc=tm_fc,
                    raw_payload=raw_payload,
                    response_hash=_hash_payload(raw_payload),
                    collected_at=resolved_collected_at,
                )
            )
            raw_count += 1
            for serving_payload in _expand_mid_term_serving_rows(region, raw_payload):
                _upsert_mid_term_serving(
                    session,
                    region=region,
                    row=serving_payload,
                    collected_at=resolved_collected_at,
                )
                serving_count += 1
    session.flush()
    return WeatherMidTermLoadResult(
        requested_region_count=len(regions),
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        seeded_region_count=seed_result.region_count,
        seeded_mapping_count=seed_result.mapping_count,
    )


def resolve_mid_term_region_mappings_for_address(
    session: Session,
    *,
    legal_dong_code: str,
) -> list[WeatherMidRegionAddressMapping]:
    sido_code = legal_dong_code[:2] + "00000000"
    sigungu_code = legal_dong_code[:5] + "00000"
    return list(
        session.scalars(
            select(WeatherMidRegionAddressMapping)
            .where(WeatherMidRegionAddressMapping.is_active.is_(True))
            .where(
                (
                    WeatherMidRegionAddressMapping.legal_dong_code_prefix.is_not(None)
                    & (
                        WeatherMidRegionAddressMapping.legal_dong_code_prefix
                        == legal_dong_code[:10]
                    )
                )
                | (
                    WeatherMidRegionAddressMapping.sigungu_code.is_not(None)
                    & (WeatherMidRegionAddressMapping.sigungu_code == sigungu_code)
                )
                | (
                    WeatherMidRegionAddressMapping.sido_code.is_not(None)
                    & (WeatherMidRegionAddressMapping.sido_code == sido_code)
                )
            )
            .order_by(WeatherMidRegionAddressMapping.priority)
        )
    )


def load_air_quality_stations(
    session: Session,
    client: AirKoreaApiClient,
    *,
    sido_names: list[str] | None = None,
    collected_at: datetime | None = None,
) -> AirQualityStationLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    raw_count = 0
    serving_count = 0
    mapped_count = 0
    for sido_name in sido_names or KST_SIDO_NAMES:
        for row in client.fetch_station_list(sido_name=sido_name):
            station_name = _required_text(row, "stationName")
            mang_name = _optional_text(row, "mangName")
            raw_payload = dict(row)
            session.add(
                AirQualityRawStation(
                    endpoint=AIRKOREA_STATION_ENDPOINT,
                    request_sido_name=sido_name,
                    station_name=station_name,
                    mang_name=mang_name,
                    raw_payload=raw_payload,
                    response_hash=_hash_payload(raw_payload),
                    collected_at=resolved_collected_at,
                )
            )
            raw_count += 1
            mapped = _upsert_air_quality_station(
                session,
                row=raw_payload,
                request_sido_name=sido_name,
                station_name=station_name,
                mang_name=mang_name,
                collected_at=resolved_collected_at,
            )
            serving_count += 1
            if mapped:
                mapped_count += 1
    session.flush()
    return AirQualityStationLoadResult(
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        mapped_row_count=mapped_count,
    )


def load_air_quality_forecasts(
    session: Session,
    client: AirKoreaApiClient,
    *,
    inform_codes: list[str] | None = None,
    collected_at: datetime | None = None,
) -> AirQualityForecastLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    raw_count = 0
    serving_count = 0
    for inform_code in inform_codes or ["PM10", "PM25", "O3"]:
        for row in client.fetch_forecast_dispatches(inform_code=inform_code):
            raw_payload = dict(row)
            resolved_code = _optional_text(row, "informCode") or inform_code
            data_time = _optional_text(row, "dataTime") or resolved_collected_at.isoformat()
            inform_data = _optional_text(row, "informData")
            session.add(
                AirQualityRawForecast(
                    endpoint=AIRKOREA_FORECAST_ENDPOINT,
                    inform_code=resolved_code,
                    data_time=data_time,
                    inform_data=inform_data,
                    raw_payload=raw_payload,
                    response_hash=_hash_payload(raw_payload),
                    collected_at=resolved_collected_at,
                )
            )
            raw_count += 1
            _upsert_air_quality_forecast(
                session,
                row=raw_payload,
                inform_code=resolved_code,
                data_time=data_time,
                inform_data=inform_data,
                collected_at=resolved_collected_at,
            )
            serving_count += 1
    session.flush()
    return AirQualityForecastLoadResult(raw_row_count=raw_count, serving_row_count=serving_count)


def load_air_quality_sido_measurements(
    session: Session,
    client: AirKoreaApiClient,
    *,
    sido_names: list[str] | None = None,
    collected_at: datetime | None = None,
) -> AirQualitySidoMeasurementLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    requested_sidos = sido_names or KST_SIDO_NAMES
    raw_count = 0
    serving_count = 0
    for sido_name in requested_sidos:
        for row in client.fetch_sido_measurements(sido_name=sido_name):
            station_name = _required_text(row, "stationName")
            data_time = _required_text(row, "dataTime")
            raw_payload = dict(row)
            session.add(
                AirQualityRawSidoMeasurement(
                    endpoint=AIRKOREA_SIDO_MEASUREMENT_ENDPOINT,
                    sido_name=sido_name,
                    station_name=station_name,
                    data_time=data_time,
                    raw_payload=raw_payload,
                    response_hash=_hash_payload(raw_payload),
                    collected_at=resolved_collected_at,
                )
            )
            raw_count += 1
            _upsert_air_quality_measurement(
                session,
                row=raw_payload,
                sido_name=sido_name,
                station_name=station_name,
                data_time=data_time,
                collected_at=resolved_collected_at,
            )
            serving_count += 1
    session.flush()
    return AirQualitySidoMeasurementLoadResult(
        requested_sido_count=len(requested_sidos),
        raw_row_count=raw_count,
        serving_row_count=serving_count,
    )


def _fetch_mid_term_rows(
    client: KmaWeatherApiClient,
    region: WeatherMidForecastRegion,
) -> list[dict[str, Any]]:
    if region.region_kind == "outlook_station":
        return client.fetch_mid_outlook(stn_id=region.provider_region_id)
    if region.region_kind == "land":
        return client.fetch_mid_land_forecast(reg_id=region.provider_region_id)
    if region.region_kind == "temperature":
        return client.fetch_mid_temperature(reg_id=region.provider_region_id)
    raise ValueError(f"Unsupported KMA mid-term region kind: {region.region_kind}")


def _expand_mid_term_serving_rows(
    region: WeatherMidForecastRegion,
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    tm_fc = _optional_text(row, "tmFc") or datetime.now(KST).strftime("%Y%m%d%H%M")
    base_date = _parse_mid_tm_fc_date(tm_fc)
    if region.region_kind == "land":
        return _expand_mid_land_rows(row, tm_fc=tm_fc, base_date=base_date)
    if region.region_kind == "temperature":
        return _expand_mid_temperature_rows(row, tm_fc=tm_fc, base_date=base_date)
    if region.region_kind == "outlook_station":
        return [
            {
                "tm_fc": tm_fc,
                "forecast_date": base_date,
                "forecast_slot": "daily",
                "weather_summary": _optional_text(row, "wfSv"),
                "rain_probability": None,
                "min_temperature": None,
                "max_temperature": None,
                "display_priority": 300,
                "raw_payload": dict(row),
            }
        ]
    return []


def _expand_mid_land_rows(
    row: dict[str, Any],
    *,
    tm_fc: str,
    base_date: date,
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for day_offset in range(3, 8):
        for slot, suffix in (("am", "Am"), ("pm", "Pm")):
            expanded.append(
                {
                    "tm_fc": tm_fc,
                    "forecast_date": base_date + timedelta(days=day_offset),
                    "forecast_slot": slot,
                    "weather_summary": _optional_text(row, f"wf{day_offset}{suffix}"),
                    "rain_probability": _optional_text(row, f"rnSt{day_offset}{suffix}"),
                    "min_temperature": None,
                    "max_temperature": None,
                    "display_priority": day_offset * 10 + (0 if slot == "am" else 1),
                    "raw_payload": dict(row),
                }
            )
    for day_offset in range(8, 11):
        expanded.append(
            {
                "tm_fc": tm_fc,
                "forecast_date": base_date + timedelta(days=day_offset),
                "forecast_slot": "daily",
                "weather_summary": _optional_text(row, f"wf{day_offset}"),
                "rain_probability": _optional_text(row, f"rnSt{day_offset}"),
                "min_temperature": None,
                "max_temperature": None,
                "display_priority": day_offset * 10,
                "raw_payload": dict(row),
            }
        )
    return [
        item
        for item in expanded
        if item["weather_summary"] is not None or item["rain_probability"] is not None
    ]


def _expand_mid_temperature_rows(
    row: dict[str, Any],
    *,
    tm_fc: str,
    base_date: date,
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for day_offset in range(3, 11):
        min_temperature = _optional_text(row, f"taMin{day_offset}")
        max_temperature = _optional_text(row, f"taMax{day_offset}")
        if min_temperature is None and max_temperature is None:
            continue
        expanded.append(
            {
                "tm_fc": tm_fc,
                "forecast_date": base_date + timedelta(days=day_offset),
                "forecast_slot": "daily",
                "weather_summary": None,
                "rain_probability": None,
                "min_temperature": min_temperature,
                "max_temperature": max_temperature,
                "display_priority": day_offset * 10,
                "raw_payload": dict(row),
            }
        )
    return expanded


def _upsert_mid_term_serving(
    session: Session,
    *,
    region: WeatherMidForecastRegion,
    row: dict[str, Any],
    collected_at: datetime,
) -> WeatherServingMidTerm:
    forecast_date = row["forecast_date"]
    forecast_slot = _required_text(row, "forecast_slot")
    tm_fc = _required_text(row, "tm_fc")
    mapping = _best_mid_region_mapping(session, region)
    mapping_method = mapping.mapping_method if mapping else None
    fallback_used = mapping_method in {"parent_region", "nearest_representative", "manual"}
    existing = session.scalar(
        select(WeatherServingMidTerm)
        .where(WeatherServingMidTerm.endpoint == region.endpoint)
        .where(WeatherServingMidTerm.region_kind == region.region_kind)
        .where(WeatherServingMidTerm.provider_region_id == region.provider_region_id)
        .where(WeatherServingMidTerm.tm_fc == tm_fc)
        .where(WeatherServingMidTerm.forecast_date == forecast_date)
        .where(WeatherServingMidTerm.forecast_slot == forecast_slot)
    )
    values = {
        "source_region_code": region.provider_region_id,
        "weather_summary": _optional_text(row, "weather_summary"),
        "rain_probability": _optional_text(row, "rain_probability"),
        "min_temperature": _optional_text(row, "min_temperature"),
        "max_temperature": _optional_text(row, "max_temperature"),
        "mapping_method": mapping_method,
        "fallback_used": fallback_used,
        "fallback_reason": "explicit_mid_term_region_mapping" if fallback_used else None,
        "display_priority": _optional_int(row.get("display_priority")) or 100,
        "raw_payload": dict(row.get("raw_payload") or {}),
        "collected_at": collected_at,
    }
    if existing is None:
        existing = WeatherServingMidTerm(
            endpoint=region.endpoint,
            region_kind=region.region_kind,
            provider_region_id=region.provider_region_id,
            tm_fc=tm_fc,
            forecast_date=forecast_date,
            forecast_slot=forecast_slot,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _best_mid_region_mapping(
    session: Session,
    region: WeatherMidForecastRegion,
) -> WeatherMidRegionAddressMapping | None:
    return session.scalar(
        select(WeatherMidRegionAddressMapping)
        .where(WeatherMidRegionAddressMapping.provider == region.provider)
        .where(WeatherMidRegionAddressMapping.endpoint == region.endpoint)
        .where(WeatherMidRegionAddressMapping.provider_region_kind == region.region_kind)
        .where(WeatherMidRegionAddressMapping.provider_region_id == region.provider_region_id)
        .where(WeatherMidRegionAddressMapping.is_active.is_(True))
        .order_by(WeatherMidRegionAddressMapping.priority)
        .limit(1)
    )


def _upsert_serving_short_term(
    session: Session,
    *,
    endpoint: str,
    row: dict[str, Any],
    nx: int,
    ny: int,
    base_date: str,
    base_time: str,
    forecast_date: str | None,
    forecast_time: str | None,
    category_code: str,
    collected_at: datetime,
) -> WeatherServingShortTerm:
    existing = session.scalar(
        select(WeatherServingShortTerm)
        .where(WeatherServingShortTerm.endpoint == endpoint)
        .where(WeatherServingShortTerm.nx == nx)
        .where(WeatherServingShortTerm.ny == ny)
        .where(WeatherServingShortTerm.base_date == base_date)
        .where(WeatherServingShortTerm.base_time == base_time)
        .where(WeatherServingShortTerm.forecast_date == forecast_date)
        .where(WeatherServingShortTerm.forecast_time == forecast_time)
        .where(WeatherServingShortTerm.category_code == category_code)
    )
    spec = SHORT_TERM_CATEGORY_SPECS.get(
        category_code,
        _CategorySpec(category_code, category_code, "unknown", None),
    )
    values = {
        "observed_at": _parse_kma_datetime(base_date, base_time),
        "forecast_at": _parse_kma_datetime(forecast_date, forecast_time),
        "category_name": spec.category_name,
        "normalized_category": spec.normalized_category,
        "value": _optional_text(row, "obsrValue") or _optional_text(row, "fcstValue") or "",
        "unit": spec.unit,
        "raw_payload": row,
        "collected_at": collected_at,
    }
    if existing is None:
        existing = WeatherServingShortTerm(
            endpoint=endpoint,
            nx=nx,
            ny=ny,
            base_date=base_date,
            base_time=base_time,
            forecast_date=forecast_date,
            forecast_time=forecast_time,
            category_code=category_code,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _upsert_alert_station(
    session: Session,
    *,
    stn_id: str,
    row: dict[str, Any],
    collected_at: datetime,
) -> WeatherKmaAlertStationCode:
    existing = session.get(WeatherKmaAlertStationCode, stn_id)
    values = {
        "station_name": _optional_text(row, "stnNm"),
        "source": "observed_alert_response",
        "raw_payload": dict(row),
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = WeatherKmaAlertStationCode(stn_id=stn_id, **values)
        session.add(existing)
    else:
        for key, value in values.items():
            if value is not None:
                setattr(existing, key, value)
    return existing


def _upsert_serving_alert(
    session: Session,
    *,
    alert_type: str,
    stn_id: str | None,
    title: str | None,
    tm_fc: str | None,
    tm_seq: str | None,
    raw_payload: dict[str, Any],
    collected_at: datetime,
) -> WeatherServingKmaAlert:
    existing = session.scalar(
        select(WeatherServingKmaAlert)
        .where(WeatherServingKmaAlert.alert_type == alert_type)
        .where(WeatherServingKmaAlert.stn_id == stn_id)
        .where(WeatherServingKmaAlert.tm_fc == tm_fc)
        .where(WeatherServingKmaAlert.tm_seq == tm_seq)
        .where(WeatherServingKmaAlert.title == title)
    )
    values = {
        "raw_payload": raw_payload,
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = WeatherServingKmaAlert(
            alert_type=alert_type,
            stn_id=stn_id,
            title=title,
            tm_fc=tm_fc,
            tm_seq=tm_seq,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _upsert_air_quality_station(
    session: Session,
    *,
    row: dict[str, Any],
    request_sido_name: str,
    station_name: str,
    mang_name: str | None,
    collected_at: datetime,
) -> bool:
    address = _required_text(row, "addr")
    lat = _optional_decimal(row.get("dmX"))
    lon = _optional_decimal(row.get("dmY"))
    boundary = _find_legal_boundary(session, longitude=lon, latitude=lat)
    existing = session.scalar(
        select(AirQualityServingStation)
        .where(AirQualityServingStation.station_name == station_name)
        .where(AirQualityServingStation.mang_name == mang_name)
        .where(AirQualityServingStation.address == address)
    )
    values = {
        "sido_name": request_sido_name,
        "item": _optional_text(row, "item"),
        "installation_year": _optional_text(row, "year"),
        "longitude": lon,
        "latitude": lat,
        "legal_dong_code": boundary.legal_dong_code if boundary else None,
        "sigungu_code": boundary.sigungu_code if boundary else None,
        "mapping_method": "postgis_point_in_polygon" if boundary else "unmapped",
        "raw_payload": dict(row),
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = AirQualityServingStation(
            station_name=station_name,
            mang_name=mang_name,
            address=address,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return boundary is not None


def _upsert_air_quality_forecast(
    session: Session,
    *,
    row: dict[str, Any],
    inform_code: str,
    data_time: str,
    inform_data: str | None,
    collected_at: datetime,
) -> AirQualityServingForecast:
    inform_overall = _optional_text(row, "informOverall")
    existing = session.scalar(
        select(AirQualityServingForecast)
        .where(AirQualityServingForecast.inform_code == inform_code)
        .where(AirQualityServingForecast.data_time == data_time)
        .where(AirQualityServingForecast.inform_data == inform_data)
        .where(AirQualityServingForecast.inform_overall == inform_overall)
    )
    values = {
        "inform_cause": _optional_text(row, "informCause"),
        "inform_grade": _optional_text(row, "informGrade"),
        "action_knack": _optional_text(row, "actionKnack"),
        "raw_payload": dict(row),
        "collected_at": collected_at,
    }
    if existing is None:
        existing = AirQualityServingForecast(
            inform_code=inform_code,
            data_time=data_time,
            inform_data=inform_data,
            inform_overall=inform_overall,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _upsert_air_quality_measurement(
    session: Session,
    *,
    row: dict[str, Any],
    sido_name: str,
    station_name: str,
    data_time: str,
    collected_at: datetime,
) -> AirQualityServingSidoMeasurement:
    existing = session.scalar(
        select(AirQualityServingSidoMeasurement)
        .where(AirQualityServingSidoMeasurement.sido_name == sido_name)
        .where(AirQualityServingSidoMeasurement.station_name == station_name)
        .where(AirQualityServingSidoMeasurement.data_time == data_time)
    )
    values = {
        "mang_name": _optional_text(row, "mangName"),
        "khai_value": _optional_text(row, "khaiValue"),
        "khai_grade": _optional_text(row, "khaiGrade"),
        "pm10_value": _optional_text(row, "pm10Value"),
        "pm10_grade": _optional_text(row, "pm10Grade"),
        "pm25_value": _optional_text(row, "pm25Value"),
        "pm25_grade": _optional_text(row, "pm25Grade"),
        "no2_value": _optional_text(row, "no2Value"),
        "no2_grade": _optional_text(row, "no2Grade"),
        "o3_value": _optional_text(row, "o3Value"),
        "o3_grade": _optional_text(row, "o3Grade"),
        "co_value": _optional_text(row, "coValue"),
        "co_grade": _optional_text(row, "coGrade"),
        "so2_value": _optional_text(row, "so2Value"),
        "so2_grade": _optional_text(row, "so2Grade"),
        "pm10_flag": _optional_text(row, "pm10Flag"),
        "pm25_flag": _optional_text(row, "pm25Flag"),
        "no2_flag": _optional_text(row, "no2Flag"),
        "o3_flag": _optional_text(row, "o3Flag"),
        "co_flag": _optional_text(row, "coFlag"),
        "so2_flag": _optional_text(row, "so2Flag"),
        "raw_payload": dict(row),
        "collected_at": collected_at,
    }
    if existing is None:
        existing = AirQualityServingSidoMeasurement(
            sido_name=sido_name,
            station_name=station_name,
            data_time=data_time,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _find_legal_boundary(
    session: Session,
    *,
    longitude: Decimal | None,
    latitude: Decimal | None,
) -> RegionServingBoundary | None:
    if longitude is None or latitude is None:
        return None
    point = func.ST_SetSRID(func.ST_MakePoint(float(longitude), float(latitude)), 4326)
    return session.scalar(
        select(RegionServingBoundary)
        .where(RegionServingBoundary.boundary_level == "legal_dong")
        .where(func.ST_Covers(RegionServingBoundary.geom, point))
        .order_by(func.ST_Area(RegionServingBoundary.geom))
        .limit(1)
    )


def _parse_kma_datetime(date_text: str | None, time_text: str | None) -> datetime | None:
    if not date_text or not time_text:
        return None
    try:
        return datetime.strptime(f"{date_text}{time_text}", "%Y%m%d%H%M").replace(tzinfo=KST)
    except ValueError:
        return None


def _parse_mid_tm_fc_date(tm_fc: str) -> date:
    try:
        return datetime.strptime(tm_fc[:8], "%Y%m%d").date()
    except ValueError:
        return datetime.now(KST).date()


def _load_mid_term_region_config(config_path: Path | str | None) -> dict[str, Any]:
    path = Path(config_path or get_settings().kma_mid_term_region_config_path)
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("KMA mid-term region config must be a JSON object.")
        return raw
    return {"provider": "kma", "source_version": "empty", "regions": [], "mappings": []}


def _read_config_list(config: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = config.get(key, [])
    if not isinstance(raw, list):
        raise ValueError(f"KMA mid-term region config field {key!r} must be a list.")
    rows = [row for row in raw if isinstance(row, dict)]
    if len(rows) != len(raw):
        raise ValueError(f"KMA mid-term region config field {key!r} has non-object rows.")
    return rows


def _required_text(row: dict[str, Any], key: str) -> str:
    value = _optional_text(row, key)
    if value is None:
        raise ValueError(f"weather row is missing required field {key}.")
    return value


def _optional_text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return _decimal(value)


def _optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _decimal(value: Decimal | float | str | Any) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"value must be decimal-compatible: {value!r}") from exc


def _resolve_collected_at(collected_at: datetime | None) -> datetime:
    if collected_at is None:
        return datetime.now(KST)
    if collected_at.tzinfo is None:
        return collected_at.replace(tzinfo=KST)
    return collected_at


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
