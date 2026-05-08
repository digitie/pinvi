from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, cast
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.redaction import redact_sensitive_text
from app.models.address import RegionServingBoundary
from app.models.ocean import (
    OceanActivityIndexForecast,
    OceanActivityIndexLocation,
    OceanActivityIndexSourceRecord,
)

KST = ZoneInfo("Asia/Seoul")
KHOA_PROVIDER = "khoa"
MAX_PAGE_SIZE = 300
MAX_PAGE_GUARD = 1000
KHOA_DATA_GO_BASE_URL = "http://apis.data.go.kr/1192136"
KHOA_MUDFLAT_INDEX_DATASET_KEY = "khoa_mudflat_index_forecast"
KHOA_SEA_SPLIT_INDEX_DATASET_KEY = "khoa_sea_split_index_forecast"
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_PERCENT_ENCODED_RE = re.compile(r"%[0-9A-Fa-f]{2}")


class KhoaOceanIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class KhoaOceanIndexDatasetDefinition:
    dataset_key: str
    display_name: str
    endpoint_path: str
    source_page_url: str
    name_keys: tuple[str, ...]
    place_code_keys: tuple[str, ...] = ("placeCode", "place_code", "장소코드")
    longitude_keys: tuple[str, ...] = ("lot", "lon", "lng", "longitude", "경도")
    latitude_keys: tuple[str, ...] = ("lat", "latitude", "위도")
    forecast_date_keys: tuple[str, ...] = ("predcYmd", "reqDate", "date", "날짜", "분석일자")
    forecast_slot_keys: tuple[str, ...] = ("predcNoonSeCd", "forecastSlot", "timeCd", "시간구분")
    activity_time_keys: tuple[str, ...] = (
        "exprnHrCn",
        "exprnPsbltyHrCn",
        "eventHrCn",
        "occrrncHrCn",
        "tdlvHrCn",
        "activityTime",
        "체험일정",
        "체험가능시간",
        "발생시간",
        "물때",
    )
    start_time_keys: tuple[str, ...] = (
        "exprnBgngTm",
        "exprnStartTime",
        "startTime",
        "bgngTm",
        "체험시작시각",
        "시작시각",
    )
    end_time_keys: tuple[str, ...] = (
        "exprnEndTm",
        "exprnEndTime",
        "endTime",
        "종료시각",
        "체험종료시각",
    )
    weather_keys: tuple[str, ...] = ("wthr", "weather", "날씨")
    air_temperature_keys: tuple[str, ...] = ("artmp", "avgArtmp", "airTemp", "기온")
    wind_speed_keys: tuple[str, ...] = ("wspd", "maxWspd", "windSpeed", "풍속")
    index_score_keys: tuple[str, ...] = ("lastScr", "scr", "score", "체험점수", "점수")
    total_index_keys: tuple[str, ...] = (
        "totalIndex",
        "index",
        "exprnIndex",
        "체험지수",
        "지수",
    )
    grade_keys: tuple[str, ...] = ("grdCn", "grade", "등급")

    @property
    def endpoint_url(self) -> str:
        return f"{KHOA_DATA_GO_BASE_URL}/{self.endpoint_path}"


@dataclass(frozen=True)
class KhoaOceanIndexLoadResult:
    dataset_key: str
    raw_row_count: int
    source_record_count: int
    location_upsert_count: int
    forecast_row_count: int
    mapped_legal_dong_count: int
    skipped_row_count: int


@dataclass(frozen=True)
class _AddressMapping:
    legal_dong_code: str | None
    sigungu_code: str | None
    sido_code: str | None
    address_snapshot: str | None
    method: str


@dataclass(frozen=True)
class _SourceRecordResult:
    record: OceanActivityIndexSourceRecord
    created: bool


class KhoaOceanIndexClientProtocol(Protocol):
    def fetch_rows(
        self,
        definition: KhoaOceanIndexDatasetDefinition,
        *,
        req_date: date | None = None,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]: ...


class KhoaOceanIndexClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        base_url: str = KHOA_DATA_GO_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._service_key = (
            service_key
            if service_key is not None
            else settings.khoa_api_key or settings.data_go_service_key
        )
        self._base_url = base_url.rstrip("/")
        self._client = client

    def fetch_rows(
        self,
        definition: KhoaOceanIndexDatasetDefinition,
        *,
        req_date: date | None = None,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        api_key = (self._service_key or "").strip()
        if not api_key:
            raise KhoaOceanIndexError("KHOA/data.go.kr service key is not configured.")

        rows: list[dict[str, Any]] = []
        page_no = 1
        last_request_params: dict[str, str] = {}
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            while page_no <= MAX_PAGE_GUARD:
                params = {
                    "serviceKey": api_key,
                    "type": "json",
                    "pageNo": str(page_no),
                    "numOfRows": str(MAX_PAGE_SIZE),
                }
                if req_date is not None:
                    params["reqDate"] = req_date.strftime("%Y%m%d")
                url = f"{self._base_url}/{definition.endpoint_path}"
                response = client.get(_data_go_url_with_service_key(url, params))
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    message = redact_sensitive_text(str(exc), extra_secret_values=(api_key,))
                    raise KhoaOceanIndexError(
                        f"{definition.dataset_key} request failed: {message}"
                    ) from None
                payload = response.json()
                if not isinstance(payload, dict):
                    raise KhoaOceanIndexError(
                        f"{definition.dataset_key} response is not an object."
                    )
                page_rows, total_count = _extract_response_rows(
                    cast(dict[str, Any], payload),
                    definition.dataset_key,
                )
                rows.extend(page_rows)
                last_request_params = {**params, "serviceKey": "***"}
                if not page_rows or len(rows) >= total_count or len(page_rows) < MAX_PAGE_SIZE:
                    return last_request_params, rows
                page_no += 1
        finally:
            if owns_client:
                client.close()
        raise KhoaOceanIndexError(f"{definition.dataset_key} pagination exceeded guard.")


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


KHOA_OCEAN_INDEX_DATASETS: dict[str, KhoaOceanIndexDatasetDefinition] = {
    KHOA_MUDFLAT_INDEX_DATASET_KEY: KhoaOceanIndexDatasetDefinition(
        dataset_key=KHOA_MUDFLAT_INDEX_DATASET_KEY,
        display_name="해양수산부 국립해양조사원_갯벌체험지수 조회",
        endpoint_path="fcstMudflatv2",
        source_page_url="https://www.data.go.kr/data/15142489/openapi.do",
        name_keys=(
            "placeName",
            "placeNm",
            "mudflatNm",
            "exprnPlaceNm",
            "갯벌체험장명",
            "장소명",
        ),
    ),
    KHOA_SEA_SPLIT_INDEX_DATASET_KEY: KhoaOceanIndexDatasetDefinition(
        dataset_key=KHOA_SEA_SPLIT_INDEX_DATASET_KEY,
        display_name="해양수산부 국립해양조사원_바다갈라짐 체험지수 조회",
        endpoint_path="fcstSeaSplitv2",
        source_page_url="https://www.data.go.kr/data/15142485/openapi.do",
        name_keys=(
            "placeName",
            "placeNm",
            "seaSplitNm",
            "occrrncPlaceNm",
            "바다갈라짐장소명",
            "장소명",
        ),
    ),
}


def load_khoa_ocean_index_dataset(
    session: Session,
    dataset_key: str,
    client: KhoaOceanIndexClientProtocol,
    *,
    collected_at: datetime | None = None,
    req_date: date | None = None,
) -> KhoaOceanIndexLoadResult:
    definition = _dataset_definition(dataset_key)
    resolved_collected_at = _resolve_collected_at(collected_at)
    request_params, rows = client.fetch_rows(definition, req_date=req_date)
    raw_count = 0
    source_count = 0
    location_count = 0
    forecast_count = 0
    mapped_count = 0
    skipped_count = 0

    for row in rows:
        normalized_row = _normalize_row(row)
        raw_count += 1
        name = _first_text(normalized_row, definition.name_keys)
        if name is None:
            skipped_count += 1
            continue
        longitude = _decimal(_first_value(normalized_row, definition.longitude_keys))
        latitude = _decimal(_first_value(normalized_row, definition.latitude_keys))
        provider_place_code = _first_text(normalized_row, definition.place_code_keys)
        provider_location_id = provider_place_code or _location_id_from_name_location(
            definition.dataset_key,
            name,
            longitude,
            latitude,
        )
        mapping = _resolve_coordinate_mapping(
            session,
            display_name=name,
            longitude=longitude,
            latitude=latitude,
        )
        if mapping.legal_dong_code:
            mapped_count += 1
        location, created = _upsert_location(
            session,
            definition=definition,
            provider_location_id=provider_location_id,
            provider_place_code=provider_place_code,
            display_name=name,
            longitude=longitude,
            latitude=latitude,
            mapping=mapping,
            collected_at=resolved_collected_at,
        )
        location_count += int(created)

        forecast_date = (
            _parse_date(_first_text(normalized_row, definition.forecast_date_keys))
            or resolved_collected_at.date()
        )
        forecast_slot = _first_text(normalized_row, definition.forecast_slot_keys) or "all_day"
        activity_time_text = _first_text(normalized_row, definition.activity_time_keys)
        activity_start_at = _combine_date_time(
            forecast_date,
            _parse_time(_first_text(normalized_row, definition.start_time_keys)),
        )
        activity_end_at = _combine_date_time(
            forecast_date,
            _parse_time(_first_text(normalized_row, definition.end_time_keys)),
        )
        activity_time_key = _activity_time_key(
            activity_time_text=activity_time_text,
            start_at=activity_start_at,
            end_at=activity_end_at,
        )
        source_record_key = (
            f"{provider_location_id}:{forecast_date.isoformat()}:{forecast_slot}:"
            f"{activity_time_key}"
        )
        source_record = _add_source_record(
            session,
            definition=definition,
            source_record_id=source_record_key,
            request_params=request_params,
            payload=normalized_row,
            response_hash=_hash_payload(normalized_row),
            collected_at=resolved_collected_at,
        )
        if source_record.created:
            source_count += 1
        _upsert_forecast(
            session,
            definition=definition,
            location=location,
            source_record=source_record.record,
            provider_place_code=provider_place_code,
            row=normalized_row,
            forecast_date=forecast_date,
            forecast_slot=forecast_slot,
            activity_time_key=activity_time_key,
            activity_time_text=activity_time_text,
            activity_start_at=activity_start_at,
            activity_end_at=activity_end_at,
            collected_at=resolved_collected_at,
        )
        forecast_count += 1

    session.flush()
    return KhoaOceanIndexLoadResult(
        dataset_key=dataset_key,
        raw_row_count=raw_count,
        source_record_count=source_count,
        location_upsert_count=location_count,
        forecast_row_count=forecast_count,
        mapped_legal_dong_count=mapped_count,
        skipped_row_count=skipped_count,
    )


def load_all_khoa_ocean_index_datasets(
    session: Session,
    client: KhoaOceanIndexClientProtocol,
    *,
    collected_at: datetime | None = None,
    req_date: date | None = None,
) -> list[KhoaOceanIndexLoadResult]:
    return [
        load_khoa_ocean_index_dataset(
            session,
            dataset_key,
            client,
            collected_at=collected_at,
            req_date=req_date,
        )
        for dataset_key in KHOA_OCEAN_INDEX_DATASETS
    ]


def _dataset_definition(dataset_key: str) -> KhoaOceanIndexDatasetDefinition:
    try:
        return KHOA_OCEAN_INDEX_DATASETS[dataset_key]
    except KeyError as exc:
        supported = ", ".join(sorted(KHOA_OCEAN_INDEX_DATASETS))
        raise KeyError(f"Unknown KHOA ocean index dataset {dataset_key!r}: {supported}") from exc


def _upsert_location(
    session: Session,
    *,
    definition: KhoaOceanIndexDatasetDefinition,
    provider_location_id: str,
    provider_place_code: str | None,
    display_name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
    mapping: _AddressMapping,
    collected_at: datetime,
) -> tuple[OceanActivityIndexLocation, bool]:
    existing = session.scalar(
        select(OceanActivityIndexLocation).where(
            OceanActivityIndexLocation.provider == KHOA_PROVIDER,
            OceanActivityIndexLocation.provider_dataset_key == definition.dataset_key,
            OceanActivityIndexLocation.provider_location_id == provider_location_id,
        )
    )
    values = {
        "provider_place_code": provider_place_code,
        "display_name": display_name,
        "normalized_name": _normalize_search_text(display_name),
        "longitude": longitude,
        "latitude": latitude,
        "geom": _point_or_none(longitude, latitude),
        "legal_dong_code": mapping.legal_dong_code,
        "sigungu_code": mapping.sigungu_code,
        "sido_code": mapping.sido_code,
        "address_snapshot": mapping.address_snapshot,
        "address_mapping_method": mapping.method,
        "source_specific_attributes": {"source_page_url": definition.source_page_url},
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = OceanActivityIndexLocation(
            provider=KHOA_PROVIDER,
            provider_dataset_key=definition.dataset_key,
            provider_location_id=provider_location_id,
            **values,
        )
        session.add(existing)
        session.flush()
        return existing, True
    for key, value in values.items():
        setattr(existing, key, value)
    return existing, False


def _add_source_record(
    session: Session,
    *,
    definition: KhoaOceanIndexDatasetDefinition,
    source_record_id: str,
    request_params: dict[str, Any],
    payload: dict[str, Any],
    response_hash: str,
    collected_at: datetime,
) -> _SourceRecordResult:
    existing = session.scalar(
        select(OceanActivityIndexSourceRecord).where(
            OceanActivityIndexSourceRecord.provider == KHOA_PROVIDER,
            OceanActivityIndexSourceRecord.dataset_key == definition.dataset_key,
            OceanActivityIndexSourceRecord.source_record_id == source_record_id,
            OceanActivityIndexSourceRecord.response_hash == response_hash,
        )
    )
    if existing is not None:
        return _SourceRecordResult(record=existing, created=False)
    record = OceanActivityIndexSourceRecord(
        provider=KHOA_PROVIDER,
        dataset_key=definition.dataset_key,
        endpoint=definition.endpoint_url,
        source_record_id=source_record_id,
        request_params=request_params,
        raw_payload=payload,
        response_hash=response_hash,
        collected_at=collected_at,
    )
    session.add(record)
    session.flush()
    return _SourceRecordResult(record=record, created=True)


def _upsert_forecast(
    session: Session,
    *,
    definition: KhoaOceanIndexDatasetDefinition,
    location: OceanActivityIndexLocation,
    source_record: OceanActivityIndexSourceRecord,
    provider_place_code: str | None,
    row: dict[str, Any],
    forecast_date: date,
    forecast_slot: str,
    activity_time_key: str,
    activity_time_text: str | None,
    activity_start_at: datetime | None,
    activity_end_at: datetime | None,
    collected_at: datetime,
) -> OceanActivityIndexForecast:
    existing = session.scalar(
        select(OceanActivityIndexForecast).where(
            OceanActivityIndexForecast.provider == KHOA_PROVIDER,
            OceanActivityIndexForecast.provider_dataset_key == definition.dataset_key,
            OceanActivityIndexForecast.location_id == location.id,
            OceanActivityIndexForecast.forecast_date == forecast_date,
            OceanActivityIndexForecast.forecast_slot == forecast_slot,
            OceanActivityIndexForecast.activity_time_key == activity_time_key,
        )
    )
    values = {
        "source_record_id": source_record.id,
        "provider_place_code": provider_place_code,
        "activity_time_text": activity_time_text,
        "activity_start_at": activity_start_at,
        "activity_end_at": activity_end_at,
        "weather": _first_text(row, definition.weather_keys),
        "air_temperature_c": _decimal(_first_value(row, definition.air_temperature_keys)),
        "wind_speed_ms": _decimal(_first_value(row, definition.wind_speed_keys)),
        "index_score": _decimal(_first_value(row, definition.index_score_keys)),
        "total_index": _first_text(row, definition.total_index_keys),
        "grade": _first_text(row, definition.grade_keys),
        "raw_payload": row,
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        existing = OceanActivityIndexForecast(
            location_id=location.id,
            provider=KHOA_PROVIDER,
            provider_dataset_key=definition.dataset_key,
            forecast_date=forecast_date,
            forecast_slot=forecast_slot,
            activity_time_key=activity_time_key,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _resolve_coordinate_mapping(
    session: Session,
    *,
    display_name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
) -> _AddressMapping:
    if longitude is None or latitude is None:
        return _AddressMapping(None, None, None, display_name, "unmapped")
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
        return _AddressMapping(None, None, None, display_name, "unmapped")
    return _AddressMapping(
        legal_dong_code=boundary.legal_dong_code,
        sigungu_code=boundary.sigungu_code,
        sido_code=boundary.sido_code,
        address_snapshot=boundary.full_region_name,
        method=method,
    )


def _extract_response_rows(
    payload: dict[str, Any],
    dataset_key: str,
) -> tuple[list[dict[str, Any]], int]:
    response = payload.get("response", payload)
    if not isinstance(response, Mapping):
        raise KhoaOceanIndexError(f"{dataset_key} response has no object body.")
    header = response.get("header")
    if isinstance(header, Mapping):
        result_code = _text(header.get("resultCode") or header.get("code"))
        result_message = _text(header.get("resultMsg") or header.get("message"))
        if result_code in {"03", "NO_DATA"}:
            return [], 0
        if result_code not in {None, "", "00", "0", "NORMAL_CODE"}:
            raise KhoaOceanIndexError(
                f"{dataset_key} response error {result_code}: {result_message or 'unknown'}"
            )
    rows = _extract_rows(response)
    total_count = _int(_deep_get(response, ("totalCount", "total_count"))) or len(rows)
    return rows, total_count


def _extract_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if not isinstance(value, Mapping):
        return []
    container_keys = ("body", "items", "item", "data", "rows", "result", "list")
    for key in container_keys:
        child = value.get(key)
        rows = _extract_rows(child)
        if rows:
            return rows
    if not any(
        key in value
        for key in (
            "header",
            "body",
            "items",
            "totalCount",
            "pageNo",
            "numOfRows",
            "resultCode",
            "resultMsg",
        )
    ):
        return [dict(value)]
    for child in value.values():
        rows = _extract_rows(child)
        if rows:
            return rows
    return []


def _normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).strip(): _normalize_value(value) for key, value in row.items()}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        text = html.unescape(_HTML_TAG_RE.sub(" ", value))
        normalized = _WHITESPACE_RE.sub(" ", text).strip()
        return normalized or None
    return value


def _first_value(row: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _first_text(row: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    return _text(_first_value(row, keys))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Any) -> Decimal | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _int(value: Any) -> int | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return int(text.replace(",", ""))
    except ValueError:
        return None


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = value.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _parse_time(value: str | None) -> time | None:
    if value is None:
        return None
    text = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%H%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _combine_date_time(value_date: date, value_time: time | None) -> datetime | None:
    if value_time is None:
        return None
    return datetime.combine(value_date, value_time, tzinfo=KST)


def _activity_time_key(
    *,
    activity_time_text: str | None,
    start_at: datetime | None,
    end_at: datetime | None,
) -> str:
    if start_at is not None or end_at is not None:
        start_text = start_at.isoformat() if start_at else "none"
        end_text = end_at.isoformat() if end_at else "none"
        return f"{start_text}-{end_text}"
    if activity_time_text:
        return hashlib.sha256(activity_time_text.encode("utf-8")).hexdigest()[:16]
    return "all_day"


def _location_id_from_name_location(
    dataset_key: str,
    display_name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
) -> str:
    payload = "|".join(
        [
            dataset_key,
            _normalize_search_text(display_name),
            str(longitude or ""),
            str(latitude or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _normalize_search_text(value: str) -> str:
    return _WHITESPACE_RE.sub("", value).casefold()


def _hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _point(longitude: Decimal, latitude: Decimal) -> WKTElement:
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def _point_or_none(longitude: Decimal | None, latitude: Decimal | None) -> WKTElement | None:
    if longitude is None or latitude is None:
        return None
    return _point(longitude, latitude)


def _deep_get(row: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    for value in row.values():
        if isinstance(value, Mapping):
            found = _deep_get(value, keys)
            if found is not None:
                return found
    return None


def _resolve_collected_at(collected_at: datetime | None) -> datetime:
    if collected_at is None:
        return datetime.now(KST)
    if collected_at.tzinfo is None:
        return collected_at.replace(tzinfo=KST)
    return collected_at.astimezone(KST)
