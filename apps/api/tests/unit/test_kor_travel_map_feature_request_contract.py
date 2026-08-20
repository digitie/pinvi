"""PinVi가 실제로 소비하는 Map 범용 Feature 요청 service 계약 gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.config import (
    KOR_TRAVEL_MAP_FEATURE_REQUEST_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
)

_SNAPSHOT = (
    Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-service.json"
)
_MAP_SOURCE_REVISION = "fa6d0d3d10456401993e12bb5f726abad4bce413"
_SNAPSHOT_SHA256 = "c878531af2acdea0a25861d81f2e87f4768244d8ff37b94cb610194e3db85c96"
_PATH = "/v1/service/feature-requests"


def _spec() -> dict[str, Any]:
    loaded = json.loads(_SNAPSHOT.read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def test_feature_request_service_snapshot_is_exact_candidate_bytes() -> None:
    assert hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA256
    assert KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256 == _SNAPSHOT_SHA256
    assert KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION == _MAP_SOURCE_REVISION
    assert KOR_TRAVEL_MAP_FEATURE_REQUEST_CAPABILITY_GENERATION == 1


def test_feature_request_submit_contract_is_exact() -> None:
    spec = _spec()
    operation = spec["paths"][_PATH]["post"]
    assert operation["security"] == [{"ServiceToken": []}]
    assert operation["parameters"] == [
        {
            "description": "같은 인증 actor가 동일 command를 재시도할 때 재사용하는 UUID. 다른 canonical payload 재사용은 409.",
            "in": "header",
            "name": "Idempotency-Key",
            "required": True,
            "schema": {
                "description": "같은 인증 actor가 동일 command를 재시도할 때 재사용하는 UUID. 다른 canonical payload 재사용은 409.",
                "format": "uuid",
                "title": "Idempotency-Key",
                "type": "string",
            },
        }
    ]
    assert operation["requestBody"] == {
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/FeatureRequestSubmitInput"}
            }
        },
        "required": True,
    }
    request = spec["components"]["schemas"]["FeatureRequestSubmitInput"]
    assert request["additionalProperties"] is False
    assert set(request["required"]) == {"request_id", "kind", "name", "coord"}
    assert set(request["properties"]) == {
        "request_id",
        "kind",
        "name",
        "coord",
        "categories",
        "note",
    }
    assert request["properties"]["kind"]["enum"] == ["place", "event"]
    coord = spec["components"]["schemas"]["FeatureRequestCoordInput"]
    assert coord["additionalProperties"] is False
    assert coord["required"] == ["lon", "lat"]
    assert coord["properties"]["lon"]["minimum"] == 124
    assert coord["properties"]["lon"]["maximum"] == 132
    assert coord["properties"]["lat"]["minimum"] == 33
    assert coord["properties"]["lat"]["maximum"] == 39.5
    assert operation["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/FeatureRequestResponse"
    }
    assert {"401", "403", "422", "503"}.issubset(operation["responses"])


def test_direct_admin_create_is_not_a_runtime_consumer() -> None:
    app_root = Path(__file__).resolve().parents[2] / "app"
    admin_client = (app_root / "clients" / "kor_travel_map_admin.py").read_text(encoding="utf-8")
    request_router = (app_root / "api" / "v1" / "admin" / "feature_requests.py").read_text(
        encoding="utf-8"
    )
    request_client = (app_root / "clients" / "kor_travel_map_feature_request.py").read_text(
        encoding="utf-8"
    )
    assert '"POST", "/v1/admin/features"' not in admin_client
    assert "get_feature_request_service_client(request)" in request_router
    assert "service_client.submit(" in request_router
    assert "/v1/service/feature-requests" in request_client
