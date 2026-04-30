from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import time
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from zoneinfo import ZoneInfo

import httpx
from geoalchemy2.elements import WKTElement
from pyproj import Transformer
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.address import RegionServingBoundary
from app.models.place import (
    MapFeature,
    MapFeatureProviderRef,
    MapFeatureSourceLink,
    MapFeatureWebLink,
    PlaceCategory,
    PlaceDetail,
    SourceRecord,
)

KST = ZoneInfo("Asia/Seoul")
DATA_GO_STANDARD_BASE_URL = "https://api.data.go.kr/openapi"
DATA_GO_PROVIDER = "data_go_kr"
MAX_PAGE_SIZE = 1000
MAX_PAGE_GUARD = 1000
REQUEST_MAX_ATTEMPTS = 3
REQUEST_RETRY_SECONDS = 1.0
_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DATA_GO_CONTENT_URL_RE = re.compile(r'"contentUrl"\s*:\s*"([^"]+)"')
_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_EPSG5174_TO_4326 = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)


class PublicPlaceDataError(RuntimeError):
    pass


SourceMode = Literal[
    "data_go_standard_api",
    "data_go_file_page",
    "go_camping_api",
    "csv_url",
    "csv_path",
]


@dataclass(frozen=True)
class PublicPlaceDatasetDefinition:
    dataset_key: str
    display_name: str
    source_mode: SourceMode
    source_url: str | None
    standard_api_path: str | None
    source_page_url: str
    default_category_code: str
    place_kind: str
    name_keys: tuple[str, ...]
    road_address_keys: tuple[str, ...]
    jibun_address_keys: tuple[str, ...]
    longitude_keys: tuple[str, ...]
    latitude_keys: tuple[str, ...]
    epsg5174_x_keys: tuple[str, ...] = ()
    epsg5174_y_keys: tuple[str, ...] = ()
    phone_keys: tuple[str, ...] = ()
    homepage_keys: tuple[str, ...] = ()
    type_keys: tuple[str, ...] = ()
    opened_on_keys: tuple[str, ...] = ()
    closed_on_keys: tuple[str, ...] = ()
    source_version_keys: tuple[str, ...] = ("referenceDate", "데이터기준일자")
    operation_status_keys: tuple[str, ...] = ()
    extra_consumed_keys: tuple[str, ...] = ()
    source_id_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicPlaceLoadResult:
    dataset_key: str
    raw_row_count: int
    source_record_count: int
    place_upsert_count: int
    linked_place_count: int
    skipped_row_count: int
    mapped_legal_dong_count: int


@dataclass(frozen=True)
class _PlaceCandidate:
    source_record_id: str
    source_version: str | None
    name: str
    normalized_name: str
    road_address: str | None
    jibun_address: str | None
    address_snapshot: str
    longitude: Decimal
    latitude: Decimal
    phone: str | None
    homepage_url: str | None
    primary_category_code: str
    operation_status: str
    opened_on: date | None
    closed_on: date | None
    source_specific_attributes: dict[str, Any]
    legal_dong_code: str | None
    sigungu_code: str | None
    sido_code: str | None
    address_resolution_status: str


class PublicPlaceClient(Protocol):
    def fetch_rows(self, definition: PublicPlaceDatasetDefinition) -> list[dict[str, Any]]: ...


class DataGoStandardApiClient:
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

    def fetch_rows(self, definition: PublicPlaceDatasetDefinition) -> list[dict[str, Any]]:
        if definition.source_mode != "data_go_standard_api" or definition.standard_api_path is None:
            raise PublicPlaceDataError(f"{definition.dataset_key} is not a standard API dataset.")

        api_key = (self._service_key or "").strip()
        if not api_key:
            raise PublicPlaceDataError("data.go.kr service key is not configured.")

        rows: list[dict[str, Any]] = []
        page_no = 1
        while page_no <= MAX_PAGE_GUARD:
            payload = self._get_json(
                definition.standard_api_path,
                {
                    "serviceKey": api_key,
                    "pageNo": str(page_no),
                    "numOfRows": str(MAX_PAGE_SIZE),
                    "type": "json",
                },
            )
            page_rows, total_count = _extract_standard_rows(payload, definition.dataset_key)
            rows.extend(page_rows)
            if not page_rows or len(rows) >= total_count or len(page_rows) < MAX_PAGE_SIZE:
                return rows
            page_no += 1
        raise PublicPlaceDataError(
            f"data.go.kr pagination exceeded guard for {definition.dataset_key}."
        )

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            payload = _get_json_with_retries(
                client,
                f"{self._base_url}/{path.lstrip('/')}",
                params=params,
                error_label="data.go.kr standard API",
            )
        finally:
            if owns_client:
                client.close()
        if not isinstance(payload, dict):
            raise PublicPlaceDataError("data.go.kr standard API response is not an object.")
        return payload


