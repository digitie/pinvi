from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from geoalchemy2.elements import WKTElement
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from sqlalchemy import Table, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.address import RegionServingBoundary
from app.models.place import (
    AreaDetail,
    MapFeature,
    MapFeatureProviderRef,
    MapFeatureSourceLink,
    MapFeatureWebLink,
    OutdoorFeatureProfile,
    PlaceCategory,
    PlaceDetail,
    RouteDetail,
    SourceRecord,
)

KST = ZoneInfo("Asia/Seoul")
KRFOREST_PROVIDER = "python-krforest-api"
KRMOIS_PROVIDER = "python-mois-api"
_WHITESPACE_RE = re.compile(r"\s+")
_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

FeatureType = Literal["place", "area", "route"]


@dataclass(frozen=True)
class OutdoorDatasetSpec:
    dataset_key: str
    dataset_name: str
    provider: str
    feature_type: FeatureType
    outdoor_kind: str
    category_code: str | None
    category_name: str
    source_entity_type: str
    place_kind: str | None = None
    route_kind: str | None = None
    area_kind: str | None = None
    feature_role: str = "primary"
    confidence: int = 90


@dataclass(frozen=True)
class OutdoorFeatureLoadResult:
    dataset_key: str
    raw_record_count: int
    source_record_count: int
    feature_upsert_count: int
    profile_upsert_count: int
    linked_source_count: int
    skipped_record_count: int
    mapped_legal_dong_count: int


@dataclass(frozen=True)
class _OutdoorCandidate:
    spec: OutdoorDatasetSpec
    source_entity_id: str
    source_version: str | None
    name: str
    normalized_name: str
    address: str | None
    road_address: str | None
    jibun_address: str | None
    phone: str | None
    website_url: str | None
    geometry: BaseGeometry
    geometry_kind: str
    longitude: Decimal
    latitude: Decimal
    status: str
    is_visible: bool
    distance_m: int | None
    duration_min: int | None
    difficulty: str | None
    safety_note: str | None
    extra: dict[str, Any]
    raw_data: dict[str, Any]


KRFOREST_SPATIAL_POINT_SPECS: dict[str, OutdoorDatasetSpec] = {
    "krforest_recreation_forest_arboretum": OutdoorDatasetSpec(
        dataset_key="krforest_recreation_forest_arboretum",
        dataset_name="산림청 휴양림수목원 위치도 SHP",
        provider=KRFOREST_PROVIDER,
        feature_type="place",
        outdoor_kind="recreation_forest",
        category_code="01020301",
        category_name="휴양림·수목원",
        source_entity_type="place",
        place_kind="tourist_spot",
        confidence=95,
    ),
    "krforest_forest_education_center": OutdoorDatasetSpec(
        dataset_key="krforest_forest_education_center",
        dataset_name="산림청 산림교육센터 현황 SHP",
        provider=KRFOREST_PROVIDER,
        feature_type="place",
        outdoor_kind="forest_education",
        category_code="01020303",
        category_name="산림교육·체험",
        source_entity_type="place",
        place_kind="tourist_spot",
        confidence=90,
    ),
    "krforest_kid_forest_center": OutdoorDatasetSpec(
        dataset_key="krforest_kid_forest_center",
        dataset_name="산림청 유아숲체험원 현황 SHP",
        provider=KRFOREST_PROVIDER,
        feature_type="place",
        outdoor_kind="kid_forest",
        category_code="01020303",
        category_name="유아숲체험원",
        source_entity_type="place",
        place_kind="tourist_spot",
        confidence=90,
    ),
    "krforest_traditional_village_forest": OutdoorDatasetSpec(
        dataset_key="krforest_traditional_village_forest",
        dataset_name="산림청 전통마을숲 위치도 SHP",
        provider=KRFOREST_PROVIDER,
        feature_type="place",
        outdoor_kind="village_forest",
        category_code="01020300",
        category_name="전통마을숲",
        source_entity_type="place",
        place_kind="tourist_spot",
        confidence=85,
    ),
}

KRFOREST_ROUTE_SPECS: dict[str, OutdoorDatasetSpec] = {
    "krforest_hiking_trail": OutdoorDatasetSpec(
        dataset_key="krforest_hiking_trail",
        dataset_name="산림청 등산로정보 ZIP",
        provider=KRFOREST_PROVIDER,
        feature_type="route",
        outdoor_kind="hiking_trail",
        category_code="02010101",
        category_name="등산로",
        source_entity_type="route",
        route_kind="hiking",
        confidence=90,
    ),
    "krforest_dulle_trail": OutdoorDatasetSpec(
        dataset_key="krforest_dulle_trail",
        dataset_name="산림청 숲길정보 ZIP",
        provider=KRFOREST_PROVIDER,
        feature_type="route",
        outdoor_kind="trekking_course",
        category_code="02010201",
        category_name="둘레길·숲길",
        source_entity_type="route",
        route_kind="walking",
        confidence=90,
    ),
}

KRFOREST_AREA_SPECS: dict[str, OutdoorDatasetSpec] = {
    "krforest_mountain_area": OutdoorDatasetSpec(
        dataset_key="krforest_mountain_area",
        dataset_name="산림청 산 정보 조회",
        provider=KRFOREST_PROVIDER,
        feature_type="area",
        outdoor_kind="mountain",
        category_code="01020200",
        category_name="산·명산",
        source_entity_type="area",
        area_kind="mountain",
        confidence=75,
    ),
}

KRFOREST_STANDARD_RECREATION_FOREST_SPEC = OutdoorDatasetSpec(
    dataset_key="krforest_standard_recreation_forest",
    dataset_name="전국휴양림표준데이터",
    provider=KRFOREST_PROVIDER,
    feature_type="place",
    outdoor_kind="recreation_forest",
    category_code="01020301",
    category_name="휴양림",
    source_entity_type="place",
    place_kind="tourist_spot",
    confidence=95,
)

