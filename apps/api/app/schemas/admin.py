"""Admin schema — `docs/api/admin.md`."""

from __future__ import annotations

import uuid
from datetime import datetime
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


class AdminUserDetail(AdminUserSummary):
    email: str
    email_status: Literal["active", "bounced", "complained"]
    is_active: bool


class AdminActionRequest(BaseModel):
    """force-verify / disable 등 위험 액션 — 사유 필수."""

    access_reason: str = Field(min_length=1, max_length=500)


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


class AdminPagedResponse(BaseModel):
    items: list[AdminUserSummary]
    total: int
    page: int
    limit: int


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
