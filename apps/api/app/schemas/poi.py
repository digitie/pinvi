"""POI Pydantic schema — `docs/api/pois.md`."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.feature import ExternalRef

PoiRiseSetStatus = Literal["pending_date", "pending_coord", "pending_fetch", "success", "failed"]

# POI 출처 — feature 연결 / 수동 입력 / 외부 provider pick(ADR-054).
PoiSource = Literal["feature", "manual", "kakao", "naver"]


class PoiCreate(BaseModel):
    day_index: int = Field(ge=1)
    sort_order: str = Field(min_length=1, max_length=80)
    feature_id: str | None = Field(default=None, min_length=1, max_length=200)
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    # ADR-054: 외부 pick(kakao/naver)이면 source + external_ref를 실어 보낸다. 서버가 POI 생성 후
    # best-effort로 feature-request를 auto-fire하고, 승인되면 reconciliation이 feature_id를 채운다.
    source: PoiSource | None = None
    external_ref: ExternalRef | None = None
    custom_marker_color: str | None = Field(default=None, pattern=r"^P-(0[1-9]|1[0-6])$")
    custom_marker_icon: str | None = Field(default=None, max_length=64)
    planned_arrival_at: datetime | None = None
    planned_departure_at: datetime | None = None
    user_note: str | None = None
    budget_amount: Decimal | None = Field(default=None, ge=0)
    actual_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="KRW", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    user_url: str | None = Field(default=None, max_length=2000)


class PoiUpdate(BaseModel):
    day_index: int | None = Field(default=None, ge=1)
    sort_order: str | None = Field(default=None, min_length=1, max_length=80)
    feature_snapshot: dict[str, Any] | None = None
    custom_marker_color: str | None = Field(default=None, pattern=r"^P-(0[1-9]|1[0-6])$")
    custom_marker_icon: str | None = Field(default=None, max_length=64)
    planned_arrival_at: datetime | None = None
    planned_departure_at: datetime | None = None
    user_note: str | None = None
    budget_amount: Decimal | None = Field(default=None, ge=0)
    actual_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    user_url: str | None = Field(default=None, max_length=2000)


class PoiReorderMove(BaseModel):
    poi_id: uuid.UUID
    new_sort_order: str = Field(min_length=1, max_length=80)


class PoiReorderRequest(BaseModel):
    day_index: int = Field(ge=1)
    moves: list[PoiReorderMove] = Field(min_length=1, max_length=200)


class PoiMoveRequest(BaseModel):
    """장소 하나를 `day_index` 일자의 `before_poi_id` 바로 앞(null이면 맨 끝)으로 옮긴다."""

    model_config = ConfigDict(extra="forbid")

    day_index: int = Field(ge=1)
    before_poi_id: uuid.UUID | None = None


class PoiRiseSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: PoiRiseSetStatus
    locdate: date | None
    sunrise_at: datetime | None
    sunset_at: datetime | None
    moonrise_at: datetime | None
    moonset_at: datetime | None
    fetched_at: datetime | None
    updated_at: datetime


class PoiResponse(BaseModel):
    attachment_id: uuid.UUID
    trip_id: uuid.UUID
    day_index: int
    sort_order: str
    feature_id: str | None
    feature_link_broken_at: datetime | None
    feature_snapshot: dict[str, Any]
    custom_marker_color: str | None
    custom_marker_icon: str | None
    source: str | None = None
    external_ref: ExternalRef | None = None
    planned_arrival_at: datetime | None
    planned_departure_at: datetime | None
    user_note: str | None
    budget_amount: Decimal | None
    actual_amount: Decimal | None
    currency: str
    user_url: str | None
    rise_set: PoiRiseSetResponse | None
    version: int
    created_at: datetime
    updated_at: datetime


class PoiMoveResponse(BaseModel):
    """`POST /trips/{trip_id}/pois/{poi_id}/move` 응답.

    `changed`는 정렬 위치·일자가 바뀐 장소 전부(옮긴 장소 포함, 도착 일자 순서)다. 순서가 그대로인
    이동이면 빈 목록이고 `poi.version`도 그대로다.
    """

    poi: PoiResponse
    from_day_index: int
    changed: list[PoiResponse]


class PoiPlaceDetails(BaseModel):
    """장소 영업 정보 — `GET|POST /trips/{trip_id}/pois/{poi_id}/place-details[/refresh]`.

    `status`: ready = 값이 하나 이상 있음, empty = 출처를 조회했지만 줄 값이 없음,
    unavailable = 출처 장애로 아직 받지 못함(저장하지 않았고 다음 열람 때 다시 시도).
    `sources`는 필드 이름 → 출처 이름(현재 `kor_travel_map`뿐)이다.
    """

    poi_id: uuid.UUID
    status: Literal["ready", "empty", "unavailable"]
    opening_hours: list[str] = Field(default_factory=list)
    closed_days: str | None = None
    phone: str | None = None
    website: str | None = None
    sources: dict[str, str] = Field(default_factory=dict)
    fetched_at: datetime | None = None
    # 이 시각 이후에 "다시 읽어오기"가 허용된다(같은 장소 60초에 1회).
    refresh_available_at: datetime | None = None
