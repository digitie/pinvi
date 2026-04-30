from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, cast
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.address import AddressServingJusoRoadAddress, RegionServingBoundary
from app.models.beach import (
    BeachIndexForecast,
    BeachObservation,
    BeachProfile,
    BeachProviderRef,
    BeachSourceRecord,
    BeachWaterQualityMeasurement,
)
from app.models.weather import WeatherBeachLocation

KST = ZoneInfo("Asia/Seoul")
KHOA_PROVIDER = "khoa"
DATA_GO_PROVIDER = "data_go_kr"
KMA_PROVIDER = "kma"
KMA_BEACH_CATALOG_DATASET_KEY = "kma_beach_catalog"
KHOA_BEACH_OBSERVATION_DATASET_KEY = "khoa_beach_observation"
KHOA_BEACH_INDEX_DATASET_KEY = "khoa_beach_index_forecast"
MOF_BEACH_INFO_DATASET_KEY = "mof_beach_info"
MOF_BEACH_WATER_QUALITY_DATASET_KEY = "mof_beach_water_quality"
KHOA_OPENAPI_INFO_URL = "https://www.khoa.go.kr/oceandata/openapi/getOpenApiInfo.do"
KHOA_BEACH_OBSERVATION_URL = "https://khoa.go.kr/oceandata/api/beach/search.do"
KHOA_BEACH_INDEX_URL = "http://apis.data.go.kr/1192136/fcstBeachv2"
MOF_BEACH_INFO_URL = (
    "https://apis.data.go.kr/1192000/service/OceansBeachInfoService1/getOceansBeachInfo1"
)
MOF_BEACH_WATER_QUALITY_URL = (
    "https://apis.data.go.kr/1192000/service/OceansBeachSeawaterService1/"
    "getOceansBeachSeawaterInfo1"
)
COASTAL_SIDO_NAMES = (
    "부산",
    "인천",
    "울산",
    "경기",
    "강원",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
)
MAX_PAGE_SIZE = 300
MAX_PAGE_GUARD = 1000
_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_PERCENT_ENCODED_RE = re.compile(r"%[0-9A-Fa-f]{2}")


class BeachSourceEtlError(RuntimeError):
    pass


class KhoaBeachObservationClientProtocol(Protocol):
    def fetch_observatory_list(self) -> list[dict[str, Any]]: ...

    def fetch_observation(
        self, beach_code: str
    ) -> tuple[dict[str, str], dict[str, Any] | None]: ...


class KhoaBeachIndexClientProtocol(Protocol):
    def fetch_index_forecast_rows(
        self,
        *,
        req_date: date | None = None,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]: ...


class MofBeachInfoClientProtocol(Protocol):
    def fetch_info_rows(
        self, sido_names: Sequence[str] = COASTAL_SIDO_NAMES
    ) -> list[dict[str, Any]]: ...


class MofBeachWaterQualityClientProtocol(Protocol):
    def fetch_quality_rows(
        self,
        *,
        year: int,
        sido_names: Sequence[str] = COASTAL_SIDO_NAMES,
    ) -> list[dict[str, Any]]: ...


class KhoaBeachObservationClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._service_key = service_key if service_key is not None else get_settings().khoa_api_key
        self._client = client

    def fetch_observatory_list(self) -> list[dict[str, Any]]:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            response = client.post(
                KHOA_OPENAPI_INFO_URL,
                data={"id": "36"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if owns_client:
                client.close()
        if not isinstance(payload, dict):
            raise BeachSourceEtlError("KHOA beach openapi metadata response is not an object.")
        observatories = payload.get("observatoryList")
        if not isinstance(observatories, list):
            detail = payload.get("openapiinfoDetail")
            if not isinstance(detail, dict):
                raise BeachSourceEtlError("KHOA beach openapi metadata has no detail object.")
            observatories = detail.get("observatoryList")
        if not isinstance(observatories, list):
            return []
        return [dict(item) for item in observatories if isinstance(item, dict)]

    def fetch_observation(self, beach_code: str) -> tuple[dict[str, str], dict[str, Any] | None]:
        api_key = (self._service_key or "").strip()
        if not api_key:
            raise BeachSourceEtlError("KHOA API key is not configured.")
        params = {
            "DataType": "beach",
            "ServiceKey": api_key,
            "BeachCode": beach_code,
            "ResultType": "json",
        }
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            response = client.get(KHOA_BEACH_OBSERVATION_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        finally:
            if owns_client:
                client.close()
        if not isinstance(payload, dict):
            raise BeachSourceEtlError("KHOA beach observation response is not an object.")
        row = _extract_first_row(cast(dict[str, Any], payload))
        return (
            {
                "DataType": "beach",
                "ServiceKey": "***",
                "BeachCode": beach_code,
                "ResultType": "json",
            },
            row,
        )


class KhoaBeachIndexClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._service_key = (
            service_key
            if service_key is not None
            else settings.khoa_api_key or settings.data_go_service_key
        )
        self._client = client

    def fetch_index_forecast_rows(
        self,
        *,
        req_date: date | None = None,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        api_key = (self._service_key or "").strip()
        if not api_key:
            raise BeachSourceEtlError("KHOA API key is not configured.")
        params = {
            "serviceKey": api_key,
            "type": "json",
            "pageNo": "1",
            "numOfRows": str(MAX_PAGE_SIZE),
        }
        if req_date is not None:
            params["reqDate"] = req_date.strftime("%Y%m%d")
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            response = client.get(_data_go_url_with_service_key(KHOA_BEACH_INDEX_URL, params))
            response.raise_for_status()
            payload = response.json()
        finally:
            if owns_client:
                client.close()
        if not isinstance(payload, dict):
            raise BeachSourceEtlError("KHOA beach index response is not an object.")
        request_params = {**params, "serviceKey": "***"}
        return request_params, _extract_rows(cast(dict[str, Any], payload))


def _data_go_url_with_service_key(base_url: str, params: Mapping[str, str]) -> str:
    service_key = params.get("serviceKey")
    if service_key is None:
        return f"{base_url}?{urlencode(params)}"
    query_parts = [f"serviceKey={_data_go_service_key_query_value(service_key)}"]
    rest = [(key, value) for key, value in params.items() if key != "serviceKey"]
    if rest:
        query_parts.append(urlencode(rest))
    return f"{base_url}?{'&'.join(query_parts)}"


def _data_go_service_key_query_value(service_key: str) -> str:
    stripped = service_key.strip()
    if _PERCENT_ENCODED_RE.search(stripped):
        return stripped
    return quote(stripped, safe="")


class MofBeachInfoClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._service_key = (
            service_key
            if service_key is not None
            else settings.mof_beach_service_key or settings.data_go_service_key
        )
        self._client = client

    def fetch_info_rows(
        self, sido_names: Sequence[str] = COASTAL_SIDO_NAMES
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for sido_name in sido_names:
            rows.extend(
                _fetch_paginated_data_go_rows(
                    service_key=self._service_key,
                    url=MOF_BEACH_INFO_URL,
                    base_params={"SIDO_NM": sido_name, "resultType": "json"},
                    client=self._client,
                    error_label="MOF beach info",
                )
            )
        return rows


class MofBeachWaterQualityClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._service_key = (
            service_key
            if service_key is not None
            else settings.mof_beach_service_key or settings.data_go_service_key
        )
        self._client = client

    def fetch_quality_rows(
        self,
        *,
        year: int,
        sido_names: Sequence[str] = COASTAL_SIDO_NAMES,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for sido_name in sido_names:
            rows.extend(
                _fetch_paginated_data_go_rows(
                    service_key=self._service_key,
                    url=MOF_BEACH_WATER_QUALITY_URL,
                    base_params={
                        "SIDO_NM": sido_name,
                        "RES_YEAR": str(year),
                        "resultType": "json",
                    },
                    client=self._client,
                    error_label="MOF beach water quality",
                )
            )
        return rows


@dataclass(frozen=True)
class BeachProfileSyncResult:
    profile_upsert_count: int
    provider_ref_upsert_count: int


@dataclass(frozen=True)
class KhoaBeachObservationLoadResult:
    catalog_count: int
    requested_beach_count: int
    raw_row_count: int
    observation_row_count: int
    profile_upsert_count: int
    mapped_legal_dong_count: int
    road_address_mapped_count: int
    skipped_row_count: int


@dataclass(frozen=True)
class BeachIndexForecastLoadResult:
    raw_row_count: int
    forecast_row_count: int
    profile_upsert_count: int
    mapped_legal_dong_count: int
    skipped_row_count: int


@dataclass(frozen=True)
class MofBeachInfoLoadResult:
    profile_upsert_count: int
    source_record_count: int
    mapped_legal_dong_count: int
    road_address_mapped_count: int
    skipped_row_count: int


@dataclass(frozen=True)
class MofBeachWaterQualityLoadResult:
    source_record_count: int
    measurement_row_count: int
    profile_upsert_count: int
    mapped_legal_dong_count: int
    skipped_row_count: int


@dataclass(frozen=True)
class _AddressMapping:
    legal_dong_code: str | None
    sigungu_code: str | None
    sido_code: str | None
    road_name_code: str | None
    road_address_management_no: str | None
    road_address: str | None
    address_snapshot: str | None
    method: str


def sync_kma_beach_profiles(
    session: Session,
    *,
    collected_at: datetime | None = None,
) -> BeachProfileSyncResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    profile_count = 0
    provider_ref_count = 0
    locations = session.scalars(
        select(WeatherBeachLocation)
        .where(WeatherBeachLocation.provider == KMA_PROVIDER)
        .where(WeatherBeachLocation.is_active.is_(True))
        .order_by(WeatherBeachLocation.beach_num)
    ).all()
    for location in locations:
        mapping = _AddressMapping(
            legal_dong_code=location.legal_dong_code,
            sigungu_code=location.sigungu_code,
            sido_code=location.sido_code,
            road_name_code=location.road_name_code,
            road_address_management_no=location.road_address_management_no,
            road_address=None,
            address_snapshot=location.beach_name,
            method=location.address_mapping_method,
        )
        beach, created = _upsert_beach_profile(
            session,
            provider=KMA_PROVIDER,
            dataset_key=KMA_BEACH_CATALOG_DATASET_KEY,
            provider_beach_id=location.beach_num,
            display_name=location.beach_name,
            longitude=location.longitude,
            latitude=location.latitude,
            mapping=mapping,
            collected_at=resolved_collected_at,
            map_feature_id=location.map_feature_id,
            source_attributes={
                "kma_beach_num": location.beach_num,
                "nx": location.nx,
                "ny": location.ny,
            },
        )
        _, ref_created = _upsert_provider_ref(
            session,
            beach=beach,
            provider=KMA_PROVIDER,
            dataset_key=KMA_BEACH_CATALOG_DATASET_KEY,
            provider_beach_id=location.beach_num,
            stable_name=location.beach_name,
            stable_address=None,
            url=None,
            fetched_at=resolved_collected_at,
        )
        profile_count += int(created)
        provider_ref_count += int(ref_created)
    session.flush()
    return BeachProfileSyncResult(
        profile_upsert_count=profile_count,
        provider_ref_upsert_count=provider_ref_count,
    )


def load_khoa_beach_observations(
    session: Session,
    client: KhoaBeachObservationClientProtocol,
    *,
    collected_at: datetime | None = None,
) -> KhoaBeachObservationLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    sync_kma_beach_profiles(session, collected_at=resolved_collected_at)
    catalog_rows = client.fetch_observatory_list()
    requested_count = 0
    raw_count = 0
    observation_count = 0
    profile_count = 0
    mapped_count = 0
    road_mapped_count = 0
    skipped_count = 0

    for catalog_row in catalog_rows:
        beach_code = _text(catalog_row.get("id"))
        beach_name = _text(catalog_row.get("name"))
        if beach_code is None or beach_name is None:
            skipped_count += 1
            continue
        longitude = _decimal(catalog_row.get("lon"))
        latitude = _decimal(catalog_row.get("lat"))
        mapping = _resolve_coordinate_mapping(
            session,
            display_name=beach_name,
            longitude=longitude,
            latitude=latitude,
        )
        if mapping.legal_dong_code:
            mapped_count += 1
        if mapping.road_address_management_no:
            road_mapped_count += 1
        beach, created = _upsert_beach_profile(
            session,
            provider=KHOA_PROVIDER,
            dataset_key=KHOA_BEACH_OBSERVATION_DATASET_KEY,
            provider_beach_id=beach_code,
            display_name=beach_name,
            longitude=longitude,
            latitude=latitude,
            mapping=mapping,
            collected_at=resolved_collected_at,
            source_attributes={"khoa_beach_code": beach_code},
        )
        profile_count += int(created)
        _upsert_provider_ref(
            session,
            beach=beach,
            provider=KHOA_PROVIDER,
            dataset_key=KHOA_BEACH_OBSERVATION_DATASET_KEY,
            provider_beach_id=beach_code,
            stable_name=beach_name,
            stable_address=mapping.address_snapshot,
            url=KHOA_BEACH_OBSERVATION_URL,
            fetched_at=resolved_collected_at,
        )
        request_params, observation_row = client.fetch_observation(beach_code)
        requested_count += 1
        if observation_row is None:
            skipped_count += 1
            continue
        normalized_row = _normalize_row(observation_row)
        response_hash = _hash_payload(normalized_row)
        observed_at = (
            _parse_datetime(_first_text(normalized_row, "obs_time", "obsTime", "관측시각"))
            or resolved_collected_at
        )
        source_record = _add_source_record(
            session,
            provider=KHOA_PROVIDER,
            dataset_key=KHOA_BEACH_OBSERVATION_DATASET_KEY,
            endpoint=KHOA_BEACH_OBSERVATION_URL,
            source_record_id=f"{beach_code}:{observed_at.isoformat()}",
            request_params=request_params,
            payload=normalized_row,
            response_hash=response_hash,
            collected_at=resolved_collected_at,
        )
        if source_record.created:
            raw_count += 1
        _upsert_observation(
            session,
            beach=beach,
            provider_beach_id=beach_code,
            source_record=source_record.record,
            row=normalized_row,
            observed_at=observed_at,
            collected_at=resolved_collected_at,
        )
        observation_count += 1

    session.flush()
    return KhoaBeachObservationLoadResult(
        catalog_count=len(catalog_rows),
        requested_beach_count=requested_count,
        raw_row_count=raw_count,
        observation_row_count=observation_count,
        profile_upsert_count=profile_count,
        mapped_legal_dong_count=mapped_count,
        road_address_mapped_count=road_mapped_count,
        skipped_row_count=skipped_count,
    )


def load_khoa_beach_index_forecasts(
    session: Session,
    client: KhoaBeachIndexClientProtocol,
    *,
    collected_at: datetime | None = None,
    req_date: date | None = None,
) -> BeachIndexForecastLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    sync_kma_beach_profiles(session, collected_at=resolved_collected_at)
    request_params, rows = client.fetch_index_forecast_rows(req_date=req_date)
    raw_count = 0
    forecast_count = 0
    profile_count = 0
    mapped_count = 0
    skipped_count = 0

    for row in rows:
        normalized_row = _normalize_row(row)
        beach_name = _first_text(normalized_row, "bbchNm", "beachName", "해수욕장명")
        if beach_name is None:
            skipped_count += 1
            continue
        longitude = _decimal(_first_value(normalized_row, "lot", "lon", "longitude", "경도"))
        latitude = _decimal(_first_value(normalized_row, "lat", "latitude", "위도"))
        mapping = _resolve_coordinate_mapping(
            session,
            display_name=beach_name,
            longitude=longitude,
            latitude=latitude,
        )
        if mapping.legal_dong_code:
            mapped_count += 1
        provider_place_code = _first_text(normalized_row, "placeCode", "place_code")
        provider_id = provider_place_code or _source_id_from_name_location(
            beach_name,
            longitude,
            latitude,
        )
        beach, created = _upsert_beach_profile(
            session,
            provider=KHOA_PROVIDER,
            dataset_key=KHOA_BEACH_INDEX_DATASET_KEY,
            provider_beach_id=provider_id,
            display_name=beach_name,
            longitude=longitude,
            latitude=latitude,
            mapping=mapping,
            collected_at=resolved_collected_at,
            source_attributes={"khoa_index_place_code": provider_place_code},
        )
        profile_count += int(created)
        _upsert_provider_ref(
            session,
            beach=beach,
            provider=KHOA_PROVIDER,
            dataset_key=KHOA_BEACH_INDEX_DATASET_KEY,
            provider_beach_id=provider_id,
            stable_name=beach_name,
            stable_address=mapping.address_snapshot,
            url=KHOA_BEACH_INDEX_URL,
            fetched_at=resolved_collected_at,
        )
        forecast_date = _parse_date(_first_text(normalized_row, "predcYmd", "forecastDate"))
        if forecast_date is None:
            skipped_count += 1
            continue
        forecast_slot = _first_text(normalized_row, "predcNoonSeCd", "forecastSlot") or "unknown"
        response_hash = _hash_payload(normalized_row)
        source_record_key = f"{provider_id}:{forecast_date.isoformat()}:{forecast_slot}"
        source_record = _add_source_record(
            session,
            provider=KHOA_PROVIDER,
            dataset_key=KHOA_BEACH_INDEX_DATASET_KEY,
            endpoint=KHOA_BEACH_INDEX_URL,
            source_record_id=source_record_key,
            request_params=request_params,
            payload=normalized_row,
            response_hash=response_hash,
            collected_at=resolved_collected_at,
        )
        if source_record.created:
            raw_count += 1
        _upsert_index_forecast(
            session,
            beach=beach,
            source_record=source_record.record,
            provider_place_code=provider_place_code,
            row=normalized_row,
            forecast_date=forecast_date,
            forecast_slot=forecast_slot,
            collected_at=resolved_collected_at,
        )
        forecast_count += 1

    session.flush()
    return BeachIndexForecastLoadResult(
        raw_row_count=raw_count,
        forecast_row_count=forecast_count,
        profile_upsert_count=profile_count,
        mapped_legal_dong_count=mapped_count,
        skipped_row_count=skipped_count,
    )


def load_mof_beach_info(
    session: Session,
    client: MofBeachInfoClientProtocol,
    *,
    collected_at: datetime | None = None,
    sido_names: Sequence[str] = COASTAL_SIDO_NAMES,
) -> MofBeachInfoLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    sync_kma_beach_profiles(session, collected_at=resolved_collected_at)
    rows = client.fetch_info_rows(sido_names)
    profile_count = 0
    source_count = 0
    mapped_count = 0
    road_mapped_count = 0
    skipped_count = 0

    for row in rows:
        normalized_row = _normalize_row(row)
        beach_name = _first_text(normalized_row, "staNm", "sta_nm", "해수욕장명", "정점명")
        if beach_name is None:
            skipped_count += 1
            continue
        longitude = _decimal(_first_value(normalized_row, "lon", "lot", "longitude", "경도"))
        latitude = _decimal(_first_value(normalized_row, "lat", "latitude", "위도"))
        mapping = _resolve_coordinate_mapping(
            session,
            display_name=beach_name,
            longitude=longitude,
            latitude=latitude,
        )
        if mapping.legal_dong_code:
            mapped_count += 1
        if mapping.road_address_management_no:
            road_mapped_count += 1
        provider_id = _mof_source_id(normalized_row, beach_name, longitude, latitude)
        source_record = _add_source_record(
            session,
            provider=DATA_GO_PROVIDER,
            dataset_key=MOF_BEACH_INFO_DATASET_KEY,
            endpoint=MOF_BEACH_INFO_URL,
            source_record_id=provider_id,
            request_params={"ServiceKey": "***", "resultType": "json"},
            payload=normalized_row,
            response_hash=_hash_payload(normalized_row),
            collected_at=resolved_collected_at,
        )
        if source_record.created:
            source_count += 1
        beach, created = _upsert_beach_profile(
            session,
            provider=DATA_GO_PROVIDER,
            dataset_key=MOF_BEACH_INFO_DATASET_KEY,
            provider_beach_id=provider_id,
            display_name=beach_name,
            longitude=longitude,
            latitude=latitude,
            mapping=mapping,
            collected_at=resolved_collected_at,
            source_attributes={"mof_num": _first_text(normalized_row, "num")},
            detail_values={
                "beach_width_m": _decimal(
                    _first_value(normalized_row, "beachWid", "beach_wid", "해변폭")
                ),
                "beach_length_m": _decimal(
                    _first_value(normalized_row, "beachLen", "beach_len", "해변총연장")
                ),
                "beach_material": _first_text(normalized_row, "beachKnd", "beach_knd", "특징"),
                "homepage_url": _normalize_url(
                    _first_text(normalized_row, "linkAddr", "link_addr", "관련사이트")
                ),
                "homepage_name": _first_text(normalized_row, "linkNm", "link_nm", "관련사이트명"),
                "image_url": _normalize_url(
                    _first_text(normalized_row, "beachImg", "beach_img", "이미지")
                ),
                "emergency_contact": _first_text(
                    normalized_row, "linkTel", "link_tel", "비상연락처"
                ),
            },
        )
        profile_count += int(created)
        _upsert_provider_ref(
            session,
            beach=beach,
            provider=DATA_GO_PROVIDER,
            dataset_key=MOF_BEACH_INFO_DATASET_KEY,
            provider_beach_id=provider_id,
            stable_name=beach_name,
            stable_address=mapping.address_snapshot,
            url=MOF_BEACH_INFO_URL,
            fetched_at=resolved_collected_at,
        )

    session.flush()
    return MofBeachInfoLoadResult(
        profile_upsert_count=profile_count,
        source_record_count=source_count,
        mapped_legal_dong_count=mapped_count,
        road_address_mapped_count=road_mapped_count,
        skipped_row_count=skipped_count,
    )


def load_mof_beach_water_quality(
    session: Session,
    client: MofBeachWaterQualityClientProtocol,
    *,
    year: int,
    collected_at: datetime | None = None,
    sido_names: Sequence[str] = COASTAL_SIDO_NAMES,
) -> MofBeachWaterQualityLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    sync_kma_beach_profiles(session, collected_at=resolved_collected_at)
    rows = client.fetch_quality_rows(year=year, sido_names=sido_names)
    source_count = 0
    measurement_count = 0
    profile_count = 0
    mapped_count = 0
    skipped_count = 0

    for row in rows:
        normalized_row = _normalize_row(row)
        beach_name = _first_text(normalized_row, "staNm", "sta_nm", "해수욕장명", "정점명")
        if beach_name is None:
            skipped_count += 1
            continue
        longitude = _decimal(_first_value(normalized_row, "lon", "lot", "longitude", "경도"))
        latitude = _decimal(_first_value(normalized_row, "lat", "latitude", "위도"))
        mapping = _resolve_coordinate_mapping(
            session,
            display_name=beach_name,
            longitude=longitude,
            latitude=latitude,
        )
        if mapping.legal_dong_code:
            mapped_count += 1
        provider_id = _mof_source_id(normalized_row, beach_name, longitude, latitude)
        beach, created = _upsert_beach_profile(
            session,
            provider=DATA_GO_PROVIDER,
            dataset_key=MOF_BEACH_WATER_QUALITY_DATASET_KEY,
            provider_beach_id=provider_id,
            display_name=beach_name,
            longitude=longitude,
            latitude=latitude,
            mapping=mapping,
            collected_at=resolved_collected_at,
            source_attributes={"mof_water_quality_num": _first_text(normalized_row, "num")},
        )
        profile_count += int(created)
        _upsert_provider_ref(
            session,
            beach=beach,
            provider=DATA_GO_PROVIDER,
            dataset_key=MOF_BEACH_WATER_QUALITY_DATASET_KEY,
            provider_beach_id=provider_id,
            stable_name=beach_name,
            stable_address=mapping.address_snapshot,
            url=MOF_BEACH_WATER_QUALITY_URL,
            fetched_at=resolved_collected_at,
        )
        source_record_key = _quality_source_key(normalized_row, provider_id, year)
        source_record = _add_source_record(
            session,
            provider=DATA_GO_PROVIDER,
            dataset_key=MOF_BEACH_WATER_QUALITY_DATASET_KEY,
            endpoint=MOF_BEACH_WATER_QUALITY_URL,
            source_record_id=source_record_key,
            request_params={"ServiceKey": "***", "resultType": "json", "RES_YEAR": str(year)},
            payload=normalized_row,
            response_hash=_hash_payload(normalized_row),
            collected_at=resolved_collected_at,
        )
        if source_record.created:
            source_count += 1
        _upsert_water_quality_measurement(
            session,
            beach=beach,
            source_record=source_record.record,
            source_record_key=source_record_key,
            row=normalized_row,
            mapping=mapping,
            longitude=longitude,
            latitude=latitude,
            collected_at=resolved_collected_at,
            default_year=year,
        )
        measurement_count += 1

    session.flush()
    return MofBeachWaterQualityLoadResult(
        source_record_count=source_count,
        measurement_row_count=measurement_count,
        profile_upsert_count=profile_count,
        mapped_legal_dong_count=mapped_count,
        skipped_row_count=skipped_count,
    )


@dataclass(frozen=True)
class _SourceRecordResult:
    record: BeachSourceRecord
    created: bool


def _fetch_paginated_data_go_rows(
    *,
    service_key: str | None,
    url: str,
    base_params: dict[str, str],
    client: httpx.Client | None,
    error_label: str,
) -> list[dict[str, Any]]:
    api_key = (service_key or "").strip()
    if not api_key:
        raise BeachSourceEtlError(f"{error_label} service key is not configured.")

    rows: list[dict[str, Any]] = []
    page_no = 1
    owns_client = client is None
    resolved_client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        while page_no <= MAX_PAGE_GUARD:
            params = {
                **base_params,
                "ServiceKey": api_key,
                "pageNo": str(page_no),
                "numOfRows": str(MAX_PAGE_SIZE),
            }
            response = resolved_client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise BeachSourceEtlError(f"{error_label} response is not an object.")
            page_rows, total_count = _extract_data_go_response_rows(cast(dict[str, Any], payload))
            rows.extend(page_rows)
            if not page_rows or len(rows) >= total_count or len(page_rows) < MAX_PAGE_SIZE:
                return rows
            page_no += 1
    finally:
        if owns_client:
            resolved_client.close()
    raise BeachSourceEtlError(f"{error_label} pagination exceeded guard.")


def _add_source_record(
    session: Session,
    *,
    provider: str,
    dataset_key: str,
    endpoint: str,
    source_record_id: str,
    request_params: dict[str, Any],
    payload: dict[str, Any],
    response_hash: str,
    collected_at: datetime,
) -> _SourceRecordResult:
    existing = session.scalar(
        select(BeachSourceRecord).where(
            BeachSourceRecord.provider == provider,
            BeachSourceRecord.dataset_key == dataset_key,
            BeachSourceRecord.source_record_id == source_record_id,
            BeachSourceRecord.response_hash == response_hash,
        )
    )
    if existing is not None:
        return _SourceRecordResult(record=existing, created=False)
    record = BeachSourceRecord(
        provider=provider,
        dataset_key=dataset_key,
        endpoint=endpoint,
        source_record_id=source_record_id,
        request_params=request_params,
        raw_payload=payload,
        response_hash=response_hash,
        collected_at=collected_at,
    )
    session.add(record)
    session.flush()
    return _SourceRecordResult(record=record, created=True)


def _upsert_observation(
    session: Session,
    *,
    beach: BeachProfile,
    provider_beach_id: str,
    source_record: BeachSourceRecord,
    row: dict[str, Any],
    observed_at: datetime,
    collected_at: datetime,
) -> BeachObservation:
    existing = session.scalar(
        select(BeachObservation).where(
            BeachObservation.provider == KHOA_PROVIDER,
            BeachObservation.provider_beach_id == provider_beach_id,
            BeachObservation.observed_at == observed_at,
        )
    )
    values = {
        "beach_id": beach.id,
        "source_record_id": source_record.id,
        "provider_dataset_key": KHOA_BEACH_OBSERVATION_DATASET_KEY,
        "observation_station_name": _first_text(row, "obs_post_name", "obsPostName"),
        "tide": _first_text(row, "tide"),
        "wave_height_m": _decimal(_first_value(row, "wave_height", "waveHeight")),
        "water_temperature_c": _decimal(_first_value(row, "water_temp", "waterTemp")),
        "wind_speed_ms": _decimal(_first_value(row, "wind_speed", "windSpeed")),
        "wind_direction": _first_text(row, "wind_direct", "windDirect"),
        "forecast_status": _extract_forecast_status(row),
        "quota_snapshot": _first_text(row, "obs_last_req_cnt", "obsLastReqCnt"),
        "raw_payload": row,
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = BeachObservation(
            provider=KHOA_PROVIDER,
            provider_beach_id=provider_beach_id,
            observed_at=observed_at,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _upsert_index_forecast(
    session: Session,
    *,
    beach: BeachProfile,
    source_record: BeachSourceRecord,
    provider_place_code: str | None,
    row: dict[str, Any],
    forecast_date: date,
    forecast_slot: str,
    collected_at: datetime,
) -> BeachIndexForecast:
    existing = session.scalar(
        select(BeachIndexForecast).where(
            BeachIndexForecast.provider == KHOA_PROVIDER,
            BeachIndexForecast.provider_dataset_key == KHOA_BEACH_INDEX_DATASET_KEY,
            BeachIndexForecast.beach_id == beach.id,
            BeachIndexForecast.forecast_date == forecast_date,
            BeachIndexForecast.forecast_slot == forecast_slot,
        )
    )
    values = {
        "source_record_id": source_record.id,
        "provider_place_code": provider_place_code,
        "index_score": _decimal(_first_value(row, "lastScr", "indexScore")),
        "total_index": _first_text(row, "totalIndex", "해수욕지수"),
        "max_wave_height_m": _decimal(_first_value(row, "maxWvhgt", "최고파고")),
        "avg_water_temperature_c": _decimal(_first_value(row, "avgWtem", "수온")),
        "avg_air_temperature_c": _decimal(_first_value(row, "avgArtmp", "기온")),
        "max_wind_speed_ms": _decimal(_first_value(row, "maxWspd", "최고풍속")),
        "raw_payload": row,
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = BeachIndexForecast(
            beach_id=beach.id,
            provider=KHOA_PROVIDER,
            provider_dataset_key=KHOA_BEACH_INDEX_DATASET_KEY,
            forecast_date=forecast_date,
            forecast_slot=forecast_slot,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _upsert_water_quality_measurement(
    session: Session,
    *,
    beach: BeachProfile,
    source_record: BeachSourceRecord,
    source_record_key: str,
    row: dict[str, Any],
    mapping: _AddressMapping,
    longitude: Decimal | None,
    latitude: Decimal | None,
    collected_at: datetime,
    default_year: int,
) -> BeachWaterQualityMeasurement:
    existing = session.scalar(
        select(BeachWaterQualityMeasurement).where(
            BeachWaterQualityMeasurement.provider == DATA_GO_PROVIDER,
            BeachWaterQualityMeasurement.source_record_key == source_record_key,
        )
    )
    survey_year = _int(_first_value(row, "resYear", "res_year", "조사년도")) or default_year
    values = {
        "beach_id": beach.id,
        "source_record_id": source_record.id,
        "survey_year": survey_year,
        "survey_date": _parse_date(_first_text(row, "resDate", "res_date", "조사일자")),
        "survey_round": _first_text(row, "resNum", "res_num", "회차"),
        "survey_kind": _first_text(row, "resKnd", "res_knd", "조사종류"),
        "survey_location": _first_text(row, "resLoc", "res_loc", "조사지점"),
        "survey_location_detail": _first_text(
            row, "resLocDetail", "res_loc_detail", "조사지점상세"
        ),
        "ecoli_result": _first_text(row, "res1", "대장균"),
        "enterococcus_result": _first_text(row, "res2", "장구균"),
        "suitability": _first_text(row, "resYn", "res_yn", "적합여부"),
        "longitude": longitude,
        "latitude": latitude,
        "geom": _point_or_none(longitude, latitude),
        "legal_dong_code": mapping.legal_dong_code,
        "sigungu_code": mapping.sigungu_code,
        "sido_code": mapping.sido_code,
        "address_mapping_method": mapping.method,
        "raw_payload": row,
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = BeachWaterQualityMeasurement(
            provider=DATA_GO_PROVIDER,
            source_record_key=source_record_key,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _upsert_beach_profile(
    session: Session,
    *,
    provider: str,
    dataset_key: str,
    provider_beach_id: str,
    display_name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
    mapping: _AddressMapping,
    collected_at: datetime,
    source_attributes: dict[str, Any],
    map_feature_id: Any | None = None,
    detail_values: dict[str, Any] | None = None,
) -> tuple[BeachProfile, bool]:
    existing = _find_profile_by_provider_ref(session, provider, dataset_key, provider_beach_id)
    if existing is None:
        existing = _find_profile_by_name_location(session, display_name, longitude, latitude)
    created = False
    if existing is None:
        existing = BeachProfile(
            canonical_key=_profile_canonical_key(
                display_name, longitude, latitude, provider, provider_beach_id
            ),
            display_name=display_name,
            normalized_name=_normalize_search_text(display_name),
            representative_provider=provider,
            representative_dataset_key=dataset_key,
            longitude=longitude,
            latitude=latitude,
            geom=_point_or_none(longitude, latitude),
            legal_dong_code=mapping.legal_dong_code,
            sigungu_code=mapping.sigungu_code,
            sido_code=mapping.sido_code,
            road_name_code=mapping.road_name_code,
            road_address_management_no=mapping.road_address_management_no,
            road_address=mapping.road_address,
            address_snapshot=mapping.address_snapshot,
            address_mapping_method=mapping.method,
            source_specific_attributes=_compact_dict(source_attributes),
            collected_at=collected_at,
            map_feature_id=map_feature_id,
            is_active=True,
        )
        session.add(existing)
        session.flush()
        created = True
    else:
        if existing.map_feature_id is None and map_feature_id is not None:
            existing.map_feature_id = map_feature_id
        if existing.longitude is None and longitude is not None:
            existing.longitude = longitude
            existing.latitude = latitude
            existing.geom = _point_or_none(longitude, latitude)
        if _address_rank(mapping.method) >= _address_rank(existing.address_mapping_method):
            existing.legal_dong_code = mapping.legal_dong_code
            existing.sigungu_code = mapping.sigungu_code
            existing.sido_code = mapping.sido_code
            existing.road_name_code = mapping.road_name_code
            existing.road_address_management_no = mapping.road_address_management_no
            existing.road_address = mapping.road_address
            existing.address_snapshot = mapping.address_snapshot
            existing.address_mapping_method = mapping.method
        existing.source_specific_attributes = {
            **(existing.source_specific_attributes or {}),
            **_compact_dict(source_attributes),
        }
        existing.collected_at = collected_at
        existing.is_active = True

    for key, value in (detail_values or {}).items():
        if value is not None:
            setattr(existing, key, value)
    return existing, created


def _upsert_provider_ref(
    session: Session,
    *,
    beach: BeachProfile,
    provider: str,
    dataset_key: str,
    provider_beach_id: str,
    stable_name: str | None,
    stable_address: str | None,
    url: str | None,
    fetched_at: datetime,
) -> tuple[BeachProviderRef, bool]:
    existing = session.scalar(
        select(BeachProviderRef).where(
            BeachProviderRef.provider == provider,
            BeachProviderRef.provider_dataset_key == dataset_key,
            BeachProviderRef.provider_beach_id == provider_beach_id,
        )
    )
    values = {
        "beach_id": beach.id,
        "stable_name": stable_name,
        "stable_address": stable_address,
        "url": url,
        "last_fetched_at": fetched_at,
    }
    if existing is None:
        existing = BeachProviderRef(
            provider=provider,
            provider_dataset_key=dataset_key,
            provider_beach_id=provider_beach_id,
            **values,
        )
        session.add(existing)
        return existing, True
    for key, value in values.items():
        setattr(existing, key, value)
    return existing, False


def _find_profile_by_provider_ref(
    session: Session,
    provider: str,
    dataset_key: str,
    provider_beach_id: str,
) -> BeachProfile | None:
    ref = session.scalar(
        select(BeachProviderRef).where(
            BeachProviderRef.provider == provider,
            BeachProviderRef.provider_dataset_key == dataset_key,
            BeachProviderRef.provider_beach_id == provider_beach_id,
        )
    )
    if ref is None:
        return None
    return session.get(BeachProfile, ref.beach_id)


def _find_profile_by_name_location(
    session: Session,
    display_name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
) -> BeachProfile | None:
    normalized_name = _normalize_search_text(display_name)
    statement = select(BeachProfile).where(BeachProfile.normalized_name == normalized_name)
    if longitude is not None and latitude is not None:
        point = _point(longitude, latitude)
        matched = session.scalar(
            statement.where(BeachProfile.geom.is_not(None))
            .where(func.ST_DWithin(BeachProfile.geom, point, 0.03))
            .order_by(func.ST_Distance(BeachProfile.geom, point))
            .limit(1)
        )
        if matched is not None:
            return matched
    return session.scalar(statement.limit(1))


def _resolve_coordinate_mapping(
    session: Session,
    *,
    display_name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
) -> _AddressMapping:
    if longitude is None or latitude is None:
        return _AddressMapping(None, None, None, None, None, None, display_name, "unmapped")
    point = _point(longitude, latitude)
    boundary = session.scalar(
        select(RegionServingBoundary)
        .where(RegionServingBoundary.boundary_level == "legal_dong")
        .where(func.ST_Covers(RegionServingBoundary.geom, point))
        .order_by(func.ST_Area(RegionServingBoundary.geom))
        .limit(1)
    )
    method = "postgis_point_in_polygon"
    if boundary is None:
        boundary = session.scalar(
            select(RegionServingBoundary)
            .where(RegionServingBoundary.boundary_level == "legal_dong")
            .where(func.ST_DWithin(RegionServingBoundary.geom, point, 0.05))
            .order_by(func.ST_Distance(RegionServingBoundary.geom, point))
            .limit(1)
        )
        method = "postgis_nearest_boundary_5km" if boundary is not None else "unmapped"
    if boundary is None or boundary.legal_dong_code is None:
        return _AddressMapping(None, None, None, None, None, None, display_name, "unmapped")

    road = _find_road_address_by_name(
        session,
        display_name=display_name,
        legal_dong_code=boundary.legal_dong_code,
    )
    if road is not None:
        return _AddressMapping(
            legal_dong_code=boundary.legal_dong_code,
            sigungu_code=boundary.sigungu_code,
            sido_code=boundary.sido_code,
            road_name_code=road.road_name_code,
            road_address_management_no=road.road_address_management_no,
            road_address=road.full_road_address,
            address_snapshot=road.full_road_address,
            method="juso_building_name_in_legal_dong",
        )
    return _AddressMapping(
        legal_dong_code=boundary.legal_dong_code,
        sigungu_code=boundary.sigungu_code,
        sido_code=boundary.sido_code,
        road_name_code=None,
        road_address_management_no=None,
        road_address=None,
        address_snapshot=boundary.full_region_name,
        method=method,
    )


def _find_road_address_by_name(
    session: Session,
    *,
    display_name: str,
    legal_dong_code: str,
) -> AddressServingJusoRoadAddress | None:
    candidates = session.scalars(
        select(AddressServingJusoRoadAddress)
        .where(AddressServingJusoRoadAddress.is_active.is_(True))
        .where(AddressServingJusoRoadAddress.legal_dong_code == legal_dong_code)
        .where(
            (AddressServingJusoRoadAddress.sigungu_building_name == display_name)
            | (AddressServingJusoRoadAddress.building_registry_name == display_name)
        )
        .limit(20)
    ).all()
    if len(candidates) == 1:
        return candidates[0]
    return None


def _extract_data_go_response_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    response = payload.get("response")
    if not isinstance(response, dict):
        for value in payload.values():
            if isinstance(value, dict):
                header = value.get("header")
                if isinstance(header, dict):
                    result_code = _text(header.get("code") or header.get("resultCode"))
                    if result_code in {"03", "NO_DATA"}:
                        return [], 0
                    if result_code not in {None, "00", "0", "NORMAL_CODE"}:
                        message = _text(header.get("message") or header.get("resultMsg"))
                        raise BeachSourceEtlError(
                            f"data.go.kr response error {result_code}: {message or 'unknown error'}"
                        )
                rows = _extract_rows(value)
                total_count = _int(value.get("totalCount")) or len(rows)
                return rows, total_count
        rows = _extract_rows(payload)
        return rows, len(rows)
    header = response.get("header")
    if isinstance(header, dict):
        result_code = _text(header.get("resultCode"))
        if result_code in {"03", "NO_DATA"}:
            return [], 0
        if result_code not in {None, "00", "0", "NORMAL_CODE"}:
            message = _text(header.get("resultMsg")) or "unknown error"
            raise BeachSourceEtlError(f"data.go.kr response error {result_code}: {message}")
    body = response.get("body")
    if not isinstance(body, dict):
        return [], 0
    rows = _extract_rows(body)
    total_count = _int(body.get("totalCount")) or len(rows)
    return rows, total_count


def _extract_first_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = _extract_rows(payload)
    return rows[0] if rows else None


def _extract_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    for key in ("data", "list", "items", "item", "result"):
        if key in payload:
            candidates.append(payload[key])
    for value in payload.values():
        if isinstance(value, dict):
            if any(key in value for key in ("items", "item", "data", "list")):
                candidates.extend(
                    [value.get("items"), value.get("item"), value.get("data"), value.get("list")]
                )
    response = payload.get("response")
    if isinstance(response, dict):
        body = response.get("body")
        if isinstance(body, dict):
            candidates.extend([body.get("items"), body.get("item")])
            items = body.get("items")
            if isinstance(items, dict):
                candidates.append(items.get("item"))
    result = payload.get("result")
    if isinstance(result, dict):
        candidates.extend([result.get("data"), result.get("list"), result.get("items")])

    for candidate in candidates:
        rows = _rows_from_candidate(candidate)
        if rows:
            return rows
    if candidates:
        return []
    return [dict(payload)] if payload else []


def _rows_from_candidate(candidate: Any) -> list[dict[str, Any]]:
    if isinstance(candidate, list):
        return [dict(item) for item in candidate if isinstance(item, dict)]
    if isinstance(candidate, dict):
        item = candidate.get("item")
        if item is not None:
            return _rows_from_candidate(item)
        return [dict(candidate)]
    return []


def _normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        normalized[str(key).strip()] = _normalize_value(value)
    return normalized


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        return _normalize_row(cast(Mapping[str, Any], value))
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _extract_forecast_status(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key.lower().startswith("day") and key.lower().endswith("status")
    }


def _mof_source_id(
    row: Mapping[str, Any],
    beach_name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
) -> str:
    explicit = _first_text(row, "num")
    if explicit is not None:
        return explicit
    sido = _first_text(row, "sidoNm", "sido_nm", "시도명") or ""
    gugun = _first_text(row, "gugunNm", "gugun_nm", "구군명") or ""
    return _source_id_from_name_location(f"{sido}:{gugun}:{beach_name}", longitude, latitude)


def _quality_source_key(row: Mapping[str, Any], provider_id: str, default_year: int) -> str:
    parts = [
        MOF_BEACH_WATER_QUALITY_DATASET_KEY,
        provider_id,
        _first_text(row, "num") or "",
        _first_text(row, "resYear", "res_year", "조사년도") or str(default_year),
        _first_text(row, "resDate", "res_date", "조사일자") or "",
        _first_text(row, "resNum", "res_num", "회차") or "",
        _first_text(row, "resLoc", "res_loc", "조사지점") or "",
        _first_text(row, "resLocDetail", "res_loc_detail", "조사지점상세") or "",
    ]
    return ":".join(parts)


def _source_id_from_name_location(
    name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
) -> str:
    coord = ""
    if longitude is not None and latitude is not None:
        coord = f":{longitude.quantize(Decimal('0.0001'))}:{latitude.quantize(Decimal('0.0001'))}"
    return hashlib.sha1(f"{_normalize_search_text(name)}{coord}".encode()).hexdigest()


def _profile_canonical_key(
    name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
    provider: str,
    provider_beach_id: str,
) -> str:
    if longitude is not None and latitude is not None:
        return (
            f"beach:{_normalize_search_text(name)}:"
            f"{longitude.quantize(Decimal('0.0001'))}:"
            f"{latitude.quantize(Decimal('0.0001'))}"
        )[:180]
    return f"beach:{provider}:{provider_beach_id}"[:180]


def _first_value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _first_text(row: Mapping[str, Any], *keys: str) -> str | None:
    return _text(_first_value(row, *keys))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = _clean_text(str(value))
    return cleaned or None


def _clean_text(value: str) -> str:
    unescaped = html.unescape(value)
    without_tags = _HTML_TAG_RE.sub(" ", unescaped)
    return _WHITESPACE_RE.sub(" ", without_tags).strip()


def _normalize_search_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", _clean_text(value).lower()).strip()


def _decimal(value: Any) -> Decimal | None:
    text_value = _text(value)
    if text_value is None:
        return None
    try:
        return Decimal(text_value.replace(",", "")).quantize(Decimal("0.00000001"))
    except (InvalidOperation, ValueError):
        return None


def _int(value: Any) -> int | None:
    text_value = _text(value)
    if text_value is None:
        return None
    try:
        return int(text_value.replace(",", ""))
    except ValueError:
        return None


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    compact = value.replace("-", "").replace(".", "").strip()
    if len(compact) == 8 and compact.isdigit():
        return date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    cleaned = value.replace("T", " ").replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S", "%Y%m%d %H%M"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.replace(tzinfo=KST)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    if _HTTP_URL_RE.match(value):
        return value
    return f"https://{value}"


def _point(longitude: Decimal, latitude: Decimal) -> WKTElement:
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def _point_or_none(longitude: Decimal | None, latitude: Decimal | None) -> WKTElement | None:
    if longitude is None or latitude is None:
        return None
    return _point(longitude, latitude)


def _hash_payload(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _compact_dict(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _address_rank(method: str | None) -> int:
    return {
        "unmapped": 0,
        "postgis_nearest_boundary_5km": 1,
        "postgis_point_in_polygon": 2,
        "juso_building_name_in_legal_dong": 3,
        "juso_road_address_exact": 4,
    }.get(method or "unmapped", 0)


def _resolve_collected_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(KST)
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)