class GoCampingApiClient:
    def __init__(
        self,
        *,
        service_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._service_key = (
            service_key if service_key is not None else get_settings().data_go_service_key
        )
        self._client = client

    def fetch_rows(self, definition: PublicPlaceDatasetDefinition) -> list[dict[str, Any]]:
        if definition.source_mode != "go_camping_api" or not definition.source_url:
            raise PublicPlaceDataError(f"{definition.dataset_key} is not a Go Camping dataset.")

        api_key = (self._service_key or "").strip()
        if not api_key:
            raise PublicPlaceDataError("Go Camping service key is not configured.")

        rows: list[dict[str, Any]] = []
        page_no = 1
        while page_no <= MAX_PAGE_GUARD:
            payload = self._get_json(
                definition.source_url,
                {
                    "serviceKey": api_key,
                    "pageNo": str(page_no),
                    "numOfRows": str(MAX_PAGE_SIZE),
                    "MobileOS": "ETC",
                    "MobileApp": "TripMate",
                    "_type": "json",
                },
            )
            page_rows, total_count = _extract_standard_rows(payload, definition.dataset_key)
            rows.extend(page_rows)
            if not page_rows or len(rows) >= total_count or len(page_rows) < MAX_PAGE_SIZE:
                return rows
            page_no += 1
        raise PublicPlaceDataError(
            f"Go Camping pagination exceeded guard for {definition.dataset_key}."
        )

    def _get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            payload = _get_json_with_retries(
                client,
                url,
                params=params,
                error_label="Go Camping API",
            )
        finally:
            if owns_client:
                client.close()
        if not isinstance(payload, dict):
            raise PublicPlaceDataError("Go Camping API response is not an object.")
        return payload


class DataGoFilePageCsvClient:
    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch_rows(self, definition: PublicPlaceDatasetDefinition) -> list[dict[str, Any]]:
        if definition.source_mode == "csv_path":
            if not definition.source_url:
                raise PublicPlaceDataError(f"{definition.dataset_key} csv_path is not configured.")
            return _read_csv_bytes(Path(definition.source_url).read_bytes())

        download_url = definition.source_url
        if definition.source_mode == "data_go_file_page":
            download_url = self._resolve_data_go_file_download_url(definition.source_page_url)
        if not download_url:
            raise PublicPlaceDataError(f"{definition.dataset_key} source URL is not configured.")

        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=60.0, follow_redirects=True)
        try:
            response = _get_response_with_retries(
                client,
                download_url,
                headers={
                    "User-Agent": "TripMate ETL/0.1",
                    "Accept": "text/csv, application/zip, */*",
                },
                error_label=f"{definition.dataset_key} file download",
            )
            return _read_csv_bytes(response.content)
        finally:
            if owns_client:
                client.close()

    def _resolve_data_go_file_download_url(self, page_url: str) -> str:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            response = _get_response_with_retries(
                client,
                page_url,
                headers={"User-Agent": "TripMate ETL/0.1"},
                error_label="data.go.kr file page",
            )
            match = _DATA_GO_CONTENT_URL_RE.search(response.text)
        finally:
            if owns_client:
                client.close()
        if match is None:
            raise PublicPlaceDataError(f"data.go.kr file download URL was not found: {page_url}")
        return html.unescape(match.group(1))


class CompositePublicPlaceClient:
    def __init__(
        self,
        *,
        standard_api_client: PublicPlaceClient | None = None,
        go_camping_client: PublicPlaceClient | None = None,
        csv_client: PublicPlaceClient | None = None,
    ) -> None:
        self._standard_api_client = standard_api_client or DataGoStandardApiClient()
        self._go_camping_client = go_camping_client or GoCampingApiClient()
        self._csv_client = csv_client or DataGoFilePageCsvClient()

    def fetch_rows(self, definition: PublicPlaceDatasetDefinition) -> list[dict[str, Any]]:
        if definition.source_mode == "data_go_standard_api":
            return self._standard_api_client.fetch_rows(definition)
        if definition.source_mode == "go_camping_api":
            return self._go_camping_client.fetch_rows(definition)
        return self._csv_client.fetch_rows(definition)


def _get_json_with_retries(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, str],
    error_label: str,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_MAX_ATTEMPTS + 1):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise PublicPlaceDataError(f"{error_label} response is not an object.")
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
    raise PublicPlaceDataError(f"{error_label} request failed without an exception.")


def _get_response_with_retries(
    client: httpx.Client,
    url: str,
    *,
    error_label: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_MAX_ATTEMPTS + 1):
        try:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response
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
    raise PublicPlaceDataError(f"{error_label} request failed without an exception.")


