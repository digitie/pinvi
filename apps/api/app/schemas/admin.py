"""Admin schema — `docs/api/admin.md`."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class AdminUserDetail(AdminUserSummary):
    email: str
    email_revealed: bool
    email_status: Literal["active", "bounced", "complained"]
    is_active: bool
    recent_audit: list[AdminAuditEntry] = Field(default_factory=list)


class AdminActionRequest(BaseModel):
    """force-verify / disable 등 위험 액션 — 사유 필수."""

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


class AdminTripDetail(AdminTripSummary):
    description: str | None
    companions: list[AdminTripCompanionSummary] = Field(default_factory=list)
    share_links: list[AdminTripShareLinkSummary] = Field(default_factory=list)
    recent_audit: list[AdminAuditEntry] = Field(default_factory=list)


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
    feature_id: str
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
