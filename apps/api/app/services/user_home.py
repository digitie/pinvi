"""개인 홈 집계 — `GET /users/me/home` (`docs/api/users.md` §개인 홈).

정의(오늘 = KST 날짜, 범위 = 휴지통 밖의 내가 소유한 여행 + 동행으로 참여한 여행(`trip_companions.user_id`가
나 — 여행 접근 권한과 같은 기준). 둘 다인 여행은 한 번만 센다):

- 여행 단계: 날짜 기준. 시작일 > 오늘 = 예정, 시작일 ≤ 오늘 ≤ 종료일 = 진행 중, 종료일 < 오늘 = 다녀온
  여행, 시작일 없음 = 날짜 미정. 사용자가 고르는 `status`(초안·완료 등)는 쓰지 않는다 — 다녀왔는지는
  날짜가 정한다.
- 여행한 날: 진행 중·다녀온 여행의 [시작일, min(종료일, 오늘)] 날짜의 합집합(겹치는 여행은 한 번).
- 다녀온 장소: 일자의 실제 날짜(일자 날짜 override, 없으면 시작일 + (일차 - 1))가 오늘 이전·오늘인
  일자에 담긴 장소. 같은 지도 feature(또는 이름+좌표가 같은 직접 추가 장소)는 한 곳으로 센다.
- 다녀온 지역: 다녀온 장소의 시도(장소 snapshot의 코드·주소 → 여행 지역 코드 → 여행 지역 메모 순),
  장소가 없는 진행·다녀온 여행은 여행 자체의 시도.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.companion import TripCompanion
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.schemas.user_home import (
    HomeRegionStat,
    HomeStats,
    HomeTripCard,
    HomeTripPhase,
    HomeVisitedPlace,
    UserHome,
)
from app.services.korea_regions import (
    sido_from_code,
    sido_from_snapshot,
    sido_from_text,
    sido_name,
)

HOME_LIST_LIMIT = 4
HOME_RECENT_PLACE_LIMIT = 8
# 한 사용자 홈이 읽는 다녀온 장소 행의 상한 — 집계가 응답 시간을 넘지 않게 한다.
HOME_VISITED_ROW_CAP = 5000
UNNAMED_PLACE = "이름 없는 장소"


@dataclass(frozen=True)
class HomeTripRow:
    trip_id: uuid.UUID
    title: str
    region_hint: str | None
    primary_region_code: str | None
    start_date: date | None
    end_date: date | None
    updated_at: datetime
    # 동행으로 참여한 여행(소유자가 아님).
    joined: bool = False


@dataclass(frozen=True)
class HomePoiRow:
    poi_id: uuid.UUID
    trip_id: uuid.UUID
    sort_order: str
    feature_id: str | None
    feature_uuid: uuid.UUID | None
    feature_snapshot: Mapping[str, Any]
    visited_on: date


def trip_phase(trip: HomeTripRow, today: date) -> HomeTripPhase:
    if trip.start_date is None:
        return "undated"
    if trip.start_date > today:
        return "upcoming"
    end = trip.end_date or trip.start_date
    return "completed" if end < today else "ongoing"


def _trip_sido(trip: HomeTripRow) -> str | None:
    return sido_from_code(trip.primary_region_code) or sido_from_text(trip.region_hint)


def _place_name(snapshot: Mapping[str, Any]) -> str:
    for key in ("name", "title"):
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return UNNAMED_PLACE


def _place_key(poi: HomePoiRow) -> str:
    """같은 장소를 한 번만 센다 — 지도 feature는 id로, 직접 추가 장소는 이름+좌표(약 10 m)로."""
    if poi.feature_uuid is not None:
        return f"u:{poi.feature_uuid}"
    if poi.feature_id:
        return f"f:{poi.feature_id}"
    coord = poi.feature_snapshot.get("coord")
    if isinstance(coord, Mapping):
        lon, lat = coord.get("lon"), coord.get("lat")
        if isinstance(lon, int | float) and isinstance(lat, int | float):
            return f"c:{_place_name(poi.feature_snapshot)}:{lon:.4f}:{lat:.4f}"
    return f"p:{poi.poi_id}"


def _travel_days(trips: Sequence[HomeTripRow], today: date) -> int:
    days: set[date] = set()
    for trip in trips:
        if trip.start_date is None or trip.start_date > today:
            continue
        last = min(trip.end_date or trip.start_date, today)
        current = trip.start_date
        while current <= last:
            days.add(current)
            current += timedelta(days=1)
    return len(days)


def summarize_home(
    *,
    today: date,
    trips: Sequence[HomeTripRow],
    place_counts: Mapping[uuid.UUID, int],
    visited: Sequence[HomePoiRow],
) -> UserHome:
    trips_by_id = {trip.trip_id: trip for trip in trips}
    phases = {trip.trip_id: trip_phase(trip, today) for trip in trips}

    # 다녀온 장소 — 같은 장소는 가장 최근 방문 한 번만 남긴다.
    latest: dict[str, tuple[HomePoiRow, str | None]] = {}
    place_sidos_by_trip: dict[uuid.UUID, Counter[str]] = defaultdict(Counter)
    for poi in sorted(visited, key=lambda row: (row.visited_on, row.sort_order)):
        trip = trips_by_id.get(poi.trip_id)
        if trip is None:
            continue
        sido = sido_from_snapshot(poi.feature_snapshot) or _trip_sido(trip)
        if sido is not None:
            place_sidos_by_trip[poi.trip_id][sido] += 1
        latest[_place_key(poi)] = (poi, sido)

    region_places: Counter[str] = Counter()
    region_trips: dict[str, set[uuid.UUID]] = defaultdict(set)
    for _poi, sido in latest.values():
        if sido is not None:
            region_places[sido] += 1
    for trip_id, counter in place_sidos_by_trip.items():
        for sido in counter:
            region_trips[sido].add(trip_id)
    for trip in trips:
        if (
            phases[trip.trip_id] in ("ongoing", "completed")
            and trip.trip_id not in place_sidos_by_trip
        ):
            sido = _trip_sido(trip)
            if sido is not None:
                region_trips[sido].add(trip.trip_id)

    regions = sorted(
        (
            HomeRegionStat(
                code=code,
                name=sido_name(code),
                place_count=region_places.get(code, 0),
                trip_count=len(trip_ids),
            )
            for code, trip_ids in region_trips.items()
        ),
        key=lambda item: (-item.place_count, -item.trip_count, item.code),
    )

    def card(trip: HomeTripRow) -> HomeTripCard:
        phase = phases[trip.trip_id]
        sido = _trip_sido(trip)
        if sido is None and place_sidos_by_trip.get(trip.trip_id):
            sido = place_sidos_by_trip[trip.trip_id].most_common(1)[0][0]
        return HomeTripCard(
            trip_id=trip.trip_id,
            title=trip.title,
            region_hint=trip.region_hint,
            region_name=sido_name(sido) if sido else None,
            start_date=trip.start_date,
            end_date=trip.end_date,
            phase=phase,
            days_until=(
                (trip.start_date - today).days
                if phase == "upcoming" and trip.start_date is not None
                else None
            ),
            place_count=place_counts.get(trip.trip_id, 0),
            joined=trip.joined,
        )

    def of_phase(phase: HomeTripPhase) -> list[HomeTripRow]:
        return [trip for trip in trips if phases[trip.trip_id] == phase]

    ongoing = sorted(of_phase("ongoing"), key=lambda t: (t.start_date or today, t.title))
    upcoming = sorted(of_phase("upcoming"), key=lambda t: (t.start_date or today, t.title))
    undated = sorted(of_phase("undated"), key=lambda t: t.updated_at, reverse=True)
    completed = sorted(
        of_phase("completed"),
        key=lambda t: (t.end_date or t.start_date or today, t.title),
        reverse=True,
    )
    planned = ongoing + upcoming
    next_trip = planned[0] if planned else None
    rest = [trip for trip in planned + undated if trip is not next_trip]

    recent_places = sorted(
        latest.values(), key=lambda item: (item[0].visited_on, item[0].sort_order), reverse=True
    )[:HOME_RECENT_PLACE_LIMIT]

    return UserHome(
        today=today,
        stats=HomeStats(
            trip_count=len(trips),
            upcoming_trip_count=len(upcoming),
            ongoing_trip_count=len(ongoing),
            completed_trip_count=len(completed),
            undated_trip_count=len(undated),
            travel_day_count=_travel_days(trips, today),
            visited_place_count=len(latest),
            region_count=len(regions),
        ),
        next_trip=card(next_trip) if next_trip else None,
        upcoming_trips=[card(trip) for trip in rest[:HOME_LIST_LIMIT]],
        recent_trips=[card(trip) for trip in completed[:HOME_LIST_LIMIT]],
        recent_places=[
            HomeVisitedPlace(
                poi_id=poi.poi_id,
                trip_id=poi.trip_id,
                trip_title=trips_by_id[poi.trip_id].title,
                name=_place_name(poi.feature_snapshot),
                category=(
                    poi.feature_snapshot.get("category")
                    if isinstance(poi.feature_snapshot.get("category"), str)
                    else None
                ),
                visited_on=poi.visited_on,
                region_name=sido_name(sido) if sido else None,
            )
            for poi, sido in recent_places
        ],
        regions=regions,
    )


def _in_scope(user_id: uuid.UUID) -> ColumnElement[bool]:
    """내가 소유했거나 동행으로 참여한 휴지통 밖 여행 — IN 하위 질의라 두 경로가 겹쳐도 한 행이다."""
    joined = select(TripCompanion.trip_id).where(TripCompanion.user_id == user_id)
    return and_(
        or_(Trip.owner_user_id == user_id, Trip.trip_id.in_(joined)),
        Trip.deleted_at.is_(None),
    )


async def build_user_home(db: AsyncSession, *, user_id: uuid.UUID, today: date) -> UserHome:
    trip_rows = (
        await db.execute(
            select(
                Trip.trip_id,
                Trip.title,
                Trip.region_hint,
                Trip.primary_region_code,
                Trip.start_date,
                Trip.end_date,
                Trip.updated_at,
                Trip.owner_user_id,
            ).where(_in_scope(user_id))
        )
    ).all()
    trips = [
        HomeTripRow(
            trip_id=row.trip_id,
            title=row.title,
            region_hint=row.region_hint,
            primary_region_code=row.primary_region_code,
            start_date=row.start_date,
            end_date=row.end_date,
            updated_at=row.updated_at,
            joined=row.owner_user_id != user_id,
        )
        for row in trip_rows
    ]
    if not trips:
        return summarize_home(today=today, trips=[], place_counts={}, visited=[])

    count_rows = (
        await db.execute(
            select(TripDayPoi.trip_id, func.count())
            .join(Trip, Trip.trip_id == TripDayPoi.trip_id)
            .where(
                _in_scope(user_id),
                TripDayPoi.deleted_at.is_(None),
            )
            .group_by(TripDayPoi.trip_id)
        )
    ).all()
    place_counts = {trip_id: int(count) for trip_id, count in count_rows}

    # 일자의 실제 날짜 = override, 없으면 시작일 + (일차 - 1) (ADR-055, `telegram_itinerary.effective_date`).
    effective_date = func.coalesce(
        TripDay.date,
        Trip.start_date + (TripDay.day_index - 1),
    )
    visited_rows = (
        await db.execute(
            select(
                TripDayPoi.attachment_id,
                TripDayPoi.trip_id,
                TripDayPoi.sort_order,
                TripDayPoi.feature_id,
                TripDayPoi.feature_uuid,
                TripDayPoi.feature_snapshot,
                effective_date,
            )
            .join(
                TripDay,
                and_(
                    TripDay.trip_id == TripDayPoi.trip_id,
                    TripDay.day_index == TripDayPoi.day_index,
                ),
            )
            .join(Trip, Trip.trip_id == TripDayPoi.trip_id)
            .where(
                _in_scope(user_id),
                TripDayPoi.deleted_at.is_(None),
                or_(Trip.start_date <= today, TripDay.date <= today),
                effective_date <= today,
            )
            .order_by(effective_date.desc(), TripDayPoi.sort_order.desc())
            .limit(HOME_VISITED_ROW_CAP)
        )
    ).all()
    visited = [
        HomePoiRow(
            poi_id=row[0],
            trip_id=row[1],
            sort_order=row[2],
            feature_id=row[3],
            feature_uuid=row[4],
            feature_snapshot=row[5] if isinstance(row[5], Mapping) else {},
            visited_on=row[6],
        )
        for row in visited_rows
    ]
    return summarize_home(today=today, trips=trips, place_counts=place_counts, visited=visited)
