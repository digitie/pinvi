"""Data subject request schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DsrRequestType = Literal["access", "correction", "delete", "suspend"]
DsrRequestStatus = Literal[
    "received",
    "identity_check",
    "processing",
    "completed",
    "rejected",
    "withdrawn",
]


class DsrRequestRecord(BaseModel):
    request_id: uuid.UUID
    user_id: uuid.UUID | None = None
    request_type: DsrRequestType
    status: DsrRequestStatus
    request_summary: str
    request_details: dict[str, Any] = Field(default_factory=dict)
    identity_proof_metadata: dict[str, Any] = Field(default_factory=dict)
    requester_email_masked: str
    assigned_cpo_user_id: uuid.UUID | None = None
    received_at: datetime
    due_at: datetime
    identity_verified_at: datetime | None = None
    processing_started_at: datetime | None = None
    completed_at: datetime | None = None
    rejected_at: datetime | None = None
    withdrawn_at: datetime | None = None
    rejection_reason: str | None = None
    result_summary: str | None = None
    result_notice_hash: str | None = None
    result_notice_email_id: uuid.UUID | None = None
    export_manifest: dict[str, Any] = Field(default_factory=dict)
    partial_response: bool = False
    evidence_attachment_id: uuid.UUID | None = None
    response_overdue: bool = False
    next_action: str
    created_at: datetime
    updated_at: datetime


class DsrRequestListResponse(BaseModel):
    items: list[DsrRequestRecord] = Field(default_factory=list)
    page_size: int
    total: int


class DsrRequestCreateRequest(BaseModel):
    request_type: DsrRequestType
    request_summary: str = Field(min_length=1, max_length=500)
    request_details: dict[str, Any] = Field(default_factory=dict)


class DsrRequestWithdrawRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class DsrIdentityCheckRequest(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)
    identity_verified: bool = True
    identity_note: str | None = Field(default=None, max_length=1000)
    evidence_attachment_id: uuid.UUID | None = None


class DsrProcessRequest(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)
    processing_note: str | None = Field(default=None, max_length=1000)
    evidence_attachment_id: uuid.UUID | None = None


class DsrCompleteRequest(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)
    result_summary: str = Field(min_length=1, max_length=4000)
    export_manifest: dict[str, Any] = Field(default_factory=dict)
    partial_response: bool = False
    evidence_attachment_id: uuid.UUID | None = None


class DsrRejectRequest(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)
    rejection_reason: str = Field(min_length=1, max_length=4000)
    evidence_attachment_id: uuid.UUID | None = None
