from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.json_types import JsonValue

TripResourceType = Literal[
    "place",
    "event",
    "route",
    "area",
    "notice",
    "festival",
    "trail",
    "scenic_road",
    "custom",
]


class TripPlanItemCreateRequest(BaseModel):
    resource_type: TripResourceType
    sort_order: int | None = Field(default=None, ge=1)
    map_feature_id: UUID | None = None
    festival_id: UUID | None = None
    resource_key: str | None = Field(default=None, max_length=180)
    title_snapshot: str | None = Field(default=None, max_length=255)
    address_snapshot: str | None = Field(default=None, max_length=700)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    operating_hours_snapshot: str | None = Field(default=None, max_length=255)
    longitude: Decimal | None = None
    latitude: Decimal | None = None
    note: str | None = Field(default=None, max_length=1000)
    resource_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class TripPlanItemResponse(BaseModel):
    id: UUID
    trip_day_id: UUID
    resource_type: str
    sort_order: int
    map_feature_id: UUID | None
    festival_id: UUID | None
    resource_key: str | None
    title_snapshot: str
    address_snapshot: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    operating_hours_snapshot: str | None
    longitude: Decimal | None
    latitude: Decimal | None
    note: str | None
    resource_metadata: dict[str, JsonValue]
