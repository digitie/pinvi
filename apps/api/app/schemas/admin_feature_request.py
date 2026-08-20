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
    """승인 입력.

    new_place는 범용 Map 요청 큐에 suggestion UUID 그대로 제출한다. ``category``가 있으면 기존
    suggestion category 목록에 중복 없이 보강한다. ``marker_*``는 correction override 호환 입력이며
    Map 큐의 최종 승인자가 정한다. ``access_reason``은 PinVi audit 사유, ``kor_travel_map_reason``은
    correction/closure change request 사유(미지정 시 access_reason)다.
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
