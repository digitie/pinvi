"""Trip Pydantic schema — `docs/api/trips.md`."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

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
    start_date: date | None = None
    end_date: date | None = None
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
    start_date: date | None = None
    end_date: date | None = None
    visibility: Literal["private", "unlisted", "public"] | None = None
    status: Literal["draft", "planned", "in_progress", "completed", "archived"] | None = None


class TripResponse(BaseModel):
    trip_id: uuid.UUID
    owner_user_id: uuid.UUID
    title: str
    description: str | None
    region_hint: str | None
    primary_region_code: str | None
    primary_region_source: RegionSource | None
    start_date: date | None
    end_date: date | None
    visibility: Literal["private", "unlisted", "public"]
    status: Literal["draft", "planned", "in_progress", "completed", "archived"]
    version: int
    created_at: datetime
    updated_at: datetime
