"""Admin schema — `docs/api/admin.md`."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.storage import AttachmentLibraryItem, AvatarApplyRequest


class AdminUserSummary(BaseModel):
    """목록용 — email은 마스킹 응답."""

    user_id: uuid.UUID
    email_masked: str
    nickname: str | None
    status: Literal["pending_verification", "pending_profile", "active", "disabled", "deleted"]
    roles: list[Literal["user", "admin", "operator", "cpo"]]
    email_verified_at: datetime | None
    created_at: datetime


class AdminAuditEntry(BaseModel):
    log_id: int
    actor_user_id: uuid.UUID
    action: str
    resource_type: str
    resource_id: str | None
    access_reason: str | None
    target_pii_fields: list[str] | None
    prev_hash: str
    content_hash: str
    occurred_at: datetime


class AdminLocationAuditEntry(BaseModel):
    log_id: int
    user_id: uuid.UUID
    occurred_at: datetime
    endpoint: str
    purpose: str
    lat_masked: str | None
    lng_masked: str | None
    request_id: uuid.UUID
    ip_hash: str
    prev_hash: str
    content_hash: str


class AdminApiCallEntry(BaseModel):
    log_id: int
    provider: str
    endpoint: str
    status_code: int | None
    latency_ms: int | None
    error_class: str | None
    error_message: str | None
    request_id: uuid.UUID | None
    occurred_at: datetime


class AdminStatsSeriesBucket(BaseModel):
    bucket_start: datetime
    users_created: int = 0
    trips_created: int = 0
    api_calls: int = 0
    api_failures: int = 0


class AdminStatsLoadSnapshot(BaseModel):
    cpu_count: int | None = None
    load_1m: float | None = None
    load_5m: float | None = None
    load_15m: float | None = None


class AdminStatsCapacitySnapshot(BaseModel):
    attachments_total_bytes: int = 0
    attachments_count: int = 0
    trip_attachment_quota_bytes: int | None = None
    user_attachment_quota_bytes: int | None = None
    attachment_max_upload_bytes: int | None = None
    avatar_max_upload_bytes: int | None = None
    users_with_quota_override: int = 0
    disk_total_bytes: int | None = None
    disk_used_bytes: int | None = None
    disk_free_bytes: int | None = None


class AdminStatsOverview(BaseModel):
    generated_at: datetime
    users_total: int
    users_24h: int
    users_pending_verification: int
    trips_total: int
    trips_active: int
    pois_total: int
    email_queue_pending: int
    api_calls_24h: int
    api_calls_failed_24h: int
    api_failure_rate_pct: float
    api_latency_p95_ms: int | None = None
    features_by_kind: dict[str, int] = Field(default_factory=dict)
    etl_last_24h: dict[str, int] = Field(default_factory=lambda: {"success": 0, "failed": 0})
    series_24h: list[AdminStatsSeriesBucket] = Field(default_factory=list)
    load: AdminStatsLoadSnapshot = Field(default_factory=AdminStatsLoadSnapshot)
    capacity: AdminStatsCapacitySnapshot = Field(default_factory=AdminStatsCapacitySnapshot)


AdminSystemStatus = Literal["ok", "degraded", "down", "unknown"]


class AdminSystemServiceStatus(BaseModel):
    key: str
    label: str
    status: AdminSystemStatus
    message: str | None = None
    latency_ms: int | None = None


class AdminSystemSummary(BaseModel):
    generated_at: datetime
    services: list[AdminSystemServiceStatus]


class AdminDockerContainerStatus(BaseModel):
    container_id: str
    name: str
    image: str
    state: str
    status: str
    health: str | None = None
    compose_project: str | None = None
    compose_service: str | None = None


class AdminSystemDetail(BaseModel):
    generated_at: datetime
    dependencies: list[AdminSystemServiceStatus]
    docker: AdminSystemServiceStatus
    containers: list[AdminDockerContainerStatus] = Field(default_factory=list)


class AdminEtlDefinitionAsset(BaseModel):
    key: str
    group_name: str | None = None
    description: str | None = None


class AdminEtlDefinitionJob(BaseModel):
    name: str
    trigger: str
    description: str | None = None
    asset_keys: list[str] = Field(default_factory=list)


class AdminEtlDefinitionSchedule(BaseModel):
    name: str
    job_name: str
    cron_schedule: str
    execution_timezone: str | None = None
    status: str = "configured"


class AdminEtlDefinitionSensor(BaseModel):
    name: str
    job_name: str | None = None
    status: str = "configured"


class AdminEmailOutboxTemplateSummary(BaseModel):
    template: str
    total: int = 0
    pending: int = 0
    sent: int = 0
    delivered: int = 0
    failed: int = 0
    bounced: int = 0
    complained: int = 0
    failure_count: int = 0
    failure_rate: float = 0.0


class AdminEmailOutboxSummary(BaseModel):
    total: int = 0
    pending_total: int = 0
    pending_due: int = 0
    pending_backoff: int = 0
    stuck_pending: int = 0
    failed: int = 0
    bounced: int = 0
    complained: int = 0
    retry_exhausted: int = 0
    oldest_pending_scheduled_at: datetime | None = None
    stuck_threshold_minutes: int
    max_attempts: int
    template_window_hours: int
    template_stats: list[AdminEmailOutboxTemplateSummary] = Field(default_factory=list)


class AdminTelegramOutboxCategorySummary(BaseModel):
    category: str
    total: int = 0
    pending: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    retry_exhausted: int = 0
    retry_exhausted_rate: float = 0.0


class AdminTelegramOutboxSummary(BaseModel):
    total: int = 0
    pending_total: int = 0
    pending_due: int = 0
    pending_backoff: int = 0
    stuck_pending: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    retry_exhausted: int = 0
    oldest_pending_scheduled_at: datetime | None = None
    stuck_threshold_minutes: int
    max_attempts: int
    category_window_hours: int
    category_stats: list[AdminTelegramOutboxCategorySummary] = Field(default_factory=list)


class AdminPiiRetentionSummary(BaseModel):
    dry_run: bool = True
    generated_at: datetime
    user_pii_cutoff: datetime
    session_cutoff: datetime
    location_cutoff: datetime
    user_pii_grace_days: int
    session_grace_days: int
    location_retention_months: int
    total_candidates: int = 0
    deleted_user_pii_candidates: int = 0
    deleted_user_oauth_identity_candidates: int = 0
    excluded_privileged_deleted_users: int = 0
    expired_signup_verifications: int = 0
    expired_password_reset_tokens: int = 0
    old_revoked_sessions: int = 0
    old_expired_sessions: int = 0
    expired_oauth_login_states: int = 0
    expired_mobile_oauth_exchanges: int = 0
    location_access_logs_over_retention: int = 0
    admin_audit_pii_over_retention: int = 0


class AdminLocationLogArchivePurposeSummary(BaseModel):
    purpose: str
    total: int = 0


class AdminLocationLogArchiveSummary(BaseModel):
    dry_run: bool = True
    generated_at: datetime
    archive_cutoff: datetime
    location_retention_months: int
    total_candidates: int = 0
    oldest_candidate_at: datetime | None = None
    newest_candidate_at: datetime | None = None
    archive_tail_log_id: int | None = None
    active_head_log_id: int | None = None
    active_rows_after_cutoff: int = 0
    chain_bridge_required: bool = False
    bridge_anchor_matches: bool | None = None
    pending_outbox_total: int = 0
    pending_outbox_before_cutoff: int = 0
    archive_blocked_by_pending_outbox: bool = False
    oldest_pending_outbox_at: datetime | None = None
    purpose_stats: list[AdminLocationLogArchivePurposeSummary] = Field(default_factory=list)


class AdminPinviEtlSummary(BaseModel):
    status: AdminSystemStatus
    message: str | None = None
    latency_ms: int | None = None
    checked_at: datetime | None = None
    dagster_version: str | None = None
    dagster_webserver_version: str | None = None
    dagster_graphql_version: str | None = None
    repository_count: int = 0
    job_count: int = 0
    asset_count: int = 0
    schedule_count: int = 0
    sensor_count: int = 0
    repositories: list[AdminDagsterRepositorySummary] = Field(default_factory=list)
    recent_runs: list[AdminDagsterRunSummary] = Field(default_factory=list)
    assets: list[AdminEtlDefinitionAsset] = Field(default_factory=list)
    jobs: list[AdminEtlDefinitionJob] = Field(default_factory=list)
    schedules: list[AdminEtlDefinitionSchedule] = Field(default_factory=list)
    sensors: list[AdminEtlDefinitionSensor] = Field(default_factory=list)
    email_outbox: AdminEmailOutboxSummary | None = None
    telegram_outbox: AdminTelegramOutboxSummary | None = None
    pii_retention: AdminPiiRetentionSummary | None = None
    location_log_archive: AdminLocationLogArchiveSummary | None = None


class AdminDagsterJobSummary(BaseModel):
    name: str
    is_job: bool = True


class AdminDagsterScheduleSummary(BaseModel):
    name: str
    job_name: str | None = None
    cron_schedule: str | None = None
    execution_timezone: str | None = None
    status: str | None = None


class AdminDagsterSensorSummary(BaseModel):
    name: str
    status: str | None = None


class AdminDagsterRepositorySummary(BaseModel):
    name: str
    location_name: str | None = None
    jobs: list[AdminDagsterJobSummary] = Field(default_factory=list)
    schedules: list[AdminDagsterScheduleSummary] = Field(default_factory=list)
    sensors: list[AdminDagsterSensorSummary] = Field(default_factory=list)
    asset_count: int = 0
    asset_groups: list[str] = Field(default_factory=list)


class AdminDagsterRunSummary(BaseModel):
    run_id: str
    status: str
    job_name: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    update_time: float | None = None
    tags: dict[str, Any] = Field(default_factory=dict)


class AdminProviderImportJobRecord(BaseModel):
    job_id: str
    kind: str
    status: str
    progress: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    status_url: str | None = None
    current_stage: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    load_batch_id: str | None = None
    parent_job_id: str | None = None
    source_checksum: str | None = None
    links: dict[str, Any] = Field(default_factory=dict)


class AdminProviderImportJobsResponse(BaseModel):
    items: list[AdminProviderImportJobRecord] = Field(default_factory=list)
    page_size: int
    next_cursor: str | None = None


class AdminProviderDatasetSummary(BaseModel):
    provider: str
    dataset_key: str
    sync_scope: str
    status: str
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    consecutive_failures: int = 0
    next_run_after: datetime | None = None
    links: dict[str, Any] = Field(default_factory=dict)
    refresh_policy: dict[str, Any] | None = None


class AdminProviderSyncResponse(BaseModel):
    items: list[AdminProviderDatasetSummary] = Field(default_factory=list)
    total: int


class AdminKorTravelMapEtlSummary(BaseModel):
    status: AdminSystemStatus
    dagster_status: str
    checked_at: datetime | None = None
    repository_count: int = 0
    job_count: int = 0
    asset_count: int = 0
    schedule_count: int = 0
    sensor_count: int = 0
    run_counts: dict[str, int] = Field(default_factory=dict)
    repositories: list[AdminDagsterRepositorySummary] = Field(default_factory=list)
    recent_runs: list[AdminDagsterRunSummary] = Field(default_factory=list)
    features_total: int | None = None
    source_records_total: int | None = None
    import_jobs_by_status: dict[str, int] = Field(default_factory=dict)
    dedup_queue_by_status: dict[str, int] = Field(default_factory=dict)
    provider_dataset_count: int = 0
    provider_failure_count: int = 0
    recent_import_jobs: list[AdminProviderImportJobRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AdminEtlSummary(BaseModel):
    generated_at: datetime
    pinvi: AdminPinviEtlSummary
    kor_travel_map: AdminKorTravelMapEtlSummary


class AdminDedupFeatureRecord(BaseModel):
    feature_id: str
    name: str
    kind: str
    category: str
    lon: float | None = None
    lat: float | None = None
    provider: str | None = None
    dataset_key: str | None = None


class AdminDedupReviewRecord(BaseModel):
    review_id: str
    status: str
    total_score: float
    name_score: float
    spatial_score: float
    category_score: float
    distance_m: float | None = None
    feature_a: AdminDedupFeatureRecord
    feature_b: AdminDedupFeatureRecord
    decision_reason: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    created_at: datetime


class AdminDedupReviewPagedResponse(BaseModel):
    items: list[AdminDedupReviewRecord] = Field(default_factory=list)
    page_size: int
    next_cursor: str | None = None


AdminDedupDecision = Literal["accepted", "rejected", "merged", "ignored"]


class AdminDedupDecisionRequest(BaseModel):
    decision: AdminDedupDecision
    access_reason: str = Field(min_length=1, max_length=500)
    kor_travel_map_reason: str | None = Field(default=None, min_length=1, max_length=500)
    master_feature_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _check_master_feature_id(self) -> AdminDedupDecisionRequest:
        if self.decision == "merged" and not self.master_feature_id:
            raise ValueError("merged decision에는 master_feature_id가 필요합니다.")
        return self


class AdminDedupDecisionResponse(BaseModel):
    review_id: str
    decision: AdminDedupDecision
    changed: bool
    master_feature_id: str | None = None
    loser_feature_id: str | None = None
    merge_id: str | None = None
    source_links_moved: int | None = None
    source_links_dropped: int | None = None


class AdminCategoryMappingItem(BaseModel):
    code: str
    label: str
    parent_code: str | None = None
    depth: int = 0
    path: list[str] = Field(default_factory=list)
    maki_icon: str = "marker"
    is_active: bool = True
    sort_order: int = 0
    tier1_code: str | None = None
    tier1_name: str | None = None
    tier2_code: str | None = None
    tier2_name: str | None = None
    tier3_code: str | None = None
    tier3_name: str | None = None
    tier4_code: str | None = None
    tier4_name: str | None = None
    db_active: bool | None = None
    db_feature_count: int | None = None


class AdminCategoryMappingsResponse(BaseModel):
    source_of_truth: str = "kor-travel-map:/v1/categories"
    mode: Literal["read_only"] = "read_only"
    include_counts: bool = True
    active_only: bool = False
    total_count: int = 0
    filtered_count: int = 0
    active_count: int = 0
    inactive_count: int = 0
    db_feature_total: int | None = None
    items: list[AdminCategoryMappingItem] = Field(default_factory=list)


class AdminSeedScenario(BaseModel):
    key: str
    title: str
    description: str
    destructive: bool = False
    confirm_phrase: str
    steps: list[str] = Field(default_factory=list)


class AdminSeedScenarioListResponse(BaseModel):
    environment: str
    enabled: bool
    mode: Literal["dry_run_only"] = "dry_run_only"
    scenarios: list[AdminSeedScenario] = Field(default_factory=list)


class AdminSeedScenarioRunRequest(BaseModel):
    confirm: str = Field(min_length=1, max_length=120)
    access_reason: str = Field(min_length=1, max_length=500)
    dry_run: bool = True


class AdminResetStatusResponse(BaseModel):
    environment: str
    enabled: bool
    mode: Literal["dry_run_only"] = "dry_run_only"
    confirm_phrase: str = "RESET"
    target_schemas: list[str] = Field(default_factory=lambda: ["app"])


class AdminResetRunRequest(BaseModel):
    confirm: str = Field(min_length=1, max_length=120)
    access_reason: str = Field(min_length=1, max_length=500)
    dry_run: bool = True
    include_seed: bool = False


class AdminDevSafetyActionResult(BaseModel):
    action: str
    target: str
    status: Literal["dry_run"]
    dry_run: bool = True
    audit_log_id: int
    would_execute: list[str] = Field(default_factory=list)
    message: str


class AdminIntegrityIssueRecord(BaseModel):
    issue_id: str
    violation_type: str
    severity: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    detected_at: datetime
    provider: str | None = None
    dataset_key: str | None = None
    feature_id: str | None = None
    source_record_key: str | None = None
    resolved_at: datetime | None = None


class AdminIntegrityIssuesResponse(BaseModel):
    items: list[AdminIntegrityIssueRecord] = Field(default_factory=list)
    page_size: int
    next_cursor: str | None = None


AdminIntegrityIssueAction = Literal["resolve", "ignore", "reopen"]


class AdminIntegrityIssueActionRequest(BaseModel):
    action: AdminIntegrityIssueAction
    access_reason: str = Field(min_length=1, max_length=500)
    kor_travel_map_reason: str | None = Field(default=None, max_length=500)


class AdminIntegrityIssueActionResponse(BaseModel):
    action: AdminIntegrityIssueAction
    issue: AdminIntegrityIssueRecord


class AdminConsistencyReportRecord(BaseModel):
    report_id: str
    batch_id: str
    started_at: datetime
    finished_at: datetime | None = None
    severity_max: str
    cases: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class AdminConsistencyReportsResponse(BaseModel):
    items: list[AdminConsistencyReportRecord] = Field(default_factory=list)
    page_size: int
    next_cursor: str | None = None


class AdminUpstreamSystemLogRecord(BaseModel):
    log_id: str
    level: str
    source: str
    event: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    created_at: datetime


class AdminUpstreamSystemLogsResponse(BaseModel):
    items: list[AdminUpstreamSystemLogRecord] = Field(default_factory=list)
    page_size: int
    next_cursor: str | None = None


class AdminUpstreamApiCallLogRecord(BaseModel):
    log_id: str
    method: str
    path: str
    status_code: int
    duration_ms: int
    request_id: str | None = None
    error_code: str | None = None
    created_at: datetime


class AdminUpstreamApiCallLogsResponse(BaseModel):
    items: list[AdminUpstreamApiCallLogRecord] = Field(default_factory=list)
    page_size: int
    next_cursor: str | None = None


AdminRequestTimelineStatus = Literal["ok", "partial"]


class AdminRequestTimelineSource(BaseModel):
    source: str
    status: Literal["ok", "degraded"]
    event_count: int = 0
    message: str | None = None


class AdminRequestTimelineEvent(BaseModel):
    event_id: str
    occurred_at: datetime
    source: str
    title: str
    status: str | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class AdminRequestTimelineResponse(BaseModel):
    request_id: uuid.UUID
    generated_at: datetime
    status: AdminRequestTimelineStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    sources: list[AdminRequestTimelineSource] = Field(default_factory=list)
    events: list[AdminRequestTimelineEvent] = Field(default_factory=list)


AdminFeatureSort = Literal[
    "name",
    "updated_at",
    "created_at",
    "kind",
    "status",
    "provider",
    "issue_count",
]
AdminFeatureSortOrder = Literal["asc", "desc"]


class AdminFeatureIssueSummary(BaseModel):
    issue_id: str | None = None
    violation_type: str | None = None
    severity: str | None = None
    message: str | None = None
    detected_at: datetime | None = None


class AdminFeatureSummary(BaseModel):
    feature_id: str
    kind: str
    name: str
    category: str
    status: str
    lon: float | None = None
    lat: float | None = None
    address_label: str | None = None
    primary_provider: str | None = None
    primary_dataset_key: str | None = None
    issue_count: int = 0
    issues: list[AdminFeatureIssueSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AdminFeaturePagedResponse(BaseModel):
    items: list[AdminFeatureSummary]
    page_size: int
    next_cursor: str | None = None
    duration_ms: int | None = None


class AdminFeatureChangeRequestRecord(BaseModel):
    request_id: str
    feature_id: str
    action: str
    status: str
    review_mode: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    requested_by: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    applied_at: datetime | None = None
    created_at: datetime


class AdminFeatureChangeRequestPagedResponse(BaseModel):
    items: list[AdminFeatureChangeRequestRecord] = Field(default_factory=list)
    review_mode: str | None = None
    page_size: int


class AdminFeatureChangeRequestActionRequest(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)
    kor_travel_map_reason: str | None = Field(default=None, max_length=500)


class AdminFeatureDetailFeature(BaseModel):
    feature_id: str
    kind: str
    name: str
    category: str
    status: str
    lon: float | None = None
    lat: float | None = None
    coord_precision_digits: int | None = None
    area_square_meters: float | None = None
    address: dict[str, Any] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)
    urls: dict[str, Any] = Field(default_factory=dict)
    raw_refs: list[dict[str, Any]] = Field(default_factory=list)
    legal_dong_code: str | None = None
    road_name_code: str | None = None
    road_address_management_no: str | None = None
    admin_dong_code: str | None = None
    sido_code: str | None = None
    sigungu_code: str | None = None
    marker_icon: str | None = None
    marker_color: str | None = None
    parent_feature_id: str | None = None
    sibling_group_id: str | None = None
    data_origin: str | None = None
    data_version: int | None = None
    user_change_kind: str | None = None
    user_change_status: str | None = None
    user_change_request_id: str | None = None
    user_deleted_at: datetime | None = None
    user_deleted_by: str | None = None
    user_change_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class AdminFeatureDetailSource(BaseModel):
    source_record_key: str
    provider: str
    dataset_key: str
    source_entity_type: str
    source_entity_id: str
    source_version: str | None = None
    source_role: str
    match_method: str
    confidence: int
    is_primary_source: bool
    raw_name: str | None = None
    raw_address: str | None = None
    raw_longitude: float | None = None
    raw_latitude: float | None = None
    raw_payload_hash: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime
    imported_at: datetime
    expires_at: datetime | None = None
    linked_at: datetime


class AdminFeatureDetailIssue(BaseModel):
    issue_id: str
    provider: str | None = None
    dataset_key: str | None = None
    source_record_key: str | None = None
    violation_type: str
    severity: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    detected_at: datetime
    resolved_at: datetime | None = None


class AdminFeatureDetailOverride(BaseModel):
    override_id: str
    source_record_key: str | None = None
    field_path: str
    source_value: Any = None
    override_value: Any = None
    prevent_provider_reactivation: bool
    status: str
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime


class AdminFeatureDetailVersion(BaseModel):
    feature_id: str
    version: int
    origin: str
    change_kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    created_by: str | None = None
    created_at: datetime


class AdminFeatureDetailFile(BaseModel):
    file_id: str
    file_type: str
    storage_backend: str
    bucket: str
    object_key: str
    source_url: str | None = None
    public_url: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    checksum_sha256: str | None = None
    width: int | None = None
    height: int | None = None
    role: str
    display_order: int
    alt_text: str | None = None
    provider: str | None = None
    dataset_key: str | None = None
    source_record_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AdminFeatureDetail(BaseModel):
    feature: AdminFeatureDetailFeature
    sources: list[AdminFeatureDetailSource] = Field(default_factory=list)
    issues: list[AdminFeatureDetailIssue] = Field(default_factory=list)
    overrides: list[AdminFeatureDetailOverride] = Field(default_factory=list)
    versions: list[AdminFeatureDetailVersion] = Field(default_factory=list)
    change_requests: list[AdminFeatureChangeRequestRecord] = Field(default_factory=list)
    files: list[AdminFeatureDetailFile] = Field(default_factory=list)


class AdminUserFileQuota(BaseModel):
    attachment_max_upload_bytes_override: int | None = Field(default=None, gt=0)
    trip_attachment_quota_bytes_override: int | None = Field(default=None, gt=0)
    user_attachment_quota_bytes_override: int | None = Field(default=None, gt=0)
    effective_attachment_max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    effective_trip_attachment_quota_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    effective_user_attachment_quota_bytes: int = Field(default=1024 * 1024 * 1024, gt=0)


class AdminUserDetail(AdminUserSummary):
    email: str
    email_revealed: bool
    email_status: Literal["active", "bounced", "complained"]
    is_active: bool
    avatar_url: str | None = None
    avatar_kind: Literal["default", "upload", "external"] = "default"
    avatar_content_type: str | None = None
    avatar_byte_size: int | None = None
    avatar_updated_at: datetime | None = None
    has_avatar: bool = False
    file_quota: AdminUserFileQuota = Field(default_factory=AdminUserFileQuota)
    recent_audit: list[AdminAuditEntry] = Field(default_factory=list)


class AdminActionRequest(BaseModel):
    """force-verify / disable 등 위험 액션 — 사유 필수."""

    access_reason: str = Field(min_length=1, max_length=500)


class AdminAvatarApplyRequest(AvatarApplyRequest):
    access_reason: str = Field(min_length=1, max_length=500)


class AdminAvatarDeleteRequest(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)


class AdminAvatarSettings(BaseModel):
    avatar_max_upload_bytes: int = Field(gt=0)


class AdminAvatarSettingsUpdateRequest(BaseModel):
    avatar_max_upload_bytes: int = Field(gt=0, le=104_857_600)
    access_reason: str = Field(min_length=1, max_length=500)


class AdminFileStorageSettings(BaseModel):
    attachment_max_upload_bytes: int = Field(gt=0)
    trip_attachment_quota_bytes: int = Field(gt=0)
    user_attachment_quota_bytes: int = Field(gt=0)


class AdminFileStorageSettingsUpdateRequest(BaseModel):
    attachment_max_upload_bytes: int = Field(gt=0, le=1_073_741_824)
    trip_attachment_quota_bytes: int = Field(gt=0, le=10_737_418_240)
    user_attachment_quota_bytes: int = Field(gt=0, le=109_951_162_777_600)
    access_reason: str = Field(min_length=1, max_length=500)


class AdminUserFileQuotaUpdateRequest(BaseModel):
    attachment_max_upload_bytes_override: int | None = Field(default=None, gt=0)
    trip_attachment_quota_bytes_override: int | None = Field(default=None, gt=0)
    user_attachment_quota_bytes_override: int | None = Field(default=None, gt=0)
    access_reason: str = Field(min_length=1, max_length=500)


class AdminPagedResponse(BaseModel):
    items: list[AdminUserSummary]
    total: int
    page: int
    limit: int


TripStatus = Literal["draft", "planned", "in_progress", "completed", "archived"]
TripVisibility = Literal["private", "unlisted", "public"]
TripCompanionRole = Literal["co_owner", "editor", "viewer"]
TripShareLinkVisibility = Literal["view_only", "comment", "edit"]
AdminOperationTarget = Literal["trip", "day", "poi"]
AdminOperationAction = Literal["copy", "move", "delete"]
AdminMoveDeletePolicy = Literal["move", "delete", "keep", "orphan"]


class AdminTripSummary(BaseModel):
    trip_id: uuid.UUID
    owner_user_id: uuid.UUID
    owner_email_masked: str
    title: str
    region_hint: str | None
    primary_region_code: str | None
    primary_region_source: Literal["manual", "poi_snapshot", "geocoded"] | None
    start_date: date | None
    end_date: date | None
    visibility: TripVisibility
    status: TripStatus
    version: int
    day_count: int
    poi_count: int
    companion_count: int
    share_link_count: int
    created_at: datetime
    updated_at: datetime


class AdminTripCompanionSummary(BaseModel):
    companion_id: uuid.UUID
    user_id: uuid.UUID | None
    invited_email_masked: str | None
    invited_nickname: str | None
    role: TripCompanionRole
    invited_at: datetime
    joined_at: datetime | None


class AdminTripShareLinkSummary(BaseModel):
    share_id: uuid.UUID
    visibility: TripShareLinkVisibility
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class AdminTripDaySummary(BaseModel):
    day_index: int
    date: date | None
    title: str | None
    note: str | None
    poi_count: int
    created_at: datetime
    updated_at: datetime


class AdminTripPoiSummary(BaseModel):
    attachment_id: uuid.UUID
    day_index: int
    day_date: date | None
    day_title: str | None
    sort_order: str
    feature_id: str | None
    feature_label: str | None
    feature_snapshot: dict[str, Any]
    lon: float | None = None
    lat: float | None = None
    address_label: str | None = None
    added_by_user_id: uuid.UUID
    added_by_email_masked: str | None
    feature_link_broken_at: datetime | None
    custom_marker_color: str | None
    custom_marker_icon: str | None
    planned_arrival_at: datetime | None
    planned_departure_at: datetime | None
    user_note: str | None
    budget_amount: Decimal | None
    actual_amount: Decimal | None
    currency: str
    user_url: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class AdminTripDetail(AdminTripSummary):
    description: str | None
    companions: list[AdminTripCompanionSummary] = Field(default_factory=list)
    days: list[AdminTripDaySummary] = Field(default_factory=list)
    pois: list[AdminTripPoiSummary] = Field(default_factory=list)
    attachments: list[AttachmentLibraryItem] = Field(default_factory=list)
    share_links: list[AdminTripShareLinkSummary] = Field(default_factory=list)
    recent_audit: list[AdminAuditEntry] = Field(default_factory=list)


class AdminTripCreateRequest(BaseModel):
    owner_user_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    region_hint: str | None = Field(default=None, max_length=120)
    primary_region_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=10,
        pattern=r"^[0-9]{2,10}$",
    )
    start_date: date | None = None
    end_date: date | None = None
    visibility: TripVisibility = "private"
    status: TripStatus = "draft"
    access_reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _check_date_range(self) -> AdminTripCreateRequest:
        if self.start_date is None and self.end_date is None:
            return self
        if self.start_date is None or self.end_date is None:
            raise ValueError("start_date와 end_date는 동시에 채워지거나 동시에 비어야 합니다.")
        if self.end_date < self.start_date:
            raise ValueError("end_date는 start_date 이후여야 합니다.")
        return self


class AdminTripPagedResponse(BaseModel):
    items: list[AdminTripSummary]
    total: int
    page: int
    limit: int


class AdminTripStatusRequest(BaseModel):
    status: TripStatus
    access_reason: str = Field(min_length=1, max_length=500)


class AdminOperationPolicyOption(BaseModel):
    value: AdminMoveDeletePolicy
    label: str
    allowed: bool
    reason: str | None = None


class AdminOperationImpact(BaseModel):
    target_type: AdminOperationTarget
    target_id: uuid.UUID | None = None
    trip_id: uuid.UUID
    day_index: int | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    policy_options: dict[str, list[AdminOperationPolicyOption]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AdminOperationResult(BaseModel):
    target_type: AdminOperationTarget
    action: AdminOperationAction
    source_trip_id: uuid.UUID
    target_trip_id: uuid.UUID | None = None
    target_id: uuid.UUID | None = None
    day_index: int | None = None
    affected: dict[str, int] = Field(default_factory=dict)


class AdminTripCopyRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    owner_user_id: uuid.UUID | None = None
    scope: Literal["all", "day", "range"] = "all"
    day_index: int | None = Field(default=None, ge=1)
    start_day_index: int | None = Field(default=None, ge=1)
    end_day_index: int | None = Field(default=None, ge=1)
    date_shift_days: int = Field(default=0, ge=-3650, le=3650)
    target_trip_id: uuid.UUID | None = None
    access_reason: str = Field(min_length=1, max_length=500)


class AdminTripMoveRequest(BaseModel):
    owner_user_id: uuid.UUID
    access_reason: str = Field(min_length=1, max_length=500)


class AdminTripDeleteRequest(BaseModel):
    child_policy: Literal["keep", "delete"] = "keep"
    access_reason: str = Field(min_length=1, max_length=500)


class AdminDayCopyRequest(BaseModel):
    target_trip_id: uuid.UUID
    target_day_index: int = Field(ge=1)
    include_pois: bool = True
    include_attachments: bool = True
    access_reason: str = Field(min_length=1, max_length=500)


class AdminDayMoveRequest(BaseModel):
    target_trip_id: uuid.UUID
    target_day_index: int = Field(ge=1)
    poi_policy: Literal["move", "delete"] = "move"
    attachment_policy: Literal["move", "delete"] = "move"
    comment_policy: Literal["move", "delete"] = "move"
    access_reason: str = Field(min_length=1, max_length=500)


class AdminDayDeleteRequest(BaseModel):
    poi_policy: Literal["delete"] = "delete"
    attachment_policy: Literal["delete"] = "delete"
    comment_policy: Literal["delete"] = "delete"
    access_reason: str = Field(min_length=1, max_length=500)


class AdminPoiCopyRequest(BaseModel):
    target_trip_id: uuid.UUID
    target_day_index: int = Field(ge=1)
    include_attachments: bool = True
    access_reason: str = Field(min_length=1, max_length=500)


class AdminPoiMoveRequest(BaseModel):
    target_trip_id: uuid.UUID
    target_day_index: int = Field(ge=1)
    attachment_policy: Literal["move", "delete"] = "move"
    comment_policy: Literal["move", "delete"] = "move"
    access_reason: str = Field(min_length=1, max_length=500)


class AdminPoiDeleteRequest(BaseModel):
    attachment_policy: Literal["delete"] = "delete"
    comment_policy: Literal["delete"] = "delete"
    access_reason: str = Field(min_length=1, max_length=500)


class AdminPoiSummary(BaseModel):
    attachment_id: uuid.UUID
    trip_id: uuid.UUID
    trip_title: str
    owner_user_id: uuid.UUID
    owner_email_masked: str
    day_index: int
    sort_order: str
    feature_id: str | None
    feature_label: str | None
    feature_link_broken_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class AdminPoiDetail(AdminPoiSummary):
    added_by_user_id: uuid.UUID
    added_by_email_masked: str | None
    feature_snapshot: dict[str, Any]
    custom_marker_color: str | None
    custom_marker_icon: str | None
    planned_arrival_at: datetime | None
    planned_departure_at: datetime | None
    user_note: str | None
    budget_amount: Decimal | None
    actual_amount: Decimal | None
    currency: str
    user_url: str | None
    recent_audit: list[AdminAuditEntry] = Field(default_factory=list)


class AdminPoiCreateRequest(BaseModel):
    trip_id: uuid.UUID
    day_index: int = Field(ge=1)
    sort_order: str = Field(min_length=1, max_length=80)
    feature_id: str | None = Field(default=None, min_length=1, max_length=200)
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    custom_marker_color: str | None = Field(default=None, pattern=r"^P-\d{2}$")
    custom_marker_icon: str | None = Field(default=None, max_length=64)
    planned_arrival_at: datetime | None = None
    planned_departure_at: datetime | None = None
    user_note: str | None = None
    budget_amount: Decimal | None = Field(default=None, ge=0)
    actual_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="KRW", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    user_url: str | None = Field(default=None, max_length=2000)
    access_reason: str = Field(min_length=1, max_length=500)


class AdminPoiPagedResponse(BaseModel):
    items: list[AdminPoiSummary]
    total: int
    page: int
    limit: int


class AdminPoiLinkStatusRequest(BaseModel):
    broken: bool
    access_reason: str = Field(min_length=1, max_length=500)


class AdminBackupSnapshotRequest(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)


class AdminBackupSnapshot(BaseModel):
    snapshot_id: str
    filename: str
    path: str
    size_bytes: int
    checksum_sha256: str | None
    status: Literal["available", "verified"]
    created_at: datetime


class AdminBackupRestoreRequest(BaseModel):
    snapshot_id: str = Field(min_length=1, max_length=200)
    access_reason: str = Field(min_length=1, max_length=500)
    confirm_schema_swap: bool


class AdminBackupRestorePhase(BaseModel):
    name: Literal["preparing", "restoring", "validating", "draining", "switching"]
    status: Literal["pending", "running", "success", "failed", "skipped"]
    message: str | None


class AdminBackupRestoreRun(BaseModel):
    restore_id: str
    snapshot_id: str
    snapshot_path: str
    restore_schema: str
    previous_schema: str
    status: Literal["succeeded", "failed"]
    phases: list[AdminBackupRestorePhase]
    started_at: datetime
    completed_at: datetime
