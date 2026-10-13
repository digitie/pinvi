"""Pinvi가 소비하는 kor-travel-map Admin/ops OpenAPI 계약 드리프트 게이트.

전체 Admin OpenAPI 산출물을 byte-for-byte vendor하고, provider ETL 화면이 호출하는
경로·인증·query와 dataset/pipeline 삼중항 응답 shape를 고정한다. Map의 무해한
비소비 필드 추가는 허용하되, Pinvi가 읽는 필드 제거·이름 회귀·타입 변경은 CI에서
즉시 실패해야 한다.
"""

from __future__ import annotations

import hashlib
import json
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin

import pytest
from pydantic import BaseModel

from app.services import kor_travel_map_ops_projection as projection
from tests.unit._kor_travel_map_snapshot_pin import SNAPSHOT, SNAPSHOT_SHA256

_SNAPSHOT = SNAPSHOT
_SNAPSHOT_SHA256 = SNAPSHOT_SHA256

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

# Map ops 응답을 받는 Pinvi 모델은 `extra="forbid"`라, vendored 스냅샷의 property를 모델이
# 하나라도 모르면 Map이 그 값을 처음 non-null로 내는 순간 응답 전체가 502가 된다
# (2026-10-13 `ProviderRefreshPolicyRecord.provider_dataset_id`: Map #966이 2026-08-11 추가,
# PinVi는 #443/#574/#579 재vendor에서 모델을 따라가지 않았다). 그래서 위 `_REQUIRED_FIELDS`
# (스키마 ⊇ Pinvi가 읽는 필드)와 반대 방향 — 스키마 property ⊆ 모델 필드, 스키마 enum ⊆ 모델
# Literal, 스키마 nullable ⇒ 모델 nullable — 을 `_CanonicalModel`을 쓰는 모든 소비 스키마에
# 고정한다. 재vendor가 들어올 때 CI에서 먼저 빨개진다.
_CONSUMED_MODELS: dict[str, type[BaseModel]] = {
    "OpsDatasetsGridData": projection._DatasetsGridData,
    "OpsDatasetGridRow": projection._DatasetGridRow,
    "ProviderRefreshPolicyRecord": projection._RefreshPolicy,
    "OpsDatasetCatalogInfo": projection._DatasetCatalog,
    "OpsDatasetPreviewCapability": projection._DatasetPreviewCapability,
    "OpsDatasetScopeRefreshCapability": projection._DatasetScopeRefreshCapability,
    "OpsDatasetScheduleSummary": projection._DatasetSchedule,
    "OpsDatasetFreshness": projection._DatasetFreshness,
    "OpsDatasetExecution": projection._DatasetExecution,
    "OpsDatasetProjectedJob": projection._DatasetProjectedJob,
    "OpsDatasetProviderDataset": projection._ProviderDatasetIdentity,
    "OpsIssueSummary": projection._IssueSummary,
    "PipelineOverviewData": projection._PipelineOverviewData,
    "PipelineDagsterOverview": projection._PipelineDagsterOverview,
    "DagsterRunSummary": projection._DagsterRunSummary,
    "DagsterSensor": projection._DagsterSensor,
    "DagsterInstigationTick": projection._DagsterInstigationTick,
    "DagsterGraphqlError": projection._DagsterGraphqlError,
    "PipelineExecutionsData": projection._PipelineExecutionsData,
    "PipelineExecutionRootRecord": projection._PipelineExecutionRoot,
    "PipelineExecutionRecord": projection._PipelineExecutionRecord,
    "PipelineExecutionDetailData": projection._PipelineExecutionDetailData,
    "PipelineProjectedJobRecord": projection._ProjectedJob,
    "PipelineProviderDatasetIdentityRecord": projection._ProviderDatasetIdentity,
    "PipelineImportJobRecord": projection._PipelineImportJobIdentity,
    "FeatureUpdateRequestRecord": projection._PipelineUpdateRequestIdentity,
    "FeatureUpdateDatasetMembership": projection._FeatureUpdateDatasetMembership,
    "PageMeta": projection._PipelinePageMeta,
    "PipelineCancellationSummaryRecord": projection._CancellationSummary,
    "PipelineCancellationDetailRecord": projection._CancellationDetail,
    "PipelineCancellationRootRecord": projection._CancellationRoot,
    "PipelineCancellationMemberRecord": projection._CancellationMember,
    "PipelineCancellationRunRecord": projection._CancellationRun,
    "PipelineCancellationErrorRecord": projection._CancellationError,
}


def _schema_enum_and_nullable(
    spec: dict[str, Any], node: dict[str, Any]
) -> tuple[set[object] | None, bool]:
    """property 스키마(최상위 anyOf/$ref/enum/const만, items는 보지 않는다)의 enum 집합과 null 허용."""

    enum_values: set[object] | None = None
    nullable = False
    pending = [node]
    while pending:
        current = pending.pop()
        if "$ref" in current:
            pending.append(spec["components"]["schemas"][current["$ref"].rsplit("/", 1)[1]])
            continue
        if current.get("type") == "null":
            nullable = True
            continue
        if "enum" in current:
            enum_values = (enum_values or set()) | set(current["enum"])
            continue
        if "const" in current:
            enum_values = (enum_values or set()) | {current["const"]}
            continue
        pending.extend(current.get("anyOf", []))
        pending.extend(current.get("oneOf", []))
    return enum_values, nullable


def _model_literal_and_nullable(annotation: object) -> tuple[set[object] | None, bool]:
    literal_values: set[object] | None = None
    nullable = False
    pending = [annotation]
    while pending:
        current = pending.pop()
        origin = get_origin(current)
        if current is type(None):
            nullable = True
        elif origin is Literal:
            literal_values = (literal_values or set()) | set(get_args(current))
        elif origin is Union or origin is UnionType:
            pending.extend(get_args(current))
    return literal_values, nullable


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
    # 리비전 이중 핀(리뷰 강제 장치)은 admin 게이트 한 곳만 갖는다 —
    # tests/unit/_kor_travel_map_snapshot_pin.py docstring 참조.
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


@pytest.mark.parametrize(("schema_name", "model"), _CONSUMED_MODELS.items())
def test_consumed_model_accepts_every_snapshot_property(
    spec: dict[str, Any], schema_name: str, model: type[BaseModel]
) -> None:
    schema = spec["components"]["schemas"][schema_name]

    assert set(schema["properties"]) <= set(model.model_fields)
    for name, property_schema in schema["properties"].items():
        schema_enum, schema_nullable = _schema_enum_and_nullable(spec, property_schema)
        model_literal, model_nullable = _model_literal_and_nullable(
            model.model_fields[name].annotation
        )
        if schema_enum is not None and model_literal is not None:
            # Map이 enum member를 더하면 모델 Literal이 그 값을 거부한다 — 이름만 같아서는
            # 못 잡는 드리프트(2026-10-13 적대 리뷰).
            assert schema_enum <= model_literal, f"{schema_name}.{name}"
        if schema_nullable:
            assert model_nullable, f"{schema_name}.{name} is nullable in the Map contract"


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
