"""Pinvi가 소비하는 kor-travel-map Admin/ops OpenAPI 계약 드리프트 게이트.

전체 Admin OpenAPI 산출물을 byte-for-byte vendor하고, provider ETL 화면이 호출하는
경로·인증·query와 dataset/pipeline 삼중항 응답 shape를 고정한다. Map의 무해한
비소비 필드 추가는 허용하되, Pinvi가 읽는 필드 제거·이름 회귀·타입 변경은 CI에서
즉시 실패해야 한다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

_SNAPSHOT = (
    Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-admin.json"
)
_UPSTREAM_COMMIT = "fa6d0d3d10456401993e12bb5f726abad4bce413"
_SNAPSHOT_SHA256 = "590f49d1c4abe6558cf46da5a4a4b6b787bb007c3194c07f343f97a3b6b8d9be"

_OPS_SECURITY = [{"AdminBFF": []}, {"OpsScope": [], "OpsToken": []}]
_CONSUMED_ENDPOINTS: dict[tuple[str, str], tuple[set[str], str]] = {
    ("/v1/ops/pipeline/overview", "get"): (
        {"run_limit", "X-Kor-Travel-Map-Ops-Scope"},
        "PipelineOverviewResponse",
    ),
    ("/v1/ops/datasets", "get"): (
        {"X-Kor-Travel-Map-Ops-Scope"},
        "OpsDatasetsGridResponse",
    ),
    ("/v1/ops/pipeline/executions", "get"): (
        {
            "kind",
            "status",
            "provider_dataset_id",
            "sync_scope",
            "operation_key",
            "load_batch_id",
            "parent_job_id",
            "created_from",
            "created_to",
            "page_size",
            "cursor",
            "X-Kor-Travel-Map-Ops-Scope",
        },
        "PipelineExecutionsListResponse",
    ),
    ("/v1/ops/pipeline/executions/{kind}/{execution_id}", "get"): (
        {
            "kind",
            "execution_id",
            "level",
            "page_size",
            "cursor",
            "X-Kor-Travel-Map-Ops-Scope",
        },
        "PipelineExecutionDetailResponse",
    ),
    ("/v1/ops/pipeline/executions/import_job/{execution_id}/cancel", "post"): (
        {"execution_id", "X-Kor-Travel-Map-Ops-Scope"},
        "PipelineCancellationResponse",
    ),
}

_REQUIRED_FIELDS: dict[str, set[str]] = {
    "OpsDatasetGridRow": {
        "provider_dataset_id",
        "provider",
        "dataset_key",
        "sync_scope",
        "operation_key",
        "status",
        "schedule",
        "latest_execution",
        "active_execution",
        "catalog",
        "dataset_issues",
    },
    "OpsDatasetCatalogInfo": {"is_active", "is_refreshable", "scope_refresh"},
    "OpsDatasetScopeRefreshCapability": {
        "supported",
        "selector",
        "effect",
        "default_sync_scope",
        "allowed_sync_scopes",
    },
    "OpsDatasetScheduleSummary": {
        "basis",
        "status",
        "schedule_names",
        "active_schedule_names",
        "next_scheduled_at",
    },
    "OpsDatasetExecution": {
        "operation_member_id",
        "sync_scope",
        "operation_key",
        "provider_datasets",
        "projected_job",
    },
    "OpsDatasetProviderDataset": {
        "provider_dataset_id",
        "sync_scope",
        "operation_key",
        "operation_member_id",
    },
    "PipelineExecutionRecord": {"provider_datasets", "operation_key"},
    "PipelineExecutionRootRecord": {
        "provider_datasets",
        "operation_key",
        "projected_job",
    },
    "PipelineImportJobRecord": {"provider_datasets", "operation_key"},
    "PipelineProjectedJobRecord": {"operation_key"},
    "PipelineProviderDatasetIdentityRecord": {
        "provider_dataset_id",
        "sync_scope",
        "operation_key",
        "operation_member_id",
    },
    "FeatureUpdateRequestRecord": {"scope", "dataset_memberships"},
    "FeatureUpdateDatasetMembership": {
        "provider_dataset_id",
        "sync_scope",
        "operation_key",
    },
}

_RETIRED_FIELDS: dict[str, set[str]] = {
    "OpsDatasetGridRow": {"provider_issues"},
    "OpsDatasetCatalogInfo": {"is_feature_load"},
    "OpsDatasetExecution": {"providers", "dataset_keys", "operation_registry_version"},
    "OpsDatasetProjectedJob": {"operation_registry_version"},
    "PipelineExecutionRecord": {
        "provider",
        "dataset_key",
        "providers",
        "dataset_keys",
        "operation_registry_version",
    },
    "PipelineExecutionRootRecord": {
        "providers",
        "dataset_keys",
        "operation_registry_version",
    },
    "PipelineImportJobRecord": {
        "provider",
        "dataset_key",
        "providers",
        "dataset_keys",
        "operation_registry_version",
    },
    "PipelineProjectedJobRecord": {"operation_registry_version"},
    "FeatureUpdateRequestRecord": {
        "providers",
        "dataset_keys",
        "requested_sync_scope",
        "effective_sync_scope",
    },
}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def test_admin_snapshot_is_exact_upstream_artifact() -> None:
    assert _UPSTREAM_COMMIT == "fa6d0d3d10456401993e12bb5f726abad4bce413"
    assert hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA256


@pytest.mark.parametrize(("path", "method"), _CONSUMED_ENDPOINTS)
def test_consumed_ops_endpoint_contract(spec: dict[str, Any], path: str, method: str) -> None:
    expected_parameters, response_schema = _CONSUMED_ENDPOINTS[(path, method)]
    operation = spec["paths"][path][method]

    assert operation["security"] == _OPS_SECURITY
    assert {parameter["name"] for parameter in operation.get("parameters", [])} == (
        expected_parameters
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": f"#/components/schemas/{response_schema}"
    }


def test_cancel_request_keeps_nullable_typed_body(spec: dict[str, Any]) -> None:
    operation = spec["paths"]["/v1/ops/pipeline/executions/import_job/{execution_id}/cancel"][
        "post"
    ]

    assert operation["requestBody"]["content"]["application/json"]["schema"]["anyOf"] == [
        {"$ref": "#/components/schemas/PipelineCancellationRequest"},
        {"type": "null"},
    ]


@pytest.mark.parametrize(("schema_name", "required_fields"), _REQUIRED_FIELDS.items())
def test_consumed_schema_requires_current_fields(
    spec: dict[str, Any], schema_name: str, required_fields: set[str]
) -> None:
    schema = spec["components"]["schemas"][schema_name]

    assert schema["additionalProperties"] is False
    assert required_fields <= set(schema["required"])
    assert required_fields <= set(schema["properties"])


@pytest.mark.parametrize(("schema_name", "retired_fields"), _RETIRED_FIELDS.items())
def test_consumed_schema_does_not_regress_to_retired_fields(
    spec: dict[str, Any], schema_name: str, retired_fields: set[str]
) -> None:
    properties = spec["components"]["schemas"][schema_name]["properties"]

    assert retired_fields.isdisjoint(properties)


def test_membership_arrays_link_to_exact_triple_schemas(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]

    assert schemas["OpsDatasetExecution"]["properties"]["provider_datasets"]["items"] == {
        "$ref": "#/components/schemas/OpsDatasetProviderDataset"
    }
    for schema_name in ("PipelineExecutionRecord", "PipelineExecutionRootRecord"):
        assert schemas[schema_name]["properties"]["provider_datasets"]["items"] == {
            "$ref": "#/components/schemas/PipelineProviderDatasetIdentityRecord"
        }
    assert schemas["FeatureUpdateRequestRecord"]["properties"]["dataset_memberships"]["items"] == {
        "$ref": "#/components/schemas/FeatureUpdateDatasetMembership"
    }


def test_ops_enums_keep_current_operation_semantics(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]

    assert schemas["OpsDatasetScheduleSummary"]["properties"]["basis"]["enum"] == [
        "dagster_operation_key_tag",
        "not_scheduled",
        "unknown",
    ]
    assert schemas["OpsDatasetScopeRefreshCapability"]["properties"]["effect"]["enum"] == [
        "dataset_wide",
        "sync_scope",
        "none",
    ]
    assert schemas["OpsDatasetCatalogInfo"]["properties"]["is_active"]["type"] == "boolean"
