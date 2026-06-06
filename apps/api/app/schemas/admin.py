"""Admin schema — `docs/api/admin.md`."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

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
