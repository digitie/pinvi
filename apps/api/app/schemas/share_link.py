"""Trip 공유 토큰 schema — `docs/api/trips.md` §7."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ShareLinkCreate(BaseModel):
    visibility: Literal["view_only", "comment", "edit"] = "view_only"
    expires_at: datetime | None = None


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
