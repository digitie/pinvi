"""Trip Pydantic schema — `docs/api/trips.md`."""

from __future__ import annotations

import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.poi import PoiRiseSetResponse
from app.schemas.storage import AttachmentResponse

RegionSource = Literal["manual", "poi_snapshot", "geocoded"]


class TripBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    region_hint: str | None = Field(default=None, max_length=120)
    primary_region_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=10,
        pattern=r"^[0-9]{2,10}$",
    )
    start_date: Date | None = None
    end_date: Date | None = None
    visibility: Literal["private", "unlisted", "public"] = "private"


class TripCompanionInvite(BaseModel):
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=80)
    role: Literal["co_owner", "editor", "viewer"] = "editor"


class TripCompanionResponse(BaseModel):
    companion_id: uuid.UUID
    trip_id: uuid.UUID
    user_id: uuid.UUID | None
    invited_email: EmailStr | None
    invited_nickname: str | None
    role: Literal["co_owner", "editor", "viewer"]
    invited_at: datetime
    joined_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TripCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    target_type: Literal["trip", "day", "poi"] = "trip"
    target_id: uuid.UUID | None = None
    day_index: int | None = Field(default=None, ge=1)

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("댓글 본문을 입력하세요.")
        return stripped


class TripCommentResponse(BaseModel):
    comment_id: uuid.UUID
    trip_id: uuid.UUID
    author_user_id: uuid.UUID | None
    body: str
    target_type: Literal["trip", "day", "poi"]
    target_id: uuid.UUID | None
    day_index: int | None
    created_at: datetime
    updated_at: datetime


class TripCreate(TripBase):
    companions: list[TripCompanionInvite] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_date_range(self) -> TripCreate:
        if self.start_date is None and self.end_date is None:
            return self
        if self.start_date is None or self.end_date is None:
            raise ValueError("start_date와 end_date는 동시에 채워지거나 동시에 비어야 합니다.")
        if self.end_date < self.start_date:
            raise ValueError("end_date는 start_date 이후여야 합니다.")
        return self

    @model_validator(mode="after")
    def _check_unique_companion_emails(self) -> TripCreate:
        emails = [str(companion.email).lower() for companion in self.companions]
        if len(emails) != len(set(emails)):
            raise ValueError("동반자 이메일이 중복되었습니다.")
        return self


class TripUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    region_hint: str | None = Field(default=None, max_length=120)
    primary_region_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=10,
        pattern=r"^[0-9]{2,10}$",
    )
    cover_attachment_id: uuid.UUID | None = None
    start_date: Date | None = None
    end_date: Date | None = None
    visibility: Literal["private", "unlisted", "public"] | None = None
    status: Literal["draft", "planned", "in_progress", "completed", "archived"] | None = None


class TripDeleteRequest(BaseModel):
    mode: Literal["soft_delete", "transfer_leader"] = "soft_delete"
    new_owner_user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_transfer_target(self) -> TripDeleteRequest:
        if self.mode == "transfer_leader" and self.new_owner_user_id is None:
            raise ValueError("transfer_leader에는 new_owner_user_id가 필요합니다.")
        return self


class TripDayCreate(BaseModel):
    day_index: int = Field(ge=1)
    date: Date | None = None
    title: str | None = Field(default=None, max_length=200)
    note: str | None = None


class TripDayUpdate(BaseModel):
    date: Date | None = None
    title: str | None = Field(default=None, max_length=200)
    note: str | None = None


class TripDayResponse(BaseModel):
    trip_id: uuid.UUID
    day_index: int
    date: Date | None
    title: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class TripCopyRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    scope: Literal["all", "day", "range"] = "all"
    day_index: int | None = Field(default=None, ge=1)
    start_day_index: int | None = Field(default=None, ge=1)
    end_day_index: int | None = Field(default=None, ge=1)
    date_shift_days: int = 0
    target_trip_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_scope(self) -> TripCopyRequest:
        if self.scope == "day" and self.day_index is None:
            raise ValueError("scope=day에는 day_index가 필요합니다.")
        if self.scope == "range":
            if self.start_day_index is None or self.end_day_index is None:
                raise ValueError("scope=range에는 start_day_index/end_day_index가 필요합니다.")
            if self.end_day_index < self.start_day_index:
                raise ValueError("end_day_index는 start_day_index 이후여야 합니다.")
        return self


class TripResponse(BaseModel):
    trip_id: uuid.UUID
    owner_user_id: uuid.UUID
    title: str
    description: str | None
    region_hint: str | None
    primary_region_code: str | None
    primary_region_source: RegionSource | None
    start_date: Date | None
    end_date: Date | None
    visibility: Literal["private", "unlisted", "public"]
    status: Literal["draft", "planned", "in_progress", "completed", "archived"]
    version: int
    created_at: datetime
    updated_at: datetime


class TripCopyResponse(BaseModel):
    trip: TripResponse
    created_trip: bool
    copied_day_count: int
    copied_poi_count: int
    copied_attachment_count: int


class TripViewPoi(BaseModel):
    poi_id: uuid.UUID
    feature_id: str | None
    sort_order: str
    title: str | None
    feature: dict[str, Any]
    marker_color: str | None
    marker_icon: str | None
    is_broken: bool
    user_note: str | None
    planned_arrival_at: datetime | None
    planned_departure_at: datetime | None
    budget_amount: Decimal | None
    actual_amount: Decimal | None
    currency: str
    user_url: str | None
    rise_set: PoiRiseSetResponse | None
    feature_link_broken_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class TripViewDay(BaseModel):
    day_index: int
    date: Date | None
    title: str | None
    pois: list[TripViewPoi]


class TripViewShareLink(BaseModel):
    share_id: uuid.UUID
    visibility: Literal["view_only", "comment", "edit"]
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class TripView(BaseModel):
    trip: TripResponse
    days: list[TripViewDay]
    companions: list[TripCompanionResponse]
    share_links: list[TripViewShareLink]
    broken_feature_count: int


class TripSharedView(BaseModel):
    visibility: Literal["view_only", "comment", "edit"]
    trip: TripResponse
    days: list[TripViewDay]
    broken_feature_count: int


class TripDayOptimizeRequest(BaseModel):
    strategy: Literal["nearest_neighbor"] = "nearest_neighbor"
    start_poi_id: uuid.UUID | None = None
    persist: bool = False


class TripDayOptimizeMove(BaseModel):
    poi_id: uuid.UUID
    old_sort_order: str
    new_sort_order: str


class TripDayOptimizeResponse(BaseModel):
    trip_id: uuid.UUID
    day_index: int
    ordered_poi_ids: list[uuid.UUID]
    moves: list[TripDayOptimizeMove]
    distance_meters: int | None
    warnings: list[str] = Field(default_factory=list)


class TripDistanceMatrixResponse(BaseModel):
    trip_id: uuid.UUID
    day_index: int
    poi_ids: list[uuid.UUID]
    distances_meters: list[list[int | None]]
    warnings: list[str] = Field(default_factory=list)


class TripAttachmentResponse(AttachmentResponse):
    pass
