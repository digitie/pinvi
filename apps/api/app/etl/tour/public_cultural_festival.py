from __future__ import annotations

import hashlib
import html
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.address import (
    AddressServingJusoRelatedJibun,
    AddressServingJusoRoadAddress,
    RegionServingBoundary,
)
from app.models.tour import (
    TourRawPublicCulturalFestival,
    TourServingPublicCulturalFestival,
)

KST = ZoneInfo("Asia/Seoul")
DATA_GO_STANDARD_BASE_URL = "https://api.data.go.kr/openapi"
DATA_GO_PROVIDER = "data_go_kr"
DATASET_KEY = "public_cultural_festival"
STANDARD_API_PATH = "tn_pubr_public_cltur_fstvl_api"
MAX_PAGE_SIZE = 500
MAX_PAGE_GUARD = 1000
REQUEST_MAX_ATTEMPTS = 3
REQUEST_RETRY_SECONDS = 1.0
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class PublicCulturalFestivalError(RuntimeError):
    pass


class PublicCulturalFestivalClient(Protocol):
    def fetch_rows(self) -> list[dict[str, Any]]: ...


class DataGoPublicCulturalFestivalClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        base_url: str = DATA_GO_STANDARD_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._service_key = (
            service_key if service_key is not None else get_settings().data_go_service_key
        )
        self._base_url = base_url.rstrip("/")
        self._client = client

    def fetch_rows(self) -> list[dict[str, Any]]:
        api_key = (self._service_key or "").strip()
        if not api_key:
            raise PublicCulturalFestivalError("data.go.kr service key is not configured.")

        rows: list[dict[str, Any]] = []
        page_no = 1
        while page_no <= MAX_PAGE_GUARD:
            payload = self._get_json(
                STANDARD_API_PATH,
                {
                    "serviceKey": api_key,
                    "pageNo": str(page_no),
                    "numOfRows": str(MAX_PAGE_SIZE),
                    "type": "json",
                },
            )
            page_rows, total_count = _extract_standard_rows(payload)
            rows.extend(page_rows)
            if not page_rows or len(rows) >= total_count or len(page_rows) < MAX_PAGE_SIZE:
                return rows
            page_no += 1
        raise PublicCulturalFestivalError("data.go.kr festival pagination exceeded guard.")

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            payload = _get_json_with_retries(
                client,
                f"{self._base_url}/{path}",
                params=params,
            )
        finally:
            if owns_client:
                client.close()
        if not isinstance(payload, dict):
            raise PublicCulturalFestivalError("data.go.kr festival response is not an object.")
        return payload


def _get_json_with_retries(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str],
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_MAX_ATTEMPTS + 1):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise PublicCulturalFestivalError(
                    "data.go.kr festival response is not an object."
                )
            return cast(dict[str, Any], payload)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code != 429 and status_code < 500:
                raise
            last_error = exc
        except (httpx.TransportError, OSError) as exc:
            last_error = exc
        if attempt < REQUEST_MAX_ATTEMPTS:
            time.sleep(REQUEST_RETRY_SECONDS * attempt)
    if last_error is not None:
        raise last_error
    raise PublicCulturalFestivalError("data.go.kr festival request failed without an exception.")


@dataclass(frozen=True)
class PublicCulturalFestivalLoadResult:
    raw_row_count: int
    serving_row_count: int
    mapped_row_count: int
    road_address_mapped_count: int
    jibun_address_mapped_count: int
    coordinate_mapped_count: int
    skipped_row_count: int
    duplicate_row_count: int


@dataclass(frozen=True)
class _AddressMapping:
    legal_dong_code: str | None
    sigungu_code: str | None
    sido_code: str | None
    road_name_code: str | None
    road_address_management_no: str | None
    method: str


@dataclass(frozen=True)
class _PreparedFestivalRow:
    source_record_id: str
    response_hash: str
    normalized_row: dict[str, Any]
    festival_name: str
    longitude: Decimal | None
    latitude: Decimal | None