MOIS_OUTDOOR_LICENSE_SPECS: dict[str, OutdoorDatasetSpec] = {
    "general_campgrounds": OutdoorDatasetSpec(
        dataset_key="krmois_general_campgrounds",
        dataset_name="행정안전부 인허가 일반야영장업",
        provider=KRMOIS_PROVIDER,
        feature_type="place",
        outdoor_kind="campground",
        category_code="03060000",
        category_name="일반야영장",
        source_entity_type="place",
        place_kind="hotel",
        feature_role="support",
        confidence=80,
    ),
    "auto_campgrounds": OutdoorDatasetSpec(
        dataset_key="krmois_auto_campgrounds",
        dataset_name="행정안전부 인허가 자동차야영장업",
        provider=KRMOIS_PROVIDER,
        feature_type="place",
        outdoor_kind="campground",
        category_code="03060100",
        category_name="자동차야영장",
        source_entity_type="place",
        place_kind="hotel",
        feature_role="support",
        confidence=80,
    ),
    "special_resorts": OutdoorDatasetSpec(
        dataset_key="krmois_special_resorts",
        dataset_name="행정안전부 인허가 전문휴양업",
        provider=KRMOIS_PROVIDER,
        feature_type="place",
        outdoor_kind="outdoor_support",
        category_code="01020300",
        category_name="전문휴양업",
        source_entity_type="place",
        place_kind="tourist_spot",
        feature_role="enrichment",
        confidence=70,
    ),
    "comprehensive_resorts": OutdoorDatasetSpec(
        dataset_key="krmois_comprehensive_resorts",
        dataset_name="행정안전부 인허가 종합휴양업",
        provider=KRMOIS_PROVIDER,
        feature_type="place",
        outdoor_kind="outdoor_support",
        category_code="01020300",
        category_name="종합휴양업",
        source_entity_type="place",
        place_kind="tourist_spot",
        feature_role="enrichment",
        confidence=70,
    ),
}

OUTDOOR_CATEGORY_ROWS: tuple[dict[str, Any], ...] = (
    {
        "category_code": "01000000",
        "tier1_name": "관광",
        "tier2_name": None,
        "tier3_name": None,
        "tier4_name": None,
        "depth": 1,
        "parent_category_code": None,
        "sort_order": 10,
    },
    {
        "category_code": "01020000",
        "tier1_name": "관광",
        "tier2_name": "자연관광",
        "tier3_name": None,
        "tier4_name": None,
        "depth": 2,
        "parent_category_code": "01000000",
        "sort_order": 20,
    },
    {
        "category_code": "01020100",
        "tier1_name": "관광",
        "tier2_name": "자연관광",
        "tier3_name": "국립공원",
        "tier4_name": None,
        "depth": 3,
        "parent_category_code": "01020000",
        "sort_order": 201,
    },
    {
        "category_code": "01020101",
        "tier1_name": "관광",
        "tier2_name": "자연관광",
        "tier3_name": "국립공원",
        "tier4_name": "국립공원",
        "depth": 4,
        "parent_category_code": "01020100",
        "sort_order": 2011,
    },
    {
        "category_code": "01020200",
        "tier1_name": "관광",
        "tier2_name": "자연관광",
        "tier3_name": "산·명산",
        "tier4_name": None,
        "depth": 3,
        "parent_category_code": "01020000",
        "sort_order": 202,
    },
    {
        "category_code": "01020201",
        "tier1_name": "관광",
        "tier2_name": "자연관광",
        "tier3_name": "산·명산",
        "tier4_name": "100대명산",
        "depth": 4,
        "parent_category_code": "01020200",
        "sort_order": 2021,
    },
    {
        "category_code": "01020300",
        "tier1_name": "관광",
        "tier2_name": "자연관광",
        "tier3_name": "산림휴양",
        "tier4_name": None,
        "depth": 3,
        "parent_category_code": "01020000",
        "sort_order": 203,
    },
    {
        "category_code": "01020301",
        "tier1_name": "관광",
        "tier2_name": "자연관광",
        "tier3_name": "산림휴양",
        "tier4_name": "휴양림",
        "depth": 4,
        "parent_category_code": "01020300",
        "sort_order": 2031,
    },
    {
        "category_code": "01020302",
        "tier1_name": "관광",
        "tier2_name": "자연관광",
        "tier3_name": "산림휴양",
        "tier4_name": "수목원",
        "depth": 4,
        "parent_category_code": "01020300",
        "sort_order": 2032,
    },
    {
        "category_code": "01020303",
        "tier1_name": "관광",
        "tier2_name": "자연관광",
        "tier3_name": "산림휴양",
        "tier4_name": "산림교육·체험",
        "depth": 4,
        "parent_category_code": "01020300",
        "sort_order": 2033,
    },
    {
        "category_code": "02000000",
        "tier1_name": "액티비티",
        "tier2_name": None,
        "tier3_name": None,
        "tier4_name": None,
        "depth": 1,
        "parent_category_code": None,
        "sort_order": 200,
    },
    {
        "category_code": "02010000",
        "tier1_name": "액티비티",
        "tier2_name": "걷기·등산",
        "tier3_name": None,
        "tier4_name": None,
        "depth": 2,
        "parent_category_code": "02000000",
        "sort_order": 210,
    },
    {
        "category_code": "02010100",
        "tier1_name": "액티비티",
        "tier2_name": "걷기·등산",
        "tier3_name": "등산로",
        "tier4_name": None,
        "depth": 3,
        "parent_category_code": "02010000",
        "sort_order": 211,
    },
    {
        "category_code": "02010101",
        "tier1_name": "액티비티",
        "tier2_name": "걷기·등산",
        "tier3_name": "등산로",
        "tier4_name": "산림청 등산로",
        "depth": 4,
        "parent_category_code": "02010100",
        "sort_order": 2111,
    },
    {
        "category_code": "02010200",
        "tier1_name": "액티비티",
        "tier2_name": "걷기·등산",
        "tier3_name": "트레킹·숲길",
        "tier4_name": None,
        "depth": 3,
        "parent_category_code": "02010000",
        "sort_order": 212,
    },
    {
        "category_code": "02010201",
        "tier1_name": "액티비티",
        "tier2_name": "걷기·등산",
        "tier3_name": "트레킹·숲길",
        "tier4_name": "둘레길·숲길",
        "depth": 4,
        "parent_category_code": "02010200",
        "sort_order": 2121,
    },
    {
        "category_code": "03000000",
        "tier1_name": "숙박",
        "tier2_name": None,
        "tier3_name": None,
        "tier4_name": None,
        "depth": 1,
        "parent_category_code": None,
        "sort_order": 300,
    },
    {
        "category_code": "03060000",
        "tier1_name": "숙박",
        "tier2_name": "캠핑장",
        "tier3_name": None,
        "tier4_name": None,
        "depth": 2,
        "parent_category_code": "03000000",
        "sort_order": 360,
    },
    {
        "category_code": "03060100",
        "tier1_name": "숙박",
        "tier2_name": "캠핑장",
        "tier3_name": "오토캠핑장",
        "tier4_name": None,
        "depth": 3,
        "parent_category_code": "03060000",
        "sort_order": 361,
    },
)


