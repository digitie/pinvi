"""kor-travel-map canonical ops DTO를 Pinvi admin 표시 계약으로 투영한다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Self
from urllib.parse import quote, urlencode
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.schemas.admin import (
    AdminProviderDatasetSummary,
    AdminProviderImportJobCancellationResult,
    AdminProviderImportJobRecord,
)

OperationState = Literal["queued", "running", "done", "failed", "cancelled"]
CancellationStatus = Literal["in_progress", "retryable", "completed", "failed"]
CancellationResult = Literal["pending", "cancelled", "already_terminal", "cancel_failed"]
_RETRYABLE_CANCELLATION_ERROR_CODES = frozenset(
    {
        "DAGSTER_TERMINATE_FAILED",
        "DAGSTER_TERMINATION_TIMEOUT",
        "DAGSTER_UNAVAILABLE",
    }
)
_FAILED_CANCELLATION_ERROR_CODES = frozenset(
    {
        "DAGSTER_RECONCILE_FAILED",
        "PIPELINE_CANCELLATION_INVARIANT",
        "PIPELINE_CANCELLATION_UNSAFE",
    }
)
_CANCELLATION_FAILURE_ERROR_CODES = (
    _RETRYABLE_CANCELLATION_ERROR_CODES | _FAILED_CANCELLATION_ERROR_CODES
)


def _is_canonical_sync_scope(value: str) -> bool:
    if value in {"dataset_wide", "target_grids"}:
        return True
    prefix = "external_system:"
    if not value.startswith(prefix):
        return False
    external_system = value.removeprefix(prefix)
    return (
        bool(external_system)
        and external_system == external_system.strip()
        and len(external_system) <= 112
    )


class KorTravelMapOpsContractError(ValueError):
    """canonical upstream 응답이 Pinvi가 고정한 계약과 다를 때 발생한다."""


class _CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _DagsterGraphqlError(_CanonicalModel):
    message: str | None = None
    stack: list[str] = Field(default_factory=list)
    class_name: str | None = None


class _DagsterInstigationTick(_CanonicalModel):
    tick_id: str
    status: str
    timestamp: float
    end_timestamp: float | None = None
    run_ids: list[str] = Field(default_factory=list)
    run_keys: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
    cursor: str | None = None
    error: _DagsterGraphqlError | None = None


class _DagsterSensor(_CanonicalModel):
    name: str
    status: str | None = None
    recent_ticks: list[_DagsterInstigationTick] = Field(default_factory=list)


class _DagsterRunSummary(_CanonicalModel):
    run_id: str
    job_name: str | None = None
    status: str
    start_time: float | None = None
    end_time: float | None = None
    update_time: float | None = None
    tags: dict[str, str]


class _PipelineDagsterOverview(_CanonicalModel):
    status: Literal["ok", "unavailable", "error"]
    dagster_url: str
    graphql_url: str
    version: str | None = None
    run_counts: dict[str, int] = Field(default_factory=dict)
    recent_runs: list[_DagsterRunSummary] = Field(default_factory=list)
    schedule_count: int = Field(default=0, ge=0)
    sensor_count: int = Field(default=0, ge=0)
    sensors: list[_DagsterSensor] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class _PipelineOverviewData(_CanonicalModel):
    checked_at: datetime
    dagster: _PipelineDagsterOverview
    operations_by_status: dict[OperationState, int]
    active_operations: int = Field(ge=0)
    failed_operations_24h: int = Field(ge=0)

    @model_validator(mode="after")
    def active_count_matches_status_counts(self) -> Self:
        if any(count < 0 for count in self.operations_by_status.values()):
            raise ValueError("operation status counts must be non-negative")
        expected_active = self.operations_by_status.get(
            "queued", 0
        ) + self.operations_by_status.get("running", 0)
        if self.active_operations != expected_active:
            raise ValueError("active_operations must match queued + running counts")
        return self


class _CancellationSummary(_CanonicalModel):
    cancellation_id: UUID
    status: CancellationStatus
    requested_at: datetime
    requested_by: str
    reason: str | None
    retryable: bool
    unresolved_member_count: int = Field(ge=0)

    @model_validator(mode="after")
    def retryable_matches_status(self) -> Self:
        if self.retryable != (self.status == "retryable"):
            raise ValueError("retryable must match cancellation status")
        return self


class _ProviderDatasetIdentity(_CanonicalModel):
    provider: str
    dataset_key: str
    sync_scope: str | None
    operation_member_id: UUID
    status: OperationState


class _ProjectedJob(_CanonicalModel):
    id: UUID
    job_kind: str
    status: OperationState
    progress: int = Field(ge=0, le=100)
    current_stage: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    dagster_run_id: str | None
    dagster_run_status: str | None
    trigger_kind: str | None
    operation_registry_version: str | None
    load_batch_id: UUID | None
    parent_job_id: UUID | None
    depth: int
    detail_url: str

    @model_validator(mode="after")
    def detail_url_matches_identity(self) -> Self:
        expected = f"/v1/ops/pipeline/executions/import_job/{self.id}"
        if self.detail_url != expected:
            raise ValueError("projected job detail_url must match its canonical id")
        return self


class _PipelineExecutionRecord(_CanonicalModel):
    kind: Literal["import_job", "update_request"]
    id: UUID
    status: OperationState
    created_at: datetime
    job_kind: str | None
    provider: str | None
    dataset_key: str | None
    progress: int | None = Field(ge=0, le=100)
    current_stage: str | None
    scope_type: str | None
    priority: int | None
    run_mode: str | None
    operator: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    dagster_run_id: str | None
    dagster_run_status: str | None
    trigger_kind: str | None
    operation_registry_version: str | None
    job_id: UUID | None
    request_id: UUID | None
    load_batch_id: UUID | None
    parent_job_id: UUID | None
    detail_url: str

    @model_validator(mode="after")
    def detail_url_matches_identity(self) -> Self:
        expected = f"/v1/ops/pipeline/executions/{self.kind}/{self.id}"
        if self.detail_url != expected:
            raise ValueError("execution detail_url must match kind and id")
        return self


class _PipelineExecutionRoot(_CanonicalModel):
    kind: Literal["import_job", "update_request"]
    id: UUID
    status: OperationState
    created_at: datetime
    providers: list[str]
    dataset_keys: list[str]
    provider_datasets: list[_ProviderDatasetIdentity]
    progress: int | None = Field(ge=0, le=100)
    current_stage: str | None
    scope_type: str | None
    priority: int | None
    run_mode: str | None
    operator: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    dagster_run_id: str | None
    dagster_run_status: str | None
    trigger_kind: str | None
    operation_registry_version: str | None
    requested_job_id: UUID | None
    linked_job_count: int = Field(ge=1)
    projected_job: _ProjectedJob
    cancellation: _CancellationSummary | None
    detail_url: str

    @model_validator(mode="after")
    def exact_members_match_projections(self) -> Self:
        if self.kind == "import_job" and self.requested_job_id is not None:
            raise ValueError("import_job root cannot carry requested_job_id")
        if self.kind == "import_job" and any(
            value is not None
            for value in (self.scope_type, self.priority, self.run_mode, self.operator)
        ):
            raise ValueError("standalone import root cannot carry request-only fields")
        member_keys = [(item.provider, item.dataset_key) for item in self.provider_datasets]
        if len(member_keys) != len(set(member_keys)):
            raise ValueError("provider_datasets must contain exact unique members")
        if len(self.providers) != len(set(self.providers)):
            raise ValueError("providers must contain exact unique identities")
        if len(self.dataset_keys) != len(set(self.dataset_keys)):
            raise ValueError("dataset_keys must contain exact unique identities")
        representative_providers = {item.provider for item in self.provider_datasets}
        representative_datasets = {item.dataset_key for item in self.provider_datasets}
        if not representative_providers.issubset(self.providers):
            raise ValueError("providers must include every representative member")
        if not representative_datasets.issubset(self.dataset_keys):
            raise ValueError("dataset_keys must include every representative member")
        # Standalone vectors are exactly the representative pair projection. Update
        # vectors additionally contain request filters; detail validation below can
        # reconstruct and compare that exact union, while list/grid projections can
        # at least require every representative identity to be present.
        if self.kind == "import_job" and set(self.providers) != representative_providers:
            raise ValueError("standalone providers must match exact projected members")
        if self.kind == "import_job" and set(self.dataset_keys) != representative_datasets:
            raise ValueError("standalone dataset_keys must match exact projected members")
        expected_url = f"/v1/ops/pipeline/executions/{self.kind}/{self.id}"
        if self.detail_url != expected_url:
            raise ValueError("execution detail_url must match root kind and id")
        return self


class _PipelineExecutionsData(_CanonicalModel):
    items: list[_PipelineExecutionRoot]
    canonical_url: str


class _PipelinePageMeta(_CanonicalModel):
    page_size: int = Field(ge=1, le=200)
    next_cursor: str | None
    total: int | None = Field(default=None, ge=0)


class _DatasetFreshness(_CanonicalModel):
    state: Literal["never_run", "fresh", "overdue", "disabled", "unknown"]
    basis: Literal["policy_stale_after", "unknown", "disabled"]
    sla_seconds: int | None
    due_at: datetime | None
    is_overdue: bool
    overdue_by_seconds: int


class _DatasetSchedule(_CanonicalModel):
    source: Literal["dagster_graphql"]
    basis: Literal["dagster_definition_tags", "not_scheduled", "unknown"]
    status: str | None
    schedule_names: list[str]
    active_schedule_names: list[str]
    next_scheduled_at: datetime | None

    @model_validator(mode="after")
    def active_schedules_are_defined(self) -> Self:
        if not set(self.active_schedule_names).issubset(self.schedule_names):
            raise ValueError("active schedules must be included in schedule_names")
        return self


class _DatasetPreviewCapability(_CanonicalModel):
    supported: bool
    sources: list[Literal["fixture"]]
    input_kind: Literal["none"]
    default_max_items: Literal[20]
    max_items_limit: Literal[100]
    timeout_seconds: float = Field(strict=True, ge=5.0, le=5.0)
    external_call_budget: Literal[0]

    @model_validator(mode="after")
    def support_matches_sources(self) -> Self:
        if self.supported != (self.sources == ["fixture"]):
            raise ValueError("preview support must match its exact fixture source")
        return self


class _DatasetScopeRefreshCapability(_CanonicalModel):
    supported: bool
    selector: Literal["none", "poi_cache_targets"]
    effect: Literal["dataset_wide", "sync_scope"]
    default_sync_scope: str
    allowed_sync_scopes: list[str]
    reason: str | None = None


class _DatasetCatalog(_CanonicalModel):
    feature_kind: str
    provider_state_default_scope: str
    label: str
    is_feature_load: bool
    is_refreshable: bool
    scope_refresh: _DatasetScopeRefreshCapability
    preview: _DatasetPreviewCapability


class _RefreshPolicy(_CanonicalModel):
    provider: str
    dataset_key: str
    source_kind: str
    targeted_policy: str
    system_interval_seconds: int | None = None
    optimal_interval_seconds: int | None = None
    min_interval_seconds: int | None = None
    stale_after_minutes: int | None = None
    max_requests_per_minute: int | None = None
    max_requests_per_hour: int | None = None
    max_requests_per_day: int | None = None
    max_concurrent: int
    burst_size: int | None = None
    rate_limit_source: dict[str, Any]
    config_source: str
    enabled: bool
    revision: str = Field(pattern=r"^[1-9][0-9]*$")
    created_at: datetime
    updated_at: datetime


class _DatasetProjectedJob(_CanonicalModel):
    id: UUID
    job_kind: str
    status: OperationState
    progress: int = Field(ge=0, le=100)
    current_stage: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    dagster_run_id: str | None
    dagster_run_status: str | None
    trigger_kind: str | None
    operation_registry_version: str | None
    depth: int
    detail_url: str

    @model_validator(mode="after")
    def detail_url_matches_identity(self) -> Self:
        expected = f"/v1/ops/pipeline/executions/import_job/{self.id}"
        if self.detail_url != expected:
            raise ValueError("dataset projected job detail_url must match canonical id")
        return self


class _DatasetExecution(_CanonicalModel):
    kind: Literal["import_job", "update_request"]
    id: UUID
    detail_url: str
    status: OperationState
    pair_status: OperationState
    operation_member_id: UUID
    sync_scope: str | None
    providers: list[str]
    dataset_keys: list[str]
    provider_datasets: list[_ProviderDatasetIdentity]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    dagster_run_id: str | None
    dagster_run_status: str | None
    trigger_kind: str | None
    operation_registry_version: str | None
    error_message: str | None
    projected_job: _DatasetProjectedJob
    cancellation: _CancellationSummary | None

    @model_validator(mode="after")
    def execution_invariants(self) -> Self:
        member_keys = [(item.provider, item.dataset_key) for item in self.provider_datasets]
        if len(member_keys) != len(set(member_keys)):
            raise ValueError("dataset execution members must be exact and unique")
        representative_providers = {item.provider for item in self.provider_datasets}
        representative_datasets = {item.dataset_key for item in self.provider_datasets}
        if not representative_providers.issubset(self.providers):
            raise ValueError("dataset execution providers must include representatives")
        if not representative_datasets.issubset(self.dataset_keys):
            raise ValueError("dataset execution datasets must include representatives")
        if self.kind == "import_job" and (
            set(self.providers) != representative_providers
            or set(self.dataset_keys) != representative_datasets
        ):
            raise ValueError("standalone dataset execution vectors must be exact")
        expected = f"/v1/ops/pipeline/executions/{self.kind}/{self.id}"
        if self.detail_url != expected:
            raise ValueError("dataset execution detail_url must match kind and id")
        if (
            self.projected_job.id == self.operation_member_id
            and self.projected_job.status != self.pair_status
        ):
            raise ValueError(
                "selected projected job lifecycle must match its representative member"
            )
        return self


class _IssueSummary(_CanonicalModel):
    open_count: int = Field(ge=0)
    severity_counts: dict[str, int]


class _DatasetGridRow(_CanonicalModel):
    provider: str
    dataset_key: str
    detail_url: str
    sync_scope: str
    status: str
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int = Field(ge=0)
    eligible_after: datetime | None
    freshness: _DatasetFreshness
    schedule: _DatasetSchedule
    latest_execution: _DatasetExecution | None
    active_execution: _DatasetExecution | None
    catalog_state: Literal["canonical", "orphan"]
    orphan_reason: str | None
    mutable: bool
    catalog: _DatasetCatalog | None
    refresh_policy: _RefreshPolicy | None
    dataset_issues: _IssueSummary
    provider_issues: _IssueSummary

    @model_validator(mode="after")
    def exact_execution_members_match_row(self) -> Self:
        if not _is_canonical_sync_scope(self.sync_scope):
            raise ValueError("dataset row sync_scope must be canonical")
        expected_detail_url = "/v1/ops/datasets/detail?" + urlencode(
            {
                "provider": self.provider,
                "dataset_key": self.dataset_key,
                "sync_scope": self.sync_scope,
            },
            quote_via=quote,
        )
        if self.detail_url != expected_detail_url:
            raise ValueError("dataset detail_url must match the exact row identity")
        if self.refresh_policy is not None and (
            self.refresh_policy.provider != self.provider
            or self.refresh_policy.dataset_key != self.dataset_key
        ):
            raise ValueError("refresh policy identity must match the dataset row")
        if self.catalog_state == "canonical" and (
            self.catalog is None or self.orphan_reason is not None or not self.mutable
        ):
            raise ValueError("canonical dataset row must expose mutable catalog data")
        if self.catalog_state == "orphan" and (
            self.catalog is not None
            or not isinstance(self.orphan_reason, str)
            or not self.orphan_reason
            or self.mutable
        ):
            raise ValueError("orphan dataset row must expose an immutable orphan reason")
        if self.catalog is not None:
            capability = self.catalog.scope_refresh
            if capability.selector == "none" and (
                capability.supported
                or capability.effect != "dataset_wide"
                or capability.default_sync_scope != "dataset_wide"
                or capability.allowed_sync_scopes
                or not capability.reason
            ):
                raise ValueError("selector-none refresh capability must be dataset-wide only")
            if capability.selector == "poi_cache_targets" and (
                not capability.supported
                or capability.effect != "sync_scope"
                or capability.default_sync_scope != "target_grids"
                or not capability.allowed_sync_scopes
                or capability.allowed_sync_scopes[0] != "target_grids"
                or len(capability.allowed_sync_scopes) != len(set(capability.allowed_sync_scopes))
                or any(
                    not scope.startswith("external_system:") or not _is_canonical_sync_scope(scope)
                    for scope in capability.allowed_sync_scopes[1:]
                )
                or capability.reason is not None
            ):
                raise ValueError("poi target refresh capability must expose canonical scopes")
            if not self.catalog.is_refreshable and capability.selector != "none":
                raise ValueError("non-refreshable catalog entry cannot expose scoped refresh")
        for execution in (self.latest_execution, self.active_execution):
            if execution is None:
                continue
            matching_members = [
                member
                for member in execution.provider_datasets
                if (member.provider, member.dataset_key) == (self.provider, self.dataset_key)
                and member.operation_member_id == execution.operation_member_id
            ]
            if len(matching_members) != 1:
                raise ValueError("dataset execution must contain the exact grid member")
            member = matching_members[0]
            logical_scope_matches = execution.sync_scope == self.sync_scope or (
                self.sync_scope == "dataset_wide" and execution.sync_scope is None
            )
            if not logical_scope_matches or member.sync_scope != execution.sync_scope:
                raise ValueError("dataset execution scope must match selected member")
            if member.status != execution.pair_status:
                raise ValueError("dataset execution pair status must match exact member")
        active_states = {"queued", "running"}
        terminal_states = {"done", "failed", "cancelled"}
        if (
            self.active_execution is not None
            and self.active_execution.pair_status not in active_states
        ):
            raise ValueError("active execution must be queued or running")
        if (
            self.latest_execution is not None
            and self.latest_execution.pair_status not in terminal_states
        ):
            raise ValueError("latest execution must be terminal")
        if self.active_execution is not None and self.latest_execution is not None:
            same_root = (
                self.active_execution.kind,
                self.active_execution.id,
            ) == (
                self.latest_execution.kind,
                self.latest_execution.id,
            )
            same_member = (
                self.active_execution.operation_member_id
                == self.latest_execution.operation_member_id
            )
            if same_root or same_member:
                raise ValueError("active and latest executions cannot identify the same operation")
        return self


class _DatasetsGridData(_CanonicalModel):
    items: list[_DatasetGridRow]
    schedule_source_status: Literal["ok", "unavailable", "error"]
    schedule_source_errors: list[str]
    execution_coverage: Literal["db_recorded_canonical_operations"]


class _CancellationError(_CanonicalModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] | None = None

    @field_validator("code", "message")
    @classmethod
    def structured_text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cancellation error text must not be blank")
        return value


class _CancellationRoot(_CanonicalModel):
    kind: Literal["import_job", "update_request"]
    id: UUID


class _CancellationRootWithoutAttempt(_CanonicalModel):
    root: _CancellationRoot
    cancellation: Literal[None]


class _CancellationMember(_CanonicalModel):
    job_id: UUID
    dagster_run_id: str | None
    operation_kind: str | None
    requires_run_termination: bool
    initial_status: str
    result: CancellationResult
    terminal_status: str | None
    error: _CancellationError | None
    updated_at: datetime

    @field_validator("operation_kind")
    @classmethod
    def operation_kind_matches_db_constraint(cls, value: str | None) -> str | None:
        if value is not None and (not value or value != value.strip()):
            raise ValueError("operation_kind must be null or exact trimmed text")
        return value


class _CancellationRun(_CanonicalModel):
    dagster_run_id: str
    initial_status: str | None
    termination_reserved_at: datetime | None
    result: CancellationResult
    terminal_status: str | None
    error: _CancellationError | None
    engine_started_at: datetime | None
    engine_finished_at: datetime | None
    updated_at: datetime


class _CancellationDetail(_CanonicalModel):
    cancellation_id: UUID
    previous_cancellation_id: UUID | None
    root: _CancellationRoot
    status: CancellationStatus
    requested_at: datetime
    requested_by: str
    reason: str | None
    error: _CancellationError | None
    updated_at: datetime
    finished_at: datetime | None
    retryable: bool
    unresolved_member_count: int = Field(ge=0)
    members: list[_CancellationMember]
    dagster_runs: list[_CancellationRun]
    committed_data_rolled_back: Literal[False]
    warnings: list[str]

    @model_validator(mode="after")
    def cancellation_invariants(self) -> Self:
        unresolved = {"pending", "cancel_failed"}
        unresolved_members = sum(member.result in unresolved for member in self.members)
        if self.unresolved_member_count != unresolved_members:
            raise ValueError("unresolved_member_count must match unresolved cancellation members")
        if self.retryable != (self.status == "retryable"):
            raise ValueError("retryable must match cancellation status")
        terminal_attempt = self.status != "in_progress"
        if (self.finished_at is not None) != terminal_attempt:
            raise ValueError("cancellation finished_at must match attempt status")
        attempt_requires_error = self.status in {"retryable", "failed"}
        if (self.error is not None) != attempt_requires_error:
            raise ValueError("cancellation error must match attempt status")
        if self.previous_cancellation_id == self.cancellation_id:
            raise ValueError("cancellation retry lineage cannot reference itself")
        if self.status == "completed" and (
            unresolved_members or any(run.result in unresolved for run in self.dagster_runs)
        ):
            raise ValueError("completed cancellation cannot contain unresolved results")
        if self.status == "retryable" and (
            any(member.result == "pending" for member in self.members)
            or any(run.result == "pending" for run in self.dagster_runs)
            or not any(member.result == "cancel_failed" for member in self.members)
            or self.error is None
        ):
            raise ValueError("retryable cancellation requires failures without pending results")
        if self.status == "failed" and (
            self.error is None or self.error.code not in _FAILED_CANCELLATION_ERROR_CODES
        ):
            raise ValueError("failed cancellation requires a canonical definitive attempt error")
        member_ids = [member.job_id for member in self.members]
        if not member_ids or len(member_ids) != len(set(member_ids)):
            raise ValueError("cancellation members must contain exact unique job ids")
        run_ids = [run.dagster_run_id for run in self.dagster_runs]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("cancellation dagster runs must contain exact unique ids")
        if any(
            member.requires_run_termination
            != (
                member.dagster_run_id is not None
                and (
                    member.initial_status == "running"
                    or (
                        member.initial_status == "queued"
                        and member.operation_kind
                        in {"provider_feature_load_run", "provider_feature_load"}
                    )
                )
            )
            for member in self.members
        ):
            raise ValueError("cancellation member run termination flag must match frozen lifecycle")
        if self.previous_cancellation_id is not None and any(
            not member.requires_run_termination for member in self.members
        ):
            raise ValueError("retry cancellation can contain only unresolved run-backed members")
        member_run_ids = {
            member.dagster_run_id for member in self.members if member.dagster_run_id is not None
        }
        if set(run_ids) != member_run_ids:
            raise ValueError("cancellation run scope must exactly match frozen members")
        for member in self.members:
            if member.result == "pending" and (
                member.terminal_status is not None or member.error is not None
            ):
                raise ValueError("pending member cannot have terminal result fields")
            if member.result == "cancelled" and (
                member.terminal_status != "cancelled" or member.error is not None
            ):
                raise ValueError("cancelled member must be error-free and terminal")
            if member.result == "already_terminal" and (
                member.terminal_status not in {"done", "failed", "cancelled"}
                or member.error is not None
            ):
                raise ValueError("already-terminal member must retain its base status")
            if member.result == "cancel_failed" and (
                member.terminal_status is not None or member.error is None
            ):
                raise ValueError("failed member requires a structured error only")
        run_by_id = {run.dagster_run_id: run for run in self.dagster_runs}
        for run in self.dagster_runs:
            if run.termination_reserved_at is not None and run.initial_status is None:
                raise ValueError("reserved cancellation run requires initial status")
            engine_times_are_empty = (
                run.engine_started_at is None and run.engine_finished_at is None
            )
            engine_times_are_terminal = (
                run.result in {"cancelled", "already_terminal"}
                and run.engine_finished_at is not None
                and (
                    run.engine_started_at is None or run.engine_started_at <= run.engine_finished_at
                )
            )
            if not (engine_times_are_empty or engine_times_are_terminal):
                raise ValueError("cancellation run engine timestamps must match result lifecycle")
            if run.result == "pending" and (
                run.terminal_status is not None or run.error is not None
            ):
                raise ValueError("pending run cannot have terminal result fields")
            if run.result == "cancelled" and (
                run.terminal_status != "CANCELED" or run.error is not None
            ):
                raise ValueError("cancelled run must be error-free and CANCELED")
            if run.result == "already_terminal" and (
                run.terminal_status not in {None, "SUCCESS", "FAILURE"} or run.error is not None
            ):
                raise ValueError("already-terminal run has invalid terminal evidence")
            if run.result == "cancel_failed" and (
                run.terminal_status is not None or run.error is None
            ):
                raise ValueError("failed run requires a structured error only")
        if self.status == "retryable":
            failed_members = [member for member in self.members if member.result == "cancel_failed"]
            failed_run_ids = {
                run.dagster_run_id for run in self.dagster_runs if run.result == "cancel_failed"
            }
            referenced_failed_run_ids = {
                member.dagster_run_id
                for member in failed_members
                if member.dagster_run_id is not None
            }
            if self.error is None or self.error.code not in _RETRYABLE_CANCELLATION_ERROR_CODES:
                raise ValueError("retryable cancellation requires exact run-backed failures")
            if not failed_run_ids.issubset(referenced_failed_run_ids):
                raise ValueError("retryable cancellation requires exact run-backed failures")
            for member in failed_members:
                member_error = member.error
                run_id = member.dagster_run_id
                if (
                    not member.requires_run_termination
                    or run_id is None
                    or member_error is None
                    or member_error.code not in _RETRYABLE_CANCELLATION_ERROR_CODES
                ):
                    raise ValueError("retryable cancellation requires exact run-backed failures")
                run = run_by_id[run_id]
                run_error = run.error
                if (
                    run.result != "cancel_failed"
                    or run_error is None
                    or run_error.code not in _RETRYABLE_CANCELLATION_ERROR_CODES
                ):
                    raise ValueError("retryable cancellation requires exact run-backed failures")
        if self.status == "failed":
            failed_members = [member for member in self.members if member.result == "cancel_failed"]
            failed_runs = [run for run in self.dagster_runs if run.result == "cancel_failed"]
            for run in failed_runs:
                run_error = run.error
                if run_error is None or run_error.code not in _CANCELLATION_FAILURE_ERROR_CODES:
                    raise ValueError("failed cancellation requires canonical run failure evidence")
            for member in failed_members:
                member_error = member.error
                if member_error is None:
                    raise ValueError("failed cancellation member requires error evidence")
                if member_error.code in _RETRYABLE_CANCELLATION_ERROR_CODES:
                    run_id = member.dagster_run_id
                    if not member.requires_run_termination or run_id is None:
                        raise ValueError("failed cancellation retryable evidence must be exact")
                    run = run_by_id[run_id]
                    run_error = run.error
                    if (
                        run.result != "cancel_failed"
                        or run_error is None
                        or run_error.code not in _RETRYABLE_CANCELLATION_ERROR_CODES
                    ):
                        raise ValueError("failed cancellation retryable evidence must be exact")
                    continue
                if member_error.code not in _FAILED_CANCELLATION_ERROR_CODES or (
                    member.initial_status != "running" and not member.requires_run_termination
                ):
                    raise ValueError("failed cancellation member evidence is not definitive")
        if self.status == "in_progress":
            for member in self.members:
                if member.result != "cancel_failed":
                    continue
                member_error = member.error
                if member_error is None:
                    raise ValueError("in-progress failed member requires error evidence")
                if member_error.code not in _CANCELLATION_FAILURE_ERROR_CODES:
                    raise ValueError("in-progress failed member has unknown error evidence")
                run_id = member.dagster_run_id
                if run_id is None:
                    if member_error.code not in _FAILED_CANCELLATION_ERROR_CODES:
                        raise ValueError("in-progress runless failure must be definitive")
                    continue
                run = run_by_id[run_id]
                if run.result in {"cancelled", "already_terminal"}:
                    continue
                if run.result != "cancel_failed" or run.error is None:
                    raise ValueError("in-progress failed member has impossible run evidence")
                expected_codes = (
                    _RETRYABLE_CANCELLATION_ERROR_CODES
                    if member_error.code in _RETRYABLE_CANCELLATION_ERROR_CODES
                    else _FAILED_CANCELLATION_ERROR_CODES
                )
                if run.error.code not in expected_codes:
                    raise ValueError("in-progress member/run failure policies must match")
        success_tracking_run_ids = {
            member.dagster_run_id
            for member in self.members
            if member.dagster_run_id is not None
            and member.operation_kind == "provider_feature_load"
            and member.initial_status != "done"
        }
        for member in self.members:
            if member.result == "pending":
                continue
            if not member.requires_run_termination:
                if member.initial_status == "queued" and member.result != "cancelled":
                    raise ValueError("queued cancellation requires the explicit DB cancel path")
                if member.initial_status in {"done", "failed", "cancelled"} and (
                    member.result != "already_terminal"
                    or member.terminal_status != member.initial_status
                ):
                    raise ValueError("initially terminal member must remain already-terminal")
                continue
            assert member.dagster_run_id is not None
            run = run_by_id[member.dagster_run_id]
            # A definitive failed attempt can be established by frozen-base drift
            # before the run snapshot settles to any particular result. Therefore a
            # cancel_failed member in a failed attempt accepts every canonical run
            # result. Before the attempt finishes, a member failure CAS can also be
            # observed beside a terminal run CAS. The retryable branch above still
            # requires the narrower exact run-backed cancel_failed evidence.
            if member.result == "cancel_failed":
                transient_terminal_run = (
                    self.status == "in_progress"
                    and self.error is None
                    and self.finished_at is None
                    and run.result in {"cancelled", "already_terminal"}
                )
                if (
                    self.status != "failed"
                    and run.result != "cancel_failed"
                    and not transient_terminal_run
                ):
                    raise ValueError("run-backed failed member requires a failed run snapshot")
                continue
            terminal_status = member.terminal_status
            expected_run_terminal = (
                {
                    ("cancelled", "cancelled"): ("cancelled", "CANCELED"),
                    ("already_terminal", "done"): ("already_terminal", "SUCCESS"),
                    ("already_terminal", "failed"): ("already_terminal", "FAILURE"),
                }.get((member.result, terminal_status))
                if terminal_status is not None
                else None
            )
            actual_run_terminal = (run.result, run.terminal_status)
            tracking_failure_after_success = (
                member.result == "already_terminal"
                and member.terminal_status == "failed"
                and member.operation_kind in {"provider_feature_load_run", "provider_feature_load"}
                and member.dagster_run_id in success_tracking_run_ids
                and actual_run_terminal == ("already_terminal", "SUCCESS")
            )
            if expected_run_terminal != actual_run_terminal and not tracking_failure_after_success:
                raise ValueError("resolved member status does not match Dagster terminal result")
        return self


class _PipelineImportJobIdentity(_CanonicalModel):
    """canonical import-job 상세 본체."""

    job_id: UUID
    kind: str
    load_batch_id: UUID | None
    parent_job_id: UUID | None
    payload: dict[str, Any]
    status: OperationState
    progress: int = Field(ge=0, le=100)
    current_stage: str | None
    source_checksum: str | None
    error_message: str | None
    dagster_run_id: str | None
    provider: str | None
    dataset_key: str | None
    trigger_kind: str | None
    operation_registry_version: str | None
    dagster_run_status: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None


class _PipelineUpdateRequestIdentity(_CanonicalModel):
    """canonical feature update request 상세 본체."""

    request_id: UUID
    scope_type: str
    scope: dict[str, Any]
    requested_sync_scope: str | None
    effective_sync_scope: str | None
    providers: list[str]
    dataset_keys: list[str]
    update_policy: dict[str, Any]
    run_mode: str
    priority: int
    status: OperationState
    matched_scope: dict[str, Any]
    job_id: UUID
    dagster_run_id: str | None
    dispatch_requested_at: datetime | None
    operator: str | None
    reason: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    generation: int = Field(ge=1)
    status_url: str

    @model_validator(mode="after")
    def status_url_matches_identity(self) -> Self:
        expected = f"/v1/ops/pipeline/executions/update_request/{self.request_id}"
        if self.status_url != expected:
            raise ValueError("update request status_url must match request identity")
        if self.scope.get("type") != self.scope_type:
            raise ValueError("update request scope type must match scope_type")
        if len(self.providers) != len(set(self.providers)):
            raise ValueError("update request providers must be unique")
        if len(self.dataset_keys) != len(set(self.dataset_keys)):
            raise ValueError("update request dataset_keys must be unique")
        return self


class _PipelineExecutionDetailData(_CanonicalModel):
    execution: _PipelineExecutionRecord
    root: _PipelineExecutionRoot
    import_job: _PipelineImportJobIdentity | None
    update_request: _PipelineUpdateRequestIdentity | None
    cancellation: _CancellationDetail | None
    events: list[dict[str, Any]]
    events_next_cursor: str | None

    @model_validator(mode="after")
    def cancellation_detail_matches_root_summary(self) -> Self:
        if self.execution.kind != "import_job" or self.import_job is None:
            raise ValueError("Pinvi import-job detail must describe an import_job")
        if self.execution.job_id is not None:
            raise ValueError("import-job execution cannot carry linked job_id")
        if any(
            value is not None
            for value in (
                self.execution.scope_type,
                self.execution.priority,
                self.execution.run_mode,
                self.execution.operator,
            )
        ):
            raise ValueError("import-job execution cannot carry request-only fields")
        if self.execution.id != self.import_job.job_id:
            raise ValueError("execution id must match import_job job_id")
        if (
            self.execution.provider,
            self.execution.dataset_key,
        ) != (self.import_job.provider, self.import_job.dataset_key):
            raise ValueError("execution scope must match import job scope")
        if (
            self.execution.status != self.import_job.status
            or self.execution.created_at != self.import_job.created_at
            or self.execution.job_kind != self.import_job.kind
            or self.execution.progress != self.import_job.progress
            or self.execution.current_stage != self.import_job.current_stage
            or self.execution.error_message != self.import_job.error_message
            or self.execution.started_at != self.import_job.started_at
            or self.execution.finished_at != self.import_job.finished_at
            or self.execution.dagster_run_id != self.import_job.dagster_run_id
            or self.execution.trigger_kind != self.import_job.trigger_kind
            or self.execution.operation_registry_version
            != self.import_job.operation_registry_version
            or self.execution.dagster_run_status != self.import_job.dagster_run_status
            or self.execution.load_batch_id != self.import_job.load_batch_id
            or self.execution.parent_job_id != self.import_job.parent_job_id
        ):
            raise ValueError("execution lifecycle must match import job")
        if (self.import_job.provider is None) != (self.import_job.dataset_key is None):
            raise ValueError("import job provider and dataset_key must be an exact pair")
        if self.import_job.provider is not None and self.import_job.dataset_key is not None:
            matching_scope = [
                member
                for member in self.root.provider_datasets
                if member.provider == self.import_job.provider
                and member.dataset_key == self.import_job.dataset_key
            ]
            if len(matching_scope) != 1:
                raise ValueError("import job scope must match one canonical root member")
        if self.root.kind == "import_job":
            if (
                self.root.requested_job_id is not None
                or self.execution.request_id is not None
                or self.update_request is not None
            ):
                raise ValueError("standalone import root cannot carry update-request linkage")
            same_root_execution = self.root.id == self.execution.id
            if not (
                same_root_execution
                or (self.root.linked_job_count > 1 and self.import_job.parent_job_id is not None)
            ):
                raise ValueError(
                    "standalone requested import must belong to its canonical ancestor"
                )
            if same_root_execution and (
                self.root.status != self.execution.status
                or self.root.created_at != self.execution.created_at
                or self.root.progress != self.execution.progress
                or self.root.current_stage != self.execution.current_stage
                or self.root.error_message != self.execution.error_message
                or self.root.started_at != self.execution.started_at
                or self.root.finished_at != self.execution.finished_at
                or self.root.dagster_run_id != self.execution.dagster_run_id
                or self.root.dagster_run_status != self.execution.dagster_run_status
                or self.root.trigger_kind != self.execution.trigger_kind
                or self.root.operation_registry_version != self.execution.operation_registry_version
            ):
                raise ValueError("identical standalone root lifecycle must match execution")
        else:
            if (
                self.execution.request_id != self.root.id
                or self.update_request is None
                or self.update_request.request_id != self.root.id
                or self.root.requested_job_id != self.update_request.job_id
            ):
                raise ValueError(
                    "update-request root must reciprocally link request and import job"
                )
            update_request = self.update_request
            scope_provider = update_request.scope.get("provider")
            scope_dataset = update_request.scope.get("dataset_key")
            effective_providers = set(update_request.providers)
            effective_datasets = set(update_request.dataset_keys)
            if update_request.scope_type == "provider_dataset":
                scope_sync = update_request.scope.get("sync_scope")
                if (
                    not isinstance(scope_provider, str)
                    or not isinstance(scope_dataset, str)
                    or (scope_sync is not None and not isinstance(scope_sync, str))
                    or update_request.requested_sync_scope != scope_sync
                    or not isinstance(update_request.effective_sync_scope, str)
                    or not _is_canonical_sync_scope(update_request.effective_sync_scope)
                    or (
                        scope_sync is not None
                        and (
                            not _is_canonical_sync_scope(scope_sync)
                            or scope_sync != update_request.effective_sync_scope
                        )
                    )
                    or update_request.providers
                    or update_request.dataset_keys
                ):
                    raise ValueError("provider_dataset request must preserve its canonical scope")
                scope_members = [
                    member
                    for member in self.root.provider_datasets
                    if (member.provider, member.dataset_key) == (scope_provider, scope_dataset)
                ]
                if len(scope_members) != 1:
                    raise ValueError(
                        "provider_dataset request must include its exact direct root member"
                    )
                member_scope = scope_members[0].sync_scope
                if member_scope != update_request.effective_sync_scope:
                    raise ValueError("canonical root member must match effective sync scope")
            else:
                if (
                    update_request.requested_sync_scope is not None
                    or update_request.effective_sync_scope is not None
                ):
                    raise ValueError("non-provider_dataset request cannot carry a sync scope")
            effective_providers.update(member.provider for member in self.root.provider_datasets)
            effective_datasets.update(member.dataset_key for member in self.root.provider_datasets)
            if (
                self.root.scope_type != update_request.scope_type
                or self.root.status != update_request.status
                or self.root.created_at != update_request.created_at
                or self.root.priority != update_request.priority
                or self.root.run_mode != update_request.run_mode
                or self.root.operator != update_request.operator
                or self.root.error_message != update_request.error_message
                or self.root.started_at != update_request.started_at
                or self.root.finished_at != update_request.finished_at
                or self.root.dagster_run_id != update_request.dagster_run_id
                or self.root.progress is not None
                or self.root.current_stage is not None
                or self.root.dagster_run_status is not None
                or self.root.trigger_kind != "update_request"
                or self.root.operation_registry_version is not None
                or effective_providers != set(self.root.providers)
                or effective_datasets != set(self.root.dataset_keys)
            ):
                raise ValueError("update request scope must match exact canonical root members")
            if self.execution.id == update_request.job_id and (
                update_request.status != self.execution.status
                or update_request.created_at != self.execution.created_at
                or update_request.error_message != self.execution.error_message
                or update_request.started_at != self.execution.started_at
                or update_request.finished_at != self.execution.finished_at
                or update_request.dagster_run_id != self.execution.dagster_run_id
            ):
                raise ValueError("update request anchor lifecycle must match requested execution")
        projected = self.root.projected_job
        if projected.id == self.execution.id and (
            projected.job_kind != self.execution.job_kind
            or projected.status != self.execution.status
            or projected.progress != self.execution.progress
            or projected.current_stage != self.execution.current_stage
            or projected.error_message != self.execution.error_message
            or projected.created_at != self.execution.created_at
            or projected.started_at != self.execution.started_at
            or projected.finished_at != self.execution.finished_at
            or projected.dagster_run_id != self.execution.dagster_run_id
            or projected.dagster_run_status != self.execution.dagster_run_status
            or projected.trigger_kind != self.execution.trigger_kind
            or projected.operation_registry_version != self.execution.operation_registry_version
            or projected.load_batch_id != self.execution.load_batch_id
            or projected.parent_job_id != self.execution.parent_job_id
        ):
            raise ValueError("projected job lifecycle must match identical execution")
        for member in self.root.provider_datasets:
            if member.operation_member_id != self.execution.id:
                continue
            if member.status != self.execution.status or (member.provider, member.dataset_key) != (
                self.execution.provider,
                self.execution.dataset_key,
            ):
                raise ValueError("provider dataset member must match identical execution")
        summary = self.root.cancellation
        detail = self.cancellation
        if (summary is None) != (detail is None):
            raise ValueError("detail cancellation must match root cancellation presence")
        if summary is not None and detail is not None:
            member_ids = [member.job_id for member in detail.members]
            member_id_set = set(member_ids)
            required_member_ids = {
                self.execution.id,
                self.root.projected_job.id,
                *(member.operation_member_id for member in self.root.provider_datasets),
            }
            if self.root.kind == "import_job":
                required_member_ids.add(self.root.id)
            elif self.root.requested_job_id is not None:
                required_member_ids.add(self.root.requested_job_id)
            requested_members = [
                member for member in detail.members if member.job_id == self.execution.id
            ]
            if (
                detail.root.kind != self.root.kind
                or detail.root.id != self.root.id
                or summary.cancellation_id != detail.cancellation_id
                or summary.status != detail.status
                or summary.requested_at != detail.requested_at
                or summary.requested_by != detail.requested_by
                or summary.reason != detail.reason
                or summary.retryable != detail.retryable
                or summary.unresolved_member_count != detail.unresolved_member_count
            ):
                raise ValueError("detail cancellation must match root cancellation summary")
            if len(member_ids) != len(set(member_ids)):
                raise ValueError("cancellation frozen members must have unique identities")
            if detail.previous_cancellation_id is None:
                if (
                    len(member_ids) != self.root.linked_job_count
                    or not required_member_ids.issubset(member_id_set)
                    or len(requested_members) != 1
                ):
                    raise ValueError("initial cancellation must freeze canonical root membership")
            elif len(member_ids) > self.root.linked_job_count:
                raise ValueError("retry cancellation cannot exceed canonical root membership")
            if requested_members:
                requested_member = requested_members[0]
                if (
                    requested_member.operation_kind != self.import_job.kind
                    or requested_member.dagster_run_id != self.import_job.dagster_run_id
                ):
                    raise ValueError(
                        "cancellation requested member must match import job execution scope"
                    )
        return self


@dataclass(frozen=True, slots=True)
class ProjectedDatasetGrid:
    items: list[AdminProviderDatasetSummary]
    schedule_source_status: Literal["ok", "unavailable", "error"]
    schedule_source_errors: list[str]


def _contract_error(label: str, _exc: ValidationError) -> KorTravelMapOpsContractError:
    return KorTravelMapOpsContractError(f"{label} contract mismatch")


def pipeline_executions_canonical_url(
    *,
    status_filter: str | None,
    load_batch_id: str | None,
    parent_job_id: str | None,
) -> str:
    """Map의 cursor/page-size 제외 canonical provenance URL을 재구성한다."""

    query = urlencode(
        [
            (name, value)
            for name, value in (
                ("kind", "import_job"),
                ("status", status_filter),
                ("load_batch_id", load_batch_id),
                ("parent_job_id", parent_job_id),
            )
            if value is not None
        ],
        quote_via=quote,
    )
    return f"/v1/ops/pipeline/executions?{query}"


def validate_pipeline_overview(data: dict[str, Any]) -> dict[str, Any]:
    """ETL summary가 소비하는 canonical overview 전체 셰입을 검증한다."""

    try:
        return _PipelineOverviewData.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        raise _contract_error("pipeline overview", exc) from exc


def project_dataset_grid_snapshot(
    data: dict[str, Any],
    *,
    key: str | None = None,
) -> ProjectedDatasetGrid:
    """dataset grid 전체 계약과 schedule 출처 상태를 검증하고 표시 DTO로 바꾼다."""

    try:
        canonical = _DatasetsGridData.model_validate(data)
        needle = (key or "").strip().casefold()
        items = [
            AdminProviderDatasetSummary(
                provider=item.provider,
                dataset_key=item.dataset_key,
                sync_scope=item.sync_scope,
                status=item.status,
                last_success_at=item.last_success_at,
                last_failure_at=item.last_failure_at,
                consecutive_failures=item.consecutive_failures,
                eligible_after=item.eligible_after,
                schedule_next_scheduled_at=item.schedule.next_scheduled_at,
                links=[
                    {
                        "rel": "detail",
                        "href": item.detail_url,
                        "label": "dataset detail",
                    }
                ],
                refresh_policy=(
                    item.refresh_policy.model_dump(mode="json")
                    if item.refresh_policy is not None
                    else None
                ),
            )
            for item in canonical.items
            if not needle
            or needle in item.provider.casefold()
            or needle in item.dataset_key.casefold()
        ]
    except ValidationError as exc:
        raise _contract_error("dataset grid", exc) from exc
    return ProjectedDatasetGrid(
        items=items,
        schedule_source_status=canonical.schedule_source_status,
        schedule_source_errors=canonical.schedule_source_errors,
    )


def project_dataset_grid(
    data: dict[str, Any],
    *,
    key: str | None = None,
) -> list[AdminProviderDatasetSummary]:
    """dataset grid를 Pinvi provider-sync 표시 DTO로 투영한다."""

    return project_dataset_grid_snapshot(data, key=key).items


def _project_pipeline_execution(
    item: _PipelineExecutionRoot,
) -> AdminProviderImportJobRecord:
    if item.kind != "import_job":
        raise KorTravelMapOpsContractError("pipeline execution kind must be import_job")
    projected = item.projected_job
    return AdminProviderImportJobRecord(
        job_id=str(item.id),
        kind="import_job",
        status=item.status,
        progress=item.progress,
        projected_job_id=str(projected.id),
        projected_job_kind=projected.job_kind,
        projected_job_status=projected.status,
        projected_job_progress=projected.progress,
        projected_job_load_batch_id=(
            str(projected.load_batch_id) if projected.load_batch_id is not None else None
        ),
        projected_job_parent_job_id=(
            str(projected.parent_job_id) if projected.parent_job_id is not None else None
        ),
        cancellation=(
            item.cancellation.model_dump(mode="json") if item.cancellation is not None else None
        ),
        payload={
            "provider": item.providers[0] if len(item.providers) == 1 else None,
            "dataset_key": item.dataset_keys[0] if len(item.dataset_keys) == 1 else None,
            "providers": item.providers,
            "dataset_keys": item.dataset_keys,
            "provider_datasets": [
                member.model_dump(mode="json") for member in item.provider_datasets
            ],
        },
        status_url=item.detail_url,
        current_stage=item.current_stage,
        error_message=item.error_message,
        created_at=item.created_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        links=[
            {
                "rel": "detail",
                "href": item.detail_url,
                "label": "pipeline execution detail",
            }
        ],
    )


def project_pipeline_execution(
    data: dict[str, Any],
    *,
    requested_job_id: str,
) -> AdminProviderImportJobRecord:
    """canonical detail의 root와 cancellation 일치성을 검증해 한 건을 투영한다."""

    try:
        requested_id = UUID(requested_job_id)
        canonical = _PipelineExecutionDetailData.model_validate(data)
        execution = canonical.execution
        if execution.id != requested_id:
            raise KorTravelMapOpsContractError(
                "pipeline execution detail does not match requested job"
            )
        root = canonical.root
        projected = root.projected_job
        return AdminProviderImportJobRecord(
            job_id=str(execution.id),
            kind="import_job",
            status=execution.status,
            progress=execution.progress,
            projected_job_id=str(projected.id),
            projected_job_kind=projected.job_kind,
            projected_job_status=projected.status,
            projected_job_progress=projected.progress,
            projected_job_load_batch_id=(
                str(projected.load_batch_id) if projected.load_batch_id is not None else None
            ),
            projected_job_parent_job_id=(
                str(projected.parent_job_id) if projected.parent_job_id is not None else None
            ),
            cancellation=(
                root.cancellation.model_dump(mode="json") if root.cancellation is not None else None
            ),
            payload={
                "provider": root.providers[0] if len(root.providers) == 1 else None,
                "dataset_key": (root.dataset_keys[0] if len(root.dataset_keys) == 1 else None),
                "providers": root.providers,
                "dataset_keys": root.dataset_keys,
                "provider_datasets": [
                    member.model_dump(mode="json") for member in root.provider_datasets
                ],
                "root_kind": root.kind,
                "root_id": str(root.id),
            },
            status_url=execution.detail_url,
            current_stage=execution.current_stage,
            error_message=execution.error_message,
            created_at=execution.created_at,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            links=[
                {
                    "rel": "detail",
                    "href": execution.detail_url,
                    "label": "pipeline execution detail",
                },
                {
                    "rel": "canonical_root",
                    "href": root.detail_url,
                    "label": "canonical pipeline root",
                },
            ],
        )
    except ValidationError as exc:
        raise _contract_error("pipeline execution", exc) from exc
    except ValueError as exc:
        if isinstance(exc, KorTravelMapOpsContractError):
            raise
        raise KorTravelMapOpsContractError("requested_job_id must be a canonical UUID") from exc


def project_pipeline_executions(
    data: dict[str, Any],
    *,
    expected_canonical_url: str,
) -> list[AdminProviderImportJobRecord]:
    """canonical import root와 projected job을 섞지 않고 각각 표시한다."""

    try:
        canonical = _PipelineExecutionsData.model_validate(data)
        if canonical.canonical_url != expected_canonical_url:
            raise KorTravelMapOpsContractError(
                "pipeline execution canonical_url provenance mismatch"
            )
        return [_project_pipeline_execution(item) for item in canonical.items]
    except ValidationError as exc:
        raise _contract_error("pipeline execution", exc) from exc


def project_pipeline_page_next_cursor(
    meta: dict[str, Any],
    *,
    expected_page_size: int,
) -> str | None:
    """cursor page metadata와 요청 page size를 fail-closed 검증한다."""

    raw_page = meta.get("page")
    if not isinstance(raw_page, dict):
        raise KorTravelMapOpsContractError("pipeline execution pagination metadata is required")
    try:
        page = _PipelinePageMeta.model_validate(raw_page)
    except ValidationError as exc:
        raise _contract_error("pipeline execution pagination", exc) from exc
    if page.page_size != expected_page_size:
        raise KorTravelMapOpsContractError("pipeline execution page_size provenance mismatch")
    return page.next_cursor


def validate_pipeline_cancellation_detail(data: dict[str, Any]) -> dict[str, Any]:
    """typed cancellation problem/success가 공유하는 전체 canonical detail을 검증한다."""

    try:
        return _CancellationDetail.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        raise _contract_error("pipeline cancellation", exc) from exc


def validate_pipeline_cancellation_root_without_attempt(
    data: dict[str, Any],
) -> dict[str, Any]:
    """아직 durable attempt가 없는 canonical root-only problem shape를 검증한다."""

    try:
        return _CancellationRootWithoutAttempt.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        raise _contract_error("pipeline cancellation root", exc) from exc


def project_pipeline_cancellation(
    data: dict[str, Any],
    *,
    requested_job_id: str,
) -> AdminProviderImportJobCancellationResult:
    """canonical cancellation 전체 계약·불변식을 검증한 뒤 감사/표시 DTO로 투영한다."""

    try:
        requested_id = UUID(requested_job_id)
        canonical = _CancellationDetail.model_validate(validate_pipeline_cancellation_detail(data))
        member_ids = {member.job_id for member in canonical.members}
        if canonical.previous_cancellation_id is None:
            if requested_id not in member_ids:
                raise KorTravelMapOpsContractError(
                    "requested job must be included in initial cancellation members"
                )
            if canonical.root.kind == "import_job" and canonical.root.id not in member_ids:
                raise KorTravelMapOpsContractError(
                    "import root must be included in initial cancellation members"
                )
        return AdminProviderImportJobCancellationResult(
            requested_job_id=str(requested_id),
            root_kind=canonical.root.kind,
            root_id=str(canonical.root.id),
            cancellation_id=str(canonical.cancellation_id),
            status=canonical.status,
            requested_at=canonical.requested_at,
            requested_by=canonical.requested_by,
            reason=canonical.reason,
            retryable=canonical.retryable,
            unresolved_member_count=canonical.unresolved_member_count,
            warnings=canonical.warnings,
        )
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, KorTravelMapOpsContractError):
            raise
        if isinstance(exc, ValidationError):
            raise _contract_error("pipeline cancellation", exc) from exc
        raise KorTravelMapOpsContractError("requested_job_id must be a canonical UUID") from exc
