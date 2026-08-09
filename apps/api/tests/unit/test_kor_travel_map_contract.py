"""kor_travel_map `openapi.user.json` 계약 드리프트 게이트 (T-210e).

kor_travel_map `f426c7b8`(T-VN-34C — 공개 feature에서 과거 `status`와 내부 상태 축을 제거)의 전체 스냅샷을 byte-for-byte
vendor하고 pinned SHA-256으로 수기 graft를 차단한다. 스냅샷(`tests/contract/kor-travel-map-openapi-user.json`)에 Pinvi user client
(`clients/kor_travel_map.py`) + 그 소비자(`api/v1/features.py`·`public.py`·`search.py`·
`admin/category_mappings.py`, `services/place_search.py`·`feature_detail.py`)가 의존하는
**경로·응답 필드**가 존재하는지, 그리고 그 필드의 **타입 계약**
(type/format/enum/array item/map value/required/nullable)이 유지되는지 검증한다(T-VN-H07B).

**profile 분리(Map `96814b2a` "split service openapi profile")**: ServiceToken 전용
batch 2경로(`/v1/features/batch`·`/v1/features/weather/batch`)는 user profile에서
분리돼 `openapi.service.json` 소속이 됐다. user client는 여전히 두 경로를 호출하므로
본 게이트는 해당 경로·batch schema 계약을 vendored **service** 스냅샷
(`tests/contract/kor-travel-map-openapi-service.json` — byte-핀은
`test_kor_travel_map_cache_target_contract.py` 소유)에서 검증하고, 나머지는 user
스냅샷에서 검증한다. 두 스냅샷에 모두 있는 schema는 양쪽 모두에서 계약을 고정한다
(profile 간 silent 분화 차단).

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
from pydantic import BaseModel

from app.schemas.public import (
    PublicBeachView,
    PublicFestivalMonth,
    PublicFestivalView,
    PublicMapMarker,
    PublicMapMarkerLayer,
)

_SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-user.json"
_UPSTREAM_COMMIT = "f426c7b78c493035952ded5c2a13f61a2a351793"
_SNAPSHOT_SHA256 = "eca7eea1dff7aa1848e50428fb8da5507e4d636c3a979b04859ef43c7f7410e7"

# service profile 스냅샷 — byte-핀·재추출 절차는 cache-target 계약 테스트
# (`test_kor_travel_map_cache_target_contract.py`)가 소유하고 본 파일은 읽기만 한다.
_SERVICE_SNAPSHOT = (
    Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-service.json"
)

# Map `96814b2a`가 user profile에서 분리한 ServiceToken 전용 경로 — user client가
# 여전히 호출하므로 계약은 service 스냅샷 기준으로 검증한다.
_SERVICE_PROFILE_PATHS: frozenset[str] = frozenset(
    {"/v1/features/batch", "/v1/features/weather/batch"}
)

# Pinvi user client(`clients/kor_travel_map.py`)가 호출하는 kor_travel_map 경로.
_CLIENT_PATHS = [
    "/v1/features/in-bounds",
    "/v1/features/nearby",
    "/v1/features/search",
    "/v1/features/{feature_id}",
    "/v1/features/{feature_id}/weather",
    "/v1/features/{feature_id}/weather/snapshot",
    "/v1/features/batch",  # service profile (_SERVICE_PROFILE_PATHS)
    "/v1/features/weather/batch",  # service profile (_SERVICE_PROFILE_PATHS)
    "/v1/categories",
    "/v1/public/beaches",
    "/v1/public/beaches/map-markers",
    "/v1/public/beaches/{feature_id}",
    "/v1/public/festivals/monthly",
    "/v1/public/festivals/map-markers",
    "/v1/public/festivals/{feature_id}",
    # 큐레이션 import는 user 표면이 아니라 admin `/v1/admin/features/curated/{id}/detail-snapshot`을
    # 쓴다(ADR-049 — kor_travel_map PR #533이 public `*-copy` 표면을 폐지). user-contract gate 범위 밖.
]

_CLIENT_QUERY_PARAMETERS: dict[str, set[str]] = {
    "/v1/features/{feature_id}/weather": set(),
    "/v1/features/{feature_id}/weather/snapshot": {"target_at", "known_at"},
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

# --- kor_travel_map user 표면에서 Pinvi가 실제로 소비하는 필드의 typed contract (T-VN-H07B) ---
#
# 소스(전수 감사): user client `clients/kor_travel_map.py`와 그 소비자 —
# `api/v1/features.py`(`_*_from_kor_travel_map`), `api/v1/public.py`, `api/v1/search.py`,
# `api/v1/admin/category_mappings.py`(같은 user client의 categories 소비),
# `services/place_search.py`, `services/feature_detail.py`.
# 응답 **컨테이너**(`PublicFeatureListData`/`FeaturesNearbyData`/`FeatureSearchData`/
# `CategoriesData`/`FeatureBatchData`)의 item·map value `$ref`도 함께 고정한다 — 이게 없으면
# item 계약이 컨테이너와 결합되지 않아 producer가 `items.$ref`를 갈아끼워도 통과한다.
# endpoint→컨테이너 link는 `_ENDPOINT_DATA_SCHEMAS`가 따로 고정한다(둘을 합쳐야 경로부터
# 필드까지 하나의 사슬이 된다).
# envelope `meta`도 대상이다 — client가 `meta.cluster.cluster_unit`와
# `meta.page.next_cursor`/`total`을 `data`로 re-projection해서 소비한다
# (`clients/kor_travel_map.py` `features_in_bounds`/`_thread_page`).
# 각 필드의 JSON type·format·enum·array item(type/`$ref`)·map value(`$ref`)·required·nullable을
# 스냅샷 기준으로 고정한다. 존재 검사용 `_SCHEMA_FIELDS`는 이 표에서 파생되므로 두 표가 서로
# 어긋날 수 없다(과거처럼 손으로 두 벌을 유지하지 않는다).
#
# `/v1/public/*`는 `PublicBeachView`/`PublicFestivalView`/`PublicMapMarkerLayer`.model_validate로
# **객체 전체**를 검증하므로(`api/v1/public.py`) 해당 Pydantic 모델이 선언한 모든 필드가 소비
# 대상이다 — `test_public_view_contracts_cover_every_validated_model_field`가 이를 강제한다.
#
# **exact property 집합은 의도적으로 고정하지 않는다.** producer(Map) 쪽 exact 집합·
# `additionalProperties` 고정은 T-VN-H07A(Map PR #814)가 소유한다. consumer가 이를 중복 고정하면
# Map의 무해한 additive 변경마다 Pinvi가 false-red가 된다(Map migration 0066의
# `external_component_id` 추가가 실제 사례). consumer는 "우리가 읽는 필드의 shape"만 본다.
#
# 공개 curated 표면(`PublicCurated*`/`PublicCuration*`)은 대상이 아니다 — user client가 호출하지
# 않으며(ADR-049, Map PR #533이 public `*-copy` 폐지), Pinvi의 큐레이션 런타임 표면은 admin
# `/v1/admin/features/curated/{id}/detail-snapshot`이라 T-VN-H07D(#815)가 소유한다.
#
# 참고(항상 None인 방어적 read — 대응 property가 user 표면에 없어 고정할 계약이 없다):
#   * `dto.get("title")` — `_summary_from_kor_travel_map`/`_detail_from_kor_travel_map`/
#     `feature_detail.build_detail_card`/`place_search.feature_item_to_result` 네 곳 모두.
#     `FeatureSummary`/`NearbyFeatureSummary`/`FeatureDetailResponse`에 `title`이 없다.
#   * `item.get("address")` — `place_search.feature_item_to_result`. `FeatureSummary`에 없다.
#
# 반대로 `features.py`의 `data.get("cluster_unit")`은 방어 코드가 아니다 — client가
# `meta.cluster.cluster_unit`를 `data`로 re-projection하므로 실제 값이 온다(위 `ClusterMeta` 핀).
# `data.get("next_cursor")`/`get("total")`(`public.py _page_meta`)도 같은 방식이다(`PageMeta` 핀).
_CONSUMED_FIELD_CONTRACTS: dict[str, dict[str, dict[str, Any]]] = {
    "FeatureSummary": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "kind": {"type": "string", "required": True, "nullable": False},
        "name": {"type": "string", "required": True, "nullable": False},
        "lon": {"type": "number", "required": True, "nullable": True},
        "lat": {"type": "number", "required": True, "nullable": True},
        "category": {"type": "string", "required": True, "nullable": False},
        "marker_color": {"type": "string", "required": False, "nullable": True},
        "marker_icon": {"type": "string", "required": False, "nullable": True},
    },
    "NearbyFeatureSummary": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "kind": {"type": "string", "required": True, "nullable": False},
        "name": {"type": "string", "required": True, "nullable": False},
        "lon": {"type": "number", "required": True, "nullable": False},
        "lat": {"type": "number", "required": True, "nullable": False},
        "category": {"type": "string", "required": True, "nullable": False},
        "distance_m": {"type": "number", "required": True, "nullable": False},
    },
    "ClusterSummary": {
        "cluster_key": {"type": "string", "required": True, "nullable": False},
        "lon": {"type": "number", "required": True, "nullable": False},
        "lat": {"type": "number", "required": True, "nullable": False},
        "feature_count": {"type": "integer", "required": True, "nullable": False},
    },
    "FeatureDetailResponse": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "kind": {"type": "string", "required": True, "nullable": False},
        "name": {"type": "string", "required": True, "nullable": False},
        "lon": {"type": "number", "required": False, "nullable": True},
        "lat": {"type": "number", "required": False, "nullable": True},
        "category": {"type": "string", "required": True, "nullable": False},
        "address": {"type": "object", "required": True, "nullable": False},
        "legal_dong_code": {"type": "string", "required": False, "nullable": True},
        "sido_code": {"type": "string", "required": False, "nullable": True},
        "sigungu_code": {"type": "string", "required": False, "nullable": True},
        "marker_color": {"type": "string", "required": False, "nullable": True},
        "marker_icon": {"type": "string", "required": False, "nullable": True},
        "urls": {"type": "object", "required": True, "nullable": False},
        "detail": {"type": "object", "required": True, "nullable": False},
        "updated_at": {
            "type": "string",
            "format": "date-time",
            "required": True,
            "nullable": False,
        },
    },
    "WeatherCardData": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "selected_at": {
            "type": "string",
            "format": "date-time",
            "required": False,
            "nullable": True,
        },
        "latest_at": {"type": "string", "format": "date-time", "required": False, "nullable": True},
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
    "WeatherSnapshotData": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "target_at": {"type": "string", "format": "date-time", "required": True, "nullable": False},
        "known_at": {"type": "string", "format": "date-time", "required": True, "nullable": False},
        "latest_at": {"type": "string", "format": "date-time", "required": False, "nullable": True},
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
        "metric_name": {"type": "string", "required": False, "nullable": True},
        "forecast_style": {"type": "string", "required": True, "nullable": False},
        "timeline_bucket": {"type": "string", "required": False, "nullable": True},
        "valid_at": {"type": "string", "format": "date-time", "required": False, "nullable": True},
        "valid_from": {
            "type": "string",
            "format": "date-time",
            "required": False,
            "nullable": True,
        },
        "valid_until": {
            "type": "string",
            "format": "date-time",
            "required": False,
            "nullable": True,
        },
        "issued_at": {"type": "string", "format": "date-time", "required": False, "nullable": True},
        "observed_at": {
            "type": "string",
            "format": "date-time",
            "required": False,
            "nullable": True,
        },
        "effective_at": {
            "type": "string",
            "format": "date-time",
            "required": False,
            "nullable": True,
        },
        "provider": {"type": "string", "required": False, "nullable": True},
        "weather_domain": {"type": "string", "required": False, "nullable": True},
        "value_number": {"type": "number", "required": False, "nullable": True},
        "value_text": {"type": "string", "required": False, "nullable": True},
        "unit": {"type": "string", "required": False, "nullable": True},
        "severity": {"type": "string", "required": False, "nullable": True},
    },
    "WeatherBatchRequest": {
        "targets": {
            "type": "array",
            "items_ref": "WeatherBatchTargetRequest",
            "min_items": 1,
            "max_items": 366,
            "required": True,
            "nullable": False,
        },
        "known_at": {
            "type": "string",
            "format": "date-time",
            "required": True,
            "nullable": False,
        },
    },
    "WeatherBatchTargetRequest": {
        "target_at": {
            "type": "string",
            "format": "date-time",
            "required": True,
            "nullable": False,
        },
        "feature_ids": {
            "type": "array",
            "items_type": "string",
            "items_max_length": 256,
            "unique_items": True,
            "min_items": 1,
            "max_items": 200,
            "required": True,
            "nullable": False,
        },
    },
    "WeatherBatchData": {
        "known_at": {
            "type": "string",
            "format": "date-time",
            "required": True,
            "nullable": False,
        },
        "targets": {
            "type": "array",
            "items_ref": "WeatherBatchTargetData",
            "required": True,
            "nullable": False,
        },
    },
    "WeatherBatchTargetData": {
        "target_at": {
            "type": "string",
            "format": "date-time",
            "required": True,
            "nullable": False,
        },
        "timeline_until": {
            "type": "string",
            "format": "date-time",
            "required": True,
            "nullable": False,
        },
        "items": {
            "type": "array",
            "items_one_of_refs": {
                "WeatherBatchFoundItem",
                "WeatherBatchNoDataItem",
                "WeatherBatchRetiredItem",
            },
            "items_discriminator": {
                "found": "WeatherBatchFoundItem",
                "no_data": "WeatherBatchNoDataItem",
                "retired": "WeatherBatchRetiredItem",
            },
            "required": True,
            "nullable": False,
        },
        "cards": {
            "type": "array",
            "items_ref": "WeatherBatchCardOut",
            "required": True,
            "nullable": False,
        },
    },
    "WeatherBatchFoundItem": {
        "state": {
            "type": "string",
            "const": "found",
            "required": True,
            "nullable": False,
        },
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "card_key": {"type": "string", "required": True, "nullable": False},
    },
    "WeatherBatchCardOut": {
        "card_key": {"type": "string", "required": True, "nullable": False},
        "source_styles": {
            "type": "array",
            "items_type": "string",
            "required": True,
            "nullable": False,
        },
        "current": {
            "type": "array",
            "items_ref": "WeatherMetricOut",
            "required": True,
            "nullable": False,
        },
        "timeline": {
            "type": "array",
            "items_ref": "WeatherMetricOut",
            "required": True,
            "nullable": False,
        },
        "latest_at": {
            "type": "string",
            "format": "date-time",
            "required": False,
            "nullable": True,
        },
        "is_stale": {"type": "boolean", "required": True, "nullable": False},
    },
    "WeatherBatchNoDataItem": {
        "state": {
            "type": "string",
            "const": "no_data",
            "required": True,
            "nullable": False,
        },
        "feature_id": {"type": "string", "required": True, "nullable": False},
    },
    "WeatherBatchRetiredItem": {
        "state": {
            "type": "string",
            "const": "retired",
            "required": True,
            "nullable": False,
        },
        "feature_id": {"type": "string", "required": True, "nullable": False},
    },
    "CategorySummary": {
        "code": {"type": "string", "required": True, "nullable": False},
        "label": {"type": "string", "required": True, "nullable": False},
        "parent_code": {"type": "string", "required": True, "nullable": True},
        "maki_icon": {"type": "string", "required": True, "nullable": False},
        "path": {"type": "array", "items_type": "string", "required": True, "nullable": False},
        "depth": {"type": "integer", "required": True, "nullable": False},
        "is_active": {"type": "boolean", "required": True, "nullable": False},
        "sort_order": {"type": "integer", "required": True, "nullable": False},
        "tier1_code": {"type": "string", "required": True, "nullable": False},
        "tier1_name": {"type": "string", "required": True, "nullable": False},
        "tier2_code": {"type": "string", "required": True, "nullable": False},
        "tier2_name": {"type": "string", "required": True, "nullable": True},
        "tier3_code": {"type": "string", "required": True, "nullable": False},
        "tier3_name": {"type": "string", "required": True, "nullable": True},
        "tier4_code": {"type": "string", "required": True, "nullable": False},
        "tier4_name": {"type": "string", "required": True, "nullable": True},
        "db_active": {"type": "boolean", "required": False, "nullable": True},
        "db_feature_count": {"type": "integer", "required": False, "nullable": True},
    },
    "FeatureBatchRequest": {
        "items": {
            "type": "array",
            "items_ref": "FeatureBatchRequestItem",
            "min_items": 1,
            "max_items": 200,
            "required": True,
            "nullable": False,
        },
        "projection": {
            "type": "string",
            "const": "trip_card",
            "required": False,
            "nullable": False,
        },
    },
    "FeatureBatchRequestItem": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "known_row_revision": {
            "type": "integer",
            "format": "int64",
            "minimum": 1,
            "required": False,
            "nullable": True,
        },
    },
    "FeatureBatchData": {
        "items": {
            "type": "array",
            "items_one_of_refs": {
                "FeatureBatchFoundItem",
                "FeatureBatchRetiredItem",
                "FeatureBatchSuppressedItem",
                "FeatureBatchMissingItem",
                "FeatureBatchUnchangedItem",
            },
            "items_discriminator": {
                "found": "FeatureBatchFoundItem",
                "retired": "FeatureBatchRetiredItem",
                "suppressed": "FeatureBatchSuppressedItem",
                "missing": "FeatureBatchMissingItem",
                "unchanged": "FeatureBatchUnchangedItem",
            },
            "required": True,
            "nullable": False,
        },
    },
    "FeatureBatchFoundItem": {
        "state": {
            "type": "string",
            "const": "found",
            "required": True,
            "nullable": False,
        },
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "row_revision": {
            "type": "integer",
            "minimum": 1,
            "required": True,
            "nullable": False,
        },
        "trip_card": {
            "type": "object",
            "ref": "FeatureTripCard",
            "required": True,
            "nullable": False,
        },
    },
    "FeatureBatchRetiredItem": {
        "state": {
            "type": "string",
            "const": "retired",
            "required": True,
            "nullable": False,
        },
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "row_revision": {
            "type": "integer",
            "minimum": 1,
            "required": True,
            "nullable": False,
        },
    },
    "FeatureBatchSuppressedItem": {
        "state": {
            "type": "string",
            "const": "suppressed",
            "required": True,
            "nullable": False,
        },
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "row_revision": {
            "type": "integer",
            "minimum": 1,
            "required": True,
            "nullable": False,
        },
    },
    "FeatureBatchMissingItem": {
        "state": {
            "type": "string",
            "const": "missing",
            "required": True,
            "nullable": False,
        },
        "feature_id": {"type": "string", "required": True, "nullable": False},
    },
    "FeatureBatchUnchangedItem": {
        "state": {
            "type": "string",
            "const": "unchanged",
            "required": True,
            "nullable": False,
        },
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "row_revision": {
            "type": "integer",
            "minimum": 1,
            "required": True,
            "nullable": False,
        },
    },
    "FeatureTripCard": {
        "feature_id": {"type": "string", "required": True, "nullable": False},
        "kind": {"type": "string", "required": True, "nullable": False},
        "name": {"type": "string", "required": True, "nullable": False},
        "category": {"type": "string", "required": True, "nullable": False},
        "lon": {"type": "number", "required": True, "nullable": True},
        "lat": {"type": "number", "required": True, "nullable": True},
        "address": {"type": "object", "required": True, "nullable": False},
        "marker_icon": {"type": "string", "required": True, "nullable": True},
        "marker_color": {"type": "string", "required": True, "nullable": True},
    },
    "PublicFeatureListData": {
        "items": {
            "type": "array",
            "items_ref": "FeatureSummary",
            "required": False,
            "nullable": False,
        },
        "clusters": {
            "type": "array",
            "items_ref": "ClusterSummary",
            "required": False,
            "nullable": False,
        },
    },
    "FeaturesNearbyData": {
        "items": {
            "type": "array",
            "items_ref": "NearbyFeatureSummary",
            "required": True,
            "nullable": False,
        },
    },
    "FeatureSearchData": {
        "items": {
            "type": "array",
            "items_ref": "FeatureSummary",
            "required": True,
            "nullable": False,
        },
    },
    "CategoriesData": {
        "items": {
            "type": "array",
            "items_ref": "CategorySummary",
            "required": True,
            "nullable": False,
        },
        "include_counts": {"type": "boolean", "required": True, "nullable": False},
    },
    "ClusterMeta": {
        "cluster_unit": {
            "type": "string",
            "enum": {"eupmyeondong", "sido", "sigungu"},
            "required": True,
            "nullable": False,
        },
    },
    "PageMeta": {
        "next_cursor": {"type": "string", "required": False, "nullable": True},
        "total": {"type": "integer", "required": False, "nullable": True},
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
        "beach_kind": {"type": "string", "required": False, "nullable": True},
        "beach_width_m": {"type": "number", "required": False, "nullable": True},
        "beach_length_m": {"type": "number", "required": False, "nullable": True},
        "beach_material": {"type": "string", "required": False, "nullable": True},
        "emergency_contact": {"type": "string", "required": False, "nullable": True},
        "homepage_url": {"type": "string", "required": False, "nullable": True},
        "image_url": {"type": "string", "required": False, "nullable": True},
        "road_address": {"type": "string", "required": False, "nullable": True},
        "jibun_address": {"type": "string", "required": False, "nullable": True},
        "legal_dong_code": {"type": "string", "required": False, "nullable": True},
        "sido_code": {"type": "string", "required": False, "nullable": True},
        "sigungu_code": {"type": "string", "required": False, "nullable": True},
        "lon": {"type": "number", "required": False, "nullable": True},
        "lat": {"type": "number", "required": False, "nullable": True},
        "marker_color": {"type": "string", "required": False, "nullable": True},
        "marker_icon": {"type": "string", "required": False, "nullable": True},
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
        "event_status": {
            "type": "string",
            "enum": {"ended", "ongoing", "scheduled", "unknown"},
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
        "event_end_date": {"type": "string", "format": "date", "required": False, "nullable": True},
        "venue_name": {"type": "string", "required": False, "nullable": True},
        "road_address": {"type": "string", "required": False, "nullable": True},
        "jibun_address": {"type": "string", "required": False, "nullable": True},
        "sido_code": {"type": "string", "required": False, "nullable": True},
        "sigungu_code": {"type": "string", "required": False, "nullable": True},
        "lon": {"type": "number", "required": False, "nullable": True},
        "lat": {"type": "number", "required": False, "nullable": True},
        "homepage_url": {"type": "string", "required": False, "nullable": True},
        "festival_content": {"type": "string", "required": False, "nullable": True},
        "organizer_name": {"type": "string", "required": False, "nullable": True},
        "auspc_instt_name": {"type": "string", "required": False, "nullable": True},
        "suprt_instt_name": {"type": "string", "required": False, "nullable": True},
        "phone_number": {"type": "string", "required": False, "nullable": True},
        "provider_org_name": {"type": "string", "required": False, "nullable": True},
        "reference_date": {"type": "string", "format": "date", "required": False, "nullable": True},
        "marker_color": {"type": "string", "required": False, "nullable": True},
        "marker_icon": {"type": "string", "required": False, "nullable": True},
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
        "sigungu_code": {"type": "string", "required": False, "nullable": True},
    },
    "PublicMapMarkerLayerData": {
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

# 존재 검사(`test_mapped_response_fields_exist_in_snapshot`)용 파생 집합 — 위 계약 표가 정본.
_SCHEMA_FIELDS: dict[str, set[str]] = {
    name: set(fields) for name, fields in _CONSUMED_FIELD_CONTRACTS.items()
}

# endpoint → 응답 envelope의 `data` 컨테이너 schema. 경로가 다른 컨테이너를 가리키게 바뀌면
# 위 필드 계약이 전부 green이어도 소비가 깨지므로 이 link를 따로 고정한다.
_ENDPOINT_DATA_SCHEMAS: dict[tuple[str, str], str] = {
    ("get", "/v1/features/in-bounds"): "PublicFeatureListData",
    ("get", "/v1/features/nearby"): "FeaturesNearbyData",
    ("get", "/v1/features/search"): "FeatureSearchData",
    ("get", "/v1/features/{feature_id}"): "FeatureDetailResponse",
    ("get", "/v1/features/{feature_id}/weather"): "WeatherCardData",
    ("get", "/v1/features/{feature_id}/weather/snapshot"): "WeatherSnapshotData",
    ("post", "/v1/features/batch"): "FeatureBatchData",
    ("post", "/v1/features/weather/batch"): "WeatherBatchData",
    ("get", "/v1/categories"): "CategoriesData",
    ("get", "/v1/public/beaches"): "PublicBeachListData",
    ("get", "/v1/public/beaches/map-markers"): "PublicMapMarkerLayerData",
    ("get", "/v1/public/beaches/{feature_id}"): "BeachPublicView",
    ("get", "/v1/public/festivals/monthly"): "PublicFestivalMonthlyData",
    ("get", "/v1/public/festivals/map-markers"): "PublicMapMarkerLayerData",
    ("get", "/v1/public/festivals/{feature_id}"): "FestivalPublicView",
}

# `model_validate`로 upstream 객체 전체를 검증하는 표면 → (스냅샷 schema, Pinvi 소비 모델).
_VALIDATED_PUBLIC_MODELS: dict[str, type[BaseModel]] = {
    "BeachPublicView": PublicBeachView,
    "FestivalPublicView": PublicFestivalView,
    "PublicFestivalMonth": PublicFestivalMonth,
    "PublicMapMarker": PublicMapMarker,
    "PublicMapMarkerLayerData": PublicMapMarkerLayer,
}


def _spec() -> dict[str, Any]:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def _service_spec() -> dict[str, Any]:
    return json.loads(_SERVICE_SNAPSHOT.read_text(encoding="utf-8"))


def _spec_for_path(
    path: str, user_spec: dict[str, Any], service_spec: dict[str, Any]
) -> dict[str, Any]:
    """경로가 속한 profile의 스냅샷 — batch 2경로만 service, 나머지는 user."""
    return service_spec if path in _SERVICE_PROFILE_PATHS else user_spec


def _specs_containing_schema(
    schema_name: str, user_spec: dict[str, Any], service_spec: dict[str, Any]
) -> list[dict[str, Any]]:
    """schema를 선언한 모든 profile 스냅샷 — 겹치는 schema는 양쪽 다 고정한다."""
    return [
        spec for spec in (user_spec, service_spec) if schema_name in spec["components"]["schemas"]
    ]


def test_snapshot_is_kor_travel_map_user_surface() -> None:
    assert hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA256, (
        f"vendored openapi.user.json이 kor_travel_map {_UPSTREAM_COMMIT} 원본과 다름"
    )
    assert _spec()["info"]["title"] == "kor-travel-map-user"
    # service profile 스냅샷의 정체 확인 — byte-핀은 cache-target 계약 테스트 소유.
    assert _service_spec()["info"]["title"] == "kor-travel-map-service"


def test_public_feature_schemas_do_not_reintroduce_legacy_state() -> None:
    """T-VN-34C: 공개 Map 응답에는 상태 축이나 과거 ``status``가 없어야 한다."""
    schemas = _spec()["components"]["schemas"]
    forbidden = {
        "status",
        "lifecycle_state",
        "publication_state",
        "quality_state",
    }
    for schema_name in ("FeatureSummary", "NearbyFeatureSummary", "FeatureDetailResponse"):
        properties = schemas[schema_name]["properties"]
        assert not forbidden & set(properties), (schema_name, sorted(forbidden & set(properties)))


def test_client_paths_exist_in_snapshot() -> None:
    user_spec, service_spec = _spec(), _service_spec()
    missing = [
        p for p in _CLIENT_PATHS if p not in _spec_for_path(p, user_spec, service_spec)["paths"]
    ]
    assert not missing, (
        f"client가 의존하는 kor_travel_map 경로가 스냅샷에 없음(드리프트): {missing}"
    )
    # profile 분리 유지 확인 — batch가 user profile로 되돌아오면 이 분기 로직이 죽은
    # 코드가 되므로 명시적으로 고정한다.
    assert not _SERVICE_PROFILE_PATHS & set(user_spec["paths"]), (
        "service profile 경로가 user 스냅샷에 다시 나타남 — profile 분기 재검토 필요"
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
    user_spec, service_spec = _spec(), _service_spec()
    actual_scheme = user_spec["components"]["securitySchemes"].get("PublicApiKey")
    assert isinstance(actual_scheme, dict)
    assert {key: actual_scheme.get(key) for key in _PUBLIC_API_KEY_SCHEME} == (
        _PUBLIC_API_KEY_SCHEME
    )

    query_leaks = {
        path: sorted(
            {
                parameter["name"]
                for operation in _spec_for_path(path, user_spec, service_spec)["paths"][
                    path
                ].values()
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
        if path not in _SERVICE_PROFILE_PATHS
        for method, operation in user_spec["paths"][path].items()
        if method in {"get", "post"}
        if operation.get("security") != _PUBLIC_API_KEY_SECURITY
    }
    assert not security_problems, (
        f"public client 경로의 header security 계약이 다름: {security_problems}"
    )

    # batch 2경로는 service profile 소속 — ServiceToken 전용 계약을 service 스냅샷에서
    # 고정하고, service profile에 PublicApiKey scheme 자체가 없음을 함께 고정한다.
    for path in sorted(_SERVICE_PROFILE_PATHS):
        assert service_spec["paths"][path]["post"].get("security") == [{"ServiceToken": []}]
    assert "PublicApiKey" not in service_spec["components"]["securitySchemes"]


def test_mapped_response_fields_exist_in_snapshot() -> None:
    user_spec, service_spec = _spec(), _service_spec()
    problems: list[str] = []
    for schema_name, fields in _SCHEMA_FIELDS.items():
        specs = _specs_containing_schema(schema_name, user_spec, service_spec)
        if not specs:
            problems.append(f"{schema_name}: schema가 어느 profile 스냅샷에도 없음")
            continue
        for spec in specs:
            props = set(spec["components"]["schemas"][schema_name].get("properties", {}))
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


def _resolve_property(prop: dict[str, Any], where: str) -> tuple[dict[str, Any], bool]:
    """nullable wrapper를 벗겨 ``(실제 schema, nullable)``을 돌려준다.

    ``X | None``이 만드는 ``anyOf`` 형태와 OpenAPI 3.1 list-form(``"type": ["string","null"]``)을
    같은 의미로 정규화한다. 두 경우 모두 non-null 분기가 2개 이상이면 producer가 필드를
    union으로 넓힌 것이고, 이는 consumer breaking change이므로 그렇게 보고한다.
    """
    branches = prop.get("anyOf")
    if isinstance(branches, list):
        non_null = [b for b in branches if isinstance(b, dict) and b.get("type") != "null"]
        nullable = any(isinstance(b, dict) and b.get("type") == "null" for b in branches)
        assert len(non_null) == 1, (
            f"{where}: 스냅샷 필드가 union으로 넓어졌다(consumer breaking) — {prop!r}"
        )
        return non_null[0], nullable
    declared = prop.get("type")
    if isinstance(declared, list):
        non_null_types = [t for t in declared if t != "null"]
        assert len(non_null_types) == 1, (
            f"{where}: 스냅샷 type이 union으로 넓어졌다(consumer breaking) — {declared!r}"
        )
        return {**prop, "type": non_null_types[0]}, "null" in declared
    return prop, False


def _deref(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """단일 ``$ref``면 component schema로 한 단계 따라간다(inline enum → named enum 대응)."""
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    resolved = spec["components"]["schemas"].get(ref.rsplit("/", 1)[-1])
    return resolved if isinstance(resolved, dict) else schema


def _assert_consumed_field(
    spec: dict[str, Any], schema_name: str, field: str, expected: dict[str, Any]
) -> None:
    """Pinvi가 읽는 필드 하나의 shape를 스냅샷 기준으로 고정한다."""
    schema = spec["components"]["schemas"][schema_name]
    properties = schema["properties"]
    where = f"{schema_name}.{field}"
    assert field in properties, f"{where}: 스냅샷에 없음(consumer breaking)"
    resolved, nullable = _resolve_property(properties[field], where)
    unresolved = resolved
    resolved = _deref(spec, resolved)

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
    if "const" in expected:
        assert resolved.get("const") == expected["const"], (
            where,
            "const",
            resolved.get("const"),
        )
    if "minimum" in expected:
        assert resolved.get("minimum") == expected["minimum"], (
            where,
            "minimum",
            resolved.get("minimum"),
        )
    if "maximum" in expected:
        assert resolved.get("maximum") == expected["maximum"], (
            where,
            "maximum",
            resolved.get("maximum"),
        )
    if "ref" in expected:
        ref = str(unresolved.get("$ref", ""))
        assert ref.rsplit("/", 1)[-1] == expected["ref"], (where, "$ref", ref)
    if "items_type" in expected or "items_ref" in expected or "items_one_of_refs" in expected:
        items = resolved.get("items")
        assert isinstance(items, dict), (where, "array items 아님", resolved.get("type"))
        if "items_type" in expected:
            assert items.get("type") == expected["items_type"], (where, "items.type", items)
        if "items_ref" in expected:
            ref = str(items.get("$ref", ""))
            assert ref.rsplit("/", 1)[-1] == expected["items_ref"], (where, "items.$ref", ref)
        if "items_one_of_refs" in expected:
            one_of = items.get("oneOf")
            assert isinstance(one_of, list), (where, "items.oneOf 아님", items)
            actual_refs = {
                str(item.get("$ref", "")).rsplit("/", 1)[-1]
                for item in one_of
                if isinstance(item, dict)
            }
            assert actual_refs == expected["items_one_of_refs"], (
                where,
                "items.oneOf.$ref",
                actual_refs,
            )
            discriminator = items.get("discriminator")
            assert isinstance(discriminator, dict), (where, "items.discriminator 아님")
            assert discriminator.get("propertyName") == "state", (
                where,
                "items.discriminator.propertyName",
            )
            mapping = discriminator.get("mapping")
            assert isinstance(mapping, dict), (where, "items.discriminator.mapping 아님")
            actual_mapping = {state: str(ref).rsplit("/", 1)[-1] for state, ref in mapping.items()}
            assert actual_mapping == expected["items_discriminator"], (
                where,
                "items.discriminator.mapping",
                actual_mapping,
            )
    if "min_items" in expected:
        assert resolved.get("minItems") == expected["min_items"], (
            where,
            "minItems",
            resolved.get("minItems"),
        )
    if "max_items" in expected:
        assert resolved.get("maxItems") == expected["max_items"], (
            where,
            "maxItems",
            resolved.get("maxItems"),
        )
    if "values_ref" in expected:
        values = resolved.get("additionalProperties")
        assert isinstance(values, dict), (where, "map value schema 아님", values)
        ref = str(values.get("$ref", ""))
        assert ref.rsplit("/", 1)[-1] == expected["values_ref"], (
            where,
            "additionalProperties.$ref",
            ref,
        )
    if "items_max_length" in expected:
        items = resolved.get("items")
        assert isinstance(items, dict), (where, "array items 아님", resolved.get("type"))
        assert items.get("maxLength") == expected["items_max_length"], (
            where,
            "items.maxLength",
            items.get("maxLength"),
        )
    if "unique_items" in expected:
        assert resolved.get("uniqueItems") is expected["unique_items"], (
            where,
            "uniqueItems",
            resolved.get("uniqueItems"),
        )


def test_consumed_response_fields_pin_types_formats_and_enums() -> None:
    """Pinvi가 읽는 모든 필드의 type/format/enum/item/map value/required/nullable을 고정한다.

    schema를 선언한 **모든** profile 스냅샷(user·service)에서 검사한다 — 겹치는
    schema(`Meta`/`WeatherMetricOut` 등)가 profile 간에 조용히 분화하면 여기서 드러난다.
    """
    user_spec, service_spec = _spec(), _service_spec()
    for schema_name, fields in _CONSUMED_FIELD_CONTRACTS.items():
        specs = _specs_containing_schema(schema_name, user_spec, service_spec)
        assert specs, f"{schema_name}: schema가 어느 profile 스냅샷에도 없음(consumer breaking)"
        for spec in specs:
            for field, expected in fields.items():
                _assert_consumed_field(spec, schema_name, field, expected)


def test_endpoint_data_schemas_bind_paths_to_pinned_containers() -> None:
    """각 경로의 200 응답 `data`가 계약이 걸린 컨테이너를 그대로 가리키는지 고정한다.

    필드 계약은 schema 이름 기준이라, 경로가 다른 컨테이너를 가리키도록 바뀌면 모든 필드
    assertion이 green인 채로 소비만 깨진다. 이 테스트가 경로→컨테이너 link를 닫는다.
    """
    user_spec, service_spec = _spec(), _service_spec()
    assert {path for _method, path in _ENDPOINT_DATA_SCHEMAS} == set(_CLIENT_PATHS), (
        "client 경로와 컨테이너 link 표가 어긋남"
    )
    for (method, path), expected_container in _ENDPOINT_DATA_SCHEMAS.items():
        spec = _spec_for_path(path, user_spec, service_spec)
        schemas = spec["components"]["schemas"]
        operation = spec["paths"][path][method]
        response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        response_name = str(response_schema.get("$ref", "")).rsplit("/", 1)[-1]
        assert response_name in schemas, (method, path, "200 응답이 component ref가 아님")
        data_property = schemas[response_name]["properties"]["data"]
        resolved, _nullable = _resolve_property(data_property, f"{response_name}.data")
        actual = str(resolved.get("$ref", "")).rsplit("/", 1)[-1]
        assert actual == expected_container, (method, path, "data 컨테이너", actual)
        assert expected_container in _CONSUMED_FIELD_CONTRACTS, (
            method,
            path,
            f"{expected_container}에 필드 계약이 없음",
        )


def test_feature_batch_request_binds_to_pinned_container() -> None:
    """batch 요청 body도 5-state validator 계약의 request component에 결합한다."""
    spec = _service_spec()
    request_schema = spec["paths"]["/v1/features/batch"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    actual = str(request_schema.get("$ref", "")).rsplit("/", 1)[-1]
    assert actual == "FeatureBatchRequest"
    assert "FeatureBatchRequest" in _CONSUMED_FIELD_CONTRACTS
    assert "FeatureBatchRequestItem" in _CONSUMED_FIELD_CONTRACTS


def test_weather_batch_request_binds_to_pinned_container() -> None:
    """weather batch body가 bitemporal request component에 결합되는지 고정한다."""
    spec = _service_spec()
    request_schema = spec["paths"]["/v1/features/weather/batch"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    actual = str(request_schema.get("$ref", "")).rsplit("/", 1)[-1]
    assert actual == "WeatherBatchRequest"
    assert "WeatherBatchRequest" in _CONSUMED_FIELD_CONTRACTS
    assert "WeatherBatchTargetRequest" in _CONSUMED_FIELD_CONTRACTS


def test_feature_batch_declares_service_unavailable_problem() -> None:
    """batch DB/transport 장애는 원천 상태가 아니라 명시적 RFC7807 503이다."""
    spec = _service_spec()
    for path in sorted(_SERVICE_PROFILE_PATHS):
        response = spec["paths"][path]["post"]["responses"]["503"]
        schema = response["content"]["application/problem+json"]["schema"]
        assert schema["$ref"].rsplit("/", 1)[-1] == "ProblemDetail"


def test_response_meta_binds_to_pinned_meta_schemas() -> None:
    """envelope `meta` 사슬도 고정한다 — client가 여기서 값을 꺼내 `data`로 re-projection한다.

    `data` 쪽과 대칭으로, 응답→`Meta`와 `Meta.cluster`/`Meta.page`→`ClusterMeta`/`PageMeta`
    link이 없으면 `ClusterMeta`/`PageMeta` 필드 계약이 응답과 결합되지 않는다.
    """
    user_spec, service_spec = _spec(), _service_spec()
    for method, path in _ENDPOINT_DATA_SCHEMAS:
        spec = _spec_for_path(path, user_spec, service_spec)
        schemas = spec["components"]["schemas"]
        operation = spec["paths"][path][method]
        response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        response_name = str(response_schema.get("$ref", "")).rsplit("/", 1)[-1]
        meta_property = schemas[response_name]["properties"]["meta"]
        resolved, _nullable = _resolve_property(meta_property, f"{response_name}.meta")
        assert str(resolved.get("$ref", "")).rsplit("/", 1)[-1] == "Meta", (method, path, "meta")

    # `Meta` 자체는 두 profile에 모두 있으므로 cluster/page link도 양쪽에서 고정한다.
    for spec in (user_spec, service_spec):
        schemas = spec["components"]["schemas"]
        for field, expected in (("cluster", "ClusterMeta"), ("page", "PageMeta")):
            resolved, nullable = _resolve_property(
                schemas["Meta"]["properties"][field], f"Meta.{field}"
            )
            assert str(resolved.get("$ref", "")).rsplit("/", 1)[-1] == expected, (field, expected)
            assert nullable is True, (field, "nullable")
            assert expected in _CONSUMED_FIELD_CONTRACTS, (field, f"{expected} 필드 계약 없음")


def test_public_view_contracts_cover_every_validated_model_field() -> None:
    """`model_validate`로 전체 객체를 검증하는 표면은 모델 선언 필드가 모두 계약에 있어야 한다.

    `api/v1/public.py`는 upstream 객체를 통째로 Pinvi 모델에 검증시키므로, 모델이 선언한
    필드 중 하나라도 producer가 타입을 바꾸면 ValidationError(500)가 난다. 이 테스트는 계약
    표를 **실제 소비 모델**(`app/schemas/public.py`)에 결합해, 모델에 필드를 추가하면 타입
    계약도 함께 적어야 통과하게 만든다(표끼리만 비교하는 자기참조 검사가 아니다).
    """
    for snapshot_schema, model in _VALIDATED_PUBLIC_MODELS.items():
        declared = set(model.model_fields)
        pinned = set(_CONSUMED_FIELD_CONTRACTS[snapshot_schema])
        assert declared <= pinned, (
            f"{snapshot_schema}: {model.__name__}가 검증하는 필드가 계약에 없음 — "
            f"{sorted(declared - pinned)}"
        )