def load_krforest_spatial_points(
    session: Session,
    dataset_key: str,
    records: Iterable[Any],
    *,
    collected_at: datetime | None = None,
) -> OutdoorFeatureLoadResult:
    spec = KRFOREST_SPATIAL_POINT_SPECS[dataset_key]
    return _load_candidates(
        session,
        spec,
        (_candidate_from_spatial_point(spec, record) for record in records),
        collected_at=collected_at,
    )


def load_krforest_spatial_features(
    session: Session,
    dataset_key: str,
    records: Iterable[Any],
    *,
    collected_at: datetime | None = None,
) -> OutdoorFeatureLoadResult:
    spec = KRFOREST_ROUTE_SPECS[dataset_key]
    return _load_candidates(
        session,
        spec,
        (_candidate_from_spatial_feature(spec, record) for record in records),
        collected_at=collected_at,
    )


def load_krforest_standard_recreation_forests(
    session: Session,
    records: Iterable[Any],
    *,
    collected_at: datetime | None = None,
) -> OutdoorFeatureLoadResult:
    spec = KRFOREST_STANDARD_RECREATION_FOREST_SPEC
    return _load_candidates(
        session,
        spec,
        (_candidate_from_standard_recreation_forest(spec, record) for record in records),
        collected_at=collected_at,
    )


def load_krforest_mountain_story_areas(
    session: Session,
    records: Iterable[Mapping[str, Any]],
    *,
    collected_at: datetime | None = None,
) -> OutdoorFeatureLoadResult:
    spec = KRFOREST_AREA_SPECS["krforest_mountain_area"]
    return _load_candidates(
        session,
        spec,
        (_candidate_from_mountain_story(spec, record) for record in records),
        collected_at=collected_at,
    )


def load_mois_outdoor_license_records(
    session: Session,
    slug: str,
    records: Iterable[Any],
    *,
    collected_at: datetime | None = None,
) -> OutdoorFeatureLoadResult:
    spec = MOIS_OUTDOOR_LICENSE_SPECS[slug]
    return _load_candidates(
        session,
        spec,
        (_candidate_from_mois_record(spec, record) for record in records),
        collected_at=collected_at,
    )


def load_default_krforest_outdoor_features(
    session: Session,
    client: Any,
    *,
    collected_at: datetime | None = None,
) -> dict[str, Any]:
    results = {
        "recreation_forest_arboretums": load_krforest_spatial_points(
            session,
            "krforest_recreation_forest_arboretum",
            client.travel.recreation_forest_arboretums(),
            collected_at=collected_at,
        ),
        "forest_education_centers": load_krforest_spatial_points(
            session,
            "krforest_forest_education_center",
            client.travel.forest_education_centers(),
            collected_at=collected_at,
        ),
        "kid_forest_centers": load_krforest_spatial_points(
            session,
            "krforest_kid_forest_center",
            client.travel.kid_forest_centers(),
            collected_at=collected_at,
        ),
        "traditional_village_forests": load_krforest_spatial_points(
            session,
            "krforest_traditional_village_forest",
            client.travel.traditional_village_forests(),
            collected_at=collected_at,
        ),
        "mountain_areas": load_krforest_mountain_story_areas(
            session,
            _iter_page_items(client, client.travel.mountain_stories),
            collected_at=collected_at,
        ),
        "hiking_trails": load_krforest_spatial_features(
            session,
            "krforest_hiking_trail",
            client.travel.forest_trail_file_features(),
            collected_at=collected_at,
        ),
        "dulle_trails": load_krforest_spatial_features(
            session,
            "krforest_dulle_trail",
            client.travel.dulle_trail_features(),
            collected_at=collected_at,
        ),
    }
    return {key: value.__dict__ for key, value in results.items()}


def load_default_mois_outdoor_license_features(
    session: Session,
    files_client: Any,
    *,
    collected_at: datetime | None = None,
) -> dict[str, Any]:
    results: dict[str, OutdoorFeatureLoadResult] = {}
    for slug in MOIS_OUTDOOR_LICENSE_SPECS:
        results[slug] = load_mois_outdoor_license_records(
            session,
            slug,
            files_client.iter(slug),
            collected_at=collected_at,
        )
    return {key: value.__dict__ for key, value in results.items()}