PUBLIC_PLACE_DATASETS: dict[str, PublicPlaceDatasetDefinition] = {
    "public_arboretum_basic": PublicPlaceDatasetDefinition(
        dataset_key="public_arboretum_basic",
        display_name="한국수목원정원관리원_수목원_기본관람정보",
        source_mode="data_go_file_page",
        source_url=None,
        standard_api_path=None,
        source_page_url="https://www.data.go.kr/data/15109934/fileData.do?recommendDataYn=Y",
        default_category_code="01030100",
        place_kind="tourist_spot",
        source_id_keys=("수목원아이디", "arboretumId"),
        name_keys=("수목원명", "arboretumNm", "name", "명칭"),
        road_address_keys=("전체주소", "주소", "소재지도로명주소", "roadAddress", "rdnmadr"),
        jibun_address_keys=("소재지지번주소", "jibunAddress", "lnmadr"),
        longitude_keys=("경도", "longitude", "lon", "lng"),
        latitude_keys=("위도", "latitude", "lat"),
        phone_keys=("전화번호", "대표전화", "연락처", "telephoneNumber"),
        homepage_keys=("홈페이지", "홈페이지주소", "홈페이지 URL", "homepageUrl"),
        type_keys=("수목원구분", "운영주체", "설립구분", "구분"),
        source_version_keys=("데이터기준일자", "referenceDate", "기준일자"),
        extra_consumed_keys=("입장료", "개관일", "휴관일", "대표수종", "교육체험프로그램"),
    ),
    "public_tourist_information_center": PublicPlaceDatasetDefinition(
        dataset_key="public_tourist_information_center",
        display_name="전국관광안내소표준데이터",
        source_mode="data_go_standard_api",
        source_url=None,
        standard_api_path="tn_pubr_public_trsmic_api",
        source_page_url="https://www.data.go.kr/data/15013112/standard.do",
        default_category_code="01060101",
        place_kind="tourist_spot",
        name_keys=("trsmicNm", "touristInformationCenterName", "관광안내소명"),
        road_address_keys=("rdnmadr", "소재지도로명주소"),
        jibun_address_keys=("lnmadr", "소재지지번주소"),
        longitude_keys=("longitude", "경도"),
        latitude_keys=("latitude", "위도"),
        phone_keys=("trsmicPhoneNumber", "phoneNumber", "안내소전화번호"),
        homepage_keys=("homepageUrl", "홈페이지주소"),
        type_keys=("trsmicLcNm", "안내소위치명"),
        source_version_keys=("referenceDate", "데이터기준일자"),
        extra_consumed_keys=(
            "trsmicLcNm",
            "ctprvnNm",
            "signguNm",
            "trsmicIntrcn",
            "additServiceInfo",
            "rstde",
            "summerOperOpenHhmm",
            "summerOperCloseHhmm",
            "winterOperOpenHhmm",
            "winterOperCloseHhmm",
            "avrgWorkNmprCo",
            "engGuidanceYn",
            "jpnGuidanceYn",
            "chnGuidanceYn",
            "guidanceLanguage",
            "institutionNm",
            "안내소위치명",
            "시도명",
            "시군구명",
            "안내소소개",
            "부가서비스정보",
            "휴무일",
            "운영시작시각(하절기)",
            "운영종료시각(하절기)",
            "운영시작시각(동절기)",
            "운영종료시각(동절기)",
            "평균근무인원수",
            "영어안내가능여부",
            "일본어안내가능여부",
            "중국어안내가능여부",
            "안내가능외국어",
            "운영기관명",
        ),
    ),
    "public_recreation_forest": PublicPlaceDatasetDefinition(
        dataset_key="public_recreation_forest",
        display_name="전국휴양림표준데이터",
        source_mode="data_go_standard_api",
        source_url=None,
        standard_api_path="tn_pubr_public_rcrfrst_api",
        source_page_url="https://www.data.go.kr/data/15013111/standard.do",
        default_category_code="03030000",
        place_kind="hotel",
        name_keys=("rcrfrstNm", "휴양림명"),
        road_address_keys=("rdnmadr", "소재지도로명주소"),
        jibun_address_keys=("lnmadr", "소재지지번주소"),
        longitude_keys=("longitude", "경도"),
        latitude_keys=("latitude", "위도"),
        phone_keys=("telephoneNumber", "휴양림전화번호"),
        homepage_keys=("homepageUrl", "홈페이지주소"),
        type_keys=("rcrfrstType", "휴양림구분"),
        source_version_keys=("referenceDate", "데이터기준일자"),
        extra_consumed_keys=("rcrfrstAr", "aceptncCo", "admfee", "stayngPosblYn", "mainFcltyNm"),
    ),
    "public_museum_art_gallery": PublicPlaceDatasetDefinition(
        dataset_key="public_museum_art_gallery",
        display_name="전국박물관미술관정보표준데이터",
        source_mode="data_go_standard_api",
        source_url=None,
        standard_api_path="tn_pubr_public_museum_artgr_info_api",
        source_page_url="https://www.data.go.kr/data/15017323/standard.do",
        default_category_code="01040000",
        place_kind="tourist_spot",
        name_keys=("fcltyNm", "시설명"),
        road_address_keys=("rdnmadr", "소재지도로명주소"),
        jibun_address_keys=("lnmadr", "소재지지번주소"),
        longitude_keys=("longitude", "경도"),
        latitude_keys=("latitude", "위도"),
        phone_keys=("operPhoneNumber", "phoneNumber", "운영기관전화번호", "관리기관전화번호"),
        homepage_keys=("homepageUrl", "운영홈페이지"),
        type_keys=("fcltyType", "박물관미술관구분"),
        source_version_keys=("referenceDate", "데이터기준일자"),
        extra_consumed_keys=(
            "fcltyInfo",
            "weekdayOperOpenHhmm",
            "weekdayOperColseHhmm",
            "holidayOperOpenHhmm",
            "holidayCloseOpenHhmm",
            "rstdeInfo",
            "adultChrge",
            "yngbgsChrge",
            "childChrge",
            "etcChrgeInfo",
            "fcltyIntrcn",
            "trnsportInfo",
        ),
    ),
    "public_campground": PublicPlaceDatasetDefinition(
        dataset_key="public_campground",
        display_name="한국관광공사_고캠핑 정보 조회서비스_GW",
        source_mode="go_camping_api",
        source_url="http://apis.data.go.kr/B551011/GoCamping/basedList",
        standard_api_path=None,
        source_page_url="https://www.data.go.kr/data/15101933/openapi.do",
        default_category_code="03060000",
        place_kind="hotel",
        source_id_keys=("contentId",),
        name_keys=("facltNm", "사업장명", "야영(캠핑)장명", "bplcNm", "campingNm"),
        road_address_keys=("addr1", "addr2", "소재지도로명주소", "도로명전체주소", "rdnmadr"),
        jibun_address_keys=("소재지전체주소", "소재지지번주소", "lnmadr"),
        longitude_keys=("mapX", "longitude", "경도"),
        latitude_keys=("mapY", "latitude", "위도"),
        epsg5174_x_keys=("좌표정보(x)", "좌표정보X", "x"),
        epsg5174_y_keys=("좌표정보(y)", "좌표정보Y", "y"),
        phone_keys=("tel", "소재지전화", "야영장전화번호", "전화번호", "telNo"),
        homepage_keys=("homepage", "홈페이지", "홈페이지주소", "homepageUrl"),
        type_keys=(
            "induty",
            "lctCl",
            "facltDivNm",
            "야영(캠핑)장구분",
            "업태구분명",
            "상세영업상태명",
        ),
        opened_on_keys=("인허가일자", "허가일자", "opnsfTeamCode"),
        closed_on_keys=("폐업일자",),
        source_version_keys=("modifiedtime", "createdtime", "데이터기준일자", "referenceDate"),
        operation_status_keys=("manageSttus", "영업상태명", "상세영업상태명", "영업상태구분코드"),
        extra_consumed_keys=(
            "lineIntro",
            "intro",
            "allar",
            "insrncAt",
            "trsagntNo",
            "bizrno",
            "facltDivNm",
            "mangeDivNm",
            "mgcDiv",
            "manageSttus",
            "hvofBgnde",
            "hvofEnddle",
            "featureNm",
            "induty",
            "lctCl",
            "doNm",
            "sigunguNm",
            "zipcode",
            "addr2",
            "direction",
            "resveUrl",
            "resveCl",
            "manageNmpr",
            "gnrlSiteCo",
            "autoSiteCo",
            "glampSiteCo",
            "caravSiteCo",
            "indvdlCaravSiteCo",
            "sitedStnc",
            "siteMg1Width",
            "siteMg2Width",
            "siteMg3Width",
            "siteMg1Vrticl",
            "siteMg2Vrticl",
            "siteMg3Vrticl",
            "siteMg1Co",
            "siteMg2Co",
            "siteMg3Co",
            "siteBottomCl1",
            "siteBottomCl2",
            "siteBottomCl3",
            "siteBottomCl4",
            "siteBottomCl5",
            "tooltip",
            "glampInnerFclty",
            "caravInnerFclty",
            "prmisnDe",
            "operPdCl",
            "operDeCl",
            "trlerAcmpnyAt",
            "caravAcmpnyAt",
            "toiletCo",
            "swrmCo",
            "wtrplCo",
            "brazierCl",
            "sbrsCl",
            "sbrsEtc",
            "posblFcltyCl",
            "posblFcltyEtc",
            "clturEventAt",
            "clturEvent",
            "exprnProgrmAt",
            "exprnProgrm",
            "extshrCo",
            "frprvtWrppCo",
            "frprvtSandCo",
            "fireSensorCo",
            "themaEnvrnCl",
            "eqpmnLendCl",
            "animalCmgCl",
            "tourEraCl",
            "firstImageUrl",
            "야영사이트수",
            "부지면적",
            "건축연면적",
            "1일최대수용인원수",
            "주차장면수",
            "편의시설",
            "안전시설",
            "기타부대시설",
            "이용시간",
            "이용요금",
            "관리기관전화번호",
            "관리기관명",
        ),
    ),
}