def load_public_cultural_festivals(
    session: Session,
    client: PublicCulturalFestivalClient,
    *,
    collected_at: datetime | None = None,
) -> PublicCulturalFestivalLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    rows = client.fetch_rows()
    prepared_rows, skipped_count, duplicate_count = _prepare_rows(rows)
    raw_count = 0
    serving_count = 0
    mapped_count = 0
    road_mapped_count = 0
    jibun_mapped_count = 0
    coordinate_mapped_count = 0

    session.execute(
        update(TourServingPublicCulturalFestival)
        .where(TourServingPublicCulturalFestival.provider == DATA_GO_PROVIDER)
        .values(is_active=False)
    )

    for prepared_row in prepared_rows:
        normalized_row = prepared_row.normalized_row
        source_record_id = prepared_row.source_record_id
        response_hash = prepared_row.response_hash
        if _add_raw_snapshot(
            session,
            source_record_id=source_record_id,
            payload=normalized_row,
            response_hash=response_hash,
            collected_at=resolved_collected_at,
        ):
            raw_count += 1

        longitude = prepared_row.longitude
        latitude = prepared_row.latitude
        road_address = _first_text(normalized_row, "rdnmadr", "소재지도로명주소")
        jibun_address = _first_text(normalized_row, "lnmadr", "소재지지번주소")
        mapping = _resolve_address_mapping(
            session,
            road_address=road_address,
            jibun_address=jibun_address,
            longitude=longitude,
            latitude=latitude,
        )
        if mapping.legal_dong_code:
            mapped_count += 1
            if mapping.method == "juso_road_address_exact":
                road_mapped_count += 1
            elif mapping.method == "juso_jibun_address_exact":
                jibun_mapped_count += 1
            elif mapping.method == "postgis_point_in_polygon":
                coordinate_mapped_count += 1

        _upsert_serving_row(
            session,
            source_record_id=source_record_id,
            row=normalized_row,
            festival_name=prepared_row.festival_name,
            longitude=longitude,
            latitude=latitude,
            mapping=mapping,
            collected_at=resolved_collected_at,
        )
        serving_count += 1

    session.flush()
    return PublicCulturalFestivalLoadResult(
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        mapped_row_count=mapped_count,
        road_address_mapped_count=road_mapped_count,
        jibun_address_mapped_count=jibun_mapped_count,
        coordinate_mapped_count=coordinate_mapped_count,
        skipped_row_count=skipped_count,
        duplicate_row_count=duplicate_count,
    )


def _prepare_rows(rows: list[dict[str, Any]]) -> tuple[list[_PreparedFestivalRow], int, int]:
    prepared_by_source_id: dict[str, _PreparedFestivalRow] = {}
    skipped_count = 0
    duplicate_count = 0
    for row in rows:
        normalized_row = _normalize_row(row)
        festival_name = _first_text(normalized_row, "fstvlNm", "축제명")
        if festival_name is None:
            skipped_count += 1
            continue

        source_record_id = _build_source_record_id(normalized_row)
        if source_record_id in prepared_by_source_id:
            duplicate_count += 1
        prepared_by_source_id[source_record_id] = _PreparedFestivalRow(
            source_record_id=source_record_id,
            response_hash=_hash_payload(normalized_row),
            normalized_row=normalized_row,
            festival_name=festival_name,
            longitude=_first_decimal(normalized_row, "longitude", "경도"),
            latitude=_first_decimal(normalized_row, "latitude", "위도"),
        )
    return list(prepared_by_source_id.values()), skipped_count, duplicate_count


def _add_raw_snapshot(
    session: Session,
    *,
    source_record_id: str,
    payload: dict[str, Any],
    response_hash: str,
    collected_at: datetime,
) -> bool:
    existing = session.scalar(
        select(TourRawPublicCulturalFestival.id).where(
            TourRawPublicCulturalFestival.provider == DATA_GO_PROVIDER,
            TourRawPublicCulturalFestival.source_record_id == source_record_id,
            TourRawPublicCulturalFestival.response_hash == response_hash,
        )
    )
    if existing is not None:
        return False
    session.add(
        TourRawPublicCulturalFestival(
            provider=DATA_GO_PROVIDER,
            source_record_id=source_record_id,
            request_params={"path": STANDARD_API_PATH, "numOfRows": MAX_PAGE_SIZE, "type": "json"},
            raw_payload=payload,
            response_hash=response_hash,
            collected_at=collected_at,
        )
    )
    return True


