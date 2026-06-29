"""Content moderation / takedown workflow schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ContentReportTargetType = Literal["trip", "comment", "attachment", "share_link"]
ContentReportReasonCode = Literal["spam", "harassment", "privacy", "illegal", "safety", "other"]
ContentReportStatus = Literal[
    "received",
    "reviewing",
    "hidden",
    "taken_down",
    "rejected",
    "appealed",
    "restored",
]
ContentModerationActionType = Literal["review", "hide", "takedown", "restore", "reject", "appeal"]


class ContentModerationActionRecord(BaseModel):
    action_id: uuid.UUID
    report_id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    action: ContentModerationActionType
    action_reason: str
    before_state: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ContentReportRecord(BaseModel):
    report_id: uuid.UUID
    target_type: ContentReportTargetType
    target_id: uuid.UUID
    target_trip_id: uuid.UUID | None = None
    target_owner_user_id: uuid.UUID | None = None
    reporter_user_id: uuid.UUID | None = None
    reason_code: ContentReportReasonCode
    reason_text: str
    status: ContentReportStatus
    target_snapshot: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    reviewer_user_id: uuid.UUID | None = None
    resolution_summary: str | None = None
    appeal_summary: str | None = None
    reviewed_at: datetime | None = None
    actioned_at: datetime | None = None
    appealed_at: datetime | None = None
    restored_at: datetime | None = None
    next_actions: list[ContentModerationActionType] = Field(default_factory=list)
    actions: list[ContentModerationActionRecord] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ContentReportListResponse(BaseModel):
    items: list[ContentReportRecord] = Field(default_factory=list)
    page_size: int
    total: int


class ContentReportCreateRequest(BaseModel):
    target_type: ContentReportTargetType
    target_id: uuid.UUID
    reason_code: ContentReportReasonCode
    reason_text: str = Field(min_length=1, max_length=2000)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ContentReportAppealRequest(BaseModel):
    appeal_reason: str = Field(min_length=1, max_length=2000)


class ContentModerationActionRequest(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)
    resolution_summary: str = Field(min_length=1, max_length=2000)
