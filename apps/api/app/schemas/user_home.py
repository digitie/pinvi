"""`GET /users/me/home` — 로그인 사용자의 개인 홈(내 여행·다녀온 장소·여행 통계)."""

from __future__ import annotations

import uuid
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel

HomeTripPhase = Literal["ongoing", "upcoming", "undated", "completed"]


class HomeTripCard(BaseModel):
    trip_id: uuid.UUID
    title: str
    region_hint: str | None
    # 시도 약칭(예: '강원') — 여행의 지역 코드·지역 메모, 없으면 장소에서 가장 많은 시도.
    region_name: str | None
    start_date: Date | None
    end_date: Date | None
    phase: HomeTripPhase
    # 시작까지 남은 날(예정 여행만, 오늘 기준 KST).
    days_until: int | None
    place_count: int


class HomeVisitedPlace(BaseModel):
    poi_id: uuid.UUID
    trip_id: uuid.UUID
    trip_title: str
    name: str
    category: str | None
    visited_on: Date
    region_name: str | None


class HomeRegionStat(BaseModel):
    code: str
    name: str
    place_count: int
    trip_count: int


class HomeStats(BaseModel):
    trip_count: int
    upcoming_trip_count: int
    ongoing_trip_count: int
    completed_trip_count: int
    undated_trip_count: int
    travel_day_count: int
    visited_place_count: int
    region_count: int


class UserHome(BaseModel):
    today: Date
    stats: HomeStats
    next_trip: HomeTripCard | None
    upcoming_trips: list[HomeTripCard]
    recent_trips: list[HomeTripCard]
    recent_places: list[HomeVisitedPlace]
    regions: list[HomeRegionStat]
