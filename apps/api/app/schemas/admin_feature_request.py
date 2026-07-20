"""Admin feature-request 검토 큐 schema — `docs/api/admin.md` (T-179).

사용자 feature 제안(`app.feature_suggestions`)을 Admin이 검토·승인/거절하는 화면용.
승인 시 kor_travel_map `/v1/admin/features*` change API로 전송(전송 client = T-180).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.feature import (
    Coord,
    ExternalRef,
    FeatureKind,
    FeatureRequestStatus,
    FeatureRequestType,
)


class AdminFeatureRequestSummary(BaseModel):
    """검토 큐 1건 (사용자 이메일은 마스킹)."""

    request_id: uuid.UUID
    requester_user_id: uuid.UUID
    requester_email_masked: str | None = None
    type: FeatureRequestType
    kind: FeatureKind
    name: str
    coord: Coord
    categories: list[str] = Field(default_factory=list)
    note: str | None = None
    target_feature_id: str | None = None
    source: str = "user"
    external_ref: ExternalRef | None = None
    status: FeatureRequestStatus
    kor_travel_map_ref: dict[str, Any] | None = None
    reviewed_by_admin_id: uuid.UUID | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class AdminFeatureRequestPagedResponse(BaseModel):
    items: list[AdminFeatureRequestSummary] = Field(default_factory=list)
    total: int
    page: int
    limit: int


class AdminFeatureRequestApprove(BaseModel):
    """승인 — kor_travel_map change API 호출 입력.

    kor_travel_map `create`(new_place)는 `category`(8자리 코드)/`marker_color`/`marker_icon`이
    필수다(사용자 제안엔 없음 → Admin이 검토하며 채운다). correction은 override로 일부만,
    closure는 불필요. `access_reason`은 Pinvi audit 사유, `kor_travel_map_reason`은 kor_travel_map로
    보낼 사유(미지정 시 access_reason).
    """

    access_reason: str = Field(min_length=1, max_length=500)
    category: str | None = Field(default=None, max_length=32)
    marker_color: str | None = Field(default=None, pattern=r"^P-\d{2}$")
    marker_icon: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kor_travel_map_reason: str | None = Field(default=None, max_length=500)


class AdminFeatureRequestReject(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)


class AdminFeatureRequestResult(BaseModel):
    """승인/거절 후 갱신된 상태."""

    request_id: uuid.UUID
    status: FeatureRequestStatus
    kor_travel_map_ref: dict[str, Any] | None = None
    reviewed_by_admin_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