def load_public_place_dataset(
    session: Session,
    dataset_key: str,
    client: PublicPlaceClient,
    *,
    collected_at: datetime | None = None,
) -> PublicPlaceLoadResult:
    definition = _dataset_definition(dataset_key)
    resolved_collected_at = _resolve_collected_at(collected_at)
    ensure_public_place_categories(session)
    rows = client.fetch_rows(definition)
    raw_count = 0
    source_record_count = 0
    place_upsert_count = 0
    linked_place_count = 0
    skipped_count = 0
    mapped_count = 0

    for row in rows:
        normalized_row = _normalize_row(row)
        raw_count += 1
        candidate = _build_candidate(session, definition, normalized_row)
        if candidate is None:
            skipped_count += 1
            continue
        if candidate.legal_dong_code:
            mapped_count += 1

        raw_hash = _hash_payload(normalized_row)
        source_record, source_record_created = _upsert_source_record(
            session,
            definition=definition,
            candidate=candidate,
            row=normalized_row,
            raw_hash=raw_hash,
            collected_at=resolved_collected_at,
        )
        if source_record_created:
            source_record_count += 1
        feature = _upsert_place(
            session,
            definition=definition,
            candidate=candidate,
            collected_at=resolved_collected_at,
        )
        _upsert_provider_ref(
            session,
            definition=definition,
            candidate=candidate,
            feature=feature,
            fetched_at=resolved_collected_at,
        )
        _upsert_source_link(session, feature=feature, source_record=source_record)
        _upsert_web_link(session, feature=feature, candidate=candidate)
        place_upsert_count += 1
        linked_place_count += 1

    session.flush()
    return PublicPlaceLoadResult(
        dataset_key=dataset_key,
        raw_row_count=raw_count,
        source_record_count=source_record_count,
        place_upsert_count=place_upsert_count,
        linked_place_count=linked_place_count,
        skipped_row_count=skipped_count,
        mapped_legal_dong_count=mapped_count,
    )


def load_all_public_place_datasets(
    session: Session,
    client: PublicPlaceClient,
    *,
    dataset_keys: Iterable[str] | None = None,
    collected_at: datetime | None = None,
) -> list[PublicPlaceLoadResult]:
    keys = tuple(dataset_keys or PUBLIC_PLACE_DATASETS)
    return [
        load_public_place_dataset(
            session,
            dataset_key,
            client,
            collected_at=collected_at,
        )
        for dataset_key in keys
    ]


def ensure_public_place_categories(session: Session) -> None:
    session.execute(
        pg_insert(PlaceCategory)
        .values(list(_place_category_seeds()))
        .on_conflict_do_nothing(index_elements=[PlaceCategory.category_code])
    )
    session.flush()


