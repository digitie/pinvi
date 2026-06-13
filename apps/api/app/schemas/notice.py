"""Notice plan schema — `docs/api/notice-plans.md`."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class NoticePlanBase(BaseModel):
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(default="recommended", min_length=1, max_length=80)
    summary: str | None = None
    source_name: str | None = Field(default=None, max_length=200)
    destination: str | None = Field(default=None, max_length=120)
    starts_on: date | None = None
    ends_on: date | None = None
    is_published: bool = False

    @model_validator(mode="after")
    def _check_period(self) -> NoticePlanBase:
        if self.starts_on is None and self.ends_on is None:
            return self
        if self.starts_on is None or self.ends_on is None:
            raise ValueError("starts_on / ends_on 동시에 채우거나 비워야 합니다.")
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on은 starts_on 이후여야 합니다.")
        return self


class NoticePlanCreate(NoticePlanBase):
    pass


class NoticePlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = None
    summary: str | None = None
    source_name: str | None = None
    destination: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    is_published: bool | None = None


class NoticePoiBase(BaseModel):
    day_index: int = Field(default=1, ge=1)
    sort_order: str = Field(min_length=1, max_length=80)
    feature_id: str | None = Field(default=None, min_length=1, max_length=200)
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    memo: str | None = None
    budget_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="KRW", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    user_url: str | None = Field(default=None, max_length=2000)
    custom_marker_color: str | None = Field(default=None, pattern=r"^P-\d{2}$")
    custom_marker_icon: str | None = Field(default=None, max_length=64)


class NoticePoiCreate(NoticePoiBase):
    pass


class NoticePoiResponse(NoticePoiBase):
    notice_poi_id: uuid.UUID
    notice_plan_id: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime


class NoticePlanResponse(NoticePlanBase):
    notice_plan_id: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime
    pois: list[NoticePoiResponse] = Field(default_factory=list)


class NoticePlanCopyRequest(BaseModel):
    target_trip_id: uuid.UUID | None = None
    trip_title: str | None = Field(default=None, max_length=200)
    trip_start_date: date | None = None
    trip_end_date: date | None = None
    poi_ids: list[uuid.UUID] = Field(default_factory=list)


class NoticePlanCopyResponse(BaseModel):
    trip_id: uuid.UUID
    created_trip: bool
    copied_poi_ids: list[uuid.UUID]
    copied_attachment_count: int


class KorTravelMapCuratedFeatureImportRequest(BaseModel):
    curated_feature_id: str = Field(min_length=1, max_length=240)
    mode: Literal["create", "upsert", "refresh"] = "create"
    is_published: bool | None = None


class KorTravelMapCuratedFeatureImportResponse(BaseModel):
    notice_plan_id: uuid.UUID
    created_plan: bool
    source_system: str
    source_curated_feature_id: str
    source_version: int | None = None
    source_etag: str | None = None
    copied_poi_count: int
    reused_feature_backed_poi_count: int
