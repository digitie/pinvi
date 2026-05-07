from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.etl.places.public_data_places import ensure_public_place_categories
from app.etl.weather.client import DataGoApiError, _fetch_all
from app.etl.weather.loader import SHORT_TERM_CATEGORY_SPECS
from app.models.address import AddressServingJusoRoadAddress, RegionServingBoundary
from app.models.place import (
    MapFeature,
    MapFeatureProviderRef,
    MapFeatureSourceLink,
    PlaceDetail,
    SourceRecord,
)
from app.models.weather import WeatherBeachLocation, WeatherRawBeach, WeatherServingBeach

KST = ZoneInfo("Asia/Seoul")
KMA_BEACH_PROVIDER = "kma"
KMA_BEACH_CATALOG_DATASET_KEY = "kma_beach_catalog"
KMA_BEACH_CATEGORY_CODE = "01050100"
KMA_BEACH_SOURCE_PAGE_URL = "https://www.data.go.kr/data/15102239/openapi.do"
KMA_BEACH_GUIDE_DOWNLOAD_URL = (
    "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003562456&fileDetailSn=1"
)
KMA_BEACH_BASE_URL = "http://apis.data.go.kr/1360000/BeachInfoservice"
KMA_BEACH_ULTRA_SHORT_ENDPOINT = "getUltraSrtFcstBeach"
KMA_BEACH_VILLAGE_ENDPOINT = "getVilageFcstBeach"
KMA_BEACH_WAVE_ENDPOINT = "getWhBuoyBeach"
KMA_BEACH_WATER_TEMP_ENDPOINT = "getTwBuoyBeach"
KMA_BEACH_TIDE_ENDPOINT = "getTideInfoBeach"
KMA_BEACH_SUN_ENDPOINT = "getSunInfoBeach"
KMA_BEACH_CATALOG_DOWNLOAD_ATTEMPTS = 3
KMA_BEACH_ENDPOINTS = (
    KMA_BEACH_ULTRA_SHORT_ENDPOINT,
    KMA_BEACH_VILLAGE_ENDPOINT,
    KMA_BEACH_WAVE_ENDPOINT,
    KMA_BEACH_WATER_TEMP_ENDPOINT,
    KMA_BEACH_TIDE_ENDPOINT,
    KMA_BEACH_SUN_ENDPOINT,
)
_WHITESPACE_RE = re.compile(r"\s+")


class KmaBeachWeatherError(RuntimeError):
    pass


class KmaBeachCatalogClient(Protocol):
    def fetch_beach_catalog_rows(self) -> list[dict[str, Any]]: ...


class KmaBeachWeatherApiClientProtocol(Protocol):
    def fetch_ultra_short_forecast(
        self,
        *,
        beach_num: str,
        base_date: str,
        base_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]: ...

    def fetch_village_forecast(
        self,
        *,
        beach_num: str,
        base_date: str,
        base_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]: ...

    def fetch_wave_height(
        self,
        *,
        beach_num: str,
        search_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]: ...

    def fetch_water_temperature(
        self,
        *,
        beach_num: str,
        search_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]: ...

    def fetch_tide_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]: ...

    def fetch_sun_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]: ...


class KmaBeachWeatherClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        base_url: str = KMA_BEACH_BASE_URL,
        catalog_download_url: str = KMA_BEACH_GUIDE_DOWNLOAD_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._service_key = (
            service_key if service_key is not None else get_settings().data_go_service_key
        )
        self._base_url = base_url.rstrip("/")
        self._catalog_download_url = catalog_download_url
        self._client = client

    def fetch_beach_catalog_rows(self) -> list[dict[str, Any]]:
        content = self._download_catalog_archive()
        file_name, xlsx_bytes = _extract_catalog_xlsx(content)
        file_hash = hashlib.sha256(xlsx_bytes).hexdigest()
        rows = _read_simple_xlsx_rows(xlsx_bytes)
        for row in rows:
            row["_source_file_name"] = file_name
            row["_source_file_hash"] = file_hash
        return rows

    def fetch_ultra_short_forecast(
        self,
        *,
        beach_num: str,
        base_date: str,
        base_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return self._fetch_endpoint(
            KMA_BEACH_ULTRA_SHORT_ENDPOINT,
            {
                "dataType": "JSON",
                "beach_num": beach_num,
                "base_date": base_date,
                "base_time": base_time,
            },
        )

    def fetch_village_forecast(
        self,
        *,
        beach_num: str,
        base_date: str,
        base_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return self._fetch_endpoint(
            KMA_BEACH_VILLAGE_ENDPOINT,
            {
                "dataType": "JSON",
                "beach_num": beach_num,
                "base_date": base_date,
                "base_time": base_time,
            },
        )

    def fetch_wave_height(
        self,
        *,
        beach_num: str,
        search_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return self._fetch_endpoint(
            KMA_BEACH_WAVE_ENDPOINT,
            {"dataType": "JSON", "beach_num": beach_num, "searchTime": search_time},
        )

    def fetch_water_temperature(
        self,
        *,
        beach_num: str,
        search_time: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return self._fetch_endpoint(
            KMA_BEACH_WATER_TEMP_ENDPOINT,
            {"dataType": "JSON", "beach_num": beach_num, "searchTime": search_time},
        )

    def fetch_tide_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return self._fetch_endpoint(
            KMA_BEACH_TIDE_ENDPOINT,
            {"dataType": "JSON", "beach_num": beach_num, "base_date": base_date},
        )

    def fetch_sun_info(
        self,
        *,
        beach_num: str,
        base_date: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        return self._fetch_endpoint(
            KMA_BEACH_SUN_ENDPOINT,
            {"dataType": "JSON", "beach_num": beach_num, "Base_date": base_date},
        )

    def _download_catalog_archive(self) -> bytes:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=60.0, follow_redirects=True)
        try:
            for attempt in range(1, KMA_BEACH_CATALOG_DOWNLOAD_ATTEMPTS + 1):
                try:
                    response = client.get(
                        self._catalog_download_url,
                        headers={
                            "User-Agent": "TripMate ETL/0.1",
                            "Accept": (
                                "application/zip, "
                                "application/vnd.openxmlformats-officedocument."
                                "spreadsheetml.sheet, */*"
                            ),
                        },
                    )
                    response.raise_for_status()
                    return bytes(response.content)
                except httpx.HTTPStatusError as exc:
                    if (
                        exc.response.status_code < 500
                        or attempt == KMA_BEACH_CATALOG_DOWNLOAD_ATTEMPTS
                    ):
                        raise
                except (
                    httpx.ConnectError,
                    httpx.ReadError,
                    httpx.RemoteProtocolError,
                    httpx.TimeoutException,
                ):
                    if attempt == KMA_BEACH_CATALOG_DOWNLOAD_ATTEMPTS:
                        raise
        finally:
            if owns_client:
                client.close()
        raise KmaBeachWeatherError("KMA beach catalog download did not return a response.")

    def _fetch_endpoint(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        rows = _fetch_all(
            base_url=self._base_url,
            endpoint=f"/{endpoint}",
            params=params,
            service_key_param="serviceKey",
            service_key=self._service_key,
            client=self._client,
        )
        return params, rows


@dataclass(frozen=True)
class BeachCatalogLoadResult:
    source_row_count: int
    place_upsert_count: int
    location_upsert_count: int
    source_record_count: int
    linked_place_count: int
    legal_dong_mapped_count: int
    road_address_mapped_count: int
    skipped_row_count: int


@dataclass(frozen=True)
class BeachWeatherLoadResult:
    endpoint: str
    requested_beach_count: int
    raw_row_count: int
    serving_row_count: int
    skipped_row_count: int
    fetch_error_count: int


@dataclass(frozen=True)
class _BeachCatalogEntry:
    beach_num: str
    beach_name: str
    nx: int
    ny: int
    longitude: Decimal
    latitude: Decimal
    source_file_name: str
    source_file_hash: str
    source_row_number: int
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class _AddressMapping:
    legal_dong_code: str | None
    sigungu_code: str | None
    sido_code: str | None
    road_name_code: str | None
    administrative_dong_code: str | None
    road_address_management_no: str | None
    road_address: str | None
    address_snapshot: str
    method: str


@dataclass(frozen=True)
class _LegalBoundaryMatch:
    boundary: RegionServingBoundary
    method: str


@dataclass(frozen=True)
class _ServingBeachRow:
    source_record_key: str
    base_date: str | None
    base_time: str | None
    forecast_date: str | None
    forecast_time: str | None
    source_observed_time: str | None
    observed_at: datetime | None
    forecast_at: datetime | None
    category_code: str
    category_name: str
    normalized_category: str
    value: str
    unit: str | None
    station_name: str | None
    raw_payload: dict[str, Any]


def load_beach_catalog(
    session: Session,
    client: KmaBeachCatalogClient,
    *,
    collected_at: datetime | None = None,
) -> BeachCatalogLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    rows = client.fetch_beach_catalog_rows()
    ensure_public_place_categories(session)
    session.query(WeatherBeachLocation).filter(
        WeatherBeachLocation.provider == KMA_BEACH_PROVIDER
    ).update({"is_active": False}, synchronize_session=False)

    place_count = 0
    location_count = 0
    source_record_count = 0
    linked_count = 0
    skipped_count = 0
    legal_mapped_count = 0
    road_mapped_count = 0
    for row in rows:
        entry = _build_catalog_entry(row)
        if entry is None:
            skipped_count += 1
            continue
        mapping = _resolve_address_mapping(
            session,
            beach_name=entry.beach_name,
            longitude=entry.longitude,
            latitude=entry.latitude,
        )
        if mapping.legal_dong_code:
            legal_mapped_count += 1
        if mapping.road_address_management_no:
            road_mapped_count += 1

        raw_hash = _hash_payload(entry.raw_payload)
        source_record, created_source_record = _upsert_place_source_record(
            session,
            entry=entry,
            raw_hash=raw_hash,
            collected_at=resolved_collected_at,
        )
        if created_source_record:
            source_record_count += 1
        place = _upsert_place(
            session,
            entry=entry,
            mapping=mapping,
            collected_at=resolved_collected_at,
        )
        place_count += 1
        if _upsert_place_source_link(session, place=place, source_record=source_record):
            linked_count += 1
        _upsert_place_provider_ref(
            session,
            place=place,
            entry=entry,
            mapping=mapping,
            fetched_at=resolved_collected_at,
        )
        _upsert_beach_location(
            session,
            place=place,
            entry=entry,
            mapping=mapping,
            collected_at=resolved_collected_at,
        )
        location_count += 1

    session.flush()
    return BeachCatalogLoadResult(
        source_row_count=len(rows),
        place_upsert_count=place_count,
        location_upsert_count=location_count,
        source_record_count=source_record_count,
        linked_place_count=linked_count,
        legal_dong_mapped_count=legal_mapped_count,
        road_address_mapped_count=road_mapped_count,
        skipped_row_count=skipped_count,
    )


def load_beach_weather_for_active_locations(
    session: Session,
    client: KmaBeachWeatherApiClientProtocol,
    *,
    endpoint: str,
    collected_at: datetime | None = None,
) -> BeachWeatherLoadResult:
    if endpoint not in KMA_BEACH_ENDPOINTS:
        raise KmaBeachWeatherError(f"Unsupported KMA beach weather endpoint: {endpoint}")

    resolved_collected_at = _resolve_collected_at(collected_at)
    locations = list(
        session.scalars(
            select(WeatherBeachLocation)
            .where(WeatherBeachLocation.provider == KMA_BEACH_PROVIDER)
            .where(WeatherBeachLocation.is_active.is_(True))
            .order_by(WeatherBeachLocation.beach_num)
        ).all()
    )
    raw_count = 0
    serving_count = 0
    skipped_count = 0
    fetch_error_count = 0
    for location in locations:
        try:
            request_params, rows = _fetch_beach_endpoint(
                client,
                endpoint=endpoint,
                beach_num=location.beach_num,
                collected_at=resolved_collected_at,
            )
        except DataGoApiError:
            raise
        except Exception as exc:
            fetch_error_count += 1
            skipped_count += 1
            if _add_raw_snapshot(
                session,
                endpoint=endpoint,
                beach_num=location.beach_num,
                request_params={
                    "beach_num": location.beach_num,
                    "fetch_error": type(exc).__name__,
                },
                payload={
                    "request_params": {"beach_num": location.beach_num},
                    "error": str(exc),
                },
                response_hash=_hash_payload(
                    {
                        "endpoint": endpoint,
                        "beach_num": location.beach_num,
                        "error": str(exc),
                    }
                ),
                collected_at=resolved_collected_at,
            ):
                raw_count += 1
            continue

        if not isinstance(rows, list):
            fetch_error_count += 1
            skipped_count += 1
            if _add_raw_snapshot(
                session,
                endpoint=endpoint,
                beach_num=location.beach_num,
                request_params=request_params,
                payload={
                    "request_params": request_params,
                    "error": (
                        f"KMA beach weather response items are not a list: {type(rows).__name__}"
                    ),
                },
                response_hash=_hash_payload(
                    {
                        "endpoint": endpoint,
                        "beach_num": location.beach_num,
                        "error": "invalid_items_shape",
                    }
                ),
                collected_at=resolved_collected_at,
            ):
                raw_count += 1
            continue

        response_payload = {"request_params": request_params, "items": rows}
        response_hash = _hash_payload(response_payload)
        if _add_raw_snapshot(
            session,
            endpoint=endpoint,
            beach_num=location.beach_num,
            request_params=request_params,
            payload=response_payload,
            response_hash=response_hash,
            collected_at=resolved_collected_at,
        ):
            raw_count += 1

        for serving_row in _build_serving_rows(endpoint, rows):
            if not _is_valid_serving_row(endpoint, serving_row):
                skipped_count += 1
                continue
            _upsert_serving_row(
                session,
                location=location,
                endpoint=endpoint,
                serving_row=serving_row,
                collected_at=resolved_collected_at,
            )
            serving_count += 1

    if locations and fetch_error_count == len(locations):
        raise KmaBeachWeatherError(
            f"Failed to fetch KMA beach weather for all active locations: {endpoint}"
        )

    session.flush()
    return BeachWeatherLoadResult(
        endpoint=endpoint,
        requested_beach_count=len(locations),
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        skipped_row_count=skipped_count,
        fetch_error_count=fetch_error_count,
    )


def _build_catalog_entry(row: Mapping[str, Any]) -> _BeachCatalogEntry | None:
    beach_num = _first_text(row, ("순번", "beach_num", "beachNum"))
    beach_name = _first_text(row, ("해수욕장", "beach_name", "beachName"))
    nx = _first_int(row, ("nx", "NX"))
    ny = _first_int(row, ("ny", "NY"))
    longitude = _first_decimal(row, ("경도", "longitude", "lon", "lng"))
    latitude = _first_decimal(row, ("위도", "latitude", "lat"))
    if (
        beach_num is None
        or beach_name is None
        or nx is None
        or ny is None
        or longitude is None
        or latitude is None
    ):
        return None
    raw_payload = {key: value for key, value in row.items() if not str(key).startswith("_")}
    return _BeachCatalogEntry(
        beach_num=str(int(Decimal(beach_num))),
        beach_name=beach_name,
        nx=nx,
        ny=ny,
        longitude=_decimal_8(longitude),
        latitude=_decimal_8(latitude),
        source_file_name=_optional_text(row.get("_source_file_name")) or "kma_beach_catalog.xlsx",
        source_file_hash=_optional_text(row.get("_source_file_hash")) or _hash_payload(raw_payload),
        source_row_number=_first_int(row, ("_source_row_number",)) or int(Decimal(beach_num)),
        raw_payload=raw_payload,
    )


def _resolve_address_mapping(
    session: Session,
    *,
    beach_name: str,
    longitude: Decimal,
    latitude: Decimal,
) -> _AddressMapping:
    boundary_match = _find_legal_boundary(session, longitude=longitude, latitude=latitude)
    boundary = boundary_match.boundary if boundary_match is not None else None
    legal_mapping_method = boundary_match.method if boundary_match is not None else "unmapped"
    legal_dong_code = boundary.legal_dong_code if boundary is not None else None
    sigungu_code = boundary.sigungu_code if boundary is not None else None
    sido_code = boundary.sido_code if boundary is not None else None
    address_snapshot = boundary.full_region_name if boundary is not None else beach_name
    if legal_dong_code is not None:
        road_row = _find_road_address_by_name(
            session,
            beach_name=beach_name,
            legal_dong_code=legal_dong_code,
        )
        if road_row is not None:
            return _AddressMapping(
                legal_dong_code=legal_dong_code,
                sigungu_code=sigungu_code,
                sido_code=sido_code,
                road_name_code=road_row.road_name_code,
                administrative_dong_code=road_row.administrative_dong_code,
                road_address_management_no=road_row.road_address_management_no,
                road_address=road_row.full_road_address,
                address_snapshot=road_row.full_road_address,
                method="juso_building_name_in_legal_dong",
            )
        return _AddressMapping(
            legal_dong_code=legal_dong_code,
            sigungu_code=sigungu_code,
            sido_code=sido_code,
            road_name_code=None,
            administrative_dong_code=None,
            road_address_management_no=None,
            road_address=None,
            address_snapshot=f"{address_snapshot} {beach_name}",
            method=legal_mapping_method,
        )
    return _AddressMapping(
        legal_dong_code=None,
        sigungu_code=None,
        sido_code=None,
        road_name_code=None,
        administrative_dong_code=None,
        road_address_management_no=None,
        road_address=None,
        address_snapshot=beach_name,
        method="unmapped",
    )


def _find_legal_boundary(
    session: Session,
    *,
    longitude: Decimal,
    latitude: Decimal,
) -> _LegalBoundaryMatch | None:
    point = _point(longitude, latitude)
    covered = session.scalar(
        select(RegionServingBoundary)
        .where(RegionServingBoundary.boundary_level == "legal_dong")
        .where(func.ST_Covers(RegionServingBoundary.geom, point))
        .order_by(func.ST_Area(RegionServingBoundary.geom))
        .limit(1)
    )
    if covered is not None:
        return _LegalBoundaryMatch(boundary=covered, method="postgis_point_in_polygon")
    nearest = session.scalar(
        select(RegionServingBoundary)
        .where(RegionServingBoundary.boundary_level == "legal_dong")
        .where(func.ST_DWithin(RegionServingBoundary.geom, point, 0.05))
        .order_by(func.ST_Distance(RegionServingBoundary.geom, point))
        .limit(1)
    )
    if nearest is not None:
        return _LegalBoundaryMatch(boundary=nearest, method="postgis_nearest_boundary_5km")
    return None


def _find_road_address_by_name(
    session: Session,
    *,
    beach_name: str,
    legal_dong_code: str,
) -> AddressServingJusoRoadAddress | None:
    candidates = list(
        session.scalars(
            select(AddressServingJusoRoadAddress)
            .where(AddressServingJusoRoadAddress.is_active.is_(True))
            .where(AddressServingJusoRoadAddress.legal_dong_code == legal_dong_code)
            .where(
                or_(
                    AddressServingJusoRoadAddress.sigungu_building_name == beach_name,
                    AddressServingJusoRoadAddress.building_registry_name == beach_name,
                )
            )
            .limit(20)
        ).all()
    )
    if len(candidates) == 1:
        return candidates[0]
    return None


def _upsert_place_source_record(
    session: Session,
    *,
    entry: _BeachCatalogEntry,
    raw_hash: str,
    collected_at: datetime,
) -> tuple[SourceRecord, bool]:
    lookup_filters = (
        SourceRecord.provider == KMA_BEACH_PROVIDER,
        SourceRecord.dataset_key == KMA_BEACH_CATALOG_DATASET_KEY,
        SourceRecord.source_entity_type == "place",
        SourceRecord.source_entity_id == entry.beach_num,
        SourceRecord.raw_payload_hash == raw_hash,
    )
    existing = session.scalar(select(SourceRecord).where(*lookup_filters))
    if existing is not None:
        return existing, False
    inserted_id = session.scalar(
        pg_insert(SourceRecord)
        .values(
            dataset_key=KMA_BEACH_CATALOG_DATASET_KEY,
            provider=KMA_BEACH_PROVIDER,
            source_entity_type="place",
            source_entity_id=entry.beach_num,
            source_version=entry.source_file_hash,
            raw_name=entry.beach_name,
            raw_address=None,
            raw_longitude=entry.longitude,
            raw_latitude=entry.latitude,
            raw_geom=_point(entry.longitude, entry.latitude),
            raw_data=entry.raw_payload,
            raw_payload_hash=raw_hash,
            fetched_at=collected_at,
            imported_at=collected_at,
            expires_at=None,
        )
        .on_conflict_do_nothing(
            index_elements=[
                SourceRecord.provider,
                SourceRecord.dataset_key,
                SourceRecord.source_entity_type,
                SourceRecord.source_entity_id,
                SourceRecord.raw_payload_hash,
            ]
        )
        .returning(SourceRecord.id)
    )
    if inserted_id is not None:
        source_record = session.get(SourceRecord, inserted_id)
        if source_record is None:
            raise KmaBeachWeatherError(f"Inserted source record not found: {inserted_id}")
        return source_record, True
    existing = session.scalar(select(SourceRecord).where(*lookup_filters))
    if existing is None:
        raise KmaBeachWeatherError(
            "KMA beach catalog source record conflict was reported but no row was visible."
        )
    return existing, False


def _upsert_place(
    session: Session,
    *,
    entry: _BeachCatalogEntry,
    mapping: _AddressMapping,
    collected_at: datetime,
) -> MapFeature:
    feature = _find_map_feature_by_provider_ref(session, entry.beach_num)
    status = "resolved" if mapping.road_address_management_no else "coordinate_only"
    if mapping.legal_dong_code is None:
        status = "unresolved"
    quality_score = 90 if mapping.road_address_management_no else 80
    if mapping.legal_dong_code is None:
        quality_score = 60
    point = _point(entry.longitude, entry.latitude)
    extra: dict[str, Any] = {
        "provider": KMA_BEACH_PROVIDER,
        "dataset_key": KMA_BEACH_CATALOG_DATASET_KEY,
        "beach_num": entry.beach_num,
        "nx": entry.nx,
        "ny": entry.ny,
        "source_file_name": entry.source_file_name,
        "source_file_hash": entry.source_file_hash,
        "source_row_number": entry.source_row_number,
        "address_mapping_method": mapping.method,
        "source_page_url": KMA_BEACH_SOURCE_PAGE_URL,
    }
    values: dict[str, Any] = {
        "feature_type": "place",
        "name": entry.beach_name,
        "display_name": entry.beach_name,
        "normalized_name": _normalize_search_text(entry.beach_name),
        "subtitle": None,
        "summary": None,
        "description": None,
        "category_code": KMA_BEACH_CATEGORY_CODE,
        "category_name": "해수욕장",
        "geom": point,
        "geometry_kind": "point",
        "centroid": point,
        "longitude": entry.longitude,
        "latitude": entry.latitude,
        "address": mapping.address_snapshot,
        "road_address": mapping.road_address,
        "jibun_address": None,
        "legal_dong_code": mapping.legal_dong_code,
        "sigungu_code": mapping.sigungu_code,
        "sido_code": mapping.sido_code,
        "road_name_code": mapping.road_name_code,
        "admin_dong_code": mapping.administrative_dong_code,
        "road_address_management_no": mapping.road_address_management_no,
        "phone": None,
        "website_url": None,
        "popularity_score": 0,
        "priority_score": 0,
        "status": "active",
        "is_visible": mapping.legal_dong_code is not None,
        "extra": extra,
        "last_seen_at": collected_at,
        "last_verified_at": collected_at,
    }
    if feature is None:
        feature = MapFeature(
            public_id=_public_id(entry.beach_num),
            parent_feature_id=None,
            first_seen_at=collected_at,
            **values,
        )
        session.add(feature)
    else:
        for key, value in values.items():
            setattr(feature, key, value)
    session.flush()
    _upsert_place_detail(
        session,
        feature=feature,
        place_kind="tourist_spot",
        operation_status="seasonal",
        address_resolution_status=status,
        quality_score=quality_score,
        extra=extra,
    )
    session.flush()
    return feature


def _upsert_place_detail(
    session: Session,
    *,
    feature: MapFeature,
    place_kind: str,
    operation_status: str,
    address_resolution_status: str,
    quality_score: int,
    extra: dict[str, Any],
) -> None:
    detail = session.get(PlaceDetail, feature.id)
    values = {
        "place_kind": place_kind,
        "operation_status": operation_status,
        "address_resolution_status": address_resolution_status,
        "verification_status": "public_data_verified",
        "quality_score": quality_score,
        "extra": extra,
    }
    if detail is None:
        session.add(PlaceDetail(feature_id=feature.id, **values))
        return
    for key, value in values.items():
        setattr(detail, key, value)


def _find_map_feature_by_provider_ref(session: Session, beach_num: str) -> MapFeature | None:
    ref = session.scalar(
        select(MapFeatureProviderRef).where(
            MapFeatureProviderRef.provider == KMA_BEACH_PROVIDER,
            MapFeatureProviderRef.provider_dataset_key == KMA_BEACH_CATALOG_DATASET_KEY,
            MapFeatureProviderRef.provider_feature_id == beach_num,
        )
    )
    if ref is None:
        return None
    return session.get(MapFeature, ref.feature_id)


def _upsert_place_provider_ref(
    session: Session,
    *,
    place: MapFeature,
    entry: _BeachCatalogEntry,
    mapping: _AddressMapping,
    fetched_at: datetime,
) -> None:
    ref = session.scalar(
        select(MapFeatureProviderRef).where(
            MapFeatureProviderRef.provider == KMA_BEACH_PROVIDER,
            MapFeatureProviderRef.provider_dataset_key == KMA_BEACH_CATALOG_DATASET_KEY,
            MapFeatureProviderRef.provider_feature_id == entry.beach_num,
        )
    )
    if ref is None:
        ref = MapFeatureProviderRef(
            feature_id=place.id,
            provider=KMA_BEACH_PROVIDER,
            provider_dataset_key=KMA_BEACH_CATALOG_DATASET_KEY,
            provider_feature_id=entry.beach_num,
        )
        session.add(ref)
    ref.url = KMA_BEACH_SOURCE_PAGE_URL
    ref.stable_name = entry.beach_name
    ref.stable_address = mapping.address_snapshot
    ref.stable_phone = None
    ref.last_fetched_at = fetched_at
    ref.expires_at = None


def _upsert_place_source_link(
    session: Session,
    *,
    place: MapFeature,
    source_record: SourceRecord,
) -> bool:
    existing = session.scalar(
        select(MapFeatureSourceLink.id).where(
            MapFeatureSourceLink.feature_id == place.id,
            MapFeatureSourceLink.source_record_id == source_record.id,
        )
    )
    if existing is not None:
        return False
    session.add(
        MapFeatureSourceLink(
            feature_id=place.id,
            source_record_id=source_record.id,
            match_method="provider_dataset_source_id",
            confidence=100,
            is_primary_source=True,
        )
    )
    return True


def _upsert_beach_location(
    session: Session,
    *,
    place: MapFeature,
    entry: _BeachCatalogEntry,
    mapping: _AddressMapping,
    collected_at: datetime,
) -> WeatherBeachLocation:
    location = session.scalar(
        select(WeatherBeachLocation).where(
            WeatherBeachLocation.provider == KMA_BEACH_PROVIDER,
            WeatherBeachLocation.beach_num == entry.beach_num,
        )
    )
    values = {
        "beach_name": entry.beach_name,
        "map_feature_id": place.id,
        "nx": entry.nx,
        "ny": entry.ny,
        "longitude": entry.longitude,
        "latitude": entry.latitude,
        "geom": _point(entry.longitude, entry.latitude),
        "legal_dong_code": mapping.legal_dong_code,
        "sigungu_code": mapping.sigungu_code,
        "sido_code": mapping.sido_code,
        "road_name_code": mapping.road_name_code,
        "road_address_management_no": mapping.road_address_management_no,
        "address_mapping_method": mapping.method,
        "source_file_name": entry.source_file_name,
        "source_file_hash": entry.source_file_hash,
        "source_row_number": entry.source_row_number,
        "raw_payload": entry.raw_payload,
        "collected_at": collected_at,
        "is_active": True,
    }
    if location is None:
        location = WeatherBeachLocation(
            provider=KMA_BEACH_PROVIDER,
            beach_num=entry.beach_num,
            **values,
        )
        session.add(location)
    else:
        for key, value in values.items():
            setattr(location, key, value)
    return location


def _fetch_beach_endpoint(
    client: KmaBeachWeatherApiClientProtocol,
    *,
    endpoint: str,
    beach_num: str,
    collected_at: datetime,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if endpoint == KMA_BEACH_ULTRA_SHORT_ENDPOINT:
        base_date, base_time = _resolve_ultra_short_forecast_base_time(collected_at)
        return client.fetch_ultra_short_forecast(
            beach_num=beach_num,
            base_date=base_date,
            base_time=base_time,
        )
    if endpoint == KMA_BEACH_VILLAGE_ENDPOINT:
        base_date, base_time = _resolve_village_forecast_base_time(collected_at)
        return client.fetch_village_forecast(
            beach_num=beach_num,
            base_date=base_date,
            base_time=base_time,
        )
    if endpoint == KMA_BEACH_WAVE_ENDPOINT:
        return client.fetch_wave_height(
            beach_num=beach_num,
            search_time=_resolve_hourly_search_time(collected_at),
        )
    if endpoint == KMA_BEACH_WATER_TEMP_ENDPOINT:
        return client.fetch_water_temperature(
            beach_num=beach_num,
            search_time=_resolve_hourly_search_time(collected_at),
        )
    if endpoint == KMA_BEACH_TIDE_ENDPOINT:
        return client.fetch_tide_info(
            beach_num=beach_num,
            base_date=collected_at.strftime("%Y%m%d"),
        )
    if endpoint == KMA_BEACH_SUN_ENDPOINT:
        return client.fetch_sun_info(
            beach_num=beach_num,
            base_date=collected_at.strftime("%Y%m%d"),
        )
    raise KmaBeachWeatherError(f"Unsupported KMA beach weather endpoint: {endpoint}")


def _add_raw_snapshot(
    session: Session,
    *,
    endpoint: str,
    beach_num: str,
    request_params: dict[str, str],
    payload: dict[str, Any],
    response_hash: str,
    collected_at: datetime,
) -> bool:
    existing = session.scalar(
        select(WeatherRawBeach.id).where(
            WeatherRawBeach.provider == KMA_BEACH_PROVIDER,
            WeatherRawBeach.endpoint == endpoint,
            WeatherRawBeach.beach_num == beach_num,
            WeatherRawBeach.response_hash == response_hash,
        )
    )
    if existing is not None:
        return False
    session.add(
        WeatherRawBeach(
            provider=KMA_BEACH_PROVIDER,
            endpoint=endpoint,
            beach_num=beach_num,
            request_params=request_params,
            raw_payload=payload,
            response_hash=response_hash,
            collected_at=collected_at,
        )
    )
    return True


def _build_serving_rows(endpoint: str, rows: Iterable[Mapping[str, Any]]) -> list[_ServingBeachRow]:
    if endpoint in {KMA_BEACH_ULTRA_SHORT_ENDPOINT, KMA_BEACH_VILLAGE_ENDPOINT}:
        return [_build_forecast_serving_row(row) for row in rows]
    if endpoint == KMA_BEACH_WAVE_ENDPOINT:
        return [_build_observed_serving_row(row, category_code="WH") for row in rows]
    if endpoint == KMA_BEACH_WATER_TEMP_ENDPOINT:
        return [_build_observed_serving_row(row, category_code="TW") for row in rows]
    if endpoint == KMA_BEACH_TIDE_ENDPOINT:
        return [_build_tide_serving_row(row) for row in rows]
    if endpoint == KMA_BEACH_SUN_ENDPOINT:
        serving_rows: list[_ServingBeachRow] = []
        for row in rows:
            serving_rows.extend(_build_sun_serving_rows(row))
        return serving_rows
    raise KmaBeachWeatherError(f"Unsupported KMA beach weather endpoint: {endpoint}")


def _build_forecast_serving_row(row: Mapping[str, Any]) -> _ServingBeachRow:
    base_date = _compact_date_text(row.get("baseDate"))
    base_time = _compact_time_text(row.get("baseTime"))
    forecast_date = _compact_date_text(row.get("fcstDate"))
    forecast_time = _compact_time_text(row.get("fcstTime"))
    category_code = _optional_text(row.get("category")) or "UNKNOWN"
    spec = SHORT_TERM_CATEGORY_SPECS.get(category_code)
    category_name = spec.category_name if spec else category_code
    normalized_category = spec.normalized_category if spec else category_code.lower()
    unit = spec.unit if spec else None
    source_key = "-".join(
        item or "" for item in (base_date, base_time, forecast_date, forecast_time, category_code)
    )
    return _ServingBeachRow(
        source_record_key=source_key,
        base_date=base_date,
        base_time=base_time,
        forecast_date=forecast_date,
        forecast_time=forecast_time,
        source_observed_time=None,
        observed_at=None,
        forecast_at=_parse_kst_datetime(forecast_date, forecast_time),
        category_code=category_code,
        category_name=category_name,
        normalized_category=normalized_category,
        value=_optional_text(row.get("fcstValue")) or "",
        unit=unit,
        station_name=None,
        raw_payload=dict(row),
    )


def _build_observed_serving_row(row: Mapping[str, Any], *, category_code: str) -> _ServingBeachRow:
    observed_time = _optional_text(row.get("tm"))
    if category_code == "WH":
        category_name = "파고"
        normalized_category = "wave_height"
        value = _optional_text(row.get("wh")) or ""
        unit = "m"
    else:
        category_name = "수온"
        normalized_category = "water_temperature"
        value = _optional_text(row.get("tw")) or ""
        unit = "deg_c"
    return _ServingBeachRow(
        source_record_key=observed_time or _hash_payload(row),
        base_date=None,
        base_time=None,
        forecast_date=None,
        forecast_time=None,
        source_observed_time=observed_time,
        observed_at=_parse_observed_time(observed_time),
        forecast_at=None,
        category_code=category_code,
        category_name=category_name,
        normalized_category=normalized_category,
        value=value,
        unit=unit,
        station_name=None,
        raw_payload=dict(row),
    )


def _build_tide_serving_row(row: Mapping[str, Any]) -> _ServingBeachRow:
    base_date = _compact_date_text(row.get("baseDate"))
    tide_time = _optional_text(row.get("tiTime"))
    tide_type = _optional_text(row.get("tiType"))
    source_key = "-".join(item or "" for item in (base_date, tide_time, tide_type))
    return _ServingBeachRow(
        source_record_key=source_key,
        base_date=base_date,
        base_time=None,
        forecast_date=None,
        forecast_time=None,
        source_observed_time=tide_time,
        observed_at=_parse_kst_datetime(base_date, tide_time),
        forecast_at=None,
        category_code="TIDE",
        category_name="조위",
        normalized_category="tide_level",
        value=_optional_text(row.get("tilevel")) or "",
        unit="cm",
        station_name=_optional_text(row.get("tiStnld")),
        raw_payload=dict(row),
    )


def _build_sun_serving_rows(row: Mapping[str, Any]) -> list[_ServingBeachRow]:
    base_date = _compact_date_text(row.get("baseDate"))
    results: list[_ServingBeachRow] = []
    for category_code, category_name, normalized_category, key in (
        ("SUNRISE", "일출", "sunrise_time", "sunrise"),
        ("SUNSET", "일몰", "sunset_time", "sunset"),
    ):
        value = _optional_text(row.get(key))
        results.append(
            _ServingBeachRow(
                source_record_key=f"{base_date or ''}-{key}",
                base_date=base_date,
                base_time=None,
                forecast_date=None,
                forecast_time=None,
                source_observed_time=value,
                observed_at=_parse_kst_datetime(base_date, value),
                forecast_at=None,
                category_code=category_code,
                category_name=category_name,
                normalized_category=normalized_category,
                value=value or "",
                unit=None,
                station_name=None,
                raw_payload=dict(row),
            )
        )
    return results


def _is_valid_serving_row(endpoint: str, serving_row: _ServingBeachRow) -> bool:
    if not serving_row.value:
        return False
    if endpoint not in {
        KMA_BEACH_WAVE_ENDPOINT,
        KMA_BEACH_WATER_TEMP_ENDPOINT,
        KMA_BEACH_TIDE_ENDPOINT,
        KMA_BEACH_SUN_ENDPOINT,
    }:
        return True
    if serving_row.value in {"-", ":"}:
        return False
    return serving_row.observed_at is not None


def _upsert_serving_row(
    session: Session,
    *,
    location: WeatherBeachLocation,
    endpoint: str,
    serving_row: _ServingBeachRow,
    collected_at: datetime,
) -> WeatherServingBeach:
    existing = session.scalar(
        select(WeatherServingBeach).where(
            WeatherServingBeach.provider == KMA_BEACH_PROVIDER,
            WeatherServingBeach.endpoint == endpoint,
            WeatherServingBeach.beach_num == location.beach_num,
            WeatherServingBeach.source_record_key == serving_row.source_record_key,
            WeatherServingBeach.category_code == serving_row.category_code,
        )
    )
    values = {
        "beach_location_id": location.id,
        "map_feature_id": location.map_feature_id,
        "base_date": serving_row.base_date,
        "base_time": serving_row.base_time,
        "forecast_date": serving_row.forecast_date,
        "forecast_time": serving_row.forecast_time,
        "source_observed_time": serving_row.source_observed_time,
        "observed_at": serving_row.observed_at,
        "forecast_at": serving_row.forecast_at,
        "category_name": serving_row.category_name,
        "normalized_category": serving_row.normalized_category,
        "value": serving_row.value,
        "unit": serving_row.unit,
        "station_name": serving_row.station_name,
        "raw_payload": serving_row.raw_payload,
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = WeatherServingBeach(
            provider=KMA_BEACH_PROVIDER,
            endpoint=endpoint,
            beach_num=location.beach_num,
            source_record_key=serving_row.source_record_key,
            category_code=serving_row.category_code,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _extract_catalog_xlsx(content: bytes) -> tuple[str, bytes]:
    if zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if "xl/workbook.xml" in archive.namelist():
                return "kma_beach_catalog.xlsx", content
            for name in archive.namelist():
                if name.lower().endswith(".xlsx"):
                    return name, archive.read(name)
    if content[:2] == b"PK":
        return "kma_beach_catalog.xlsx", content
    raise KmaBeachWeatherError("KMA beach catalog download did not contain an xlsx file.")


def _read_simple_xlsx_rows(xlsx_bytes: bytes) -> list[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        shared_strings = _read_xlsx_shared_strings(archive)
        sheet_name = next(
            (
                name
                for name in sorted(archive.namelist())
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            ),
            None,
        )
        if sheet_name is None:
            raise KmaBeachWeatherError("KMA beach catalog xlsx has no worksheet.")
        root = ElementTree.fromstring(archive.read(sheet_name))
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    table: list[tuple[int, list[Any]]] = []
    for row_node in root.findall(".//x:sheetData/x:row", namespace):
        row_number = int(row_node.attrib.get("r", "0") or "0")
        values: list[Any] = []
        for cell in row_node.findall("x:c", namespace):
            col_index = _xlsx_col_index(cell.attrib.get("r", ""))
            while len(values) <= col_index:
                values.append(None)
            values[col_index] = _read_xlsx_cell(cell, shared_strings, namespace)
        table.append((row_number, values))

    header: list[str] | None = None
    rows: list[dict[str, Any]] = []
    for row_number, values in table:
        text_values = [_optional_text(value) for value in values]
        if header is None:
            if any(text_values):
                header = [value or "" for value in text_values]
            continue
        item: dict[str, Any] = {"_source_row_number": row_number}
        has_cell_value = False
        for index, key in enumerate(header):
            if not key:
                continue
            value = values[index] if index < len(values) else None
            item[key] = value
            if value is not None and str(value).strip():
                has_cell_value = True
        if has_cell_value:
            rows.append(item)
    return rows


def _read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for node in root.findall(".//x:si", namespace):
        values.append("".join(text.text or "" for text in node.findall(".//x:t", namespace)))
    return values


def _read_xlsx_cell(
    cell: ElementTree.Element,
    shared_strings: list[str],
    namespace: dict[str, str],
) -> Any:
    value_node = cell.find("x:v", namespace)
    if value_node is None or value_node.text is None:
        return None
    value = value_node.text
    if cell.attrib.get("t") == "s":
        return shared_strings[int(value)]
    return value


def _xlsx_col_index(reference: str) -> int:
    letters = "".join(char for char in reference if char.isalpha()).upper()
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def _resolve_ultra_short_forecast_base_time(value: datetime) -> tuple[str, str]:
    now = value.astimezone(KST) - timedelta(minutes=45)
    minute = 30 if now.minute >= 30 else 0
    return now.strftime("%Y%m%d"), f"{now.hour:02d}{minute:02d}"


def _resolve_village_forecast_base_time(value: datetime) -> tuple[str, str]:
    now = value.astimezone(KST) - timedelta(minutes=20)
    base_hours = [2, 5, 8, 11, 14, 17, 20, 23]
    selected_hour = max((hour for hour in base_hours if hour <= now.hour), default=23)
    selected_date = now
    if selected_hour == 23 and now.hour < 2:
        selected_date = now - timedelta(days=1)
    return selected_date.strftime("%Y%m%d"), f"{selected_hour:02d}00"


def _resolve_hourly_search_time(value: datetime) -> str:
    now = value.astimezone(KST) - timedelta(hours=1)
    return now.strftime("%Y%m%d%H00")


def _parse_kst_datetime(date_text: str | None, time_text: str | None) -> datetime | None:
    date_digits = _compact_date_text(date_text)
    time_digits = _compact_time_text(time_text)
    if date_digits is None or time_digits is None:
        return None
    try:
        return datetime.strptime(f"{date_digits}{time_digits}", "%Y%m%d%H%M").replace(tzinfo=KST)
    except ValueError:
        return None


def _parse_observed_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    for fmt, length in (("%Y%m%d%H%M", 12), ("%Y%m%d%H", 10)):
        if len(digits) >= length:
            try:
                return datetime.strptime(digits[:length], fmt).replace(tzinfo=KST)
            except ValueError:
                continue
    return None


def _first_text(row: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        text = _optional_text(row.get(key))
        if text is not None:
            return text
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _WHITESPACE_RE.sub(" ", str(value)).strip()
    return text or None


def _compact_date_text(value: Any) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        return digits[:8]
    return text if len(text) <= 8 else None


def _compact_time_text(value: Any) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 4:
        return digits[-4:]
    if len(digits) == 3:
        return f"0{digits}"
    if len(digits) == 2:
        return f"{digits}00"
    return text if len(text) <= 4 else None


def _first_int(row: Mapping[str, Any], keys: Iterable[str]) -> int | None:
    for key in keys:
        text = _optional_text(row.get(key))
        if text is None:
            continue
        try:
            return int(Decimal(text.replace(",", "")))
        except (InvalidOperation, ValueError):
            continue
    return None


def _first_decimal(row: Mapping[str, Any], keys: Iterable[str]) -> Decimal | None:
    for key in keys:
        text = _optional_text(row.get(key))
        if text is None:
            continue
        try:
            return Decimal(text.replace(",", ""))
        except InvalidOperation:
            continue
    return None


def _decimal_8(value: Decimal) -> Decimal:
    return Decimal(f"{value:.8f}")


def _normalize_search_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.lower()).strip()


def _hash_payload(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _public_id(beach_num: str) -> str:
    digest = hashlib.sha1(f"{KMA_BEACH_CATALOG_DATASET_KEY}:{beach_num}".encode()).hexdigest()
    return f"pl_{digest[:20]}"


def _point(longitude: Decimal, latitude: Decimal) -> WKTElement:
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def _resolve_collected_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(KST)
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)