def _place_category_seeds() -> tuple[dict[str, Any], ...]:
    return (
        _category_seed("00000000", "미분류", None, None, None, 0, None, 0),
        _category_seed("01000000", "관광", None, None, None, 1, None, 10),
        _category_seed("01030000", "관광", "수목원·식물원", None, None, 2, "01000000", 30),
        _category_seed("01030100", "관광", "수목원·식물원", "수목원", None, 3, "01030000", 31),
        _category_seed(
            "01030101",
            "관광",
            "수목원·식물원",
            "수목원",
            "국립수목원",
            4,
            "01030100",
            311,
        ),
        _category_seed(
            "01030102",
            "관광",
            "수목원·식물원",
            "수목원",
            "공립수목원",
            4,
            "01030100",
            312,
        ),
        _category_seed(
            "01030103",
            "관광",
            "수목원·식물원",
            "수목원",
            "사립수목원",
            4,
            "01030100",
            313,
        ),
        _category_seed("01050000", "관광", "자연명소", None, None, 2, "01000000", 50),
        _category_seed("01050100", "관광", "자연명소", "해수욕장", None, 3, "01050000", 51),
        _category_seed("01060000", "관광", "관광안내", None, None, 2, "01000000", 60),
        _category_seed("01060100", "관광", "관광안내", "관광안내소", None, 3, "01060000", 61),
        _category_seed(
            "01060101",
            "관광",
            "관광안내",
            "관광안내소",
            "공공 관광안내소",
            4,
            "01060100",
            611,
        ),
        _category_seed("01040000", "관광", "문화시설", None, None, 2, "01000000", 40),
        _category_seed("01040100", "관광", "문화시설", "박물관", None, 3, "01040000", 41),
        _category_seed(
            "01040101",
            "관광",
            "문화시설",
            "박물관",
            "국공립 박물관",
            4,
            "01040100",
            411,
        ),
        _category_seed(
            "01040102",
            "관광",
            "문화시설",
            "박물관",
            "사립 박물관",
            4,
            "01040100",
            412,
        ),
        _category_seed(
            "01040103",
            "관광",
            "문화시설",
            "박물관",
            "테마 박물관",
            4,
            "01040100",
            413,
        ),
        _category_seed(
            "01040200",
            "관광",
            "문화시설",
            "미술관·갤러리",
            None,
            3,
            "01040000",
            42,
        ),
        _category_seed(
            "01040201",
            "관광",
            "문화시설",
            "미술관·갤러리",
            "미술관",
            4,
            "01040200",
            421,
        ),
        _category_seed(
            "01040202",
            "관광",
            "문화시설",
            "미술관·갤러리",
            "갤러리",
            4,
            "01040200",
            422,
        ),
        _category_seed("03000000", "숙박", None, None, None, 1, None, 300),
        _category_seed("03030000", "숙박", "휴양림", None, None, 2, "03000000", 330),
        _category_seed("03030100", "숙박", "휴양림", "국립휴양림", None, 3, "03030000", 331),
        _category_seed(
            "03030101",
            "숙박",
            "휴양림",
            "국립휴양림",
            "산림청 운영",
            4,
            "03030100",
            3311,
        ),
        _category_seed("03030200", "숙박", "휴양림", "공립휴양림", None, 3, "03030000", 332),
        _category_seed(
            "03030201",
            "숙박",
            "휴양림",
            "공립휴양림",
            "지자체 운영",
            4,
            "03030200",
            3321,
        ),
        _category_seed("03030300", "숙박", "휴양림", "사립휴양림", None, 3, "03030000", 333),
        _category_seed(
            "03030301",
            "숙박",
            "휴양림",
            "사립휴양림",
            "민간 운영",
            4,
            "03030300",
            3331,
        ),
        _category_seed("03060000", "숙박", "캠핑장", None, None, 2, "03000000", 360),
        _category_seed("03060100", "숙박", "캠핑장", "오토캠핑장", None, 3, "03060000", 361),
        _category_seed(
            "03060101",
            "숙박",
            "캠핑장",
            "오토캠핑장",
            "일반 사이트",
            4,
            "03060100",
            3611,
        ),
        _category_seed(
            "03060102",
            "숙박",
            "캠핑장",
            "오토캠핑장",
            "카라반·캠핑카 사이트",
            4,
            "03060100",
            3612,
        ),
        _category_seed(
            "03060200",
            "숙박",
            "캠핑장",
            "글램핑·카라반",
            None,
            3,
            "03060000",
            362,
        ),
        _category_seed(
            "03060201",
            "숙박",
            "캠핑장",
            "글램핑·카라반",
            "글램핑",
            4,
            "03060200",
            3621,
        ),
        _category_seed(
            "03060202",
            "숙박",
            "캠핑장",
            "글램핑·카라반",
            "카라반 대여",
            4,
            "03060200",
            3622,
        ),
    )


def _category_seed(
    category_code: str,
    tier1_name: str,
    tier2_name: str | None,
    tier3_name: str | None,
    tier4_name: str | None,
    depth: int,
    parent_category_code: str | None,
    sort_order: int,
) -> dict[str, Any]:
    return {
        "category_code": category_code,
        "tier1_code": category_code[0:2],
        "tier2_code": category_code[2:4],
        "tier3_code": category_code[4:6],
        "tier4_code": category_code[6:8],
        "tier1_name": tier1_name,
        "tier2_name": tier2_name,
        "tier3_name": tier3_name,
        "tier4_name": tier4_name,
        "depth": depth,
        "parent_category_code": parent_category_code,
        "sort_order": sort_order,
        "is_active": True,
    }


def _dataset_definition(dataset_key: str) -> PublicPlaceDatasetDefinition:
    try:
        definition = PUBLIC_PLACE_DATASETS[dataset_key]
    except KeyError as exc:
        supported = ", ".join(sorted(PUBLIC_PLACE_DATASETS))
        raise KeyError(
            f"Unknown public place dataset {dataset_key!r}. Supported: {supported}"
        ) from exc

    if dataset_key == "public_arboretum_basic":
        settings = get_settings()
        csv_path = settings.arboretum_basic_csv_path
        csv_url = settings.arboretum_basic_csv_url
        if csv_path:
            return PublicPlaceDatasetDefinition(
                **{**definition.__dict__, "source_mode": "csv_path", "source_url": csv_path}
            )
        if csv_url:
            return PublicPlaceDatasetDefinition(
                **{**definition.__dict__, "source_mode": "csv_url", "source_url": csv_url}
            )
    return definition