def ensure_outdoor_place_categories(
    session: Session, *, collected_at: datetime | None = None
) -> None:
    now = _resolve_collected_at(collected_at)
    rows = []
    for row in OUTDOOR_CATEGORY_ROWS:
        category_code = row["category_code"]
        rows.append(
            {
                **row,
                "tier1_code": category_code[0:2],
                "tier2_code": category_code[2:4],
                "tier3_code": category_code[4:6],
                "tier4_code": category_code[6:8],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
    statement = pg_insert(cast(Table, PlaceCategory.__table__)).values(rows)
    session.execute(statement.on_conflict_do_nothing(index_elements=["category_code"]))


def _load_candidates(
    session: Session,
    spec: OutdoorDatasetSpec,
    candidates: Iterable[_OutdoorCandidate | None],
    *,
    collected_at: datetime | None,
) -> OutdoorFeatureLoadResult:
    collected = _resolve_collected_at(collected_at)
    ensure_outdoor_place_categories(session, collected_at=collected)

    raw_count = 0
    source_count = 0
    feature_count = 0
    profile_count = 0
    link_count = 0
    skipped_count = 0
    mapped_legal_count = 0

    for candidate in candidates:
        raw_count += 1
        if candidate is None:
            skipped_count += 1
            continue

        region = _find_legal_region(
            session,
            longitude=candidate.longitude,
            latitude=candidate.latitude,
        )
        if region is not None:
            mapped_legal_count += 1

        raw_hash = _hash_payload(candidate.raw_data)
        source_record, created_source = _upsert_source_record(
            session,
            candidate=candidate,
            raw_hash=raw_hash,
            collected_at=collected,
        )
        if created_source:
            source_count += 1

        feature, changed_feature = _upsert_feature(
            session,
            candidate=candidate,
            source_record=source_record,
            region=region,
            collected_at=collected,
        )
        if changed_feature:
            feature_count += 1

        if _upsert_profile(session, feature=feature, candidate=candidate):
            profile_count += 1
        if _upsert_source_link(session, feature=feature, source_record=source_record):
            link_count += 1
        _upsert_provider_ref(
            session,
            feature=feature,
            candidate=candidate,
            fetched_at=collected,
        )
        _upsert_web_link(session, feature=feature, candidate=candidate)
        _upsert_detail(session, feature=feature, candidate=candidate)

    session.flush()
    return OutdoorFeatureLoadResult(
        dataset_key=spec.dataset_key,
        raw_record_count=raw_count,
        source_record_count=source_count,
        feature_upsert_count=feature_count,
        profile_upsert_count=profile_count,
        linked_source_count=link_count,
        skipped_record_count=skipped_count,
        mapped_legal_dong_count=mapped_legal_count,
    )


def _candidate_from_spatial_point(
    spec: OutdoorDatasetSpec, record: Any
) -> _OutdoorCandidate | None:
    raw = _json_ready(_get_attr(record, "raw") or _model_dump(record))
    name = _first_text(
        _get_attr(record, "name"),
        _mapping_text(raw, "name"),
        _mapping_text(raw, "명칭"),
        _mapping_text(raw, "NAME"),
    )
    lon_lat = _coordinate_lon_lat(_get_attr(record, "coordinate"))
    if name is None or lon_lat is None:
        return None
    lon, lat = lon_lat
    geometry = Point(lon, lat)
    address = _address_text(_get_attr(record, "address"), raw)
    category = _first_text(_get_attr(record, "category"), spec.category_name)
    outdoor_kind = _resolve_forest_point_kind(name, category, spec.outdoor_kind)
    category_code = "01020302" if outdoor_kind == "arboretum" else spec.category_code
    category_name = "수목원" if outdoor_kind == "arboretum" else spec.category_name
    resolved_spec = (
        spec
        if (
            outdoor_kind == spec.outdoor_kind
            and category_code == spec.category_code
            and category_name == spec.category_name
        )
        else OutdoorDatasetSpec(
            **{
                **spec.__dict__,
                "outdoor_kind": outdoor_kind,
                "category_code": category_code,
                "category_name": category_name,
            }
        )
    )
    extra = {
        "category": category,
        "owner_name": _get_attr(record, "owner_name"),
        "operation_status": _get_attr(record, "operation_status"),
        "region_code": _get_attr(record, "region_code"),
        "region_name": _get_attr(record, "region_name"),
        "projected_x": _get_attr(record, "projected_x"),
        "projected_y": _get_attr(record, "projected_y"),
        "year": _get_attr(record, "year"),
    }
    return _build_candidate(
        resolved_spec,
        name=name,
        source_entity_id=_source_entity_id(
            resolved_spec.dataset_key,
            raw,
            fallback_parts=(name, address, f"{lon:.8f}", f"{lat:.8f}"),
        ),
        source_version=_first_text(_get_attr(record, "year"), _mapping_text(raw, "year")),
        address=address,
        phone=_first_text(_get_attr(record, "phone_number"), _mapping_text(raw, "전화번호")),
        website_url=_first_text(_get_attr(record, "homepage_url"), _mapping_text(raw, "홈페이지")),
        geometry=geometry,
        status=_operation_status(_get_attr(record, "operation_status")),
        extra={key: value for key, value in extra.items() if value is not None},
        raw_data=raw,
    )


def _candidate_from_spatial_feature(
    spec: OutdoorDatasetSpec,
    record: Any,
) -> _OutdoorCandidate | None:
    raw = _json_ready(_get_attr(record, "raw") or _model_dump(record))
    name = _first_text(
        _get_attr(record, "name"),
        _mapping_text(raw, "name"),
        _mapping_text(raw, "노선명"),
        _mapping_text(raw, "코스명"),
        spec.category_name,
    )
    geometry_data = _get_attr(record, "geometry")
    geometry = _geometry_from_any(geometry_data, _get_attr(record, "coordinate"))
    if name is None or geometry is None or geometry.is_empty:
        return None
    centroid = geometry.centroid
    distance_m = _first_distance_m(
        _get_attr(record, "distance_m"),
        _mapping_text(raw, "distance_m"),
        _mapping_text(raw, "거리"),
        _mapping_text(raw, "DISTANCE"),
    )
    duration_min = _first_duration_min(
        _get_attr(record, "duration_min"),
        _mapping_text(raw, "duration_min"),
        _mapping_text(raw, "소요시간"),
        _mapping_text(raw, "TIME"),
    )
    difficulty = _first_text(
        _get_attr(record, "difficulty"),
        _mapping_text(raw, "난이도"),
        _mapping_text(raw, "difficulty"),
    )
    return _build_candidate(
        spec,
        name=name,
        source_entity_id=_source_entity_id(
            spec.dataset_key,
            raw,
            fallback_parts=(name, geometry.wkt[:500]),
        ),
        source_version=_first_text(
            _get_attr(record, "source_file"),
            _get_attr(record, "layer_name"),
        ),
        address=None,
        phone=None,
        website_url=None,
        geometry=geometry,
        longitude=_decimal_from_float(centroid.x),
        latitude=_decimal_from_float(centroid.y),
        distance_m=distance_m,
        duration_min=duration_min,
        difficulty=difficulty,
        status="active",
        extra={
            "source_file": _get_attr(record, "source_file"),
            "layer_name": _get_attr(record, "layer_name"),
            "bbox": _get_attr(record, "bbox"),
            "geometry_type": _get_attr(record, "geometry_type"),
        },
        raw_data=raw,
    )


def _candidate_from_standard_recreation_forest(
    spec: OutdoorDatasetSpec,
    record: Any,
) -> _OutdoorCandidate | None:
    raw = _json_ready(_get_attr(record, "raw") or _model_dump(record))
    name = _first_text(_get_attr(record, "name"), _mapping_text(raw, "rcrfrstNm"))
    lon_lat = _coordinate_lon_lat(_get_attr(record, "coordinate"))
    if name is None or lon_lat is None:
        return None
    lon, lat = lon_lat
    address = _address_text(_get_attr(record, "address"), raw)
    return _build_candidate(
        spec,
        name=name,
        source_entity_id=_source_entity_id(
            spec.dataset_key,
            raw,
            keys=("institution_code", "instt_code", "institutionCode"),
            fallback_parts=(name, address, f"{lon:.8f}", f"{lat:.8f}"),
        ),
        source_version=_first_text(
            _get_attr(record, "reference_date"), _mapping_text(raw, "referenceDate")
        ),
        address=address,
        phone=_get_attr(record, "phone_number"),
        website_url=_get_attr(record, "homepage_url"),
        geometry=Point(lon, lat),
        status="active",
        extra={
            "forest_type": _get_attr(record, "forest_type"),
            "area": _get_attr(record, "area"),
            "capacity": _get_attr(record, "capacity"),
            "entrance_fee": _get_attr(record, "entrance_fee"),
            "accommodation_available": _get_attr(record, "accommodation_available"),
            "main_facilities": _get_attr(record, "main_facilities"),
            "management_agency": _get_attr(record, "management_agency"),
        },
        raw_data=raw,
    )


def _candidate_from_mountain_story(
    spec: OutdoorDatasetSpec,
    record: Mapping[str, Any],
) -> _OutdoorCandidate | None:
    raw = _json_ready(record)
    name = _first_text(
        _mapping_text(raw, "mntiname"),
        _mapping_text(raw, "mntiName"),
        _mapping_text(raw, "mntnNm"),
        _mapping_text(raw, "mntn_nm"),
        _mapping_text(raw, "mnt_nm"),
        _mapping_text(raw, "mountain_name"),
        _mapping_text(raw, "산명"),
        _mapping_text(raw, "name"),
    )
    lon = _first_float(
        _mapping_text(raw, "longitude"),
        _mapping_text(raw, "lon"),
        _mapping_text(raw, "lng"),
        _mapping_text(raw, "mntilon"),
        _mapping_text(raw, "mnti_lng"),
        _mapping_text(raw, "경도"),
        _mapping_text(raw, "X"),
        _mapping_text(raw, "x"),
    )
    lat = _first_float(
        _mapping_text(raw, "latitude"),
        _mapping_text(raw, "lat"),
        _mapping_text(raw, "mntilat"),
        _mapping_text(raw, "mnti_lat"),
        _mapping_text(raw, "위도"),
        _mapping_text(raw, "Y"),
        _mapping_text(raw, "y"),
    )
    if name is None or lon is None or lat is None:
        return None
    address = _first_text(
        _mapping_text(raw, "mntiadd"),
        _mapping_text(raw, "mntiaddr"),
        _mapping_text(raw, "address"),
        _mapping_text(raw, "addr"),
        _mapping_text(raw, "소재지"),
    )
    height = _first_text(
        _mapping_text(raw, "mntihigh"),
        _mapping_text(raw, "mntnHght"),
        _mapping_text(raw, "height"),
        _mapping_text(raw, "높이"),
    )
    summary = _first_text(
        _mapping_text(raw, "mntidetails"),
        _mapping_text(raw, "mntisummary"),
        _mapping_text(raw, "details"),
        _mapping_text(raw, "summary"),
    )
    return _build_candidate(
        spec,
        name=name,
        source_entity_id=_source_entity_id(
            spec.dataset_key,
            raw,
            keys=("mntiid", "mountain_id", "id"),
            fallback_parts=(name, address, f"{lon:.8f}", f"{lat:.8f}"),
        ),
        source_version=None,
        address=address,
        phone=None,
        website_url=None,
        geometry=Point(lon, lat),
        status="active",
        extra={
            "height": height,
            "summary": summary,
            "geometry_note": (
                "산 정보 원천이 중심점만 제공하면 area feature의 centroid로 우선 적재한다."
            ),
        },
        raw_data=raw,
    )


def _candidate_from_mois_record(spec: OutdoorDatasetSpec, record: Any) -> _OutdoorCandidate | None:
    raw = _json_ready(_get_attr(record, "raw") or _get_attr(record, "data") or _model_dump(record))
    name = _first_text(_get_attr(record, "business_name"), _mapping_text(raw, "BPLC_NM"))
    coordinates = _get_attr(record, "coordinates")
    lon_lat = _coordinate_lon_lat(_get_attr(coordinates, "wgs84_point") or coordinates)
    if name is None or lon_lat is None:
        return None
    lon, lat = lon_lat
    address = _first_text(
        _mapping_text(raw, "RDNWHLADDR"),
        _mapping_text(raw, "SITEWHLADDR"),
        _mapping_text(raw, "address"),
    )
    status = "inactive" if _get_attr(record, "is_open") is False else "active"
    return _build_candidate(
        spec,
        name=name,
        source_entity_id=_source_entity_id(
            spec.dataset_key,
            raw,
            keys=("MNG_NO", "management_number"),
            fallback_parts=(name, address, f"{lon:.8f}", f"{lat:.8f}"),
        ),
        source_version=_first_text(
            _date_text(_get_attr(record, "updated_at")),
            _date_text(_get_attr(record, "modified_at")),
        ),
        address=address,
        phone=_first_text(_mapping_text(raw, "SITE_TEL"), _mapping_text(raw, "phone")),
        website_url=None,
        geometry=Point(lon, lat),
        status=status,
        is_visible=status == "active",
        extra={
            "service_slug": _get_attr(record, "service_slug"),
            "title": _get_attr(record, "title"),
            "license_date": _date_text(_get_attr(record, "license_date")),
            "business_status_code": _get_attr(record, "business_status_code"),
            "business_status_name": _get_attr(record, "business_status_name"),
        },
        raw_data=raw,
    )


def _build_candidate(
    spec: OutdoorDatasetSpec,
    *,
    name: str,
    source_entity_id: str,
    source_version: str | None,
    address: str | None,
    phone: str | None,
    website_url: str | None,
    geometry: BaseGeometry,
    status: str,
    raw_data: dict[str, Any],
    normalized_name: str | None = None,
    road_address: str | None = None,
    jibun_address: str | None = None,
    longitude: Decimal | None = None,
    latitude: Decimal | None = None,
    distance_m: int | None = None,
    duration_min: int | None = None,
    difficulty: str | None = None,
    safety_note: str | None = None,
    extra: dict[str, Any] | None = None,
    is_visible: bool | None = None,
) -> _OutdoorCandidate:
    centroid = geometry.centroid
    lon = longitude if longitude is not None else _decimal_from_float(centroid.x)
    lat = latitude if latitude is not None else _decimal_from_float(centroid.y)
    visible = status == "active" if is_visible is None else is_visible
    return _OutdoorCandidate(
        spec=spec,
        source_entity_id=source_entity_id[:255],
        source_version=source_version,
        name=name,
        normalized_name=normalized_name or _normalize_search_text(name),
        address=address,
        road_address=road_address or address,
        jibun_address=jibun_address,
        phone=phone,
        website_url=_normalize_url(website_url),
        geometry=geometry,
        geometry_kind=_geometry_kind(geometry),
        longitude=lon,
        latitude=lat,
        status=status,
        is_visible=visible,
        distance_m=distance_m,
        duration_min=duration_min,
        difficulty=difficulty,
        safety_note=safety_note,
        extra={key: value for key, value in (extra or {}).items() if value is not None},
        raw_data=raw_data,
    )


def _upsert_source_record(
    session: Session,
    *,
    candidate: _OutdoorCandidate,
    raw_hash: str,
    collected_at: datetime,
) -> tuple[SourceRecord, bool]:
    spec = candidate.spec
    existing = session.scalar(
        select(SourceRecord).where(
            SourceRecord.provider == spec.provider,
            SourceRecord.dataset_key == spec.dataset_key,
            SourceRecord.source_entity_type == spec.source_entity_type,
            SourceRecord.source_entity_id == candidate.source_entity_id,
            SourceRecord.raw_payload_hash == raw_hash,
        )
    )
    if existing is not None:
        return existing, False

    source_record = SourceRecord(
        provider=spec.provider,
        dataset_key=spec.dataset_key,
        source_entity_type=spec.source_entity_type,
        source_entity_id=candidate.source_entity_id,
        source_version=candidate.source_version,
        raw_name=candidate.name,
        raw_address=candidate.address,
        raw_longitude=candidate.longitude,
        raw_latitude=candidate.latitude,
        raw_geom=_wkt(candidate.geometry),
        raw_data=candidate.raw_data,
        raw_payload_hash=raw_hash,
        fetched_at=collected_at,
        imported_at=collected_at,
        expires_at=None,
    )
    session.add(source_record)
    session.flush()
    return source_record, True


def _upsert_feature(
    session: Session,
    *,
    candidate: _OutdoorCandidate,
    source_record: SourceRecord,
    region: RegionServingBoundary | None,
    collected_at: datetime,
) -> tuple[MapFeature, bool]:
    spec = candidate.spec
    feature = _find_feature_by_provider_ref(session, spec, candidate.source_entity_id)
    extra = {
        **candidate.extra,
        "outdoor": {
            "kind": spec.outdoor_kind,
            "feature_role": spec.feature_role,
            "source_dataset_key": spec.dataset_key,
        },
    }
    values: dict[str, Any] = {
        "feature_type": spec.feature_type,
        "name": candidate.name,
        "display_name": candidate.name,
        "normalized_name": candidate.normalized_name,
        "subtitle": spec.category_name,
        "summary": None,
        "description": None,
        "category_code": spec.category_code,
        "category_name": spec.category_name,
        "geom": _wkt(candidate.geometry),
        "geometry_kind": candidate.geometry_kind,
        "centroid": _point(candidate.longitude, candidate.latitude),
        "longitude": candidate.longitude,
        "latitude": candidate.latitude,
        "address": candidate.address,
        "road_address": candidate.road_address,
        "jibun_address": candidate.jibun_address,
        "legal_dong_code": region.legal_dong_code if region is not None else None,
        "sigungu_code": region.sigungu_code if region is not None else None,
        "sido_code": region.sido_code if region is not None else None,
        "admin_dong_code": None,
        "road_name_code": None,
        "road_address_management_no": None,
        "phone": candidate.phone,
        "website_url": candidate.website_url,
        "popularity_score": 0,
        "priority_score": 0,
        "status": candidate.status,
        "is_visible": candidate.is_visible,
        "primary_source_record_id": source_record.id,
        "extra": extra,
        "last_seen_at": collected_at,
        "last_verified_at": collected_at,
    }
    if feature is None:
        feature = MapFeature(
            public_id=_public_id(spec.dataset_key, candidate.source_entity_id),
            parent_feature_id=None,
            first_seen_at=collected_at,
            **values,
        )
        session.add(feature)
        session.flush()
        return feature, True

    changed = False
    for key, value in values.items():
        if getattr(feature, key) != value:
            setattr(feature, key, value)
            changed = True
    session.flush()
    return feature, changed


def _upsert_profile(
    session: Session,
    *,
    feature: MapFeature,
    candidate: _OutdoorCandidate,
) -> bool:
    spec = candidate.spec
    profile = session.get(OutdoorFeatureProfile, feature.id)
    values = {
        "outdoor_kind": spec.outdoor_kind,
        "feature_role": spec.feature_role,
        "source_provider": spec.provider,
        "source_dataset_key": spec.dataset_key,
        "source_dataset_name": spec.dataset_name,
        "confidence": spec.confidence,
        "difficulty": candidate.difficulty,
        "distance_m": candidate.distance_m,
        "duration_min": candidate.duration_min,
        "elevation_gain_m": None,
        "recommended_season": None,
        "reservation_url": candidate.website_url,
        "safety_note": candidate.safety_note,
        "data_quality_note": None,
        "extra": candidate.extra,
    }
    if profile is None:
        session.add(OutdoorFeatureProfile(feature_id=feature.id, **values))
        return True
    changed = False
    for key, value in values.items():
        if getattr(profile, key) != value:
            setattr(profile, key, value)
            changed = True
    return changed


def _upsert_detail(session: Session, *, feature: MapFeature, candidate: _OutdoorCandidate) -> None:
    spec = candidate.spec
    if spec.feature_type == "place":
        place_detail = session.get(PlaceDetail, feature.id)
        values = {
            "place_kind": spec.place_kind or "tourist_spot",
            "operation_status": "closed" if candidate.status == "inactive" else "unknown",
            "address_resolution_status": "resolved" if feature.legal_dong_code else "unresolved",
            "verification_status": "public_data_verified",
            "quality_score": spec.confidence,
            "opened_on": None,
            "closed_on": None,
            "extra": candidate.extra,
        }
        if place_detail is None:
            session.add(PlaceDetail(feature_id=feature.id, **values))
        else:
            for key, value in values.items():
                setattr(place_detail, key, value)
        return

    if spec.feature_type == "route":
        route_detail = session.get(RouteDetail, feature.id)
        values = {
            "route_kind": spec.route_kind or "hiking",
            "distance_m": candidate.distance_m,
            "duration_min": candidate.duration_min,
            "difficulty": candidate.difficulty,
            "start_name": None,
            "end_name": None,
            "elevation_gain_m": None,
            "elevation_loss_m": None,
            "min_elevation_m": None,
            "max_elevation_m": None,
            "is_loop": False,
            "recommended_season": None,
            "surface_type": None,
            "accessibility_note": None,
            "safety_note": candidate.safety_note,
            "extra": candidate.extra,
        }
        if route_detail is None:
            session.add(RouteDetail(feature_id=feature.id, **values))
        else:
            for key, value in values.items():
                setattr(route_detail, key, value)
        return

    area_detail = session.get(AreaDetail, feature.id)
    values = {
        "area_kind": spec.area_kind or "forest_area",
        "managing_org": None,
        "contact_phone": candidate.phone,
        "website_url": candidate.website_url,
        "rules": None,
        "fee_info": None,
        "open_season_start": None,
        "open_season_end": None,
        "area_size_m2": None,
        "is_restricted": False,
        "restriction_note": None,
        "extra": candidate.extra,
    }
    if area_detail is None:
        session.add(AreaDetail(feature_id=feature.id, **values))
    else:
        for key, value in values.items():
            setattr(area_detail, key, value)


def _upsert_provider_ref(
    session: Session,
    *,
    feature: MapFeature,
    candidate: _OutdoorCandidate,
    fetched_at: datetime,
) -> None:
    spec = candidate.spec
    ref = session.scalar(
        select(MapFeatureProviderRef).where(
            MapFeatureProviderRef.provider == spec.provider,
            MapFeatureProviderRef.provider_dataset_key == spec.dataset_key,
            MapFeatureProviderRef.provider_feature_id == candidate.source_entity_id,
        )
    )
    if ref is None:
        ref = MapFeatureProviderRef(
            feature_id=feature.id,
            provider=spec.provider,
            provider_dataset_key=spec.dataset_key,
            provider_feature_id=candidate.source_entity_id,
        )
        session.add(ref)
    ref.stable_name = candidate.name
    ref.stable_address = candidate.address
    ref.stable_phone = candidate.phone
    ref.last_fetched_at = fetched_at
    ref.expires_at = None


def _upsert_source_link(
    session: Session,
    *,
    feature: MapFeature,
    source_record: SourceRecord,
) -> bool:
    link = session.scalar(
        select(MapFeatureSourceLink).where(
            MapFeatureSourceLink.feature_id == feature.id,
            MapFeatureSourceLink.source_record_id == source_record.id,
        )
    )
    if link is not None:
        link.is_primary_source = True
        link.source_role = "primary"
        return False
    session.add(
        MapFeatureSourceLink(
            feature_id=feature.id,
            source_record_id=source_record.id,
            source_role="primary",
            match_method="provider_dataset_source_id",
            confidence=100,
            is_primary_source=True,
        )
    )
    return True


def _upsert_web_link(
    session: Session,
    *,
    feature: MapFeature,
    candidate: _OutdoorCandidate,
) -> None:
    if not candidate.website_url:
        return
    link = session.scalar(
        select(MapFeatureWebLink).where(
            MapFeatureWebLink.feature_id == feature.id,
            MapFeatureWebLink.url == candidate.website_url,
        )
    )
    if link is None:
        session.add(
            MapFeatureWebLink(
                feature_id=feature.id,
                link_type="official",
                provider=candidate.spec.provider,
                url=candidate.website_url,
                title="공식 홈페이지",
                is_primary=True,
                sort_order=0,
            )
        )
        return
    link.link_type = "official"
    link.provider = candidate.spec.provider
    link.title = "공식 홈페이지"
    link.is_primary = True
    link.sort_order = 0


def _find_feature_by_provider_ref(
    session: Session,
    spec: OutdoorDatasetSpec,
    source_entity_id: str,
) -> MapFeature | None:
    ref = session.scalar(
        select(MapFeatureProviderRef).where(
            MapFeatureProviderRef.provider == spec.provider,
            MapFeatureProviderRef.provider_dataset_key == spec.dataset_key,
            MapFeatureProviderRef.provider_feature_id == source_entity_id,
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


def _geometry_from_any(
    geometry_data: Any,
    coordinate: Any | None,
) -> BaseGeometry | None:
    if isinstance(geometry_data, BaseGeometry):
        return geometry_data
    if isinstance(geometry_data, Mapping):
        return shape(geometry_data)
    lon_lat = _coordinate_lon_lat(coordinate)
    if lon_lat is None:
        return None
    return Point(lon_lat[0], lon_lat[1])


def _coordinate_lon_lat(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    lon = _get_attr(value, "longitude")
    lat = _get_attr(value, "latitude")
    if lon is None:
        lon = _get_attr(value, "lon")
    if lat is None:
        lat = _get_attr(value, "lat")
    if lon is not None and lat is not None:
        try:
            return float(lon), float(lat)
        except (TypeError, ValueError):
            return None
    if hasattr(value, "as_tuple"):
        try:
            lon_value, lat_value = value.as_tuple()
            return float(lon_value), float(lat_value)
        except (TypeError, ValueError):
            return None
    return None


def _address_text(address: Any, raw: Mapping[str, Any]) -> str | None:
    if address is not None:
        direct = _first_text(
            _get_attr(address, "road_address"),
            _get_attr(address, "jibun_address"),
            _get_attr(address, "full_address"),
            _get_attr(address, "full_text"),
            _get_attr(address, "text"),
        )
        if direct is not None:
            return direct
        if isinstance(address, str):
            return _normalize_value(address)
    return _first_text(
        _mapping_text(raw, "address"),
        _mapping_text(raw, "주소"),
        _mapping_text(raw, "전체주소"),
        _mapping_text(raw, "rdnmadr"),
        _mapping_text(raw, "lnmadr"),
    )


def _source_entity_id(
    dataset_key: str,
    raw: Mapping[str, Any],
    *,
    fallback_parts: tuple[Any, ...],
    keys: tuple[str, ...] = (
        "id",
        "ID",
        "objectid",
        "OBJECTID",
        "fid",
        "FID",
        "관리번호",
        "MNG_NO",
    ),
) -> str:
    for key in keys:
        text = _mapping_text(raw, key)
        if text:
            return text
    seed = "|".join(str(part or "") for part in (dataset_key, *fallback_parts))
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def _resolve_forest_point_kind(name: str, category: str | None, default: str) -> str:
    text = f"{name} {category or ''}"
    if "수목원" in text or "정원" in text:
        return "arboretum"
    if "휴양림" in text:
        return "recreation_forest"
    return default


def _operation_status(value: Any) -> str:
    text = _normalize_value(value)
    if not text:
        return "active"
    if any(token in text for token in ("폐", "중단", "취소")):
        return "inactive"
    return "active"


def _geometry_kind(geometry: BaseGeometry) -> str:
    geom_type = geometry.geom_type.lower()
    if "point" in geom_type:
        return "point"
    if "line" in geom_type:
        return "line"
    if "polygon" in geom_type:
        return "polygon"
    return "mixed"


def _get_attr(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _mapping_text(row: Mapping[str, Any], key: str) -> str | None:
    return _normalize_value(row.get(key))


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _normalize_value(value)
        if text:
            return text
    return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        text = _normalize_value(value)
        if not text:
            continue
        digits = re.sub(r"[^0-9.]", "", text)
        if not digits:
            continue
        try:
            return int(float(digits))
        except ValueError:
            continue
    return None


def _first_distance_m(*values: Any) -> int | None:
    for value in values:
        text = _normalize_value(value)
        if not text:
            continue
        normalized = text.replace(",", "").lower()
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", normalized)
        if match is None:
            continue
        amount = float(match.group(1))
        if "km" in normalized or "킬로" in normalized:
            amount *= 1000
        return int(round(amount))
    return None


def _first_duration_min(*values: Any) -> int | None:
    for value in values:
        text = _normalize_value(value)
        if not text:
            continue
        normalized = text.replace(",", "").lower()
        clock = re.fullmatch(r"([0-9]{1,2}):([0-9]{1,2})", normalized)
        if clock is not None:
            return int(clock.group(1)) * 60 + int(clock.group(2))

        hours = 0.0
        hour_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:시간|h|hr|hour)", normalized)
        if hour_match is not None:
            hours = float(hour_match.group(1))
        minute_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:분|min|minute)", normalized)
        if hour_match is not None or minute_match is not None:
            minutes = float(minute_match.group(1)) if minute_match is not None else 0.0
            return int(round(hours * 60 + minutes))

        try:
            return int(round(float(normalized)))
        except ValueError:
            continue
    return None


def _first_float(*values: Any) -> float | None:
    for value in values:
        text = _normalize_value(value)
        if not text:
            continue
        try:
            return float(text.replace(",", ""))
        except ValueError:
            continue
    return None


def _normalize_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = _WHITESPACE_RE.sub(" ", value).strip()
    else:
        text = str(value).strip()
    return text or None


def _normalize_search_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.lower()).strip()


def _normalize_url(value: str | None) -> str | None:
    text = _normalize_value(value)
    if text is None:
        return None
    if _HTTP_URL_RE.match(text):
        return text
    if "." in text and " " not in text:
        return f"https://{text}"
    return text


def _date_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _normalize_value(value)


def _hash_payload(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(_json_ready(payload), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, BaseGeometry):
        return value.__geo_interface__
    if hasattr(value, "model_dump"):
        return _json_ready(value.model_dump(mode="json"))
    return value


def _public_id(dataset_key: str, source_record_id: str) -> str:
    digest = hashlib.sha1(f"{dataset_key}:{source_record_id}".encode()).hexdigest()
    return f"od_{digest[:20]}"


def _point(longitude: Decimal, latitude: Decimal) -> WKTElement:
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def _wkt(geometry: BaseGeometry) -> WKTElement:
    return WKTElement(geometry.wkt, srid=4326)


def _decimal_from_float(value: float) -> Decimal:
    return Decimal(f"{value:.8f}")


def _resolve_collected_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(KST)
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def _iter_page_items(client: Any, fetch_page: Any) -> Iterable[Mapping[str, Any]]:
    for page in client.iter_pages(fetch_page, num_of_rows=100, max_pages=100):
        for item in page.items:
            if isinstance(item, Mapping):
                yield item
