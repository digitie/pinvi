"""Storage / presigned PUT schema — `docs/api/storage.md`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AttachmentPurpose = Literal[
    "media_asset",
    "avatar",
    "trip_attachment",
    "poi_attachment",
    "notice_plan_attachment",
    "notice_poi_attachment",
]


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    content_length: int = Field(gt=0)
    purpose: AttachmentPurpose


class UploadUrlResponse(BaseModel):
    method: Literal["PUT"] = "PUT"
    bucket: str
    storage_key: str
    upload_url: str
    headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime
    max_upload_bytes: int
    public_url: str | None = None


class AttachmentCreate(BaseModel):
    bucket: str = Field(min_length=1, max_length=80)
    storage_key: str = Field(min_length=1, max_length=1024)
    original_filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0)
    public_url: str | None = None
    checksum_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    role: Literal["attachment", "image", "document", "reference"] = "attachment"
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)


class AttachmentResponse(BaseModel):
    attachment_id: uuid.UUID
    trip_id: uuid.UUID | None
    trip_poi_id: uuid.UUID | None
    notice_plan_id: uuid.UUID | None
    notice_poi_id: uuid.UUID | None
    source_attachment_id: uuid.UUID | None
    bucket: str
    storage_key: str
    original_filename: str
    content_type: str
    byte_size: int
    public_url: str | None
    role: Literal["attachment", "image", "document", "reference"]
    description: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