def _build_candidate(
    session: Session,
    definition: PublicPlaceDatasetDefinition,
    row: dict[str, Any],
) -> _PlaceCandidate | None:
    name = _first_text(row, definition.name_keys)
    if name is None:
        return None

    road_address = _first_text(row, definition.road_address_keys)
    jibun_address = _first_text(row, definition.jibun_address_keys)
    address_snapshot = road_address or jibun_address
    if address_snapshot is None:
        return None

    coordinates = _resolve_coordinates(definition, row)
    if coordinates is None:
        return None
    longitude, latitude = coordinates

    legal_region = _find_legal_region(session, longitude=longitude, latitude=latitude)
    legal_dong_code = legal_region.legal_dong_code if legal_region else None
    sigungu_code = legal_region.sigungu_code if legal_region else None
    sido_code = legal_region.sido_code if legal_region else None
    address_resolution_status = "resolved" if legal_dong_code else "coordinate_only"

    category_code = _resolve_category_code(definition, row, name)
    operation_status = _resolve_operation_status(definition, row)
    source_record_id = _build_source_record_id(
        definition=definition,
        row=row,
        name=name,
        address=address_snapshot,
        longitude=longitude,
        latitude=latitude,
    )
    consumed_keys = _consumed_keys(definition)

    return _PlaceCandidate(
        source_record_id=source_record_id,
        source_version=_first_text(row, definition.source_version_keys),
        name=name,
        normalized_name=_normalize_search_text(name),
        road_address=road_address,
        jibun_address=jibun_address,
        address_snapshot=address_snapshot,
        longitude=longitude,
        latitude=latitude,
        phone=_first_text(row, definition.phone_keys),
        homepage_url=_normalize_url(_first_text(row, definition.homepage_keys)),
        primary_category_code=category_code,
        operation_status=operation_status,
        opened_on=_first_date(row, definition.opened_on_keys),
        closed_on=_first_date(row, definition.closed_on_keys),
        source_specific_attributes=_build_source_specific_attributes(row, consumed_keys),
        legal_dong_code=legal_dong_code,
        sigungu_code=sigungu_code,
        sido_code=sido_code,
        address_resolution_status=address_resolution_status,
    )


def _upsert_source_record(
    session: Session,
    *,
    definition: PublicPlaceDatasetDefinition,
    candidate: _PlaceCandidate,
    row: dict[str, Any],
    raw_hash: str,
    collected_at: datetime,
) -> tuple[SourceRecord, bool]:
    existing = session.scalar(
        select(SourceRecord).where(
            SourceRecord.provider == DATA_GO_PROVIDER,
            SourceRecord.dataset_key == definition.dataset_key,
            SourceRecord.source_entity_type == "place",
            SourceRecord.source_entity_id == candidate.source_record_id,
            SourceRecord.raw_payload_hash == raw_hash,
        )
    )
    if existing is not None:
        return existing, False

    source_record = SourceRecord(
        provider=DATA_GO_PROVIDER,
        dataset_key=definition.dataset_key,
        source_entity_type="place",
        source_entity_id=candidate.source_record_id,
        source_version=candidate.source_version,
        raw_name=candidate.name,
        raw_address=candidate.address_snapshot,
        raw_longitude=candidate.longitude,
        raw_latitude=candidate.latitude,
        raw_geom=_point(candidate.longitude, candidate.latitude),
        raw_data=row,
        raw_payload_hash=raw_hash,
        fetched_at=collected_at,
        imported_at=collected_at,
        expires_at=None,
    )
    session.add(source_record)
    session.flush()
    return source_record, True


def _upsert_place(
    session: Session,
    *,
    definition: PublicPlaceDatasetDefinition,
    candidate: _PlaceCandidate,
    collected_at: datetime,
) -> MapFeature:
    feature = _find_feature_by_provider_ref(session, definition, candidate.source_record_id)
    is_visible = (
        candidate.operation_status != "closed"
        and candidate.legal_dong_code is not None
        and candidate.primary_category_code != "00000000"
    )
    status = "inactive" if candidate.operation_status == "closed" else "active"
    point = _point(candidate.longitude, candidate.latitude)
    values: dict[str, Any] = {
        "feature_type": "place",
        "name": candidate.name,
        "display_name": candidate.name,
        "normalized_name": candidate.normalized_name,
        "subtitle": None,
        "summary": None,
        "description": None,
        "category_code": candidate.primary_category_code,
        "category_name": None,
        "geom": point,
        "geometry_kind": "point",
        "centroid": point,
        "longitude": candidate.longitude,
        "latitude": candidate.latitude,
        "address": candidate.address_snapshot,
        "road_address": candidate.road_address,
        "jibun_address": candidate.jibun_address,
        "legal_dong_code": candidate.legal_dong_code,
        "sigungu_code": candidate.sigungu_code,
        "sido_code": candidate.sido_code,
        "admin_dong_code": None,
        "road_name_code": None,
        "road_address_management_no": None,
        "phone": candidate.phone,
        "website_url": candidate.homepage_url,
        "popularity_score": 0,
        "priority_score": 0,
        "status": status,
        "is_visible": is_visible,
        "extra": {},
        "last_seen_at": collected_at,
        "last_verified_at": collected_at,
    }
    if feature is None:
        feature = MapFeature(
            public_id=_public_id(definition.dataset_key, candidate.source_record_id),
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
        definition=definition,
        candidate=candidate,
    )
    session.flush()
    return feature


