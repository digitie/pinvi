"""Storage / presigned PUT schema — `docs/api/storage.md`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

AttachmentPurpose = Literal[
    "media_asset",
    "avatar",
    "trip_attachment",
    "poi_attachment",
    "curated_plan_attachment",
    "curated_poi_attachment",
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
    bucket: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")
    storage_key: str = Field(min_length=1, max_length=1024)
    original_filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0)
    public_url: str | None = Field(default=None, max_length=2048)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    role: Literal["attachment", "image", "document", "reference"] = "attachment"
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_storage_refs(self) -> Self:
        # 클라이언트가 임의 storage_key/public_url을 주입하지 못하도록 입력 위생 검증.
        # 경로 traversal·절대경로·역슬래시 금지(presigned 업로드가 발급한 key만 정상).
        if (
            self.storage_key.startswith("/")
            or "\\" in self.storage_key
            or ".." in self.storage_key.split("/")
        ):
            raise ValueError("storage_key 형식이 올바르지 않습니다.")
        if self.public_url is not None and not self.public_url.startswith(("http://", "https://")):
            raise ValueError("public_url은 http(s) URL이어야 합니다.")
        return self


class AttachmentResponse(BaseModel):
    attachment_id: uuid.UUID
    trip_id: uuid.UUID | None
    trip_poi_id: uuid.UUID | None
    curated_plan_id: uuid.UUID | None = None
    curated_poi_id: uuid.UUID | None = None
    notice_plan_id: uuid.UUID | None = None
    notice_poi_id: uuid.UUID | None = None
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

    @model_validator(mode="after")
    def sync_notice_aliases(self) -> Self:
        self.curated_plan_id, self.notice_plan_id = _sync_alias_pair(
            "curated_plan_id",
            self.curated_plan_id,
            "notice_plan_id",
            self.notice_plan_id,
        )
        self.curated_poi_id, self.notice_poi_id = _sync_alias_pair(
            "curated_poi_id",
            self.curated_poi_id,
            "notice_poi_id",
            self.notice_poi_id,
        )
        return self


def _sync_alias_pair(
    canonical_name: str,
    canonical_value: uuid.UUID | None,
    alias_name: str,
    alias_value: uuid.UUID | None,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    if canonical_value is not None and alias_value is not None and canonical_value != alias_value:
        raise ValueError(f"{alias_name} must match {canonical_name}")
    value = canonical_value or alias_value
    return value, value
