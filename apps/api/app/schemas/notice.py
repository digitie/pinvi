from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.json_types import JsonValue


class NoticePoiBase(BaseModel):
    day_index: int = Field(default=1, ge=1)
    sort_order: str = Field(min_length=1, max_length=80)
    feature_id: str | None = Field(default=None, max_length=120)
    map_feature_id: UUID | None = None
    snapshot: dict[str, JsonValue] = Field(default_factory=dict)
    memo: str | None = Field(default=None, max_length=2000)
    budget: Decimal | None = None
    currency: str = Field(default="KRW", min_length=3, max_length=3)
    user_url: str | None = Field(default=None, max_length=2000)
    custom_marker_color: str | None = Field(default=None, max_length=16)
    custom_marker_icon: str | None = Field(default=None, max_length=120)


class AdminNoticePoiCreate(NoticePoiBase):
    pass


class AdminNoticePoiUpdate(BaseModel):
    day_index: int | None = Field(default=None, ge=1)
    sort_order: str | None = Field(default=None, min_length=1, max_length=80)
    feature_id: str | None = Field(default=None, max_length=120)
    map_feature_id: UUID | None = None
    snapshot: dict[str, JsonValue] | None = None
    memo: str | None = Field(default=None, max_length=2000)
    budget: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    user_url: str | None = Field(default=None, max_length=2000)
    custom_marker_color: str | None = Field(default=None, max_length=16)
    custom_marker_icon: str | None = Field(default=None, max_length=120)


class NoticePlanDates(BaseModel):
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if (self.starts_on is None) != (self.ends_on is None):
            raise ValueError("starts_on and ends_on must both be set or both be omitted")
        if (
            self.starts_on is not None
            and self.ends_on is not None
            and self.ends_on < self.starts_on
        ):
            raise ValueError("ends_on must be greater than or equal to starts_on")
        return self


class AdminNoticePlanCreate(NoticePlanDates):
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(default="recommended", min_length=1, max_length=80)
    summary: str | None = Field(default=None, max_length=2000)
    source_name: str | None = Field(default=None, max_length=200)
    destination: str | None = Field(default=None, max_length=120)
    is_published: bool = False
    pois: list[AdminNoticePoiCreate] = Field(default_factory=list)


class AdminNoticePlanUpdate(BaseModel):
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    summary: str | None = Field(default=None, max_length=2000)
    source_name: str | None = Field(default=None, max_length=200)
    destination: str | None = Field(default=None, max_length=120)
    starts_on: date | None = None
    ends_on: date | None = None
    is_published: bool | None = None


class NoticePoiResponse(NoticePoiBase):
    id: UUID
    notice_plan_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class NoticePlanResponse(NoticePlanDates):
    id: UUID
    slug: str
    title: str
    category: str
    summary: str | None
    source_name: str | None
    destination: str | None
    is_published: bool
    version: int
    created_at: datetime
    updated_at: datetime
    pois: list[NoticePoiResponse] = Field(default_factory=list)


class NoticePlanListResponse(BaseModel):
    items: list[NoticePlanResponse]
    total: int
    page: int
    limit: int


class NoticePlanCopyRequest(BaseModel):
    target_trip_id: UUID | None = None
    target_trip_title: str | None = Field(default=None, min_length=1, max_length=120)
    target_trip_destination: str | None = Field(default=None, min_length=1, max_length=120)
    poi_ids: list[UUID] | None = Field(default=None, min_length=1)


class NoticePlanCopyResponse(BaseModel):
    target_trip_id: UUID
    created_trip: bool
    copied_poi_ids: list[UUID]
