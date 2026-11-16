"""일정 화면 날씨 새로고침 요청·응답(요청 15, `services/weather_refresh.py`)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class TripWeatherRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: 한 장소만. 비우면 그 일자의 날씨 대상 장소 전부.
    poi_id: uuid.UUID | None = None


class TripWeatherRefreshResponse(BaseModel):
    trip_id: uuid.UUID
    day_index: int
    #: 위치를 새로 해석한 feature 수(직접 경로는 다음 조회의 재해석을 예약한 수).
    refreshed: int
    #: 60초 안에 이미 해석돼 이번엔 건너뛴 수 — `retry_after_seconds` 뒤 다시 시도할 수 있다.
    cooldown: int
    #: 반경(최대 100 km) 안에 날씨 위치가 없는 수.
    no_data: int
    #: 날씨 서비스 오류로 해석하지 못한 수.
    failed: int
    #: 좌표나 Map 장소 연결이 없어 날씨 대상이 아닌 장소 수.
    skipped: int
    retry_after_seconds: int | None = None
