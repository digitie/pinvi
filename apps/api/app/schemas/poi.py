"""POI Pydantic schema — `docs/api/pois.md`."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class PoiCreate(BaseModel):
    day_index: int = Field(ge=1)
    sort_order: str = Field(min_length=1, max_length=80)
    feature_id: str = Field(min_length=1, max_length=200)
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    custom_marker_color: str | None = Field(default=None, pattern=r"^P-\d{2}$")
    custom_marker_icon: str | None = Field(default=None, max_length=64)
    planned_arrival_at: datetime | None = None
    planned_departure_at: datetime | None = None
    user_note: str | None = None
    budget_amount: Decimal | None = Field(default=None, ge=0)
    actual_amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="KRW", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    user_url: str | None = Field(default=None, max_length=2000)


class PoiUpdate(BaseModel):
    sort_order: str | None = Field(default=None, min_length=1, max_length=80)
    feature_snapshot: dict[str, Any] | None = None
    custom_marker_color: str | None = Field(default=None, pattern=r"^P-\d{2}$")
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
    moves: list[PoiReorderMove] = Field(min_length=1, max_length=200)


class PoiResponse(BaseModel):
    attachment_id: uuid.UUID
    trip_id: uuid.UUID
    day_index: int
    sort_order: str
    feature_id: str
    feature_link_broken_at: datetime | None
    feature_snapshot: dict[str, Any]
    custom_marker_color: str | None
    custom_marker_icon: str | None
    planned_arrival_at: datetime | None
    planned_departure_at: datetime | None
    user_note: str | None
    budget_amount: Decimal | None
    actual_amount: Decimal | None
    currency: str
    user_url: str | None
    version: int
    created_at: datetime
    updated_at: datetime