def _upsert_place_detail(
    session: Session,
    *,
    feature: MapFeature,
    definition: PublicPlaceDatasetDefinition,
    candidate: _PlaceCandidate,
) -> None:
    detail = session.get(PlaceDetail, feature.id)
    values = {
        "place_kind": definition.place_kind,
        "operation_status": candidate.operation_status,
        "address_resolution_status": candidate.address_resolution_status,
        "verification_status": "public_data_verified",
        "quality_score": 80 if candidate.legal_dong_code else 60,
        "opened_on": candidate.opened_on,
        "closed_on": candidate.closed_on,
        "extra": candidate.source_specific_attributes,
    }
    if detail is None:
        session.add(PlaceDetail(feature_id=feature.id, **values))
        return
    for key, value in values.items():
        setattr(detail, key, value)


def _upsert_provider_ref(
    session: Session,
    *,
    definition: PublicPlaceDatasetDefinition,
    candidate: _PlaceCandidate,
    feature: MapFeature,
    fetched_at: datetime,
) -> None:
    ref = session.scalar(
        select(MapFeatureProviderRef).where(
            MapFeatureProviderRef.provider == DATA_GO_PROVIDER,
            MapFeatureProviderRef.provider_dataset_key == definition.dataset_key,
            MapFeatureProviderRef.provider_feature_id == candidate.source_record_id,
        )
    )
    if ref is None:
        ref = MapFeatureProviderRef(
            feature_id=feature.id,
            provider=DATA_GO_PROVIDER,
            provider_dataset_key=definition.dataset_key,
            provider_feature_id=candidate.source_record_id,
        )
        session.add(ref)
    ref.url = definition.source_page_url
    ref.stable_name = candidate.name
    ref.stable_address = candidate.address_snapshot
    ref.stable_phone = candidate.phone
    ref.last_fetched_at = fetched_at
    ref.expires_at = None


def _upsert_source_link(
    session: Session,
    *,
    feature: MapFeature,
    source_record: SourceRecord,
) -> None:
    link = session.scalar(
        select(MapFeatureSourceLink).where(
            MapFeatureSourceLink.feature_id == feature.id,
            MapFeatureSourceLink.source_record_id == source_record.id,
        )
    )
    if link is None:
        session.add(
            MapFeatureSourceLink(
                feature_id=feature.id,
                source_record_id=source_record.id,
                match_method="provider_dataset_source_id",
                confidence=100,
                is_primary_source=True,
            )
        )


def _upsert_web_link(
    session: Session,
    *,
    feature: MapFeature,
    candidate: _PlaceCandidate,
) -> None:
    if not candidate.homepage_url:
        return
    link = session.scalar(
        select(MapFeatureWebLink).where(
            MapFeatureWebLink.feature_id == feature.id,
            MapFeatureWebLink.url == candidate.homepage_url,
        )
    )
    if link is None:
        session.add(
            MapFeatureWebLink(
                feature_id=feature.id,
                link_type="official",
                provider=None,
                url=candidate.homepage_url,
                title="공식 홈페이지",
                is_primary=True,
                sort_order=0,
            )
        )
        return
    link.link_type = "official"
    link.title = "공식 홈페이지"
    link.is_primary = True
    link.sort_order = 0


def _find_feature_by_provider_ref(
    session: Session,
    definition: PublicPlaceDatasetDefinition,
    source_record_id: str,
) -> MapFeature | None:
    ref = session.scalar(
        select(MapFeatureProviderRef).where(
            MapFeatureProviderRef.provider == DATA_GO_PROVIDER,
            MapFeatureProviderRef.provider_dataset_key == definition.dataset_key,
            MapFeatureProviderRef.provider_feature_id == source_record_id,
        )
    )
    if ref is None:
        return None
    return session.get(MapFeature, ref.feature_id)


def _find_legal_region(
    session: Session,
    *,
    longitude: Decimal,
    latitude: Decimal,
) -> RegionServingBoundary | None:
    point = _point(longitude, latitude)
    return session.scalar(
        select(RegionServingBoundary)
        .where(
            RegionServingBoundary.boundary_level == "legal_dong",
            func.ST_Covers(RegionServingBoundary.geom, point),
        )
        .order_by(func.ST_Area(RegionServingBoundary.geom))
        .limit(1)
    )


def _extract_standard_rows(
    payload: Mapping[str, Any],
    dataset_key: str,
) -> tuple[list[dict[str, Any]], int]:
    response = payload.get("response", payload)
    if not isinstance(response, Mapping):
        raise PublicPlaceDataError(f"{dataset_key} response has no response object.")
    header = response.get("header", {})
    if isinstance(header, Mapping):
        result_code = str(header.get("resultCode", "")).strip()
        result_message = str(header.get("resultMsg", "")).strip()
        if result_code and result_code not in {"00", "0000", "NORMAL_CODE"}:
            if result_code in {"03", "NODATA_ERROR"}:
                return [], 0
            raise PublicPlaceDataError(f"{dataset_key} API failed: {result_code} {result_message}")
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
    raise PublicPlaceDataError(f"{dataset_key} response items shape is invalid.")