def _upsert_serving_row(
    session: Session,
    *,
    source_record_id: str,
    row: dict[str, Any],
    festival_name: str,
    longitude: Decimal | None,
    latitude: Decimal | None,
    mapping: _AddressMapping,
    collected_at: datetime,
) -> TourServingPublicCulturalFestival:
    existing = session.scalar(
        select(TourServingPublicCulturalFestival)
        .where(TourServingPublicCulturalFestival.provider == DATA_GO_PROVIDER)
        .where(TourServingPublicCulturalFestival.source_record_id == source_record_id)
    )
    event_start = _first_date(row, "fstvlStartDate", "축제시작일자")
    event_end = _first_date(row, "fstvlEndDate", "축제종료일자")
    values = {
        "place_join_key": f"{DATA_GO_PROVIDER}:{DATASET_KEY}:{source_record_id}",
        "festival_name": festival_name,
        "normalized_festival_name": _normalize_search_text(festival_name),
        "venue_name": _first_text(row, "opar", "개최장소"),
        "event_start_date": event_start,
        "event_end_date": event_end,
        "event_status": _event_status(event_start, event_end, collected_at.date()),
        "festival_content": _first_text(row, "fstvlCo", "축제내용"),
        "mnnst_name": _first_text(row, "mnnstNm", "주관기관명", "주관기관"),
        "auspc_instt_name": _first_text(row, "auspcInsttNm", "주최기관명", "주최기관"),
        "suprt_instt_name": _first_text(row, "suprtInsttNm", "후원기관명", "후원기관"),
        "phone_number": _first_text(row, "phoneNumber", "전화번호"),
        "homepage_url": _normalize_url(_first_text(row, "homepageUrl", "홈페이지주소")),
        "related_info": _first_text(row, "relateInfo", "관련정보"),
        "road_address": _first_text(row, "rdnmadr", "소재지도로명주소"),
        "jibun_address": _first_text(row, "lnmadr", "소재지지번주소"),
        "address_snapshot": _address_snapshot(row),
        "longitude": longitude,
        "latitude": latitude,
        "geom": _point_geometry(longitude, latitude),
        "legal_dong_code": mapping.legal_dong_code,
        "road_name_code": mapping.road_name_code,
        "road_address_management_no": mapping.road_address_management_no,
        "sigungu_code": mapping.sigungu_code,
        "sido_code": mapping.sido_code,
        "address_mapping_method": mapping.method,
        "provider_institution_code": _first_text(row, "instt_code", "제공기관코드"),
        "provider_institution_name": _first_text(row, "instt_nm", "제공기관기관명"),
        "reference_date": _first_date(row, "referenceDate", "데이터기준일자"),
        "raw_payload": row,
        "collected_at": collected_at,
        "is_active": True,
    }
    if existing is None:
        festival = TourServingPublicCulturalFestival(
            provider=DATA_GO_PROVIDER,
            source_record_id=source_record_id,
            **values,
        )
        session.add(festival)
        return festival

    for key, value in values.items():
        setattr(existing, key, value)
    return existing


def _resolve_address_mapping(
    session: Session,
    *,
    road_address: str | None,
    jibun_address: str | None,
    longitude: Decimal | None,
    latitude: Decimal | None,
) -> _AddressMapping:
    road_mapping = _find_road_address_mapping(session, road_address)
    if road_mapping is not None:
        return road_mapping

    jibun_mapping = _find_jibun_address_mapping(session, jibun_address)
    if jibun_mapping is not None:
        return jibun_mapping

    boundary = _find_legal_boundary(session, longitude=longitude, latitude=latitude)
    if boundary is not None and boundary.legal_dong_code:
        return _AddressMapping(
            legal_dong_code=boundary.legal_dong_code,
            sigungu_code=boundary.sigungu_code,
            sido_code=boundary.sido_code,
            road_name_code=None,
            road_address_management_no=None,
            method="postgis_point_in_polygon",
        )
    return _AddressMapping(
        legal_dong_code=None,
        sigungu_code=None,
        sido_code=None,
        road_name_code=None,
        road_address_management_no=None,
        method="unmapped",
    )


def _find_road_address_mapping(
    session: Session,
    road_address: str | None,
) -> _AddressMapping | None:
    if road_address is None:
        return None
    row = session.scalar(
        select(AddressServingJusoRoadAddress)
        .where(AddressServingJusoRoadAddress.is_active.is_(True))
        .where(AddressServingJusoRoadAddress.full_road_address == road_address)
        .limit(1)
    )
    if row is None:
        return None
    return _AddressMapping(
        legal_dong_code=row.legal_dong_code,
        sigungu_code=_derive_sigungu_code(row.legal_dong_code),
        sido_code=_derive_sido_code(row.legal_dong_code),
        road_name_code=row.road_name_code,
        road_address_management_no=row.road_address_management_no,
        method="juso_road_address_exact",
    )


def _find_jibun_address_mapping(
    session: Session,
    jibun_address: str | None,
) -> _AddressMapping | None:
    if jibun_address is None:
        return None
    row = session.scalar(
        select(AddressServingJusoRelatedJibun)
        .where(AddressServingJusoRelatedJibun.is_active.is_(True))
        .where(AddressServingJusoRelatedJibun.full_jibun_address == jibun_address)
        .limit(1)
    )
    if row is None:
        return None
    return _AddressMapping(
        legal_dong_code=row.legal_dong_code,
        sigungu_code=_derive_sigungu_code(row.legal_dong_code),
        sido_code=_derive_sido_code(row.legal_dong_code),
        road_name_code=row.road_name_code,
        road_address_management_no=row.road_address_management_no,
        method="juso_jibun_address_exact",
    )


