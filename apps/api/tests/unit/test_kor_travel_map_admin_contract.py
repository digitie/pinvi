"""kor-travel-map Admin OpenAPI의 Pinvi feature 소비 계약 게이트 (T-VN-42)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_SNAPSHOT = (
    Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-admin.json"
)
_UPSTREAM_COMMIT = "da2c740aa4b4239821075519959c38534cc65d2f"
_SNAPSHOT_SHA256 = "22e3f2f07192706bd06b35d2b9841c4a023047053be03731d5cfbfba8a746d32"

_ADMIN_FEATURE_QUERY_PARAMETERS = {
    "q",
    "kind",
    "category",
    "lifecycle_state",
    "publication_state",
    "quality_state",
    "provider_dataset_id",
    "has_coord",
    "has_issue",
    "issue_type",
    "updated_from",
    "updated_to",
    "include_ended",
    "page_size",
    "cursor",
    "sort",
    "order",
}


def _spec() -> dict[str, Any]:
    loaded = json.loads(_SNAPSHOT.read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def _schema(spec: dict[str, Any], name: str) -> dict[str, Any]:
    return spec["components"]["schemas"][name]


def _response_ref(operation: dict[str, Any]) -> str:
    return operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]


def _query_names(operation: dict[str, Any]) -> set[str]:
    return {
        parameter["name"]
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "query"
    }


def test_admin_snapshot_is_byte_pinned_to_a_reviewed_map_revision() -> None:
    assert _UPSTREAM_COMMIT == "da2c740aa4b4239821075519959c38534cc65d2f"
    assert hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA256


def test_admin_feature_paths_auth_responses_and_query_sets_are_exact() -> None:
    spec = _spec()
    operations = {
        "/v1/admin/features": spec["paths"]["/v1/admin/features"]["get"],
        "/v1/admin/features/{feature_id}": spec["paths"]["/v1/admin/features/{feature_id}"]["get"],
        "/v1/admin/features/{feature_id}/weather": spec["paths"][
            "/v1/admin/features/{feature_id}/weather"
        ]["get"],
    }
    assert all(operation["security"] == [{"AdminBFF": []}] for operation in operations.values())
    assert _query_names(operations["/v1/admin/features"]) == _ADMIN_FEATURE_QUERY_PARAMETERS
    assert _query_names(operations["/v1/admin/features/{feature_id}"]) == set()
    assert _query_names(operations["/v1/admin/features/{feature_id}/weather"]) == set()
    assert _response_ref(operations["/v1/admin/features"]) == (
        "#/components/schemas/AdminFeaturesListResponse"
    )
    assert _response_ref(operations["/v1/admin/features/{feature_id}"]) == (
        "#/components/schemas/AdminFeatureDetailResponse"
    )
    assert _response_ref(operations["/v1/admin/features/{feature_id}/weather"]) == (
        "#/components/schemas/FeatureWeatherResponse"
    )


def test_admin_feature_response_containers_keep_consumed_item_refs() -> None:
    spec = _spec()
    assert _schema(spec, "AdminFeaturesListResponse")["properties"]["data"]["$ref"] == (
        "#/components/schemas/AdminFeaturesListData"
    )
    assert _schema(spec, "AdminFeaturesListData")["properties"]["items"]["items"]["$ref"] == (
        "#/components/schemas/AdminFeatureRecord"
    )
    assert _schema(spec, "AdminFeatureDetailResponse")["properties"]["data"]["$ref"] == (
        "#/components/schemas/AdminFeatureDetailData"
    )
    detail = _schema(spec, "AdminFeatureDetailData")["properties"]
    assert detail["feature"]["$ref"] == ("#/components/schemas/AdminFeatureDetailFeatureRecord")
    assert {
        name: detail[name]["items"]["$ref"]
        for name in (
            "sources",
            "issues",
            "overrides",
            "state_transitions",
            "files",
            "curations",
        )
    } == {
        "sources": "#/components/schemas/AdminFeatureDetailSourceRecord",
        "issues": "#/components/schemas/AdminFeatureDetailIssueRecord",
        "overrides": "#/components/schemas/AdminFeatureDetailOverrideRecord",
        "state_transitions": ("#/components/schemas/AdminFeatureStateTransitionAuditRecord"),
        "files": "#/components/schemas/AdminFeatureDetailFileRecord",
        "curations": "#/components/schemas/AdminCurationItemView",
    }


def test_admin_feature_state_axes_transition_and_curation_shapes_are_pinned() -> None:
    spec = _spec()
    for name in ("AdminFeatureRecord", "AdminFeatureDetailFeatureRecord"):
        schema = _schema(spec, name)
        assert {
            "lifecycle_state",
            "publication_state",
            "quality_state",
        } <= set(schema["required"])
        assert "status" not in schema["properties"]
        assert schema["properties"]["lifecycle_state"]["enum"] == ["active", "retired"]
        assert schema["properties"]["publication_state"]["enum"] == [
            "draft",
            "published",
            "suppressed",
        ]
        assert schema["properties"]["quality_state"]["enum"] == [
            "valid",
            "quarantined",
        ]

    transition = _schema(spec, "AdminFeatureStateTransitionAuditRecord")
    assert set(transition["required"]) == {
        "transition_id",
        "to_lifecycle_state",
        "to_publication_state",
        "to_quality_state",
        "transition_kind",
        "reason_code",
        "principal",
        "occurred_at",
        "row_revision",
    }
    assert transition["properties"]["occurred_at"] == {
        "format": "date-time",
        "title": "Occurred At",
        "type": "string",
    }
    assert transition["properties"]["row_revision"]["minimum"] == 1.0

    curation = _schema(spec, "AdminCurationItemView")
    consumed_curation_fields = {
        "curation_item_id",
        "collection_id",
        "collection_key",
        "title",
        "edition_key",
        "theme_slug",
        "theme_name",
        "theme_group",
        "feature_id",
        "feature_name",
        "feature_kind",
        "feature_category",
        "place_name",
        "address_hint",
        "status",
        "sort_order",
        "item_title",
        "item_summary",
        "curation_relation",
        "reuse_policy",
        "row_revision",
        "updated_at",
    }
    assert consumed_curation_fields <= set(curation["required"])
    assert consumed_curation_fields <= set(curation["properties"])
    assert curation["properties"]["curation_item_id"]["format"] == "uuid"
    assert curation["properties"]["collection_id"]["format"] == "uuid"
    assert curation["properties"]["status"]["enum"] == [
        "candidate",
        "included",
        "rejected",
        "archived",
    ]
    assert curation["properties"]["curation_relation"]["enum"] == [
        "primary_stop",
        "food_stop",
        "cafe_stop",
        "bookstore_stop",
        "nearby_option",
        "accessibility_support",
        "pet_support",
        "family_support",
        "theme_area_anchor",
    ]
    assert curation["properties"]["reuse_policy"]["enum"] == [
        "allowed",
        "blocked",
        "manual_review",
    ]
    assert curation["properties"]["row_revision"]["pattern"] == "^[1-9][0-9]*$"
    assert curation["properties"]["updated_at"]["format"] == "date-time"
    for name in (
        "feature_id",
        "feature_name",
        "feature_kind",
        "feature_category",
        "address_hint",
        "item_title",
        "item_summary",
    ):
        assert {"type": "null"} in curation["properties"][name]["anyOf"]


def test_admin_weather_card_keeps_the_fields_pinvi_projects() -> None:
    spec = _spec()
    weather_response = _schema(spec, "FeatureWeatherResponse")
    assert weather_response["properties"]["data"]["$ref"] == (
        "#/components/schemas/WeatherCardData"
    )
    weather = _schema(spec, "WeatherCardData")
    assert {"feature_id", "is_stale", "source_styles", "metrics"} <= set(weather["required"])
    assert {"selected_at", "latest_at"} <= set(weather["properties"])
    assert {
        tuple(sorted(item.items())) for item in weather["properties"]["selected_at"]["anyOf"]
    } == {
        (("format", "date-time"), ("type", "string")),
        (("type", "null"),),
    }
    assert weather["properties"]["metrics"]["items"]["$ref"] == (
        "#/components/schemas/WeatherMetricOut"
    )
