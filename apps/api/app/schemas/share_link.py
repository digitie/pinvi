"""Trip 공유 토큰 schema — `docs/api/trips.md` §7."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, field_validator


class ShareLinkCreate(BaseModel):
    visibility: Literal["view_only", "comment", "edit"] = "view_only"
    expires_at: AwareDatetime | None = None

    @field_validator("expires_at")
    @classmethod
    def _future_expiry(cls, value: datetime | None) -> datetime | None:
        if value is not None and value <= datetime.now(UTC):
            raise ValueError("만료 시각은 현재 이후여야 합니다.")
        return value


class ShareLinkResponse(BaseModel):
    share_id: uuid.UUID
    trip_id: uuid.UUID
    visibility: Literal["view_only", "comment", "edit"]
    token: str
    url: str
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
