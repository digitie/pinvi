from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

AttachmentRole = Literal["attachment", "image", "document", "reference"]


class PlanPoiAttachmentCreateRequest(BaseModel):
    bucket: str = Field(min_length=3, max_length=80)
    storage_key: str = Field(min_length=1, max_length=1024)
    original_filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=255)
    byte_size: int = Field(gt=0)
    public_url: str | None = Field(default=None, max_length=2000)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    role: AttachmentRole = "attachment"
    description: str | None = Field(default=None, max_length=1000)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("storage_key")
    @classmethod
    def validate_storage_key(cls, value: str) -> str:
        normalized = value.strip().lstrip("/")
        if not normalized or ".." in normalized.split("/"):
            raise ValueError("storage_key must be a safe RustFS object key")
        return normalized

    @field_validator("checksum_sha256")
    @classmethod
    def normalize_checksum(cls, value: str | None) -> str | None:
        return value.lower() if value else value


class PlanPoiAttachmentResponse(BaseModel):
    id: UUID
    trip_id: UUID | None
    trip_poi_id: UUID | None
    notice_plan_id: UUID | None
    notice_poi_id: UUID | None
    source_attachment_id: UUID | None
    bucket: str
    storage_key: str
    original_filename: str
    content_type: str
    byte_size: int
    public_url: str | None
    checksum_sha256: str | None
    role: str
    description: str | None
    sort_order: int
    uploaded_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class PlanPoiAttachmentListResponse(BaseModel):
    items: list[PlanPoiAttachmentResponse]
    total: int
