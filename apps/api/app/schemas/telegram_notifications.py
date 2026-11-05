"""일정 알림 API. 큐 payload·chat credential은 응답하지 않는다."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TelegramSendRequest(BaseModel):
    request_id: uuid.UUID
    scope: Literal["trip", "day"] = "trip"
    day_index: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def check_scope(self) -> TelegramSendRequest:
        if (self.scope == "day") != (self.day_index is not None):
            raise ValueError("day 범위에만 day_index가 필요합니다.")
        return self


class TelegramPreferencesBody(BaseModel):
    weather_enabled: bool = False
    daily_enabled: bool = False
    weekly_enabled: bool = False
    send_time: str = Field(default="08:00", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    weekly_day: int = Field(default=0, ge=0, le=6)
    weekly_target_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_weekly_target(self) -> TelegramPreferencesBody:
        if self.weekly_enabled and self.weekly_target_id is None:
            raise ValueError("주간 알림 대상을 선택하세요.")
        return self


class TelegramDeliveryResponse(BaseModel):
    id: uuid.UUID
    target_id: uuid.UUID | None
    status: str
    sent_chunks: int
    total_chunks: int
    attempts: int
    retry_at: datetime | None
    error_code: str | None
    error_message: str | None


class TelegramNotificationResponse(BaseModel):
    id: uuid.UUID
    category: str
    trip_ids: list[uuid.UUID]
    created_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    deliveries: list[TelegramDeliveryResponse]
