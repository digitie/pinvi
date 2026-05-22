from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

StorageUploadPurpose = Literal[
    "media_asset",
    "avatar",
    "trip_attachment",
    "plan_attachment",
    "poi_attachment",
    "notice_plan_attachment",
    "notice_poi_attachment",
]


class StorageUploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=255)
    content_length: int = Field(gt=0)
    purpose: StorageUploadPurpose = "media_asset"


class StorageUploadUrlResponse(BaseModel):
    method: Literal["PUT"]
    bucket: str
    storage_key: str
    upload_url: str
    headers: dict[str, str]
    expires_at: datetime
    max_upload_bytes: int
    public_url: str | None


class StorageObjectResponse(BaseModel):
    key: str
    size: int | None
    last_modified: datetime | None
    etag: str | None
    storage_class: str | None
    public_url: str | None


class StorageObjectListResponse(BaseModel):
    bucket: str
    prefix: str
    objects: list[StorageObjectResponse]
    is_truncated: bool
    next_continuation_token: str | None
