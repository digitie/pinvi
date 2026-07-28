"""kor_travel_map **admin** detail-snapshot 계약 드리프트 게이트 (T-VN-H07D, map#815).

`test_kor_travel_map_contract.py`(T-210e/T-VN-H07B)가 **user** 표면을 덮는 반면, Pinvi의 큐레이션
import 런타임은 admin `GET /v1/admin/curated-features/{id}/detail-snapshot`을 쓴다
(`clients/kor_travel_map_admin.py::get_curated_detail_snapshot` →
`services/notice_plan.py::import_kor_travel_map_curated_feature`). 이 표면은 지금까지 어떤
계약 게이트도 없었다.

vendored 정본은 Map full 스펙(1 MB+) 전체가 아니라 **해당 경로와 응답 스키마의 전이적 폐포**만
잘라낸 subset이다(`scripts/vendor_kor_travel_map_admin_snapshot.py`가 결정적으로 추출). 무관한
Map 변경마다 diff가 나지 않으면서 계약 회귀는 그대로 잡는다.

**freshness**: 추출이 결정적이므로 CI가 Map을 핀 커밋으로 체크아웃해 같은 스크립트를 다시 돌리고
byte 비교한다(`.github/workflows/api.yml`의 `contract-freshness`). 과거처럼 sibling 체크아웃이
없다고 skip되어 green이 되는 경로를 없앤다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

_SNAPSHOT = (
    Path(__file__).resolve().parent.parent
    / "contract"
    / "kor-travel-map-openapi-admin-detail-snapshot.json"
)
# 추출 원본 — kor-travel-map main. 갱신 절차는 docs/integrations/kor-travel-map-rest-api.md §8.
_UPSTREAM_COMMIT = "5c0e0cae0cdb6009eb81c7c9030dcf5baf2719a2"
_SNAPSHOT_SHA256 = "c28608480f6b52f06297c433ca84beaa21a6bd85b845fd570483887fba710ee3"

# Map 문서 경로. Pinvi가 호출하는 것은 같은 핸들러의 alias(`/v1/admin/curated-features/...`)이며
# `include_in_schema=False`라 스펙에 없다 — alias 존재 자체는 Map 쪽
# `test_admin_curated_snapshot_contract.py`가 라우트 등록 수준에서 고정한다.
_SNAPSHOT_PATH = "/v1/admin/features/curated/{curated_feature_id}/detail-snapshot"
_PINVI_CLIENT_PATH = "/v1/admin/curated-features/{curated_feature_id}/detail-snapshot"

# Pinvi가 실제로 읽는 필드만 고정한다(consumer 계약 — producer의 무해한 additive 변경에
# false-red가 나지 않게 exact property 집합은 고정하지 않는다. exact 집합은 Map 쪽 소유).
#   snapshot   : services/notice_plan.py:695-780
#   content    : title/category/summary/destination_name/region_code
#   source     : source_name/provider
#   theme      : theme_slug
#   item       : curated_feature_item_id/day_index/sort_order/feature_id/memo/feature_snapshot
#   feature_snapshot: name/lon/lat/address (services/admin_pois.py 추출기 + api/v1/search.py SQL)
_CONSUMED_FIELD_CONTRACTS: dict[str, dict[str, dict[str, Any]]] = {
    "CuratedFeatureDetailSnapshotView": {
        "curated_feature_id": {"type": "string", "required": True, "nullable": False},
        "version": {"type": "integer", "required": True, "nullable": False},
        "etag": {"type": "string", "required": True, "nullable": False},
        "theme": {"type": "$ref", "ref": "CuratedFeatureDetailThemeView", "required": True, "nullable": False},
        "content": {"type": "$ref", "ref": "CuratedFeatureDetailContentView", "required": True, "nullable": False},
        "source": {"type": "$ref", "ref": "CuratedFeatureDetailSourceView", "required": True, "nullable": False},
        "items": {"type": "array", "items_ref": "CuratedFeatureDetailItemView", "required": True, "nullable": False},
    },
    "CuratedFeatureDetailThemeView": {
        "theme_slug": {"type": "string", "required": True, "nullable": False},
    },
    "CuratedFeatureDetailContentView": {
        "title": {"type": "string", "required": True, "nullable": False},
        "category": {"type": "string", "required": True, "nullable": False},
        "summary": {"type": "string", "required": True, "nullable": True},
        "destination_name": {"type": "string", "required": True, "nullable": True},
        "region_code": {"type": "string", "required": True, "nullable": True},
    },
    "CuratedFeatureDetailSourceView": {
        "source_name": {"type": "string", "required": True, "nullable": False},
        "provider": {"type": "string", "required": True, "nullable": False},
    },
    "CuratedFeatureDetailItemView": {
        "curated_feature_item_id": {"type": "string", "required": True, "nullable": False},
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "sort_order": {"type": "integer", "required": True, "nullable": False},
        "day_index": {"type": "integer", "required": True, "nullable": True},
        "memo": {"type": "string", "required": True, "nullable": True},
        "feature_snapshot": {
            "type": "$ref",
            "ref": "CuratedFeatureDetailFeatureSnapshotView",
            "required": True,
            "nullable": False,
        },
    },
    "CuratedFeatureDetailFeatureSnapshotView": {
        "name": {"type": "string", "required": True, "nullable": False},
        "lon": {"type": "number", "required": True, "nullable": True},
        "lat": {"type": "number", "required": True, "nullable": True},
        "address": {"type": "object", "required": True, "nullable": False},
    },
}


def _spec() -> dict[str, Any]:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def _resolve_property(prop: dict[str, Any], where: str) -> tuple[dict[str, Any], bool]:
    """nullable wrapper(anyOf / OpenAPI 3.1 list-form type)를 벗겨 ``(schema, nullable)``."""
    branches = prop.get("anyOf")
    if isinstance(branches, list):
        non_null = [b for b in branches if isinstance(b, dict) and b.get("type") != "null"]
        nullable = any(isinstance(b, dict) and b.get("type") == "null" for b in branches)
        assert len(non_null) == 1, f"{where}: union으로 넓어짐(consumer breaking) — {prop!r}"
        return non_null[0], nullable
    declared = prop.get("type")
    if isinstance(declared, list):
        non_null_types = [t for t in declared if t != "null"]
        assert len(non_null_types) == 1, f"{where}: type union으로 넓어짐 — {declared!r}"
        return {**prop, "type": non_null_types[0]}, "null" in declared
    return prop, False


def _assert_consumed_field(
    spec: dict[str, Any], schema_name: str, field: str, expected: dict[str, Any]
) -> None:
    schema = spec["components"]["schemas"][schema_name]
    properties = schema["properties"]
    where = f"{schema_name}.{field}"
    assert field in properties, f"{where}: vendored 스냅샷에 없음(consumer breaking)"
    resolved, nullable = _resolve_property(properties[field], where)

    if expected["type"] == "$ref":
        ref = str(resolved.get("$ref", "")).rsplit("/", 1)[-1]
        assert ref == expected["ref"], (where, "$ref", ref)
    else:
        assert resolved.get("type") == expected["type"], (where, "type", resolved.get("type"))
    assert nullable is expected["nullable"], (where, "nullable", nullable)
    is_required = field in set(schema.get("required", []))
    assert is_required is expected["required"], (where, "required", is_required)
    if "items_ref" in expected:
        items = resolved.get("items")
        assert isinstance(items, dict), (where, "array items 아님")
        ref = str(items.get("$ref", "")).rsplit("/", 1)[-1]
        assert ref == expected["items_ref"], (where, "items.$ref", ref)


def test_admin_snapshot_subset_is_pinned() -> None:
    assert hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA256, (
        f"vendored admin subset이 kor_travel_map {_UPSTREAM_COMMIT} 추출 결과와 다름"
    )
    spec = _spec()
    assert _SNAPSHOT_PATH in spec["paths"]


def test_admin_snapshot_response_binds_pinned_view() -> None:
    """경로 → 200 응답 → `data` 컨테이너 결합을 고정한다(필드 계약이 dangling하지 않게)."""
    spec = _spec()
    operation = spec["paths"][_SNAPSHOT_PATH]["get"]
    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    response_name = response_ref.rsplit("/", 1)[-1]
    assert response_name == "CuratedFeatureDetailSnapshotResponse"
    data_property = spec["components"]["schemas"][response_name]["properties"]["data"]
    resolved, _nullable = _resolve_property(data_property, f"{response_name}.data")
    assert (
        str(resolved.get("$ref", "")).rsplit("/", 1)[-1] == "CuratedFeatureDetailSnapshotView"
    )


def test_consumed_admin_snapshot_fields_pin_types_and_nullability() -> None:
    """Pinvi curated import가 읽는 필드의 shape를 vendored 스냅샷 기준으로 고정한다."""
    spec = _spec()
    for schema_name, fields in _CONSUMED_FIELD_CONTRACTS.items():
        for field, expected in fields.items():
            _assert_consumed_field(spec, schema_name, field, expected)


def test_client_calls_the_alias_path_of_the_pinned_operation() -> None:
    """client가 호출하는 경로 문자열이 계약 대상 operation의 alias와 일치하는지 고정한다.

    alias는 Map에서 `include_in_schema=False`라 스펙에 없다. 문자열이 조용히 바뀌면 404가 되므로
    client 소스의 실제 경로와 여기 기록한 alias를 대조한다.
    """
    client_source = (
        Path(__file__).resolve().parents[2] / "app" / "clients" / "kor_travel_map_admin.py"
    ).read_text(encoding="utf-8")
    literal = _PINVI_CLIENT_PATH.replace("{curated_feature_id}", "{curated_feature_id}")
    assert literal in client_source, (
        "admin client의 detail-snapshot 경로가 계약에 기록된 alias와 다르다"
    )


@pytest.mark.parametrize(
    "schema_name",
    sorted(_CONSUMED_FIELD_CONTRACTS),
)
def test_consumed_schemas_exist_in_subset(schema_name: str) -> None:
    """계약 대상 스키마가 vendored subset에 실제로 들어 있는지(추출 누락 방지)."""
    assert schema_name in _spec()["components"]["schemas"]
