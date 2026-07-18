"""kor-travel-map canonical ops → Pinvi 표시 DTO 투영 계약 테스트."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.kor_travel_map_ops_projection import (
    KorTravelMapOpsContractError,
    project_dataset_grid,
    project_dataset_grid_snapshot,
    project_pipeline_cancellation,
    project_pipeline_execution,
    project_pipeline_executions,
    project_pipeline_page_next_cursor,
    validate_pipeline_overview,
)

ROOT_ID = "11111111-1111-4111-8111-111111111111"
PROJECTED_ID = "22222222-2222-4222-8222-222222222222"
CHILD_ID = "33333333-3333-4333-8333-333333333333"
CANCELLATION_ID = "44444444-4444-4444-8444-444444444444"


def _overview() -> dict[str, object]:
    return {
        "checked_at": "2026-07-18T00:00:00+09:00",
        "dagster": {
            "status": "ok",
            "dagster_url": "http://dagster.internal",
            "graphql_url": "http://dagster.internal/graphql",
            "version": "1.11.0",
            "run_counts": {"STARTED": 1},
            "recent_runs": [
                {
                    "run_id": "run-1",
                    "job_name": "provider_import",
                    "status": "STARTED",
                    "start_time": 1.0,
                    "end_time": None,
                    "update_time": 2.0,
                    "tags": {"provider": "kma"},
                }
            ],
            "schedule_count": 1,
            "sensor_count": 1,
            "sensors": [{"name": "refresh", "status": "RUNNING", "recent_ticks": []}],
            "errors": [],
        },
        "operations_by_status": {
            "queued": 0,
            "running": 1,
            "done": 2,
            "failed": 0,
            "cancelled": 0,
        },
        "active_operations": 1,
        "failed_operations_24h": 0,
    }


def _projected_job(progress: int) -> dict[str, object]:
    return {
        "id": PROJECTED_ID,
        "job_kind": "provider_import",
        "status": "running",
        "progress": progress,
        "current_stage": "normalize",
        "error_message": None,
        "created_at": "2026-07-18T00:00:00+09:00",
        "started_at": "2026-07-18T00:01:00+09:00",
        "finished_at": None,
        "dagster_run_id": "run-1",
        "dagster_run_status": "STARTED",
        "trigger_kind": "manual",
        "operation_registry_version": "1",
        "load_batch_id": None,
        "parent_job_id": None,
        "depth": 1,
        "detail_url": f"/v1/ops/pipeline/executions/import_job/{PROJECTED_ID}",
    }


def _execution(progress: int = 1) -> dict[str, object]:
    return {
        "kind": "import_job",
        "id": ROOT_ID,
        "status": "running",
        "created_at": "2026-07-18T00:00:00+09:00",
        "providers": ["kma"],
        "dataset_keys": ["special_days"],
        "provider_datasets": [
            {
                "provider": "kma",
                "dataset_key": "special_days",
                "sync_scope": None,
                "operation_member_id": PROJECTED_ID,
                "status": "running",
            }
        ],
        "progress": progress,
        "current_stage": "normalize",
        "scope_type": None,
        "priority": None,
        "run_mode": None,
        "operator": None,
        "error_message": None,
        "started_at": "2026-07-18T00:01:00+09:00",
        "finished_at": None,
        "dagster_run_id": "run-1",
        "dagster_run_status": "STARTED",
        "trigger_kind": "manual",
        "operation_registry_version": "1",
        "requested_job_id": None,
        "linked_job_count": 2,
        "projected_job": _projected_job(progress),
        "cancellation": None,
        "detail_url": f"/v1/ops/pipeline/executions/import_job/{ROOT_ID}",
    }


def _dataset_row() -> dict[str, object]:
    return {
        "provider": "kma",
        "dataset_key": "special_days",
        "detail_url": (
            "/v1/ops/datasets/detail?provider=kma&dataset_key=special_days&sync_scope=dataset_wide"
        ),
        "sync_scope": "dataset_wide",
        "status": "healthy",
        "last_success_at": "2026-07-18T00:00:00+09:00",
        "last_failure_at": None,
        "consecutive_failures": 0,
        "eligible_after": "2026-07-18T01:00:00+09:00",
        "freshness": {
            "state": "fresh",
            "basis": "policy_stale_after",
            "sla_seconds": 3600,
            "due_at": "2026-07-18T02:00:00+09:00",
            "is_overdue": False,
            "overdue_by_seconds": 0,
        },
        "schedule": {
            "source": "dagster_graphql",
            "basis": "dagster_definition_tags",
            "status": "RUNNING",
            "schedule_names": ["kma_schedule"],
            "active_schedule_names": ["kma_schedule"],
            "next_scheduled_at": "2026-07-19T03:30:00+09:00",
        },
        "latest_execution": None,
        "active_execution": None,
        "catalog_state": "canonical",
        "orphan_reason": None,
        "mutable": True,
        "catalog": {
            "feature_kind": "weather",
            "provider_state_default_scope": "daily",
            "label": "특일",
            "is_feature_load": True,
            "is_refreshable": True,
            "scope_refresh": {
                "supported": False,
                "selector": "none",
                "effect": "dataset_wide",
                "default_sync_scope": "dataset_wide",
                "allowed_sync_scopes": [],
                "reason": "이 dataset은 전체 dataset 단위로만 갱신합니다.",
            },
            "preview": {
                "supported": True,
                "sources": ["fixture"],
                "input_kind": "none",
                "default_max_items": 20,
                "max_items_limit": 100,
                "timeout_seconds": 5.0,
                "external_call_budget": 0,
            },
        },
        "refresh_policy": None,
        "dataset_issues": {"open_count": 0, "severity_counts": {}},
        "provider_issues": {"open_count": 0, "severity_counts": {}},
    }


def _dataset_grid() -> dict[str, object]:
    return {
        "items": [_dataset_row()],
        "schedule_source_status": "ok",
        "schedule_source_errors": [],
        "execution_coverage": "db_recorded_canonical_operations",
    }


def _cancellation() -> dict[str, object]:
    return {
        "cancellation_id": CANCELLATION_ID,
        "previous_cancellation_id": None,
        "root": {"kind": "update_request", "id": PROJECTED_ID},
        "status": "completed",
        "requested_at": "2026-07-18T00:02:00+09:00",
        "requested_by": "service:pinvi",
        "reason": "duplicate",
        "error": None,
        "updated_at": "2026-07-18T00:03:00+09:00",
        "finished_at": "2026-07-18T00:03:00+09:00",
        "retryable": False,
        "unresolved_member_count": 0,
        "members": [
            {
                "job_id": ROOT_ID,
                "dagster_run_id": "run-1",
                "operation_kind": "provider_import",
                "requires_run_termination": True,
                "initial_status": "running",
                "result": "cancelled",
                "terminal_status": "cancelled",
                "error": None,
                "updated_at": "2026-07-18T00:03:00+09:00",
            }
        ],
        "dagster_runs": [
            {
                "dagster_run_id": "run-1",
                "initial_status": "STARTED",
                "termination_reserved_at": "2026-07-18T00:02:30+09:00",
                "result": "cancelled",
                "terminal_status": "CANCELED",
                "error": None,
                "engine_started_at": "2026-07-18T00:02:30+09:00",
                "engine_finished_at": "2026-07-18T00:03:00+09:00",
                "updated_at": "2026-07-18T00:03:00+09:00",
            }
        ],
        "committed_data_rolled_back": False,
        "warnings": ["committed data is retained"],
    }


def _completed_cancellation_member(job_id: str, run_id: str) -> dict[str, object]:
    return {
        "job_id": job_id,
        "dagster_run_id": run_id,
        "operation_kind": "provider_import",
        "requires_run_termination": True,
        "initial_status": "running",
        "result": "cancelled",
        "terminal_status": "cancelled",
        "error": None,
        "updated_at": "2026-07-18T00:03:00+09:00",
    }


def _completed_cancellation_run(run_id: str) -> dict[str, object]:
    return {
        "dagster_run_id": run_id,
        "initial_status": "STARTED",
        "termination_reserved_at": "2026-07-18T00:02:30+09:00",
        "result": "cancelled",
        "terminal_status": "CANCELED",
        "error": None,
        "engine_started_at": "2026-07-18T00:02:30+09:00",
        "engine_finished_at": "2026-07-18T00:03:00+09:00",
        "updated_at": "2026-07-18T00:03:00+09:00",
    }


def _execution_detail() -> dict[str, object]:
    execution = _execution(progress=37)
    projected_job = execution["projected_job"]
    assert isinstance(projected_job, dict)
    projected_job["id"] = ROOT_ID
    projected_job["detail_url"] = f"/v1/ops/pipeline/executions/import_job/{ROOT_ID}"
    projected_job["depth"] = 0
    execution["linked_job_count"] = 1
    execution["provider_datasets"][0]["operation_member_id"] = ROOT_ID  # type: ignore[index]
    return {
        "execution": {
            "kind": "import_job",
            "id": ROOT_ID,
            "status": "running",
            "created_at": "2026-07-18T00:00:00+09:00",
            "job_kind": "provider_import",
            "provider": "kma",
            "dataset_key": "special_days",
            "progress": 37,
            "current_stage": "normalize",
            "scope_type": None,
            "priority": None,
            "run_mode": None,
            "operator": None,
            "error_message": None,
            "started_at": "2026-07-18T00:01:00+09:00",
            "finished_at": None,
            "dagster_run_id": "run-1",
            "dagster_run_status": "STARTED",
            "trigger_kind": "manual",
            "operation_registry_version": "1",
            "job_id": None,
            "request_id": None,
            "load_batch_id": None,
            "parent_job_id": None,
            "detail_url": f"/v1/ops/pipeline/executions/import_job/{ROOT_ID}",
        },
        "root": execution,
        "import_job": _import_job_detail(),
        "update_request": None,
        "cancellation": None,
        "events": [],
        "events_next_cursor": None,
    }


def _import_job_detail() -> dict[str, object]:
    return {
        "job_id": ROOT_ID,
        "kind": "provider_import",
        "load_batch_id": None,
        "parent_job_id": None,
        "payload": {"sync_scope": "dataset_wide"},
        "status": "running",
        "progress": 37,
        "current_stage": "normalize",
        "source_checksum": None,
        "error_message": None,
        "dagster_run_id": "run-1",
        "provider": "kma",
        "dataset_key": "special_days",
        "trigger_kind": "manual",
        "operation_registry_version": "1",
        "dagster_run_status": "STARTED",
        "created_at": "2026-07-18T00:00:00+09:00",
        "started_at": "2026-07-18T00:01:00+09:00",
        "finished_at": None,
        "heartbeat_at": "2026-07-18T00:02:00+09:00",
    }


def _update_request_detail() -> dict[str, object]:
    return {
        "request_id": PROJECTED_ID,
        "scope_type": "provider_dataset",
        "scope": {
            "type": "provider_dataset",
            "provider": "kma",
            "dataset_key": "special_days",
        },
        "requested_sync_scope": None,
        "effective_sync_scope": "dataset_wide",
        "providers": [],
        "dataset_keys": [],
        "update_policy": {"mode": "refresh"},
        "run_mode": "now",
        "priority": 100,
        "status": "running",
        "matched_scope": {},
        "job_id": ROOT_ID,
        "dagster_run_id": "run-1",
        "dispatch_requested_at": "2026-07-18T00:00:30+09:00",
        "operator": "service:pinvi",
        "reason": "refresh",
        "error_message": None,
        "created_at": "2026-07-18T00:00:00+09:00",
        "started_at": "2026-07-18T00:01:00+09:00",
        "finished_at": None,
        "generation": 1,
        "status_url": (f"/v1/ops/pipeline/executions/update_request/{PROJECTED_ID}"),
    }


def _as_update_request_detail() -> dict[str, object]:
    detail = _execution_detail()
    root = detail["root"]
    execution = detail["execution"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    root.update(
        {
            "kind": "update_request",
            "id": PROJECTED_ID,
            "requested_job_id": ROOT_ID,
            "scope_type": "provider_dataset",
            "priority": 100,
            "run_mode": "now",
            "operator": "service:pinvi",
            "progress": None,
            "current_stage": None,
            "dagster_run_status": None,
            "trigger_kind": "update_request",
            "operation_registry_version": None,
            "detail_url": (f"/v1/ops/pipeline/executions/update_request/{PROJECTED_ID}"),
        }
    )
    root["provider_datasets"][0]["sync_scope"] = "dataset_wide"  # type: ignore[index]
    execution["request_id"] = PROJECTED_ID
    detail["update_request"] = _update_request_detail()
    return detail


def _dataset_execution(
    *,
    status: str = "running",
    pair_status: str | None = None,
    sync_scope: str | None = "dataset_wide",
) -> dict[str, object]:
    root = _execution(progress=37)
    member = root["provider_datasets"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    member["sync_scope"] = sync_scope
    member["status"] = pair_status or status
    projected_job = deepcopy(root["projected_job"])
    assert isinstance(projected_job, dict)
    del projected_job["load_batch_id"]
    del projected_job["parent_job_id"]
    projected_job["status"] = pair_status or status
    return {
        "kind": root["kind"],
        "id": root["id"],
        "detail_url": root["detail_url"],
        "status": status,
        "pair_status": pair_status or status,
        "operation_member_id": PROJECTED_ID,
        "sync_scope": sync_scope,
        "providers": root["providers"],
        "dataset_keys": root["dataset_keys"],
        "provider_datasets": root["provider_datasets"],
        "created_at": root["created_at"],
        "started_at": root["started_at"],
        "finished_at": root["finished_at"],
        "dagster_run_id": root["dagster_run_id"],
        "dagster_run_status": root["dagster_run_status"],
        "trigger_kind": root["trigger_kind"],
        "operation_registry_version": root["operation_registry_version"],
        "error_message": root["error_message"],
        "projected_job": projected_job,
        "cancellation": None,
    }


def test_dataset_grid_keeps_rate_limit_and_schedule_times_separate() -> None:
    records = project_dataset_grid(_dataset_grid(), key="SPECIAL")

    assert len(records) == 1
    assert records[0].sync_scope == "dataset_wide"
    assert records[0].eligible_after.isoformat() == "2026-07-18T01:00:00+09:00"
    assert records[0].schedule_next_scheduled_at.isoformat() == "2026-07-19T03:30:00+09:00"


def test_dataset_grid_rejects_missing_schedule_source_contract() -> None:
    data = _dataset_grid()
    del data["execution_coverage"]

    with pytest.raises(KorTravelMapOpsContractError, match="dataset grid"):
        project_dataset_grid(data)


def test_dataset_grid_preserves_degraded_schedule_source_details() -> None:
    data = _dataset_grid()
    data["schedule_source_status"] = "unavailable"
    data["schedule_source_errors"] = ["Dagster GraphQL unavailable"]

    snapshot = project_dataset_grid_snapshot(data)

    assert snapshot.schedule_source_status == "unavailable"
    assert snapshot.schedule_source_errors == ["Dagster GraphQL unavailable"]


def test_dataset_grid_accepts_exact_active_member_scope() -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    row["active_execution"] = _dataset_execution()

    assert len(project_dataset_grid(data)) == 1


def test_dataset_grid_accepts_dataset_wide_nullable_execution_scope() -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    row["sync_scope"] = "dataset_wide"
    row["active_execution"] = _dataset_execution(sync_scope=None)

    assert len(project_dataset_grid(data)) == 1


def test_dataset_grid_rejects_duplicate_provider_dataset_members() -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    execution = _dataset_execution()
    duplicate = deepcopy(execution["provider_datasets"][0])  # type: ignore[index]
    duplicate["sync_scope"] = "target_grids"
    duplicate["operation_member_id"] = CHILD_ID
    execution["provider_datasets"].append(duplicate)  # type: ignore[union-attr]
    row["active_execution"] = execution

    with pytest.raises(KorTravelMapOpsContractError, match="dataset grid"):
        project_dataset_grid(data)


def test_dataset_grid_rejects_execution_scope_outside_selected_member() -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    execution = _dataset_execution()
    execution["sync_scope"] = "target_grids"
    row["active_execution"] = execution

    with pytest.raises(KorTravelMapOpsContractError, match="dataset grid"):
        project_dataset_grid(data)


@pytest.mark.parametrize(
    ("slot", "status"),
    [("active_execution", "done"), ("latest_execution", "running")],
)
def test_dataset_grid_rejects_wrong_execution_lifecycle_class(
    slot: str,
    status: str,
) -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    row[slot] = _dataset_execution(status=status)

    with pytest.raises(KorTravelMapOpsContractError, match="dataset grid"):
        project_dataset_grid(data)


def test_dataset_grid_classifies_execution_by_pair_status() -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    row["active_execution"] = _dataset_execution(status="done", pair_status="running")
    row["latest_execution"] = _dataset_execution(status="running", pair_status="failed")
    row["latest_execution"]["id"] = CHILD_ID  # type: ignore[index]
    row["latest_execution"]["detail_url"] = (  # type: ignore[index]
        f"/v1/ops/pipeline/executions/import_job/{CHILD_ID}"
    )
    row["latest_execution"]["operation_member_id"] = CHILD_ID  # type: ignore[index]
    row["latest_execution"]["provider_datasets"][0][  # type: ignore[index]
        "operation_member_id"
    ] = CHILD_ID

    assert len(project_dataset_grid(data)) == 1


def test_dataset_grid_rejects_same_operation_in_active_and_latest() -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    row["active_execution"] = _dataset_execution()
    row["latest_execution"] = _dataset_execution(status="running", pair_status="failed")

    with pytest.raises(KorTravelMapOpsContractError, match="dataset grid"):
        project_dataset_grid(data)


@pytest.mark.parametrize(
    "drift",
    [
        "detail_url",
        "selector_none_allowed_scope",
        "selector_none_reason",
        "preview_sources",
        "canonical_without_catalog",
        "orphan_with_catalog",
        "nonrefreshable_scoped_selector",
    ],
)
def test_dataset_grid_rejects_capability_and_identity_drift(drift: str) -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    catalog = row["catalog"]
    assert isinstance(catalog, dict)
    if drift == "detail_url":
        row["detail_url"] = "/v1/ops/datasets/detail?provider=kma"
    elif drift == "selector_none_allowed_scope":
        catalog["scope_refresh"]["allowed_sync_scopes"] = ["dataset_wide"]  # type: ignore[index]
    elif drift == "selector_none_reason":
        catalog["scope_refresh"]["reason"] = None  # type: ignore[index]
    elif drift == "preview_sources":
        catalog["preview"]["sources"] = []  # type: ignore[index]
    elif drift == "canonical_without_catalog":
        row["catalog"] = None
    elif drift == "orphan_with_catalog":
        row.update(
            {
                "catalog_state": "orphan",
                "orphan_reason": "catalog_missing_with_sync_state",
                "mutable": False,
            }
        )
    else:
        catalog["is_refreshable"] = False
        catalog["scope_refresh"] = {
            "supported": True,
            "selector": "poi_cache_targets",
            "effect": "sync_scope",
            "default_sync_scope": "target_grids",
            "allowed_sync_scopes": ["target_grids"],
            "reason": None,
        }

    with pytest.raises(KorTravelMapOpsContractError, match="dataset grid"):
        project_dataset_grid(data)


def test_dataset_grid_accepts_canonical_poi_scope_capability() -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    row["catalog"]["scope_refresh"] = {  # type: ignore[index]
        "supported": True,
        "selector": "poi_cache_targets",
        "effect": "sync_scope",
        "default_sync_scope": "target_grids",
        "allowed_sync_scopes": ["target_grids", "external_system:pinvi"],
        "reason": None,
    }

    assert len(project_dataset_grid(data)) == 1


@pytest.mark.parametrize("invalid_scope", ["default", "daily", "external_system:"])
def test_dataset_grid_rejects_noncanonical_row_scope(invalid_scope: str) -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    row["sync_scope"] = invalid_scope
    row["detail_url"] = (
        f"/v1/ops/datasets/detail?provider=kma&dataset_key=special_days&sync_scope={invalid_scope}"
    )

    with pytest.raises(KorTravelMapOpsContractError, match="dataset grid"):
        project_dataset_grid(data)


def test_dataset_grid_rejects_dataset_wide_in_poi_allowed_scopes() -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    row["catalog"]["scope_refresh"] = {  # type: ignore[index]
        "supported": True,
        "selector": "poi_cache_targets",
        "effect": "sync_scope",
        "default_sync_scope": "target_grids",
        "allowed_sync_scopes": ["target_grids", "dataset_wide"],
        "reason": None,
    }

    with pytest.raises(KorTravelMapOpsContractError, match="dataset grid"):
        project_dataset_grid(data)


def test_dataset_grid_rejects_selected_projected_job_status_drift() -> None:
    data = _dataset_grid()
    row = data["items"][0]  # type: ignore[index]
    assert isinstance(row, dict)
    execution = _dataset_execution()
    execution["projected_job"]["status"] = "done"  # type: ignore[index]
    row["active_execution"] = execution

    with pytest.raises(KorTravelMapOpsContractError, match="dataset grid"):
        project_dataset_grid(data)


@pytest.mark.parametrize("progress", [0, 1, 100])
def test_pipeline_execution_preserves_direct_integer_percent(progress: int) -> None:
    record = project_pipeline_executions(
        {
            "items": [_execution(progress)],
            "canonical_url": "/v1/ops/pipeline/executions?kind=import_job",
        },
        expected_canonical_url="/v1/ops/pipeline/executions?kind=import_job",
    )[0]

    assert record.job_id == ROOT_ID
    assert record.kind == "import_job"
    assert record.progress == progress
    assert record.projected_job_id == PROJECTED_ID
    assert record.projected_job_kind == "provider_import"
    assert record.projected_job_progress == progress


def test_pipeline_execution_detail_uses_same_strict_projection() -> None:
    record = project_pipeline_execution(_execution_detail(), requested_job_id=ROOT_ID)

    assert record.job_id == ROOT_ID
    assert record.progress == 37
    assert record.status_url == f"/v1/ops/pipeline/executions/import_job/{ROOT_ID}"


def test_pipeline_execution_detail_preserves_matching_cancellation_overlay() -> None:
    detail = _execution_detail()
    cancellation = _cancellation()
    cancellation["root"] = {"kind": "import_job", "id": ROOT_ID}
    detail["cancellation"] = cancellation
    root = detail["root"]
    assert isinstance(root, dict)
    root["cancellation"] = {
        "cancellation_id": CANCELLATION_ID,
        "status": "completed",
        "requested_at": "2026-07-18T00:02:00+09:00",
        "requested_by": "service:pinvi",
        "reason": "duplicate",
        "retryable": False,
        "unresolved_member_count": 0,
    }

    record = project_pipeline_execution(detail, requested_job_id=ROOT_ID)

    assert record.cancellation is not None
    assert record.cancellation.status == "completed"


def test_pipeline_execution_detail_accepts_retry_subset_without_resolved_root() -> None:
    detail = _execution_detail()
    cancellation = _cancellation()
    cancellation.update(
        {
            "previous_cancellation_id": PROJECTED_ID,
            "root": {"kind": "import_job", "id": ROOT_ID},
        }
    )
    cancellation["members"][0]["job_id"] = CHILD_ID  # type: ignore[index]
    detail["cancellation"] = cancellation
    root = detail["root"]
    assert isinstance(root, dict)
    root["linked_job_count"] = 2
    root["cancellation"] = {
        "cancellation_id": CANCELLATION_ID,
        "status": "completed",
        "requested_at": "2026-07-18T00:02:00+09:00",
        "requested_by": "service:pinvi",
        "reason": "duplicate",
        "retryable": False,
        "unresolved_member_count": 0,
    }

    record = project_pipeline_execution(detail, requested_job_id=ROOT_ID)

    assert record.cancellation is not None
    assert record.cancellation.status == "completed"


@pytest.mark.parametrize(
    "drift",
    [
        "execution_id",
        "execution_detail_url",
        "import_job_id",
        "standalone_request_id",
    ],
)
def test_pipeline_execution_detail_rejects_impossible_requested_identity(
    drift: str,
) -> None:
    detail = _execution_detail()
    execution = detail["execution"]
    import_job = detail["import_job"]
    assert isinstance(execution, dict)
    assert isinstance(import_job, dict)
    if drift == "execution_id":
        execution["id"] = PROJECTED_ID
    elif drift == "execution_detail_url":
        execution["detail_url"] = f"/v1/ops/pipeline/executions/import_job/{PROJECTED_ID}"
    elif drift == "import_job_id":
        import_job["job_id"] = PROJECTED_ID
    else:
        execution["request_id"] = PROJECTED_ID

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_pipeline_execution_detail_rejects_wrong_requested_path_identity() -> None:
    with pytest.raises(KorTravelMapOpsContractError, match="requested job"):
        project_pipeline_execution(_execution_detail(), requested_job_id=PROJECTED_ID)


def test_pipeline_execution_detail_rejects_partial_import_job_fixture() -> None:
    detail = _execution_detail()
    detail["import_job"] = {
        "job_id": ROOT_ID,
        "provider": "kma",
        "dataset_key": "special_days",
    }

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("job_kind", "other_import"),
        ("status", "queued"),
        ("created_at", "2026-07-17T00:00:00+09:00"),
        ("progress", 38),
        ("current_stage", "fetch"),
        ("error_message", "boom"),
        ("started_at", None),
        ("finished_at", "2026-07-18T00:03:00+09:00"),
        ("dagster_run_id", "run-2"),
        ("dagster_run_status", "SUCCESS"),
        ("trigger_kind", "scheduled"),
        ("operation_registry_version", "2"),
        ("load_batch_id", "55555555-5555-4555-8555-555555555555"),
        ("parent_job_id", "66666666-6666-4666-8666-666666666666"),
    ],
)
def test_pipeline_execution_detail_rejects_import_lifecycle_drift(
    field: str,
    value: object,
) -> None:
    detail = _execution_detail()
    execution = detail["execution"]
    assert isinstance(execution, dict)
    execution[field] = value

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "queued"),
        ("created_at", "2026-07-17T00:00:00+09:00"),
        ("progress", 38),
        ("current_stage", "fetch"),
        ("error_message", "boom"),
        ("started_at", None),
        ("finished_at", "2026-07-18T00:03:00+09:00"),
        ("dagster_run_id", "run-2"),
        ("dagster_run_status", "SUCCESS"),
        ("trigger_kind", "scheduled"),
        ("operation_registry_version", "2"),
    ],
)
def test_pipeline_execution_detail_rejects_standalone_root_lifecycle_drift(
    field: str,
    value: object,
) -> None:
    detail = _execution_detail()
    root = detail["root"]
    assert isinstance(root, dict)
    root[field] = value

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_pipeline_execution_detail_rejects_import_scope_outside_root() -> None:
    detail = _execution_detail()
    import_job = detail["import_job"]
    assert isinstance(import_job, dict)
    import_job["dataset_key"] = "impossible_dataset"

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_pipeline_execution_detail_does_not_bind_import_payload_scope_to_root() -> None:
    detail = _execution_detail()
    import_job = detail["import_job"]
    assert isinstance(import_job, dict)
    import_job["payload"] = {"sync_scope": "target_grids"}

    record = project_pipeline_execution(detail, requested_job_id=ROOT_ID)

    assert record.job_id == ROOT_ID


def test_pipeline_execution_detail_rejects_cancellation_member_drift() -> None:
    detail = _execution_detail()
    cancellation = _cancellation()
    cancellation["root"] = {"kind": "import_job", "id": ROOT_ID}
    cancellation["members"][0]["job_id"] = PROJECTED_ID  # type: ignore[index]
    detail["cancellation"] = cancellation
    root = detail["root"]
    assert isinstance(root, dict)
    root["cancellation"] = {
        "cancellation_id": CANCELLATION_ID,
        "status": "completed",
        "requested_at": "2026-07-18T00:02:00+09:00",
        "requested_by": "service:pinvi",
        "reason": "duplicate",
        "retryable": False,
        "unresolved_member_count": 0,
    }

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


@pytest.mark.parametrize("missing", ["anchor", "exposed_member"])
def test_pipeline_execution_detail_rejects_frozen_topology_substitution(
    missing: str,
) -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    execution = detail["execution"]
    import_job = detail["import_job"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    assert isinstance(import_job, dict)
    unrelated_id = "55555555-5555-4555-8555-555555555555"
    requested_job_id = ROOT_ID
    if missing == "anchor":
        root["linked_job_count"] = 2
        execution.update(
            {
                "id": CHILD_ID,
                "detail_url": (f"/v1/ops/pipeline/executions/import_job/{CHILD_ID}"),
            }
        )
        import_job.update(
            {
                "job_id": CHILD_ID,
                "parent_job_id": ROOT_ID,
            }
        )
        requested_job_id = CHILD_ID
        frozen_ids = [CHILD_ID, unrelated_id]
    else:
        root["provider_datasets"].append(  # type: ignore[union-attr]
            {
                "provider": "visitkorea",
                "dataset_key": "places",
                "sync_scope": "target_grids",
                "operation_member_id": CHILD_ID,
                "status": "running",
            }
        )
        root["linked_job_count"] = 2
        frozen_ids = [ROOT_ID, unrelated_id]
    cancellation = _cancellation()
    cancellation["members"] = [
        _completed_cancellation_member(frozen_ids[0], "run-1"),
        _completed_cancellation_member(frozen_ids[1], "run-2"),
    ]
    cancellation["dagster_runs"] = [
        _completed_cancellation_run("run-1"),
        _completed_cancellation_run("run-2"),
    ]
    detail["cancellation"] = cancellation
    root["cancellation"] = {
        "cancellation_id": CANCELLATION_ID,
        "status": "completed",
        "requested_at": "2026-07-18T00:02:00+09:00",
        "requested_by": "service:pinvi",
        "reason": "duplicate",
        "retryable": False,
        "unresolved_member_count": 0,
    }

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=requested_job_id)


def test_import_job_detail_keeps_requested_job_when_canonical_root_is_update_request() -> None:
    detail = _execution_detail()
    root = detail["root"]
    assert isinstance(root, dict)
    root["kind"] = "update_request"
    root["id"] = PROJECTED_ID
    root["requested_job_id"] = ROOT_ID
    root["scope_type"] = "provider_dataset"
    root["priority"] = 100
    root["run_mode"] = "now"
    root["operator"] = "service:pinvi"
    root["progress"] = None
    root["current_stage"] = None
    root["dagster_run_status"] = None
    root["trigger_kind"] = "update_request"
    root["operation_registry_version"] = None
    root["provider_datasets"][0]["sync_scope"] = "dataset_wide"  # type: ignore[index]
    root["detail_url"] = f"/v1/ops/pipeline/executions/update_request/{PROJECTED_ID}"
    projected_job = root["projected_job"]
    assert isinstance(projected_job, dict)
    projected_job["id"] = ROOT_ID
    projected_job["detail_url"] = f"/v1/ops/pipeline/executions/import_job/{ROOT_ID}"
    execution = detail["execution"]
    assert isinstance(execution, dict)
    execution["request_id"] = PROJECTED_ID
    detail["update_request"] = _update_request_detail()

    record = project_pipeline_execution(detail, requested_job_id=ROOT_ID)

    assert record.job_id == ROOT_ID
    assert record.payload["root_kind"] == "update_request"
    assert record.payload["root_id"] == PROJECTED_ID


def test_import_job_detail_rejects_update_request_reciprocal_job_drift() -> None:
    detail = _execution_detail()
    root = detail["root"]
    execution = detail["execution"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    root["kind"] = "update_request"
    root["id"] = PROJECTED_ID
    root["requested_job_id"] = ROOT_ID
    root["detail_url"] = f"/v1/ops/pipeline/executions/update_request/{PROJECTED_ID}"
    execution["request_id"] = PROJECTED_ID
    update_request = _update_request_detail()
    update_request["job_id"] = PROJECTED_ID
    detail["update_request"] = update_request

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    "drift",
    [
        "providers",
        "dataset_keys",
        "scope_provider",
        "requested_sync_scope",
        "effective_sync_scope",
        "effective_sync_scope_null",
        "raw_alias_scope",
        "raw_random_scope",
        "provider_filter",
        "dataset_filter",
        "root_sync_scope",
    ],
)
def test_import_job_detail_rejects_update_request_scope_topology_drift(
    drift: str,
) -> None:
    detail = _execution_detail()
    root = detail["root"]
    execution = detail["execution"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    root["kind"] = "update_request"
    root["id"] = PROJECTED_ID
    root["requested_job_id"] = ROOT_ID
    root["scope_type"] = "provider_dataset"
    root["priority"] = 100
    root["run_mode"] = "now"
    root["operator"] = "service:pinvi"
    root["progress"] = None
    root["current_stage"] = None
    root["dagster_run_status"] = None
    root["trigger_kind"] = "update_request"
    root["operation_registry_version"] = None
    root["provider_datasets"][0]["sync_scope"] = "dataset_wide"  # type: ignore[index]
    root["detail_url"] = f"/v1/ops/pipeline/executions/update_request/{PROJECTED_ID}"
    execution["request_id"] = PROJECTED_ID
    update_request = _update_request_detail()
    detail["update_request"] = update_request

    if drift == "providers":
        update_request["providers"] = ["visitkorea"]
    elif drift == "dataset_keys":
        update_request["dataset_keys"] = ["places"]
    elif drift == "scope_provider":
        update_request["scope"]["provider"] = "visitkorea"  # type: ignore[index]
    elif drift == "requested_sync_scope":
        update_request["requested_sync_scope"] = "target_grids"
    elif drift == "effective_sync_scope":
        update_request["effective_sync_scope"] = "target_grids"
    elif drift == "effective_sync_scope_null":
        update_request["effective_sync_scope"] = None
    elif drift == "raw_alias_scope":
        update_request["scope"]["sync_scope"] = "default"  # type: ignore[index]
        update_request["requested_sync_scope"] = "default"
    elif drift == "raw_random_scope":
        update_request["scope"]["sync_scope"] = "random"  # type: ignore[index]
        update_request["requested_sync_scope"] = "random"
    elif drift == "provider_filter":
        update_request["providers"] = ["kma"]
    elif drift == "dataset_filter":
        update_request["dataset_keys"] = ["special_days"]
    else:
        root["provider_datasets"][0]["sync_scope"] = "target_grids"  # type: ignore[index]

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_import_job_detail_accepts_selector_none_effective_scope() -> None:
    detail = _execution_detail()
    root = detail["root"]
    execution = detail["execution"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    root.update(
        {
            "kind": "update_request",
            "id": PROJECTED_ID,
            "requested_job_id": ROOT_ID,
            "scope_type": "provider_dataset",
            "priority": 100,
            "run_mode": "now",
            "operator": "service:pinvi",
            "progress": None,
            "current_stage": None,
            "dagster_run_status": None,
            "trigger_kind": "update_request",
            "operation_registry_version": None,
            "detail_url": (f"/v1/ops/pipeline/executions/update_request/{PROJECTED_ID}"),
        }
    )
    root["provider_datasets"][0]["sync_scope"] = "dataset_wide"  # type: ignore[index]
    execution["request_id"] = PROJECTED_ID
    detail["update_request"] = _update_request_detail()

    record = project_pipeline_execution(detail, requested_job_id=ROOT_ID)

    assert record.payload["root_kind"] == "update_request"


def test_import_job_detail_accepts_explicit_canonical_scope() -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    update_request = detail["update_request"]
    assert isinstance(root, dict)
    assert isinstance(update_request, dict)
    update_request["scope"]["sync_scope"] = "target_grids"  # type: ignore[index]
    update_request["requested_sync_scope"] = "target_grids"
    update_request["effective_sync_scope"] = "target_grids"
    root["provider_datasets"][0]["sync_scope"] = "target_grids"  # type: ignore[index]

    record = project_pipeline_execution(detail, requested_job_id=ROOT_ID)

    assert record.job_id == ROOT_ID


def test_import_job_detail_accepts_update_root_with_child_provider_pairs() -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    assert isinstance(root, dict)
    root["provider_datasets"].append(  # type: ignore[union-attr]
        {
            "provider": "visitkorea",
            "dataset_key": "places",
            "sync_scope": "target_grids",
            "operation_member_id": CHILD_ID,
            "status": "running",
        }
    )
    root["providers"] = ["kma", "visitkorea"]
    root["dataset_keys"] = ["places", "special_days"]
    root["linked_job_count"] = 2

    record = project_pipeline_execution(detail, requested_job_id=ROOT_ID)

    assert record.job_id == ROOT_ID
    assert record.payload["root_id"] == PROJECTED_ID


@pytest.mark.parametrize("drift", ["missing_child_vector", "unrelated_vector"])
def test_provider_dataset_root_rejects_effective_vector_drift(drift: str) -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    assert isinstance(root, dict)
    root["provider_datasets"].append(  # type: ignore[union-attr]
        {
            "provider": "visitkorea",
            "dataset_key": "places",
            "sync_scope": "target_grids",
            "operation_member_id": CHILD_ID,
            "status": "running",
        }
    )
    root["providers"] = ["kma", "visitkorea"]
    root["dataset_keys"] = ["places", "special_days"]
    root["linked_job_count"] = 2
    if drift == "missing_child_vector":
        root["providers"] = ["kma"]
        root["dataset_keys"] = ["special_days"]
    else:
        root["providers"].append("unrelated-provider")  # type: ignore[union-attr]
        root["dataset_keys"].append("unrelated-dataset")  # type: ignore[union-attr]

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_import_job_detail_accepts_non_exact_root_filters_without_pair_projection() -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    execution = detail["execution"]
    import_job = detail["import_job"]
    update_request = detail["update_request"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    assert isinstance(import_job, dict)
    assert isinstance(update_request, dict)
    root.update(
        {
            "scope_type": "feature_ids",
            "providers": ["kma", "visitkorea"],
            "dataset_keys": ["places", "special_days"],
            "provider_datasets": [],
        }
    )
    execution.update({"provider": None, "dataset_key": None})
    import_job.update({"provider": None, "dataset_key": None})
    update_request.update(
        {
            "scope_type": "feature_ids",
            "scope": {"type": "feature_ids", "feature_ids": ["feature-1"]},
            "requested_sync_scope": None,
            "effective_sync_scope": None,
            "providers": ["kma", "visitkorea"],
            "dataset_keys": ["places", "special_days"],
        }
    )

    record = project_pipeline_execution(detail, requested_job_id=ROOT_ID)

    assert record.job_id == ROOT_ID
    assert record.payload["root_id"] == PROJECTED_ID


def test_import_job_detail_accepts_non_exact_filter_and_representative_union() -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    execution = detail["execution"]
    import_job = detail["import_job"]
    update_request = detail["update_request"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    assert isinstance(import_job, dict)
    assert isinstance(update_request, dict)
    root.update(
        {
            "scope_type": "feature_ids",
            "providers": ["filter-provider", "kma"],
            "dataset_keys": ["filter-dataset", "special_days"],
        }
    )
    root["provider_datasets"][0]["sync_scope"] = None  # type: ignore[index]
    root["provider_datasets"][0]["operation_member_id"] = CHILD_ID  # type: ignore[index]
    root["linked_job_count"] = 2
    execution.update({"provider": None, "dataset_key": None})
    import_job.update({"provider": None, "dataset_key": None})
    update_request.update(
        {
            "scope_type": "feature_ids",
            "scope": {"type": "feature_ids", "feature_ids": ["feature-1"]},
            "requested_sync_scope": None,
            "effective_sync_scope": None,
            "providers": ["filter-provider"],
            "dataset_keys": ["filter-dataset"],
        }
    )

    record = project_pipeline_execution(detail, requested_job_id=ROOT_ID)

    assert record.job_id == ROOT_ID


@pytest.mark.parametrize("drift", ["missing_representative", "unrelated_vector"])
def test_import_job_detail_rejects_non_exact_effective_vector_drift(
    drift: str,
) -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    execution = detail["execution"]
    import_job = detail["import_job"]
    update_request = detail["update_request"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    assert isinstance(import_job, dict)
    assert isinstance(update_request, dict)
    root.update(
        {
            "scope_type": "feature_ids",
            "providers": ["filter-provider", "kma"],
            "dataset_keys": ["filter-dataset", "special_days"],
        }
    )
    root["provider_datasets"][0]["sync_scope"] = None  # type: ignore[index]
    root["provider_datasets"][0]["operation_member_id"] = CHILD_ID  # type: ignore[index]
    root["linked_job_count"] = 2
    execution.update({"provider": None, "dataset_key": None})
    import_job.update({"provider": None, "dataset_key": None})
    update_request.update(
        {
            "scope_type": "feature_ids",
            "scope": {"type": "feature_ids", "feature_ids": ["feature-1"]},
            "requested_sync_scope": None,
            "effective_sync_scope": None,
            "providers": ["filter-provider"],
            "dataset_keys": ["filter-dataset"],
        }
    )
    if drift == "missing_representative":
        root["providers"] = ["filter-provider"]
        root["dataset_keys"] = ["filter-dataset"]
    else:
        root["providers"].append("unrelated-provider")  # type: ignore[union-attr]
        root["dataset_keys"].append("unrelated-dataset")  # type: ignore[union-attr]

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_import_job_detail_accepts_nonrepresentative_same_pair_child() -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    execution = detail["execution"]
    import_job = detail["import_job"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    assert isinstance(import_job, dict)
    root["linked_job_count"] = 2
    execution.update(
        {
            "id": CHILD_ID,
            "parent_job_id": ROOT_ID,
            "detail_url": f"/v1/ops/pipeline/executions/import_job/{CHILD_ID}",
        }
    )
    import_job.update(
        {
            "job_id": CHILD_ID,
            "parent_job_id": ROOT_ID,
        }
    )

    record = project_pipeline_execution(detail, requested_job_id=CHILD_ID)

    assert record.job_id == CHILD_ID
    assert root["provider_datasets"][0]["operation_member_id"] == ROOT_ID  # type: ignore[index]


def test_standalone_arbitrary_depth_descendant_keeps_ancestor_lifecycle_separate() -> None:
    detail = _execution_detail()
    root = detail["root"]
    execution = detail["execution"]
    import_job = detail["import_job"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    assert isinstance(import_job, dict)
    root["linked_job_count"] = 3
    execution.update(
        {
            "id": CHILD_ID,
            "parent_job_id": "66666666-6666-4666-8666-666666666666",
            "status": "queued",
            "progress": 0,
            "current_stage": None,
            "started_at": None,
            "dagster_run_id": None,
            "dagster_run_status": None,
            "detail_url": f"/v1/ops/pipeline/executions/import_job/{CHILD_ID}",
        }
    )
    import_job.update(
        {
            "job_id": CHILD_ID,
            "parent_job_id": "66666666-6666-4666-8666-666666666666",
            "status": "queued",
            "progress": 0,
            "current_stage": None,
            "started_at": None,
            "dagster_run_id": None,
            "dagster_run_status": None,
        }
    )

    record = project_pipeline_execution(detail, requested_job_id=CHILD_ID)

    assert record.job_id == CHILD_ID
    assert record.status == "queued"
    assert record.payload["root_id"] == ROOT_ID


def test_standalone_unlinked_execution_cannot_claim_another_root() -> None:
    detail = _execution_detail()
    root = detail["root"]
    execution = detail["execution"]
    import_job = detail["import_job"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    assert isinstance(import_job, dict)
    root["linked_job_count"] = 2
    execution["id"] = CHILD_ID
    execution["detail_url"] = f"/v1/ops/pipeline/executions/import_job/{CHILD_ID}"
    import_job["job_id"] = CHILD_ID
    import_job["parent_job_id"] = None

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=CHILD_ID)


def test_import_job_detail_rejects_duplicate_provider_dataset_pair() -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    assert isinstance(root, dict)
    duplicate = deepcopy(root["provider_datasets"][0])  # type: ignore[index]
    duplicate["sync_scope"] = "target_grids"
    duplicate["operation_member_id"] = CHILD_ID
    root["provider_datasets"].append(duplicate)  # type: ignore[union-attr]
    root["linked_job_count"] = 2

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_import_job_detail_accepts_requested_child_execution() -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    execution = detail["execution"]
    import_job = detail["import_job"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    assert isinstance(import_job, dict)
    root["provider_datasets"].append(  # type: ignore[union-attr]
        {
            "provider": "visitkorea",
            "dataset_key": "places",
            "sync_scope": "target_grids",
            "operation_member_id": CHILD_ID,
            "status": "running",
        }
    )
    root["providers"] = ["kma", "visitkorea"]
    root["dataset_keys"] = ["places", "special_days"]
    root["linked_job_count"] = 2
    execution.update(
        {
            "id": CHILD_ID,
            "provider": "visitkorea",
            "dataset_key": "places",
            "detail_url": (f"/v1/ops/pipeline/executions/import_job/{CHILD_ID}"),
        }
    )
    import_job.update(
        {
            "job_id": CHILD_ID,
            "provider": "visitkorea",
            "dataset_key": "places",
        }
    )

    record = project_pipeline_execution(detail, requested_job_id=CHILD_ID)

    assert record.job_id == CHILD_ID
    assert record.payload["root_id"] == PROJECTED_ID
    assert record.projected_job_id == ROOT_ID


@pytest.mark.parametrize("invalid_scope", [None, "default", "random"])
def test_import_job_detail_rejects_noncanonical_direct_member_scope(
    invalid_scope: str | None,
) -> None:
    detail = _execution_detail()
    root = detail["root"]
    execution = detail["execution"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    root.update(
        {
            "kind": "update_request",
            "id": PROJECTED_ID,
            "requested_job_id": ROOT_ID,
            "scope_type": "provider_dataset",
            "priority": 100,
            "run_mode": "now",
            "operator": "service:pinvi",
            "progress": None,
            "current_stage": None,
            "dagster_run_status": None,
            "trigger_kind": "update_request",
            "operation_registry_version": None,
            "detail_url": (f"/v1/ops/pipeline/executions/update_request/{PROJECTED_ID}"),
        }
    )
    root["provider_datasets"][0]["sync_scope"] = invalid_scope  # type: ignore[index]
    execution["request_id"] = PROJECTED_ID
    detail["update_request"] = _update_request_detail()

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "queued"),
        ("created_at", "2026-07-17T00:00:00+09:00"),
        ("priority", 99),
        ("run_mode", "queued"),
        ("operator", "service:other"),
        ("error_message", "boom"),
        ("started_at", None),
        ("finished_at", "2026-07-18T00:03:00+09:00"),
        ("dagster_run_id", "run-2"),
        ("progress", 1),
        ("current_stage", "fetch"),
        ("dagster_run_status", "STARTED"),
        ("trigger_kind", "manual"),
        ("operation_registry_version", "1"),
    ],
)
def test_pipeline_execution_detail_rejects_update_root_lifecycle_drift(
    field: str,
    value: object,
) -> None:
    detail = _execution_detail()
    root = detail["root"]
    execution = detail["execution"]
    assert isinstance(root, dict)
    assert isinstance(execution, dict)
    root.update(
        {
            "kind": "update_request",
            "id": PROJECTED_ID,
            "requested_job_id": ROOT_ID,
            "scope_type": "provider_dataset",
            "priority": 100,
            "run_mode": "now",
            "operator": "service:pinvi",
            "progress": None,
            "current_stage": None,
            "dagster_run_status": None,
            "trigger_kind": "update_request",
            "operation_registry_version": None,
            "detail_url": (f"/v1/ops/pipeline/executions/update_request/{PROJECTED_ID}"),
        }
    )
    root["provider_datasets"][0]["sync_scope"] = "dataset_wide"  # type: ignore[index]
    root[field] = value
    execution["request_id"] = PROJECTED_ID
    detail["update_request"] = _update_request_detail()

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "queued"),
        ("created_at", "2026-07-17T00:00:00+09:00"),
        ("error_message", "boom"),
        ("started_at", None),
        ("finished_at", "2026-07-18T00:03:00+09:00"),
        ("dagster_run_id", "run-2"),
    ],
)
def test_pipeline_execution_detail_rejects_anchor_lifecycle_drift(
    field: str,
    value: object,
) -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    update_request = detail["update_request"]
    assert isinstance(root, dict)
    assert isinstance(update_request, dict)
    root[field] = value
    update_request[field] = value

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_pipeline_execution_detail_rejects_same_id_projected_lifecycle_drift() -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    assert isinstance(root, dict)
    root["projected_job"]["status"] = "queued"  # type: ignore[index]

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_pipeline_execution_detail_rejects_same_id_member_lifecycle_drift() -> None:
    detail = _as_update_request_detail()
    root = detail["root"]
    assert isinstance(root, dict)
    root["provider_datasets"][0]["status"] = "queued"  # type: ignore[index]

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    "drift",
    [
        "operation_kind",
        "dagster_run_id",
        "missing_run",
        "extra_run",
        "duplicate_run",
        "termination_without_run",
    ],
)
def test_pipeline_execution_detail_rejects_cancellation_scope_drift(
    drift: str,
) -> None:
    detail = _execution_detail()
    cancellation = _cancellation()
    cancellation["root"] = {"kind": "import_job", "id": ROOT_ID}
    detail["cancellation"] = cancellation
    root = detail["root"]
    assert isinstance(root, dict)
    root["cancellation"] = {
        "cancellation_id": CANCELLATION_ID,
        "status": "completed",
        "requested_at": "2026-07-18T00:02:00+09:00",
        "requested_by": "service:pinvi",
        "reason": "duplicate",
        "retryable": False,
        "unresolved_member_count": 0,
    }

    if drift == "operation_kind":
        cancellation["members"][0]["operation_kind"] = "wrong"  # type: ignore[index]
    elif drift == "dagster_run_id":
        cancellation["members"][0]["dagster_run_id"] = "wrong-run"  # type: ignore[index]
    elif drift == "missing_run":
        cancellation["dagster_runs"] = []
    elif drift == "extra_run":
        extra_run = deepcopy(cancellation["dagster_runs"][0])  # type: ignore[index]
        extra_run["dagster_run_id"] = "extra-run"
        cancellation["dagster_runs"].append(extra_run)  # type: ignore[union-attr]
    elif drift == "duplicate_run":
        cancellation["dagster_runs"].append(  # type: ignore[union-attr]
            deepcopy(cancellation["dagster_runs"][0])  # type: ignore[index]
        )
    else:
        execution = detail["execution"]
        import_job = detail["import_job"]
        projected_job = root["projected_job"]
        assert isinstance(execution, dict)
        assert isinstance(import_job, dict)
        assert isinstance(projected_job, dict)
        execution["dagster_run_id"] = None
        import_job["dagster_run_id"] = None
        root["dagster_run_id"] = None
        projected_job["dagster_run_id"] = None
        cancellation["members"][0]["dagster_run_id"] = None  # type: ignore[index]
        cancellation["dagster_runs"] = []

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_execution(detail, requested_job_id=ROOT_ID)


def test_pipeline_execution_keeps_root_and_projected_lifecycle_separate() -> None:
    execution = _execution(progress=1)
    execution["projected_job"]["status"] = "done"  # type: ignore[index]
    execution["projected_job"]["progress"] = 100  # type: ignore[index]

    record = project_pipeline_executions(
        {
            "items": [execution],
            "canonical_url": "/v1/ops/pipeline/executions?kind=import_job",
        },
        expected_canonical_url="/v1/ops/pipeline/executions?kind=import_job",
    )[0]

    assert record.status == "running"
    assert record.progress == 1
    assert record.projected_job_status == "done"
    assert record.projected_job_progress == 100


def test_pipeline_execution_rejects_noncanonical_member_status() -> None:
    execution = _execution()
    execution["provider_datasets"][0]["status"] = "healthy"  # type: ignore[index]

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_executions(
            {
                "items": [execution],
                "canonical_url": "/v1/ops/pipeline/executions?kind=import_job",
            },
            expected_canonical_url="/v1/ops/pipeline/executions?kind=import_job",
        )


def test_pipeline_execution_rejects_detail_url_identity_drift() -> None:
    execution = _execution()
    execution["projected_job"]["detail_url"] = (  # type: ignore[index]
        f"/v1/ops/import-jobs/{PROJECTED_ID}"
    )

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline execution"):
        project_pipeline_executions(
            {
                "items": [execution],
                "canonical_url": "/v1/ops/pipeline/executions?kind=import_job",
            },
            expected_canonical_url="/v1/ops/pipeline/executions?kind=import_job",
        )


@pytest.mark.parametrize(
    "canonical_url",
    [
        "/v1/ops/pipeline/executions",
        "/v1/ops/import-jobs?kind=import_job",
        "/v1/ops/pipeline/executions?kind=update_request",
    ],
)
def test_pipeline_execution_rejects_canonical_url_provenance_drift(
    canonical_url: str,
) -> None:
    with pytest.raises(KorTravelMapOpsContractError, match="canonical_url"):
        project_pipeline_executions(
            {"items": [_execution()], "canonical_url": canonical_url},
            expected_canonical_url="/v1/ops/pipeline/executions?kind=import_job",
        )


@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"page": {}},
        {"page": {"page_size": 49, "next_cursor": None}},
        {"page": {"page_size": 50}},
        {"page": {"page_size": 50, "next_cursor": None, "legacy": True}},
    ],
)
def test_pipeline_execution_rejects_missing_or_malformed_page_meta(
    meta: dict[str, object],
) -> None:
    with pytest.raises(KorTravelMapOpsContractError, match=r"pagination|page_size"):
        project_pipeline_page_next_cursor(meta, expected_page_size=50)


def test_pipeline_execution_page_meta_preserves_next_cursor() -> None:
    assert (
        project_pipeline_page_next_cursor(
            {"page": {"page_size": 50, "next_cursor": "next", "total": 60}},
            expected_page_size=50,
        )
        == "next"
    )


def test_pipeline_cancellation_keeps_requested_and_canonical_root_ids() -> None:
    result = project_pipeline_cancellation(_cancellation(), requested_job_id=ROOT_ID)

    assert result.requested_job_id == ROOT_ID
    assert result.root_kind == "update_request"
    assert result.root_id == PROJECTED_ID
    assert result.status == "completed"


def test_pipeline_cancellation_accepts_retry_subset_without_resolved_requested_job() -> None:
    data = deepcopy(_cancellation())
    data.update(
        {
            "previous_cancellation_id": PROJECTED_ID,
            "root": {"kind": "import_job", "id": ROOT_ID},
        }
    )
    data["members"][0]["job_id"] = CHILD_ID  # type: ignore[index]

    result = project_pipeline_cancellation(data, requested_job_id=ROOT_ID)

    assert result.requested_job_id == ROOT_ID
    assert result.root_id == ROOT_ID


def test_pipeline_cancellation_rejects_non_run_backed_retry_member() -> None:
    data = deepcopy(_cancellation())
    data["previous_cancellation_id"] = PROJECTED_ID
    data["members"][0].update(  # type: ignore[index]
        {"dagster_run_id": None, "requires_run_termination": False}
    )
    data["dagster_runs"] = []

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


def test_pipeline_cancellation_rejects_missing_requested_member() -> None:
    with pytest.raises(KorTravelMapOpsContractError, match="requested job"):
        project_pipeline_cancellation(_cancellation(), requested_job_id=PROJECTED_ID)


def test_pipeline_cancellation_rejects_unresolved_count_drift() -> None:
    data = deepcopy(_cancellation())
    data["unresolved_member_count"] = 1

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    "drift",
    ["missing_run", "extra_run", "duplicate_run", "termination_without_run"],
)
def test_pipeline_cancellation_rejects_run_scope_drift(drift: str) -> None:
    data = deepcopy(_cancellation())
    if drift == "missing_run":
        data["dagster_runs"] = []
    elif drift == "extra_run":
        extra_run = deepcopy(data["dagster_runs"][0])  # type: ignore[index]
        extra_run["dagster_run_id"] = "extra-run"
        data["dagster_runs"].append(extra_run)  # type: ignore[union-attr]
    elif drift == "duplicate_run":
        data["dagster_runs"].append(  # type: ignore[union-attr]
            deepcopy(data["dagster_runs"][0])  # type: ignore[index]
        )
    else:
        data["members"][0]["dagster_run_id"] = None  # type: ignore[index]
        data["dagster_runs"] = []

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    "drift",
    [
        "retryable_pending",
        "cancelled_member_error",
        "failed_member_without_error",
        "run_member_result_mismatch",
        "reserved_run_without_initial_status",
        "cancelled_run_terminal_status",
    ],
)
def test_pipeline_cancellation_rejects_normalized_result_drift(drift: str) -> None:
    data = deepcopy(_cancellation())
    member = data["members"][0]  # type: ignore[index]
    run = data["dagster_runs"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    assert isinstance(run, dict)
    structured_error = {
        "code": "DAGSTER_UNAVAILABLE",
        "message": "Dagster unavailable",
        "details": {},
    }
    if drift == "retryable_pending":
        data.update(
            {
                "status": "retryable",
                "retryable": True,
                "error": structured_error,
                "finished_at": None,
                "unresolved_member_count": 1,
            }
        )
        member.update({"result": "pending", "terminal_status": None, "error": None})
        run.update({"result": "pending", "terminal_status": None, "error": None})
    elif drift == "cancelled_member_error":
        member["error"] = structured_error
    elif drift == "failed_member_without_error":
        data.update(
            {
                "status": "failed",
                "error": structured_error,
                "unresolved_member_count": 1,
            }
        )
        member.update({"result": "cancel_failed", "terminal_status": None, "error": None})
        run.update(
            {
                "result": "cancel_failed",
                "terminal_status": None,
                "error": structured_error,
            }
        )
    elif drift == "run_member_result_mismatch":
        run.update({"result": "already_terminal", "terminal_status": "SUCCESS"})
    elif drift == "reserved_run_without_initial_status":
        run["initial_status"] = None
    else:
        run["terminal_status"] = "SUCCESS"

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    ("run_result", "terminal_status"),
    [
        ("already_terminal", "SUCCESS"),
        ("cancelled", "CANCELED"),
        ("pending", None),
    ],
)
def test_pipeline_cancellation_accepts_definitive_member_drift_for_canonical_run(
    run_result: str,
    terminal_status: str | None,
) -> None:
    data = deepcopy(_cancellation())
    member = data["members"][0]  # type: ignore[index]
    run = data["dagster_runs"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    assert isinstance(run, dict)
    definitive_error = {
        "code": "PIPELINE_CANCELLATION_UNSAFE",
        "message": "frozen member tracking diverged",
        "details": {},
    }
    data.update(
        {
            "status": "failed",
            "error": definitive_error,
            "retryable": False,
            "unresolved_member_count": 1,
        }
    )
    member.update(
        {
            "result": "cancel_failed",
            "terminal_status": None,
            "error": definitive_error,
        }
    )
    run.update(
        {
            "result": run_result,
            "terminal_status": terminal_status,
            "error": None,
            "engine_started_at": (None if run_result == "pending" else "2026-07-18T00:02:30+09:00"),
            "engine_finished_at": (
                None if run_result == "pending" else "2026-07-18T00:03:00+09:00"
            ),
        }
    )

    result = project_pipeline_cancellation(data, requested_job_id=ROOT_ID)

    assert result.status == "failed"
    assert result.unresolved_member_count == 1


def _retryable_cancellation() -> dict[str, object]:
    data = deepcopy(_cancellation())
    retryable_error = {
        "code": "DAGSTER_UNAVAILABLE",
        "message": "Dagster unavailable",
        "details": {},
    }
    data.update(
        {
            "status": "retryable",
            "error": retryable_error,
            "finished_at": "2026-07-18T00:03:00+09:00",
            "retryable": True,
            "unresolved_member_count": 1,
        }
    )
    data["members"][0].update(  # type: ignore[index]
        {
            "result": "cancel_failed",
            "terminal_status": None,
            "error": retryable_error,
        }
    )
    data["dagster_runs"][0].update(  # type: ignore[index]
        {
            "result": "cancel_failed",
            "terminal_status": None,
            "error": retryable_error,
            "engine_started_at": None,
            "engine_finished_at": None,
        }
    )
    return data


def _failed_cancellation(
    *,
    attempt_code: str = "PIPELINE_CANCELLATION_UNSAFE",
    member_code: str = "PIPELINE_CANCELLATION_INVARIANT",
    run_code: str = "DAGSTER_UNAVAILABLE",
) -> dict[str, object]:
    data = deepcopy(_cancellation())
    attempt_error = {
        "code": attempt_code,
        "message": "definitive cancellation failure",
        "details": {},
    }
    member_error = {
        "code": member_code,
        "message": "frozen member tracking diverged",
        "details": {},
    }
    run_error = {
        "code": run_code,
        "message": "Dagster termination failed",
        "details": {},
    }
    data.update(
        {
            "status": "failed",
            "error": attempt_error,
            "retryable": False,
            "unresolved_member_count": 1,
        }
    )
    data["members"][0].update(  # type: ignore[index]
        {
            "result": "cancel_failed",
            "terminal_status": None,
            "error": member_error,
        }
    )
    data["dagster_runs"][0].update(  # type: ignore[index]
        {
            "result": "cancel_failed",
            "terminal_status": None,
            "error": run_error,
            "engine_started_at": None,
            "engine_finished_at": None,
        }
    )
    return data


def test_pipeline_cancellation_accepts_exact_retryable_run_failure() -> None:
    result = project_pipeline_cancellation(
        _retryable_cancellation(),
        requested_job_id=ROOT_ID,
    )

    assert result.status == "retryable"
    assert result.retryable is True


@pytest.mark.parametrize(
    "failed_code",
    [
        "DAGSTER_RECONCILE_FAILED",
        "PIPELINE_CANCELLATION_INVARIANT",
        "PIPELINE_CANCELLATION_UNSAFE",
    ],
)
@pytest.mark.parametrize(
    "run_code",
    ["DAGSTER_UNAVAILABLE", "PIPELINE_CANCELLATION_UNSAFE"],
)
def test_pipeline_cancellation_accepts_canonical_failed_error_codes(
    failed_code: str,
    run_code: str,
) -> None:
    result = project_pipeline_cancellation(
        _failed_cancellation(
            attempt_code=failed_code,
            member_code=failed_code,
            run_code=run_code,
        ),
        requested_job_id=ROOT_ID,
    )

    assert result.status == "failed"
    assert result.retryable is False


def test_pipeline_cancellation_accepts_failed_attempt_with_retryable_evidence() -> None:
    result = project_pipeline_cancellation(
        _failed_cancellation(
            member_code="DAGSTER_UNAVAILABLE",
            run_code="DAGSTER_UNAVAILABLE",
        ),
        requested_job_id=ROOT_ID,
    )

    assert result.status == "failed"
    assert result.unresolved_member_count == 1


def test_pipeline_cancellation_accepts_mixed_retryable_and_definitive_evidence() -> None:
    data = _failed_cancellation(
        member_code="DAGSTER_UNAVAILABLE",
        run_code="DAGSTER_UNAVAILABLE",
    )
    definitive_error = {
        "code": "DAGSTER_RECONCILE_FAILED",
        "message": "frozen base run mapping changed",
        "details": {},
    }
    definitive_member = deepcopy(data["members"][0])  # type: ignore[index]
    definitive_member.update(
        {
            "job_id": CHILD_ID,
            "dagster_run_id": "run-2",
            "error": definitive_error,
        }
    )
    definitive_run = deepcopy(data["dagster_runs"][0])  # type: ignore[index]
    definitive_run.update(
        {
            "dagster_run_id": "run-2",
            "result": "already_terminal",
            "terminal_status": "SUCCESS",
            "error": None,
        }
    )
    data["members"].append(definitive_member)  # type: ignore[union-attr]
    data["dagster_runs"].append(definitive_run)  # type: ignore[union-attr]
    data["unresolved_member_count"] = 2

    result = project_pipeline_cancellation(data, requested_job_id=ROOT_ID)

    assert result.status == "failed"
    assert result.unresolved_member_count == 2


def test_pipeline_cancellation_accepts_failed_pending_snapshot() -> None:
    data = _failed_cancellation()
    data["members"][0].update(  # type: ignore[index]
        {"result": "pending", "terminal_status": None, "error": None}
    )
    data["dagster_runs"][0].update(  # type: ignore[index]
        {"result": "pending", "terminal_status": None, "error": None}
    )

    result = project_pipeline_cancellation(data, requested_job_id=ROOT_ID)

    assert result.status == "failed"
    assert result.unresolved_member_count == 1


@pytest.mark.parametrize(
    "drift",
    [
        "retryable_attempt_error",
        "invalid_member_error",
        "retryable_member_without_failed_run",
        "invalid_run_error",
    ],
)
def test_pipeline_cancellation_rejects_noncanonical_failed_error_evidence(
    drift: str,
) -> None:
    data = _failed_cancellation()
    retryable_error = {
        "code": "DAGSTER_UNAVAILABLE",
        "message": "retryable evidence is not definitive",
        "details": {},
    }
    if drift == "retryable_attempt_error":
        data["error"] = retryable_error
    elif drift == "invalid_member_error":
        data["members"][0]["error"] = {  # type: ignore[index]
            "code": "UNKNOWN_MEMBER_FAILURE",
            "message": "not a canonical cancellation error",
            "details": {},
        }
    elif drift == "retryable_member_without_failed_run":
        data["members"][0]["error"] = retryable_error  # type: ignore[index]
        data["dagster_runs"][0].update(  # type: ignore[index]
            {
                "result": "already_terminal",
                "terminal_status": "SUCCESS",
                "error": None,
            }
        )
    else:
        data["dagster_runs"][0]["error"] = {  # type: ignore[index]
            "code": "UNKNOWN_DAGSTER_FAILURE",
            "message": "not a canonical cancellation error",
            "details": {},
        }

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    "drift",
    [
        "non_run_backed_member",
        "cancelled_run",
        "already_terminal_run",
        "non_retryable_error",
    ],
)
def test_pipeline_cancellation_rejects_non_retryable_failure_evidence(
    drift: str,
) -> None:
    data = _retryable_cancellation()
    member = data["members"][0]  # type: ignore[index]
    run = data["dagster_runs"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    assert isinstance(run, dict)
    if drift == "non_run_backed_member":
        member["requires_run_termination"] = False
    elif drift == "cancelled_run":
        run.update({"result": "cancelled", "terminal_status": "CANCELED", "error": None})
    elif drift == "already_terminal_run":
        run.update(
            {
                "result": "already_terminal",
                "terminal_status": "SUCCESS",
                "error": None,
            }
        )
    else:
        definitive_error = {
            "code": "PIPELINE_CANCELLATION_UNSAFE",
            "message": "not retry capable",
            "details": {},
        }
        data["error"] = definitive_error
        member["error"] = definitive_error
        run["error"] = definitive_error

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


def test_pipeline_cancellation_rejects_noncanonical_run_result() -> None:
    data = deepcopy(_cancellation())
    data["dagster_runs"][0]["result"] = "unknown_terminal"  # type: ignore[index]

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    "drift",
    [
        "in_progress_finished",
        "in_progress_error",
        "completed_without_finish",
        "retryable_without_finish",
        "failed_without_finish",
    ],
)
def test_pipeline_cancellation_rejects_attempt_lifecycle_drift(drift: str) -> None:
    if drift == "retryable_without_finish":
        data = _retryable_cancellation()
        data["finished_at"] = None
    elif drift == "failed_without_finish":
        data = _failed_cancellation()
        data["finished_at"] = None
    else:
        data = deepcopy(_cancellation())
        if drift == "in_progress_finished":
            data["status"] = "in_progress"
        elif drift == "in_progress_error":
            data.update(
                {
                    "status": "in_progress",
                    "finished_at": None,
                    "error": {
                        "code": "PIPELINE_CANCELLATION_INVARIANT",
                        "message": "premature attempt error",
                        "details": {},
                    },
                }
            )
        else:
            data["finished_at"] = None

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


def test_pipeline_cancellation_accepts_in_progress_pending_lifecycle() -> None:
    data = deepcopy(_cancellation())
    data.update(
        {
            "status": "in_progress",
            "finished_at": None,
            "unresolved_member_count": 1,
        }
    )
    data["members"][0].update(  # type: ignore[index]
        {"result": "pending", "terminal_status": None, "error": None}
    )
    data["dagster_runs"][0].update(  # type: ignore[index]
        {
            "result": "pending",
            "terminal_status": None,
            "error": None,
            "engine_started_at": None,
            "engine_finished_at": None,
        }
    )

    result = project_pipeline_cancellation(data, requested_job_id=ROOT_ID)

    assert result.status == "in_progress"


@pytest.mark.parametrize(
    ("run_result", "terminal_status"),
    [
        ("cancelled", "CANCELED"),
        ("already_terminal", "SUCCESS"),
        ("already_terminal", "FAILURE"),
    ],
)
def test_pipeline_cancellation_accepts_in_progress_member_run_cas_drift(
    run_result: str,
    terminal_status: str,
) -> None:
    data = deepcopy(_cancellation())
    data.update(
        {
            "status": "in_progress",
            "finished_at": None,
            "unresolved_member_count": 1,
        }
    )
    data["members"][0].update(  # type: ignore[index]
        {
            "result": "cancel_failed",
            "terminal_status": None,
            "error": {
                "code": "DAGSTER_UNAVAILABLE",
                "message": "member CAS observed before attempt finish",
                "details": {},
            },
        }
    )
    data["dagster_runs"][0].update(  # type: ignore[index]
        {
            "result": run_result,
            "terminal_status": terminal_status,
            "error": None,
        }
    )

    result = project_pipeline_cancellation(data, requested_job_id=ROOT_ID)

    assert result.status == "in_progress"
    assert result.unresolved_member_count == 1


@pytest.mark.parametrize(
    "drift",
    [
        "pending_run",
        "unknown_member_error",
        "retryable_attempt",
        "member_run_policy_mismatch",
    ],
)
def test_pipeline_cancellation_rejects_impossible_member_run_cas_drift(
    drift: str,
) -> None:
    data = deepcopy(_cancellation())
    retryable_error = {
        "code": "DAGSTER_UNAVAILABLE",
        "message": "member CAS observation",
        "details": {},
    }
    data.update(
        {
            "status": "in_progress",
            "finished_at": None,
            "unresolved_member_count": 1,
        }
    )
    data["members"][0].update(  # type: ignore[index]
        {
            "result": "cancel_failed",
            "terminal_status": None,
            "error": retryable_error,
        }
    )
    run = data["dagster_runs"][0]  # type: ignore[index]
    assert isinstance(run, dict)
    if drift == "pending_run":
        run.update(
            {
                "result": "pending",
                "terminal_status": None,
                "error": None,
                "engine_started_at": None,
                "engine_finished_at": None,
            }
        )
    elif drift == "unknown_member_error":
        data["members"][0]["error"] = {  # type: ignore[index]
            "code": "UNKNOWN_CAS_FAILURE",
            "message": "unknown member policy",
            "details": {},
        }
    elif drift == "retryable_attempt":
        data.update(
            {
                "status": "retryable",
                "finished_at": "2026-07-18T00:03:00+09:00",
                "retryable": True,
                "error": retryable_error,
            }
        )
    else:
        run.update(
            {
                "result": "cancel_failed",
                "terminal_status": None,
                "error": {
                    "code": "PIPELINE_CANCELLATION_UNSAFE",
                    "message": "definitive run policy",
                    "details": {},
                },
                "engine_started_at": None,
                "engine_finished_at": None,
            }
        )

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    "drift",
    [
        "failed_run_engine_time",
        "pending_run_engine_time",
        "terminal_run_missing_finish",
        "terminal_run_reversed_times",
    ],
)
def test_pipeline_cancellation_rejects_run_engine_lifecycle_drift(
    drift: str,
) -> None:
    if drift == "failed_run_engine_time":
        data = _retryable_cancellation()
        data["dagster_runs"][0]["engine_started_at"] = (  # type: ignore[index]
            "2026-07-18T00:02:30+09:00"
        )
    else:
        data = deepcopy(_cancellation())
        run = data["dagster_runs"][0]  # type: ignore[index]
        assert isinstance(run, dict)
        if drift == "pending_run_engine_time":
            data.update(
                {
                    "status": "in_progress",
                    "finished_at": None,
                    "unresolved_member_count": 1,
                }
            )
            data["members"][0].update(  # type: ignore[index]
                {"result": "pending", "terminal_status": None, "error": None}
            )
            run.update(
                {
                    "result": "pending",
                    "terminal_status": None,
                    "error": None,
                    "engine_finished_at": None,
                }
            )
        elif drift == "terminal_run_missing_finish":
            run["engine_finished_at"] = None
        else:
            run.update(
                {
                    "engine_started_at": "2026-07-18T00:04:00+09:00",
                    "engine_finished_at": "2026-07-18T00:03:00+09:00",
                }
            )

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    "drift",
    [
        "running_run_backed_false",
        "queued_feature_load_false",
        "queued_generic_true",
        "terminal_run_backed_true",
    ],
)
def test_pipeline_cancellation_rejects_run_termination_flag_drift(
    drift: str,
) -> None:
    data = deepcopy(_cancellation())
    member = data["members"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    if drift == "running_run_backed_false":
        member["requires_run_termination"] = False
    elif drift == "queued_feature_load_false":
        member.update(
            {
                "initial_status": "queued",
                "operation_kind": "provider_feature_load",
                "requires_run_termination": False,
            }
        )
    elif drift == "queued_generic_true":
        member["initial_status"] = "queued"
    else:
        member["initial_status"] = "done"

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


def test_pipeline_cancellation_accepts_queued_feature_load_run_termination() -> None:
    data = deepcopy(_cancellation())
    data["members"][0].update(  # type: ignore[index]
        {
            "initial_status": "queued",
            "operation_kind": "provider_feature_load",
        }
    )

    result = project_pipeline_cancellation(data, requested_job_id=ROOT_ID)

    assert result.status == "completed"


@pytest.mark.parametrize("initial_status", ["queued", "done"])
def test_pipeline_cancellation_rejects_non_run_backed_resolved_member_drift(
    initial_status: str,
) -> None:
    data = deepcopy(_cancellation())
    data["members"][0].update(  # type: ignore[index]
        {
            "dagster_run_id": None,
            "requires_run_termination": False,
            "initial_status": initial_status,
            "result": "already_terminal",
            "terminal_status": ("done" if initial_status == "queued" else "failed"),
        }
    )
    data["dagster_runs"] = []

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    ("operation_kind", "member_status", "run_status"),
    [
        ("provider_import", "done", "SUCCESS"),
        ("provider_import", "failed", "FAILURE"),
        ("provider_feature_load", "failed", "SUCCESS"),
    ],
)
def test_pipeline_cancellation_accepts_canonical_resolved_run_mapping(
    operation_kind: str,
    member_status: str,
    run_status: str,
) -> None:
    data = deepcopy(_cancellation())
    data["members"][0].update(  # type: ignore[index]
        {
            "operation_kind": operation_kind,
            "result": "already_terminal",
            "terminal_status": member_status,
        }
    )
    data["dagster_runs"][0].update(  # type: ignore[index]
        {"result": "already_terminal", "terminal_status": run_status}
    )

    result = project_pipeline_cancellation(data, requested_job_id=ROOT_ID)

    assert result.status == "completed"


@pytest.mark.parametrize(
    ("member_status", "run_result", "run_status"),
    [
        ("done", "already_terminal", "FAILURE"),
        ("failed", "already_terminal", "SUCCESS"),
        ("cancelled", "cancelled", "CANCELED"),
    ],
)
def test_pipeline_cancellation_rejects_resolved_run_mapping_drift(
    member_status: str,
    run_result: str,
    run_status: str,
) -> None:
    data = deepcopy(_cancellation())
    data["members"][0].update(  # type: ignore[index]
        {"result": "already_terminal", "terminal_status": member_status}
    )
    data["dagster_runs"][0].update(  # type: ignore[index]
        {"result": run_result, "terminal_status": run_status}
    )

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    ("target", "field"),
    [
        ("attempt", "code"),
        ("attempt", "message"),
        ("member", "code"),
        ("member", "message"),
        ("run", "code"),
        ("run", "message"),
    ],
)
def test_pipeline_cancellation_rejects_blank_structured_error_text(
    target: str,
    field: str,
) -> None:
    data = _failed_cancellation()
    if target == "attempt":
        error = data["error"]
    elif target == "member":
        error = data["members"][0]["error"]  # type: ignore[index]
    else:
        error = data["dagster_runs"][0]["error"]  # type: ignore[index]
    assert isinstance(error, dict)
    error[field] = " \t "

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


@pytest.mark.parametrize(
    "operation_kind",
    ["", " ", " provider_import", "provider_import ", "\tprovider_import"],
)
def test_pipeline_cancellation_rejects_noncanonical_operation_kind(
    operation_kind: str,
) -> None:
    data = deepcopy(_cancellation())
    data["members"][0]["operation_kind"] = operation_kind  # type: ignore[index]

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline cancellation"):
        project_pipeline_cancellation(data, requested_job_id=ROOT_ID)


def test_pipeline_cancellation_accepts_null_operation_kind() -> None:
    data = deepcopy(_cancellation())
    data["members"][0]["operation_kind"] = None  # type: ignore[index]

    result = project_pipeline_cancellation(data, requested_job_id=ROOT_ID)

    assert result.status == "completed"


def test_pipeline_overview_preserves_canonical_operation_counts() -> None:
    overview = validate_pipeline_overview(_overview())

    assert overview["operations_by_status"] == {
        "queued": 0,
        "running": 1,
        "done": 2,
        "failed": 0,
        "cancelled": 0,
    }
    assert overview["active_operations"] == 1


def test_pipeline_overview_rejects_active_count_drift() -> None:
    overview = _overview()
    overview["active_operations"] = 0

    with pytest.raises(KorTravelMapOpsContractError, match="pipeline overview"):
        validate_pipeline_overview(overview)
