"""kor_travel_map `openapi.user.json` 계약 드리프트 게이트 (T-210e).

vendor된 스냅샷(`tests/contract/kor-travel-map-openapi-user.json`)에 Pinvi user client
(`clients/kor_travel_map.py`) + 매핑(`api/v1/features.py _*_from_kor_travel_map`)이 의존하는 **경로·응답
필드**가 존재하는지 검증한다.

운영: kor_travel_map 스펙이 갱신되면 스냅샷을 교체(`docs/integrations/kor-travel-map-rest-api.md`
"드리프트 게이트" 절)하고 본 테스트를 돌린다. 우리 가정이 깨졌으면 여기서 실패 → client/매핑을
맞춘다. 수기 httpx client는 kor_travel_map 권고대로 유지하되, 본 게이트로 silent drift를 막는다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

_SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-user.json"

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
        "key",
    },
    "/v1/public/beaches/{feature_id}": {"key"},
}

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


def _live_spec_path() -> Path | None:
    """sibling `kor-travel-map` repo의 live 스펙 경로(있으면). env override 가능."""
    override = os.environ.get("PINVI_KOR_TRAVEL_MAP_OPENAPI_USER_PATH")
    if override:
        return Path(override)
    repo_root = Path(__file__).resolve().parents[3]  # apps/api/tests/unit → pinvi-claude
    for repo_name in ("kor-travel-map-codex", "kor-travel-map"):
        repo = repo_root.parent / repo_name
        for relative in (
            Path("packages/kor-travel-map-api/openapi.user.json"),
            Path("packages/kor-travel-map-admin/openapi.user.json"),
        ):
            candidate = repo / relative
            if candidate.exists():
                return candidate
    return None


@pytest.mark.skipif(
    _live_spec_path() is None, reason="kor_travel_map repo 미존재(CI/타 환경) — 핀 신선도 검사 생략"
)
def test_vendored_snapshot_matches_live_kor_travel_map() -> None:
    """로컬 전용: vendored beach query가 kor_travel_map live와 같은지 확인."""
    live_path = _live_spec_path()
    assert live_path is not None
    live = json.loads(live_path.read_text(encoding="utf-8"))
    query_problems = {
        path: {
            "snapshot": sorted(_query_parameter_names(_spec(), path)),
            "live": sorted(_query_parameter_names(live, path)),
        }
        for path in _CLIENT_QUERY_PARAMETERS
        if _query_parameter_names(_spec(), path) != _query_parameter_names(live, path)
    }
    assert not query_problems, (
        f"vendored 스냅샷 query parameter가 kor_travel_map live와 다름: {query_problems}"
    )
