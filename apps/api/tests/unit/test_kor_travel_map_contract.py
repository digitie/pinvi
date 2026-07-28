"""kor_travel_map `openapi.user.json` 계약 드리프트 게이트 (T-210e).

kor_travel_map main(`8880c29b`, Map PR #814/T-VN-H07A 포함)의 전체 스냅샷을 byte-for-byte
vendor하고 pinned SHA-256으로 수기 graft를 차단한다. 스냅샷(`tests/contract/kor-travel-map-openapi-user.json`)에 Pinvi user client
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
_UPSTREAM_COMMIT = "8880c29bdfbcd7805c89eafe0645f3c447f27530"
_SNAPSHOT_SHA256 = "0a7f16847ef7620c168cac61b4a7221747ede747b19d8531c4345d5add4b2116"

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


# --- T-VN-H07B: PinVi가 실제로 읽는 필드의 typed consumer contract ---
#
# main의 `test_mapped_response_fields_exist_in_snapshot`은 "필드 존재"만 본다. 아래는 같은
# `_SCHEMA_FIELDS` 집합(= user client `clients/kor_travel_map.py` + 매핑
# `api/v1/features.py _*_from_kor_travel_map`이 실제로 읽는 필드)에 대해 JSON type·format·
# enum·array item·required/nullable까지 vendored 스냅샷 기준으로 고정한다.
#
# **exact property 집합은 의도적으로 고정하지 않는다.** producer(Map) 쪽 exact 집합·
# additionalProperties 고정은 T-VN-H07A(Map PR #814)가 소유한다. consumer가 같은 집합을 다시
# 고정하면 Map의 무해한 additive 변경마다 PinVi가 false-red가 된다 — 실제로 Map migration
# 0066이 `PublicCurationItemView.external_component_id`를 추가했을 때가 그 사례였다. consumer
# 계약은 "우리가 읽는 필드의 shape"만 고정해 breaking change에만 반응한다.
#
# 공개 curated 표면(`PublicCurated*`/`PublicCuration*`)은 여기서 다루지 않는다. PinVi user
# client는 해당 경로를 호출하지 않으며(`_CLIENT_PATHS` 주석·ADR-049 — Map PR #533이 public
# `*-copy` 표면 폐지), 실제 큐레이션 런타임 표면은 admin
# `/v1/admin/curated-features/{id}/detail-snapshot`이라 그 필드레벨 계약은 T-VN-H07D(#815)가
# 소유한다.

_CONSUMED_FIELD_CONTRACTS: dict[str, dict[str, dict[str, Any]]] = {
    "FeatureSummary": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "kind": {"type": "string", "required": True, "nullable": False},
        "name": {"type": "string", "required": True, "nullable": False},
        "status": {"type": "string", "required": True, "nullable": False},
        # 좌표는 required이지만 nullable — 매핑이 None을 반드시 처리해야 한다.
        "lon": {"type": "number", "required": True, "nullable": True},
        "lat": {"type": "number", "required": True, "nullable": True},
        "marker_color": {"type": "string", "required": False, "nullable": True},
        "marker_icon": {"type": "string", "required": False, "nullable": True},
    },
    "ClusterSummary": {
        "cluster_key": {"type": "string", "required": True, "nullable": False},
        "feature_count": {"type": "integer", "required": True, "nullable": False},
        "lon": {"type": "number", "required": True, "nullable": False},
        "lat": {"type": "number", "required": True, "nullable": False},
    },
    "FeatureDetailResponse": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "kind": {"type": "string", "required": True, "nullable": False},
        "name": {"type": "string", "required": True, "nullable": False},
        "status": {"type": "string", "required": True, "nullable": False},
        "address": {"type": "object", "required": True, "nullable": False},
        "detail": {"type": "object", "required": True, "nullable": False},
        "urls": {"type": "object", "required": True, "nullable": False},
        "updated_at": {
            "type": "string",
            "format": "date-time",
            "required": True,
            "nullable": False,
        },
        "lon": {"type": "number", "required": False, "nullable": True},
        "lat": {"type": "number", "required": False, "nullable": True},
        "legal_dong_code": {"type": "string", "required": False, "nullable": True},
        "sido_code": {"type": "string", "required": False, "nullable": True},
        "sigungu_code": {"type": "string", "required": False, "nullable": True},
        "marker_color": {"type": "string", "required": False, "nullable": True},
        "marker_icon": {"type": "string", "required": False, "nullable": True},
    },
    "WeatherCardData": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "is_stale": {"type": "boolean", "required": True, "nullable": False},
        "source_styles": {
            "type": "array",
            "items_type": "string",
            "required": True,
            "nullable": False,
        },
        "metrics": {
            "type": "array",
            "items_ref": "WeatherMetricOut",
            "required": True,
            "nullable": False,
        },
    },
    "WeatherMetricOut": {
        "metric_key": {"type": "string", "required": True, "nullable": False},
        "forecast_style": {"type": "string", "required": True, "nullable": False},
        "value_number": {"type": "number", "required": False, "nullable": True},
        "unit": {"type": "string", "required": False, "nullable": True},
    },
    "CategorySummary": {
        "code": {"type": "string", "required": True, "nullable": False},
        "label": {"type": "string", "required": True, "nullable": False},
        "maki_icon": {"type": "string", "required": True, "nullable": False},
        "path": {
            "type": "array",
            "items_type": "string",
            "required": True,
            "nullable": False,
        },
        "depth": {"type": "integer", "required": True, "nullable": False},
        "is_active": {"type": "boolean", "required": True, "nullable": False},
        "sort_order": {"type": "integer", "required": True, "nullable": False},
    },
    "FeatureBatchData": {
        # T-VN-11이 5-state로 바꿀 표면 — 현재 계약은 found map + missing 목록이다.
        "found": {"type": "object", "required": True, "nullable": False},
        "missing": {
            "type": "array",
            "items_type": "string",
            "required": True,
            "nullable": False,
        },
    },
    "BeachPublicView": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "display_name": {"type": "string", "required": True, "nullable": False},
        "address": {"type": "object", "required": True, "nullable": False},
        "source_providers": {
            "type": "array",
            "items_type": "string",
            "required": True,
            "nullable": False,
        },
        "updated_at": {
            "type": "string",
            "format": "date-time",
            "required": True,
            "nullable": False,
        },
        "lon": {"type": "number", "required": False, "nullable": True},
        "lat": {"type": "number", "required": False, "nullable": True},
        "road_address": {"type": "string", "required": False, "nullable": True},
        "sido_code": {"type": "string", "required": False, "nullable": True},
        "sigungu_code": {"type": "string", "required": False, "nullable": True},
        "beach_width_m": {"type": "number", "required": False, "nullable": True},
        "beach_length_m": {"type": "number", "required": False, "nullable": True},
        "beach_material": {"type": "string", "required": False, "nullable": True},
        "latest_water_quality": {"type": "object", "required": False, "nullable": True},
        "latest_weather": {"type": "object", "required": False, "nullable": True},
        "upcoming_index_forecasts": {
            "type": "array",
            "items_type": "object",
            "required": False,
            "nullable": False,
        },
    },
    "PublicBeachListData": {
        "items": {
            "type": "array",
            "items_ref": "BeachPublicView",
            "required": True,
            "nullable": False,
        },
    },
    "FestivalPublicView": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "festival_name": {"type": "string", "required": True, "nullable": False},
        # 매핑이 분기하는 상태 값 — enum 축소/확장은 PinVi breaking change다.
        "event_status": {
            "type": "string",
            "enum": {"scheduled", "ongoing", "ended", "unknown"},
            "required": True,
            "nullable": False,
        },
        "address": {"type": "object", "required": True, "nullable": False},
        "source_providers": {
            "type": "array",
            "items_type": "string",
            "required": True,
            "nullable": False,
        },
        "updated_at": {
            "type": "string",
            "format": "date-time",
            "required": True,
            "nullable": False,
        },
        "event_start_date": {
            "type": "string",
            "format": "date",
            "required": False,
            "nullable": True,
        },
        "event_end_date": {
            "type": "string",
            "format": "date",
            "required": False,
            "nullable": True,
        },
        "venue_name": {"type": "string", "required": False, "nullable": True},
        "lon": {"type": "number", "required": False, "nullable": True},
        "lat": {"type": "number", "required": False, "nullable": True},
        "homepage_url": {"type": "string", "required": False, "nullable": True},
    },
    "PublicFestivalMonth": {
        "year": {"type": "integer", "required": True, "nullable": False},
        "month": {"type": "integer", "required": True, "nullable": False},
        "count": {"type": "integer", "required": True, "nullable": False},
    },
    "PublicFestivalMonthlyData": {
        "months": {
            "type": "array",
            "items_ref": "PublicFestivalMonth",
            "required": True,
            "nullable": False,
        },
        "items": {
            "type": "array",
            "items_ref": "FestivalPublicView",
            "required": True,
            "nullable": False,
        },
    },
    "PublicMapMarker": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "name": {"type": "string", "required": True, "nullable": False},
        "lon": {"type": "number", "required": True, "nullable": False},
        "lat": {"type": "number", "required": True, "nullable": False},
    },
    "PublicMapMarkerLayerData": {
        # 지도 레이어 분기 키 — 값 집합이 곧 PinVi가 처리하는 레이어 종류다.
        "layer_key": {
            "type": "string",
            "enum": {"beach", "festival"},
            "required": True,
            "nullable": False,
        },
        "display_name": {"type": "string", "required": True, "nullable": False},
        "marker_icon": {"type": "string", "required": True, "nullable": False},
        "marker_color": {"type": "string", "required": True, "nullable": False},
        "items": {
            "type": "array",
            "items_ref": "PublicMapMarker",
            "required": True,
            "nullable": False,
        },
    },
}


def _resolve_property(prop: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """``X | None``이 만드는 ``anyOf`` nullable shape를 벗겨 (실제 schema, nullable)."""
    branches = prop.get("anyOf")
    if not isinstance(branches, list):
        return prop, False
    non_null = [b for b in branches if isinstance(b, dict) and b.get("type") != "null"]
    nullable = any(isinstance(b, dict) and b.get("type") == "null" for b in branches)
    assert len(non_null) == 1, f"다중 non-null anyOf는 consumer 계약 대상이 아님: {prop!r}"
    return non_null[0], nullable


def _assert_consumed_field(
    spec: dict[str, Any], schema_name: str, field: str, expected: dict[str, Any]
) -> None:
    """PinVi가 읽는 필드 하나의 shape를 스냅샷 기준으로 고정한다."""
    schema = spec["components"]["schemas"][schema_name]
    properties = schema["properties"]
    where = f"{schema_name}.{field}"
    assert field in properties, f"{where}: 스냅샷에 없음"
    resolved, nullable = _resolve_property(properties[field])

    assert resolved.get("type") == expected["type"], (where, "type", resolved.get("type"))
    assert nullable is expected["nullable"], (where, "nullable", nullable)
    is_required = field in set(schema.get("required", []))
    assert is_required is expected["required"], (where, "required", is_required)

    if "format" in expected:
        assert resolved.get("format") == expected["format"], (
            where,
            "format",
            resolved.get("format"),
        )
    if "enum" in expected:
        enum = resolved.get("enum")
        assert isinstance(enum, list), (where, "enum 아님", enum)
        assert set(enum) == expected["enum"], (where, "enum", enum)
    if "items_type" in expected:
        assert resolved["items"].get("type") == expected["items_type"], (
            where,
            "items.type",
            resolved.get("items"),
        )
    if "items_ref" in expected:
        ref = str(resolved["items"].get("$ref", ""))
        assert ref.rsplit("/", 1)[-1] == expected["items_ref"], (where, "items.$ref", ref)


def test_consumed_field_contract_covers_exactly_the_mapped_fields() -> None:
    """계약 표와 매핑 의존 필드 목록이 서로 드리프트하지 않게 한다.

    매핑이 새 필드를 읽기 시작하면 ``_SCHEMA_FIELDS``에 추가되는데, 그때 타입 계약도 함께
    적어야 이 테스트가 통과한다(존재 검사만 하고 shape를 비워두는 경로를 막는다).
    """
    assert set(_CONSUMED_FIELD_CONTRACTS) == set(_SCHEMA_FIELDS)
    for schema_name, fields in _SCHEMA_FIELDS.items():
        assert set(_CONSUMED_FIELD_CONTRACTS[schema_name]) == fields, schema_name


def test_consumed_response_fields_pin_types_formats_and_enums() -> None:
    """PinVi가 읽는 모든 필드의 type/format/enum/item/required/nullable을 고정한다."""
    spec = _spec()
    for schema_name, fields in _CONSUMED_FIELD_CONTRACTS.items():
        for field, expected in fields.items():
            _assert_consumed_field(spec, schema_name, field, expected)
