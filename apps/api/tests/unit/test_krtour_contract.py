"""krtour `openapi.user.json` 계약 드리프트 게이트 (T-210e).

vendor된 스냅샷(`tests/contract/krtour-openapi-user.json`)에 TripMate user client
(`clients/krtour_map.py`) + 매핑(`api/v1/features.py _*_from_krtour`)이 의존하는 **경로·응답
필드**가 존재하는지 검증한다.

운영: krtour 스펙이 갱신되면 스냅샷을 교체(`docs/integrations/krtour-map-rest-api.md`
"드리프트 게이트" 절)하고 본 테스트를 돌린다. 우리 가정이 깨졌으면 여기서 실패 → client/매핑을
맞춘다. 수기 httpx client는 krtour 권고대로 유지하되, 본 게이트로 silent drift를 막는다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

_SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "krtour-openapi-user.json"

# TripMate user client(`clients/krtour_map.py`)가 호출하는 krtour 경로.
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
]

# 매핑(`features.py _*_from_krtour`)이 읽는 응답 필드 — 스키마별 필수 존재.
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


def test_snapshot_is_krtour_user_surface() -> None:
    assert _spec()["info"]["title"] == "krtour-map-user"


def test_client_paths_exist_in_snapshot() -> None:
    paths = set(_spec()["paths"])
    missing = [p for p in _CLIENT_PATHS if p not in paths]
    assert not missing, f"client가 의존하는 krtour 경로가 스냅샷에 없음(드리프트): {missing}"


def test_mapped_response_fields_exist_in_snapshot() -> None:
    schemas = _spec()["components"]["schemas"]
    problems: list[str] = []
    for schema_name, fields in _SCHEMA_FIELDS.items():
        props = set(schemas.get(schema_name, {}).get("properties", {}))
        gone = fields - props
        if gone:
            problems.append(f"{schema_name}: {sorted(gone)}")
    assert not problems, f"매핑이 의존하는 krtour 응답 필드가 스냅샷에 없음(드리프트): {problems}"


def _live_spec_path() -> Path | None:
    """sibling `python-krtour-map` repo의 live 스펙 경로(있으면). env override 가능."""
    override = os.environ.get("TRIPMATE_KRTOUR_OPENAPI_USER_PATH")
    if override:
        return Path(override)
    repo_root = Path(__file__).resolve().parents[3]  # apps/api/tests/unit → tripmate-claude
    candidate = (
        repo_root.parent
        / "python-krtour-map"
        / "packages"
        / "krtour-map-admin"
        / "openapi.user.json"
    )
    return candidate if candidate.exists() else None


@pytest.mark.skipif(
    _live_spec_path() is None, reason="krtour repo 미존재(CI/타 환경) — 핀 신선도 검사 생략"
)
def test_vendored_snapshot_matches_live_krtour() -> None:
    """로컬 전용: vendored 스냅샷 경로 집합이 krtour live와 같은지(핀 신선도). CI에서는 skip."""
    live_path = _live_spec_path()
    assert live_path is not None
    live = json.loads(live_path.read_text(encoding="utf-8"))
    assert set(live["paths"]) == set(_spec()["paths"]), (
        "vendored 스냅샷 경로가 krtour live와 다름 — 스냅샷 갱신 필요"
        " (cp openapi.user.json → tests/contract/krtour-openapi-user.json)"
    )