def _find_legal_boundary(
    session: Session,
    *,
    longitude: Decimal | None,
    latitude: Decimal | None,
) -> RegionServingBoundary | None:
    point = _point_geometry(longitude, latitude)
    if point is None:
        return None
    return session.scalar(
        select(RegionServingBoundary)
        .where(RegionServingBoundary.boundary_level == "legal_dong")
        .where(func.ST_Covers(RegionServingBoundary.geom, point))
        .order_by(func.ST_Area(RegionServingBoundary.geom))
        .limit(1)
    )


def _extract_standard_rows(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int]:
    response = payload.get("response", payload)
    if not isinstance(response, Mapping):
        raise PublicCulturalFestivalError("festival response has no response object.")
    header = response.get("header", {})
    if isinstance(header, Mapping):
        result_code = str(header.get("resultCode", "")).strip()
        result_message = str(header.get("resultMsg", "")).strip()
        if result_code and result_code not in {"00", "0000", "NORMAL_CODE"}:
            if result_code in {"03", "NODATA_ERROR"}:
                return [], 0
            raise PublicCulturalFestivalError(
                f"festival API failed: {result_code} {result_message}"
            )
    body = response.get("body", response)
    if not isinstance(body, Mapping):
        return [], 0
    total_count = _parse_int(body.get("totalCount")) or 0
    items = body.get("items", [])
    if isinstance(items, Mapping):
        items = items.get("item", [])
    if items is None:
        return [], total_count
    if isinstance(items, Mapping):
        return [dict(items)], total_count or 1
    if isinstance(items, list):
        return [dict(item) for item in items if isinstance(item, Mapping)], total_count
    raise PublicCulturalFestivalError("festival response items shape is invalid.")


def _build_source_record_id(row: Mapping[str, Any]) -> str:
    seed = "|".join(
        _first_text(row, *keys) or ""
        for keys in (
            ("fstvlNm", "축제명"),
            ("fstvlStartDate", "축제시작일자"),
            ("fstvlEndDate", "축제종료일자"),
            ("opar", "개최장소"),
            ("rdnmadr", "소재지도로명주소"),
            ("lnmadr", "소재지지번주소"),
            ("instt_code", "제공기관코드"),
        )
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def _hash_payload(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).strip(): _normalize_value(value) for key, value in row.items()}


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = html.unescape(value)
        text = _HTML_TAG_RE.sub(" ", text)
        text = _WHITESPACE_RE.sub(" ", text).strip()
        return text if text and text.upper() not in {"N/A", "NA", "NULL", "NONE", "없음"} else None
    return value


def _first_text(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        text = _optional_text(row.get(key))
        if text is not None:
            return text
    return None


def _optional_text(value: Any) -> str | None:
    normalized = _normalize_value(value)
    if isinstance(normalized, str):
        return normalized
    if normalized is None:
        return None
    return str(normalized)


def _first_decimal(row: Mapping[str, Any], *keys: str) -> Decimal | None:
    for key in keys:
        value = _parse_decimal(row.get(key))
        if value is not None:
            return value
    return None


def _parse_decimal(value: Any) -> Decimal | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _first_date(row: Mapping[str, Any], *keys: str) -> date | None:
    for key in keys:
        text = _optional_text(row.get(key))
        if text is None:
            continue
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                value = text[:10] if fmt == "%Y-%m-%d" else text[:8]
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _parse_int(value: Any) -> int | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        return int(text.replace(",", ""))
    except ValueError:
        return None


def _point_geometry(longitude: Decimal | None, latitude: Decimal | None) -> WKTElement | None:
    if longitude is None or latitude is None:
        return None
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def _event_status(
    start_date: date | None,
    end_date: date | None,
    reference_date: date,
) -> str:
    if start_date is None and end_date is None:
        return "unknown"
    if start_date is not None and reference_date < start_date:
        return "upcoming"
    if end_date is not None and reference_date > end_date:
        return "ended"
    return "ongoing"


def _address_snapshot(row: Mapping[str, Any]) -> str | None:
    return _first_text(row, "rdnmadr", "소재지도로명주소") or _first_text(
        row,
        "lnmadr",
        "소재지지번주소",
    )


def _normalize_search_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.lower()).strip()


def _normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    if _HTTP_URL_RE.match(value):
        return value
    if "." in value and " " not in value:
        return f"https://{value}"
    return value


def _resolve_collected_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(KST)
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def _derive_sido_code(legal_dong_code: str) -> str:
    return f"{legal_dong_code[:2]}00000000"


def _derive_sigungu_code(legal_dong_code: str) -> str:
    return f"{legal_dong_code[:5]}00000"
