"""Admin schema — `docs/api/admin.md`."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.storage import AvatarApplyRequest


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


class AdminStatsOverview(BaseModel):
    users_total: int
    users_24h: int
    users_pending_verification: int
    trips_total: int
    trips_active: int
    pois_total: int
    email_queue_pending: int
    api_calls_24h: int
    api_calls_failed_24h: int
    features_by_kind: dict[str, int] = Field(default_factory=dict)
    etl_last_24h: dict[str, int] = Field(default_factory=lambda: {"success": 0, "failed": 0})


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


class AdminPagedResponse(BaseModel):
    items: list[AdminUserSummary]
    total: int
    page: int
    limit: int


TripStatus = Literal["draft", "planned", "in_progress", "completed", "archived"]
TripVisibility = Literal["private", "unlisted", "public"]
TripCompanionRole = Literal["co_owner", "editor", "viewer"]
TripShareLinkVisibility = Literal["view_only", "comment", "edit"]


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
