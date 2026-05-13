from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

StorageUploadPurpose = Literal["media_asset", "avatar", "trip_attachment"]


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