def _read_csv_bytes(content: bytes) -> list[dict[str, Any]]:
    resolved_content = (
        _extract_csv_from_zip(content) if zipfile.is_zipfile(io.BytesIO(content)) else content
    )
    text = _decode_csv(resolved_content)
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _extract_csv_from_zip(content: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        candidates = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not candidates:
            raise PublicPlaceDataError("CSV file was not found in ZIP archive.")
        with archive.open(candidates[0]) as handle:
            return handle.read()


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


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


def _build_source_specific_attributes(
    row: Mapping[str, Any],
    consumed_keys: set[str],
) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for key, value in row.items():
        if key in consumed_keys or value in {None, ""}:
            continue
        attributes[key] = value
    return attributes


def _consumed_keys(definition: PublicPlaceDatasetDefinition) -> set[str]:
    return {
        *definition.name_keys,
        *definition.road_address_keys,
        *definition.jibun_address_keys,
        *definition.longitude_keys,
        *definition.latitude_keys,
        *definition.epsg5174_x_keys,
        *definition.epsg5174_y_keys,
        *definition.phone_keys,
        *definition.homepage_keys,
        *definition.type_keys,
        *definition.source_id_keys,
        *definition.opened_on_keys,
        *definition.closed_on_keys,
        *definition.source_version_keys,
        *definition.operation_status_keys,
    }


def _resolve_coordinates(
    definition: PublicPlaceDatasetDefinition,
    row: Mapping[str, Any],
) -> tuple[Decimal, Decimal] | None:
    longitude = _first_decimal(row, definition.longitude_keys)
    latitude = _first_decimal(row, definition.latitude_keys)
    if longitude is not None and latitude is not None:
        return longitude, latitude

    x = _first_decimal(row, definition.epsg5174_x_keys)
    y = _first_decimal(row, definition.epsg5174_y_keys)
    if x is None or y is None:
        return None
    lon_float, lat_float = _EPSG5174_TO_4326.transform(float(x), float(y))
    return _decimal_from_float(lon_float), _decimal_from_float(lat_float)


def _resolve_category_code(
    definition: PublicPlaceDatasetDefinition,
    row: Mapping[str, Any],
    name: str,
) -> str:
    type_text = " ".join(
        text for key in definition.type_keys if (text := _optional_text(row.get(key))) is not None
    )
    category_text = f"{name} {type_text}"

    if definition.dataset_key == "public_arboretum_basic":
        if _contains_any(category_text, ("국립",)):
            return "01030101"
        if _contains_any(category_text, ("공립", "시립", "도립", "군립", "구립", "공영")):
            return "01030102"
        if _contains_any(category_text, ("사립", "사유", "민간")):
            return "01030103"
        return "01030100"

    if definition.dataset_key == "public_recreation_forest":
        if _contains_any(category_text, ("국유림", "국립", "산림청")):
            return "03030101"
        if _contains_any(category_text, ("공유림", "공립", "시유림", "도유림", "군유림", "지자체")):
            return "03030201"
        if _contains_any(category_text, ("사유림", "사립", "민간")):
            return "03030301"
        return "03030000"

    if definition.dataset_key == "public_museum_art_gallery":
        if _contains_any(category_text, ("갤러리", "화랑")):
            return "01040202"
        if _contains_any(category_text, ("미술관",)):
            return "01040201"
        if _contains_any(category_text, ("국립", "공립", "시립", "도립", "군립", "구립")):
            return "01040101"
        if _contains_any(category_text, ("사립",)):
            return "01040102"
        if _contains_any(category_text, ("테마", "민속", "자연사", "과학")):
            return "01040103"
        return "01040100"

    if definition.dataset_key == "public_campground":
        if _contains_any(category_text, ("글램핑",)):
            return "03060201"
        if _contains_any(category_text, ("카라반", "캠핑카")):
            return "03060202"
        if _contains_any(category_text, ("자동차", "오토")):
            return "03060102"
        if _contains_any(category_text, ("야영", "캠핑")):
            return "03060101"
        return "03060000"

    return definition.default_category_code


def _resolve_operation_status(
    definition: PublicPlaceDatasetDefinition,
    row: Mapping[str, Any],
) -> str:
    status_text = " ".join(
        text
        for key in definition.operation_status_keys
        if (text := _optional_text(row.get(key))) is not None
    )
    if _contains_any(status_text, ("폐업", "취소", "말소", "직권폐쇄")):
        return "closed"
    if _contains_any(status_text, ("휴업", "중지")):
        return "temporarily_closed"
    if _contains_any(status_text, ("영업", "정상", "운영")):
        return "operating"
    return "unknown"


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _build_source_record_id(
    *,
    definition: PublicPlaceDatasetDefinition,
    row: Mapping[str, Any],
    name: str,
    address: str,
    longitude: Decimal,
    latitude: Decimal,
) -> str:
    stable_source_id = _first_text(row, definition.source_id_keys)
    if stable_source_id is not None:
        return stable_source_id

    provider_code = _first_text(row, ("instt_code", "제공기관코드", "관리기관명", "institutionNm"))
    seed = "|".join(
        [
            definition.dataset_key,
            name,
            address,
            str(longitude),
            str(latitude),
            provider_code or "",
        ]
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def _hash_payload(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _public_id(dataset_key: str, source_record_id: str) -> str:
    digest = hashlib.sha1(f"{dataset_key}:{source_record_id}".encode()).hexdigest()
    return f"pl_{digest[:20]}"


def _point(longitude: Decimal, latitude: Decimal) -> WKTElement:
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def _first_text(row: Mapping[str, Any], keys: Iterable[str]) -> str | None:
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


def _first_decimal(row: Mapping[str, Any], keys: Iterable[str]) -> Decimal | None:
    for key in keys:
        parsed = _parse_decimal(row.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_decimal(value: Any) -> Decimal | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _decimal_from_float(value: float) -> Decimal:
    return Decimal(f"{value:.8f}")


def _first_date(row: Mapping[str, Any], keys: Iterable[str]) -> date | None:
    for key in keys:
        text = _optional_text(row.get(key))
        if text is None:
            continue
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:8], fmt).date()
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
