"""kor_travel_map `openapi.user.json` 계약 드리프트 게이트 (T-210e).

kor_travel_map PR #794 merge commit의 전체 스냅샷을 byte-for-byte vendor하고 pinned SHA-256으로
수기 graft를 차단한다. 스냅샷(`tests/contract/kor-travel-map-openapi-user.json`)에 Pinvi user client
(`clients/kor_travel_map.py`) + 매핑(`api/v1/features.py _*_from_kor_travel_map`)이 의존하는 **경로·응답
필드**가 존재하는지 검증한다.

운영: kor_travel_map 스펙이 갱신되면 스냅샷을 교체(`docs/integrations/kor-travel-map-rest-api.md`
"드리프트 게이트" 절)하고 본 테스트를 돌린다. 우리 가정이 깨졌으면 여기서 실패 → client/매핑을
맞춘다. 수기 httpx client는 kor_travel_map 권고대로 유지하되, 본 게이트로 silent drift를 막는다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

_SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-user.json"
_UPSTREAM_COMMIT = "cf1f0bba6a2ea18f23eb647216236b84fc7b5a80"
_SNAPSHOT_SHA256 = "91b30f4011509c30d2ba8284fad8bf1c0dad695bfc5f05557bec0165124a119f"

# Pinvi user client(`clients/kor_travel_map.py`)가 호출하는 kor_travel_map 경로.
_CLIENT_PATHS = [
    "/v1/features/in-bounds",
    "/v1/features/nearby",
    "/v1/features/search",
    "/v1/features/{feature_id}",
    "/v1/features/{feature_id}/weather",
    "/v1/features/batch",
    "/v1/categories",
    "/v1/public/beaches",
    "/v1/public/beaches/map-markers",
    "/v1/public/beaches/{feature_id}",
    "/v1/public/festivals/monthly",
    "/v1/public/festivals/map-markers",
    "/v1/public/festivals/{feature_id}",
    # 큐레이션 import는 user 표면이 아니라 admin `/v1/admin/curated-features/{id}/detail-snapshot`을
    # 쓴다(ADR-049 — kor_travel_map PR #533이 public `*-copy` 표면을 폐지). user-contract gate 범위 밖.
]

_CLIENT_QUERY_PARAMETERS: dict[str, set[str]] = {
    "/v1/public/beaches": {
        "sido_code",
        "sigungu_code",
        "q",
        "page_size",
        "cursor",
    },
    "/v1/public/beaches/{feature_id}": set(),
}

_PUBLIC_API_KEY_SCHEME = {
    "type": "apiKey",
    "in": "header",
    "name": "X-Kor-Travel-Map-Api-Key",
}
_PUBLIC_API_KEY_SECURITY = [{"PublicApiKey": []}, {"ServiceToken": []}]

# 매핑(`features.py _*_from_kor_travel_map`)이 읽는 응답 필드 — 스키마별 필수 존재.
_SCHEMA_FIELDS: dict[str, set[str]] = {
    "FeatureSummary": {
        "feature_id",
        "kind",
        "name",
        "lon",
        "lat",
        "marker_color",
        "marker_icon",
        "status",
    },
    "ClusterSummary": {"cluster_key", "lon", "lat", "feature_count"},
    "FeatureDetailResponse": {
        "feature_id",
        "kind",
        "name",
        "lon",
        "lat",
        "address",
        "legal_dong_code",
        "sido_code",
        "sigungu_code",
        "marker_color",
        "marker_icon",
        "urls",
        "detail",
        "status",
        "updated_at",
    },
    "WeatherCardData": {"feature_id", "is_stale", "source_styles", "metrics"},
    "WeatherMetricOut": {"metric_key", "forecast_style", "value_number", "unit"},
    "CategorySummary": {"code", "label", "maki_icon", "path", "depth", "is_active", "sort_order"},
    "FeatureBatchData": {"found", "missing"},
    "BeachPublicView": {
        "feature_id",
        "display_name",
        "address",
        "source_providers",
        "updated_at",
        "lon",
        "lat",
        "road_address",
        "sido_code",
        "sigungu_code",
        "beach_width_m",
        "beach_length_m",
        "beach_material",
        "latest_water_quality",
        "upcoming_index_forecasts",
        "latest_weather",
    },
    "PublicBeachListData": {"items"},
    "FestivalPublicView": {
        "feature_id",
        "festival_name",
        "event_status",
        "address",
        "source_providers",
        "updated_at",
        "event_start_date",
        "event_end_date",
        "venue_name",
        "lon",
        "lat",
        "homepage_url",
    },
    "PublicFestivalMonth": {"year", "month", "count"},
    "PublicFestivalMonthlyData": {"months", "items"},
    "PublicMapMarker": {"feature_id", "name", "lon", "lat"},
    "PublicMapMarkerLayerData": {
        "layer_key",
        "display_name",
        "marker_icon",
        "marker_color",
        "items",
    },
}


def _spec() -> dict[str, Any]:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_is_kor_travel_map_user_surface() -> None:
    assert hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA256, (
        f"vendored openapi.user.json이 kor_travel_map {_UPSTREAM_COMMIT} 원본과 다름"
    )
    assert _spec()["info"]["title"] == "kor-travel-map-user"


def test_client_paths_exist_in_snapshot() -> None:
    paths = set(_spec()["paths"])
    missing = [p for p in _CLIENT_PATHS if p not in paths]
    assert not missing, (
        f"client가 의존하는 kor_travel_map 경로가 스냅샷에 없음(드리프트): {missing}"
    )


def _query_parameter_names(spec: dict[str, Any], path: str) -> set[str]:
    parameters = spec["paths"][path]["get"].get("parameters", [])
    return {parameter["name"] for parameter in parameters if parameter.get("in") == "query"}


def test_client_query_parameters_match_snapshot() -> None:
    spec = _spec()
    problems = {
        path: {
            "expected": sorted(expected),
            "actual": sorted(_query_parameter_names(spec, path)),
        }
        for path, expected in _CLIENT_QUERY_PARAMETERS.items()
        if _query_parameter_names(spec, path) != expected
    }
    assert not problems, f"client query 계약이 스냅샷과 다름(드리프트): {problems}"


def test_public_api_key_contract_is_header_only() -> None:
    spec = _spec()
    actual_scheme = spec["components"]["securitySchemes"].get("PublicApiKey")
    assert isinstance(actual_scheme, dict)
    assert {key: actual_scheme.get(key) for key in _PUBLIC_API_KEY_SCHEME} == (
        _PUBLIC_API_KEY_SCHEME
    )

    query_leaks = {
        path: sorted(
            {
                parameter["name"]
                for operation in spec["paths"][path].values()
                if isinstance(operation, dict)
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "query" and parameter.get("name") == "key"
            }
        )
        for path in _CLIENT_PATHS
    }
    assert not {path: names for path, names in query_leaks.items() if names}, (
        f"public API key가 client 경로의 URL query에 남아 있음: {query_leaks}"
    )

    security_problems = {
        path: operation.get("security")
        for path in _CLIENT_PATHS
        if path != "/v1/features/batch"
        for method, operation in spec["paths"][path].items()
        if method in {"get", "post"}
        if operation.get("security") != _PUBLIC_API_KEY_SECURITY
    }
    assert not security_problems, (
        f"public client 경로의 header security 계약이 다름: {security_problems}"
    )

    assert spec["paths"]["/v1/features/batch"]["post"].get("security") == [{"ServiceToken": []}]


def test_mapped_response_fields_exist_in_snapshot() -> None:
    schemas = _spec()["components"]["schemas"]
    problems: list[str] = []
    for schema_name, fields in _SCHEMA_FIELDS.items():
        props = set(schemas.get(schema_name, {}).get("properties", {}))
        gone = fields - props
        if gone:
            problems.append(f"{schema_name}: {sorted(gone)}")
    assert not problems, (
        f"매핑이 의존하는 kor_travel_map 응답 필드가 스냅샷에 없음(드리프트): {problems}"
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _find_live_spec_path(project_root: Path, override: str | None) -> Path | None:
    """표준 workspace sibling 또는 명시 override에서 Map user spec을 찾는다."""
    if override:
        return Path(override)
    for repo_name in (
        "kor-travel-map-codex",
        "kor-travel-map-claude",
        "kor-travel-map-antigravity",
        "kor-travel-map",
    ):
        repo = project_root.parent / repo_name
        for relative in (
            Path("packages/kor-travel-map-api/openapi.user.json"),
            Path("packages/kor-travel-map-admin/openapi.user.json"),
        ):
            candidate = repo / relative
            if candidate.exists():
                return candidate
    return None


def _live_spec_path() -> Path | None:
    """sibling `kor-travel-map` repo의 live 스펙 경로(있으면). env override 가능."""
    return _find_live_spec_path(
        _project_root(), os.environ.get("PINVI_KOR_TRAVEL_MAP_OPENAPI_USER_PATH")
    )


def test_live_spec_search_starts_at_repository_root() -> None:
    project_root = _project_root()
    assert (project_root / "AGENTS.md").is_file()
    assert (project_root / "apps/api/tests/unit").is_dir()


def test_live_spec_search_finds_standard_workspace_sibling(tmp_path: Path) -> None:
    project_root = tmp_path / "pinvi-codex"
    candidate = tmp_path / "kor-travel-map-codex" / "packages/kor-travel-map-api/openapi.user.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("{}\n", encoding="utf-8")

    assert _find_live_spec_path(project_root, None) == candidate


@pytest.mark.skipif(
    _live_spec_path() is None, reason="kor_travel_map repo 미존재(CI/타 환경) — 핀 신선도 검사 생략"
)
def test_vendored_snapshot_matches_live_kor_travel_map() -> None:
    """로컬 전용: vendored 문서 전체가 kor_travel_map live와 byte 단위로 같은지 확인."""
    live_path = _live_spec_path()
    assert live_path is not None
    assert _SNAPSHOT.read_bytes() == live_path.read_bytes(), (
        "vendored openapi.user.json 전체가 kor_travel_map live 원본과 다름"
    )


# --- T-VN-H07: PinVi 소비 curated surface의 필드 단위(required/type/enum) 계약 ---
#
# 위 게이트는 "경로/property 존재"만 고정한다(드리프트 회피 1단계). 아래 helper·상수·
# 테스트는 PinVi가 REST로 읽는 **공개 curated 응답 schema**를 vendored user-profile
# OpenAPI 스냅샷 기준으로 required 집합·JSON type·format·enum(및 discriminator const)
# 까지 고정한다. kor_travel_map 저장소 측 field-level contract(part ①,
# `test_export_openapi.py`)를 PinVi 소비 half로 미러링하는 T-VN-H07 part ②이다.
# 값을 명시 리터럴로 박아 실제 계약 드리프트에서 FAIL한다(non-tautological).
#
# 주: 위 `_CLIENT_PATHS` 주석의 큐레이션 import(admin `/v1/admin/curated-features/{id}/
# detail-snapshot`)와 달리, 아래 대상은 user-profile 표면의 공개 curated union
# (`/v1/curated-features`·`/v1/curations*`) 응답 schema다.


def _property_json_type(prop: dict[str, Any]) -> str:
    """생성 OpenAPI property의 primitive JSON type을 돌려준다.

    ``X | None`` 필드가 만드는 ``anyOf: [<schema>, {"type": "null"}]`` nullable
    shape를 벗겨내고, component 참조는 ``"$ref"``로 보고해 호출자가 필드별 JSON
    type을 정확히 고정할 수 있게 한다.
    """
    if "$ref" in prop:
        return "$ref"
    if "type" in prop:
        return str(prop["type"])
    branches = prop.get("anyOf")
    if isinstance(branches, list):
        non_null = [
            branch
            for branch in branches
            if isinstance(branch, dict) and branch.get("type") != "null"
        ]
        if len(non_null) == 1:
            only = non_null[0]
            if "$ref" in only:
                return "$ref"
            if "type" in only:
                return str(only["type"])
    raise AssertionError(f"cannot resolve JSON type for property: {prop!r}")


def _property_ref(prop: dict[str, Any]) -> str | None:
    """(nullable 포함) ``$ref`` property가 가리키는 schema 이름."""
    ref = prop.get("$ref")
    if not isinstance(ref, str):
        for branch in prop.get("anyOf", []):
            if isinstance(branch, dict) and isinstance(branch.get("$ref"), str):
                ref = branch["$ref"]
                break
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None


def _property_format(prop: dict[str, Any]) -> str | None:
    """(nullable 포함) property의 선언된 ``format``."""
    if "format" in prop:
        return str(prop["format"])
    for branch in prop.get("anyOf", []):
        if isinstance(branch, dict) and branch.get("type") != "null" and "format" in branch:
            return str(branch["format"])
    return None


def _one_of_refs(branches: list[dict[str, Any]]) -> set[str]:
    """oneOf 분기가 가리키는 component schema 이름 집합."""
    names: set[str] = set()
    for branch in branches:
        ref = branch.get("$ref")
        if isinstance(ref, str):
            names.add(ref.rsplit("/", 1)[-1])
    return names


def _assert_object_schema_contract(
    spec: dict[str, Any],
    name: str,
    *,
    required: set[str],
    types: dict[str, str],
    formats: dict[str, str] | None = None,
    enums: dict[str, set[str]] | None = None,
    consts: dict[str, str] | None = None,
    refs: dict[str, str] | None = None,
) -> None:
    """vendored object schema 하나의 필드 단위 계약을 검증한다.

    exact property 집합, exact ``required`` 집합, 필드별 JSON type, ``format``,
    enum 값 집합, discriminator ``const``, ``$ref`` 대상을 모두 고정한다
    (T-VN-H07 PinVi 소비 half — Map part ① 미러).
    """
    schema = spec["components"]["schemas"][name]
    assert schema.get("type") == "object", name
    assert schema.get("additionalProperties") is False, name
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == set(types), (name, set(properties) ^ set(types))
    observed_required = set(schema.get("required", []))
    assert observed_required == required, (name, observed_required ^ required)
    for field, expected in types.items():
        assert _property_json_type(properties[field]) == expected, (
            name,
            field,
            _property_json_type(properties[field]),
        )
    for field, fmt in (formats or {}).items():
        assert _property_format(properties[field]) == fmt, (name, field)
    for field, values in (enums or {}).items():
        enum = properties[field].get("enum")
        assert isinstance(enum, list), (name, field, enum)
        assert set(enum) == values, (name, field, enum)
    for field, value in (consts or {}).items():
        assert properties[field].get("const") == value, (name, field)
    for field, target in (refs or {}).items():
        assert _property_ref(properties[field]) == target, (name, field)


# PinVi curated_features union variant가 공유하는 base 필드 계약.
_CURATED_FEATURE_BASE_TYPES: dict[str, str] = {
    "curated_feature_id": "string",
    "theme_slug": "string",
    "theme_name": "string",
    "theme_group": "string",
    "feature_id": "string",
    "feature_name": "string",
    "feature_category": "string",
    "lon": "number",
    "lat": "number",
    "sido_code": "string",
    "sigungu_code": "string",
    "legal_dong_code": "string",
    "address": "$ref",
    "source_name": "string",
    "source_url": "string",
    "display_title": "string",
    "display_summary": "string",
    "curation_relation": "string",
    "reuse_policy": "string",
    "content_version": "integer",
    "updated_at": "string",
}
_CURATED_FEATURE_BASE_REQUIRED: set[str] = {
    "curated_feature_id",
    "theme_slug",
    "theme_name",
    "theme_group",
    "feature_id",
    "feature_name",
    "feature_category",
    "address",
    "source_name",
    "curation_relation",
    "reuse_policy",
    "content_version",
    "updated_at",
}
_CURATED_FEATURE_BASE_FORMATS: dict[str, str] = {
    "updated_at": "date-time",
    "source_url": "uri",
}
# feature_kind 판별값 → (variant schema, detail schema | None). price/weather는 detail=null.
_CURATED_FEATURE_VARIANTS: dict[str, tuple[str, str | None]] = {
    "place": ("PublicCuratedPlaceFeatureView", "PublicCuratedPlaceDetail"),
    "event": ("PublicCuratedEventFeatureView", "PublicCuratedEventDetail"),
    "notice": ("PublicCuratedNoticeFeatureView", "PublicCuratedNoticeDetail"),
    "area": ("PublicCuratedAreaFeatureView", "PublicCuratedAreaDetail"),
    "route": ("PublicCuratedRouteFeatureView", "PublicCuratedRouteDetail"),
    "price": ("PublicCuratedPriceFeatureView", None),
    "weather": ("PublicCuratedWeatherFeatureView", None),
}
_CURATED_DETAIL_CONTRACTS: dict[str, dict[str, Any]] = {
    "PublicCuratedPlaceDetail": {
        "required": {"feature_id"},
        "types": {
            "feature_id": "string",
            "place_kind": "string",
            "phones": "array",
            "reviews_link": "$ref",
            "business_hours": "$ref",
            "facility_info": "$ref",
            "license_date": "string",
            "biz_number": "string",
        },
        "formats": {"license_date": "date"},
    },
    "PublicCuratedEventDetail": {
        "required": {"feature_id"},
        "types": {
            "feature_id": "string",
            "event_kind": "string",
            "starts_on": "string",
            "ends_on": "string",
            "timezone": "string",
            "opening_hours": "$ref",
            "venue_name": "string",
            "tel": "string",
            "content_id": "string",
            "content_type_id": "string",
            "area_code": "string",
            "sigungu_code": "string",
        },
        "formats": {"starts_on": "date", "ends_on": "date"},
    },
    "PublicCuratedNoticeDetail": {
        "required": {"feature_id", "notice_type"},
        "types": {
            "feature_id": "string",
            "notice_type": "string",
            "severity": "integer",
            "valid_start_time": "string",
            "valid_end_time": "string",
            "source_agency": "string",
            "officer_name": "string",
        },
        "formats": {
            "valid_start_time": "date-time",
            "valid_end_time": "date-time",
        },
    },
    "PublicCuratedAreaDetail": {
        "required": {"feature_id"},
        "types": {
            "feature_id": "string",
            "area_kind": "string",
            "area_square_meters": "number",
            "boundary_source": "string",
            "regulation_scope": "string",
            "administrative_office": "string",
            "description": "string",
        },
    },
    "PublicCuratedRouteDetail": {
        "required": {"feature_id"},
        "types": {
            "feature_id": "string",
            "route_type": "string",
            "geometry_source": "string",
            "geometry_status": "string",
            "total_distance_meters": "number",
            "expected_duration_minutes": "integer",
            "difficulty": "string",
            "begin_name": "string",
            "begin_address": "string",
            "end_name": "string",
            "end_address": "string",
        },
    },
}


def test_public_curated_feature_schemas_pin_required_types_and_enums() -> None:
    """PinVi가 소비하는 curated feature union을 required/type/const(kind) 단위로 고정."""
    spec = _spec()
    schemas = spec["components"]["schemas"]

    union = schemas["PublicCuratedFeatureView"]
    assert union["discriminator"]["propertyName"] == "feature_kind"
    assert union["discriminator"]["mapping"] == {
        kind: f"#/components/schemas/{variant}"
        for kind, (variant, _detail) in _CURATED_FEATURE_VARIANTS.items()
    }
    assert _one_of_refs(union["oneOf"]) == {
        variant for variant, _detail in _CURATED_FEATURE_VARIANTS.values()
    }

    for kind, (variant, detail) in _CURATED_FEATURE_VARIANTS.items():
        types = {**_CURATED_FEATURE_BASE_TYPES, "feature_kind": "string"}
        required = _CURATED_FEATURE_BASE_REQUIRED | {"feature_kind"}
        refs = {"address": "PublicCuratedAddress"}
        if detail is None:
            types["detail"] = "null"
        else:
            types["detail"] = "$ref"
            required = required | {"detail"}
            refs["detail"] = detail
        _assert_object_schema_contract(
            spec,
            variant,
            required=required,
            types=types,
            formats=_CURATED_FEATURE_BASE_FORMATS,
            consts={"feature_kind": kind},
            refs=refs,
        )

    for detail_name, contract in _CURATED_DETAIL_CONTRACTS.items():
        _assert_object_schema_contract(
            spec,
            detail_name,
            required=contract["required"],
            types=contract["types"],
            formats=contract.get("formats"),
        )


def test_public_curation_collection_item_group_pin_required_types_and_enums() -> None:
    """공개 curation collection/item/feature-group schema를 required/type/enum 고정."""
    spec = _spec()

    _assert_object_schema_contract(
        spec,
        "PublicCurationCollectionView",
        required={
            "collection_id",
            "collection_key",
            "theme_id",
            "theme_slug",
            "theme_name",
            "theme_group",
            "source_id",
            "provider",
            "dataset_key",
            "source_name",
            "source_url",
            "title",
            "edition_key",
            "description",
            "status",
            "visibility",
            "item_count",
            "created_at",
            "updated_at",
            "archived_at",
        },
        types={
            "collection_id": "string",
            "collection_key": "string",
            "theme_id": "string",
            "theme_slug": "string",
            "theme_name": "string",
            "theme_group": "string",
            "source_id": "string",
            "provider": "string",
            "dataset_key": "string",
            "source_name": "string",
            "source_url": "string",
            "title": "string",
            "edition_key": "string",
            "description": "string",
            "status": "string",
            "visibility": "string",
            "item_count": "integer",
            "created_at": "string",
            "updated_at": "string",
            "archived_at": "string",
        },
        formats={
            "collection_id": "uuid",
            "theme_id": "uuid",
            "source_id": "uuid",
            "created_at": "date-time",
            "updated_at": "date-time",
            "archived_at": "date-time",
        },
        enums={
            "status": {"draft", "published", "archived"},
            "visibility": {"admin_only", "public"},
        },
    )

    _assert_object_schema_contract(
        spec,
        "PublicCurationItemView",
        required={
            "curation_item_id",
            "collection_id",
            "collection_key",
            "title",
            "edition_key",
            "theme_slug",
            "theme_name",
            "theme_group",
            "provider",
            "dataset_key",
            "source_name",
            "source_url",
            "feature_id",
            "feature_name",
            "feature_kind",
            "feature_category",
            "lon",
            "lat",
            "address",
            "external_item_id",
            "place_name",
            "address_hint",
            "status",
            "sort_order",
            "item_title",
            "item_summary",
            "curation_relation",
            "reuse_policy",
            "created_at",
            "updated_at",
            "archived_at",
        },
        types={
            "curation_item_id": "string",
            "collection_id": "string",
            "collection_key": "string",
            "title": "string",
            "edition_key": "string",
            "theme_slug": "string",
            "theme_name": "string",
            "theme_group": "string",
            "provider": "string",
            "dataset_key": "string",
            "source_name": "string",
            "source_url": "string",
            "feature_id": "string",
            "feature_name": "string",
            "feature_kind": "string",
            "feature_category": "string",
            "lon": "number",
            "lat": "number",
            "address": "object",
            "external_item_id": "string",
            "place_name": "string",
            "address_hint": "string",
            "status": "string",
            "sort_order": "integer",
            "item_title": "string",
            "item_summary": "string",
            "curation_relation": "string",
            "reuse_policy": "string",
            "created_at": "string",
            "updated_at": "string",
            "archived_at": "string",
        },
        formats={
            "curation_item_id": "uuid",
            "collection_id": "uuid",
            "created_at": "date-time",
            "updated_at": "date-time",
            "archived_at": "date-time",
        },
        enums={
            "status": {"candidate", "included", "rejected", "archived"},
            "curation_relation": {
                "primary_stop",
                "food_stop",
                "cafe_stop",
                "bookstore_stop",
                "nearby_option",
                "accessibility_support",
                "pet_support",
                "family_support",
                "theme_area_anchor",
            },
            "reuse_policy": {"allowed", "blocked", "manual_review"},
        },
    )

    _assert_object_schema_contract(
        spec,
        "CurationFeatureView",
        required={
            "feature_id",
            "name",
            "kind",
            "category",
            "lon",
            "lat",
            "address",
            "status",
        },
        types={
            "feature_id": "string",
            "name": "string",
            "kind": "string",
            "category": "string",
            "lon": "number",
            "lat": "number",
            "address": "object",
            "status": "string",
        },
    )

    _assert_object_schema_contract(
        spec,
        "FeatureCurationGroupView",
        required={"feature", "curations", "curation_count"},
        types={
            "feature": "$ref",
            "curations": "array",
            "curation_count": "integer",
        },
        refs={"feature": "CurationFeatureView"},
    )
    group_curations = spec["components"]["schemas"]["FeatureCurationGroupView"]["properties"][
        "curations"
    ]["items"]
    assert group_curations == {"$ref": "#/components/schemas/PublicCurationItemView"}
