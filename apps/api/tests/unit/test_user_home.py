"""개인 홈 집계(`services/user_home.summarize_home`)와 시도 판정(`services/korea_regions`)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from app.services.korea_regions import sido_from_code, sido_from_snapshot, sido_from_text
from app.services.user_home import HomePoiRow, HomeTripRow, summarize_home, trip_phase

TODAY = date(2026, 11, 16)
STAMP = datetime(2026, 11, 1, tzinfo=UTC)


def _trip(title: str, start: date | None, end: date | None, **kw: object) -> HomeTripRow:
    return HomeTripRow(
        trip_id=uuid.uuid4(),
        title=title,
        region_hint=kw.get("region_hint"),  # type: ignore[arg-type]
        primary_region_code=kw.get("code"),  # type: ignore[arg-type]
        start_date=start,
        end_date=end,
        updated_at=kw.get("updated_at", STAMP),  # type: ignore[arg-type]
    )


def _poi(trip: HomeTripRow, on: date, name: str, **kw: object) -> HomePoiRow:
    snapshot: dict[str, object] = {"name": name, "coord": {"lon": 128.9, "lat": 37.8}}
    snapshot.update(kw.get("snapshot", {}))  # type: ignore[call-overload]
    return HomePoiRow(
        poi_id=uuid.uuid4(),
        trip_id=trip.trip_id,
        sort_order=str(kw.get("order", "a0")),
        feature_id=kw.get("feature_id"),  # type: ignore[arg-type]
        feature_uuid=None,
        feature_snapshot=snapshot,
        visited_on=on,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1100000000", "11"),
        ("4215010100", "51"),  # 옛 강원 코드 → 강원특별자치도
        ("45", "52"),  # 옛 전북 코드 → 전북특별자치도
        ("99", None),
        ("abc", None),
        (None, None),
    ],
)
def test_sido_from_code(value: object, expected: str | None) -> None:
    assert sido_from_code(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("강원특별자치도 강릉시 창해로 514", "51"),
        ("강릉", "51"),
        ("경주시 불국로", "47"),
        ("경기 광주시", "41"),
        ("광주시", None),  # 경기 광주시 — 광주광역시로 오판하지 않는다
        ("고성", None),  # 강원·경남 모두에 있다
        ("제주시 애월읍", "50"),
        ("부산광역시 해운대구", "26"),
        ("어딘가", None),
        ("", None),
    ],
)
def test_sido_from_text(value: str, expected: str | None) -> None:
    assert sido_from_text(value) == expected


def test_sido_from_snapshot_prefers_codes_then_address_and_ignores_name() -> None:
    assert sido_from_snapshot({"region": {"sido_code": "26"}, "address": "서울 중구"}) == "26"
    assert sido_from_snapshot({"address": {"label": "전라남도 여수시"}}) == "46"
    assert sido_from_snapshot({"address_label": "충북 단양군 단양읍"}) == "43"
    # 이름 속 지명('서울숲')은 지역 근거가 아니다.
    assert sido_from_snapshot({"name": "서울숲 카페"}) is None


def test_trip_phase_is_date_driven() -> None:
    assert trip_phase(_trip("a", None, None), TODAY) == "undated"
    assert trip_phase(_trip("a", date(2026, 11, 20), date(2026, 11, 21)), TODAY) == "upcoming"
    assert trip_phase(_trip("a", date(2026, 11, 15), date(2026, 11, 17)), TODAY) == "ongoing"
    assert trip_phase(_trip("a", date(2026, 11, 16), None), TODAY) == "ongoing"
    assert trip_phase(_trip("a", date(2026, 11, 1), date(2026, 11, 15)), TODAY) == "completed"


def test_summarize_home_counts_and_lists() -> None:
    gangneung = _trip("강릉 바다", date(2026, 10, 1), date(2026, 10, 3), region_hint="강릉")
    overlap = _trip("강릉 하루 더", date(2026, 10, 3), date(2026, 10, 3), code="5115000000")
    ongoing = _trip("경주 진행 중", date(2026, 11, 15), date(2026, 11, 17))
    upcoming = _trip("제주 예정", date(2026, 12, 1), date(2026, 12, 3), region_hint="제주")
    soon = _trip("부산 곧", date(2026, 11, 20), date(2026, 11, 21))
    undated = _trip("언젠가 서울", None, None, region_hint="서울")
    trips = [gangneung, overlap, ongoing, upcoming, soon, undated]

    visited = [
        _poi(gangneung, date(2026, 10, 1), "경포해변", feature_id="f-1"),
        _poi(gangneung, date(2026, 10, 2), "정동진", feature_id="f-2", order="a1"),
        # 다른 여행에서 같은 feature를 다시 방문 — 장소는 한 곳, 최근 방문 날짜로 남는다.
        _poi(overlap, date(2026, 10, 3), "경포해변", feature_id="f-1"),
        _poi(
            ongoing,
            date(2026, 11, 15),
            "불국사",
            feature_id="f-3",
            snapshot={"address": {"label": "경북 경주시 진현동"}},
        ),
        # 직접 추가 장소(feature 없음) — 지역 근거가 없으면 지역 집계에서 빠진다.
        _poi(ongoing, date(2026, 11, 16), "이름만 있는 곳", order="a2"),
    ]
    home = summarize_home(
        today=TODAY,
        trips=trips,
        place_counts={gangneung.trip_id: 3, ongoing.trip_id: 2},
        visited=visited,
    )

    stats = home.stats
    assert stats.trip_count == 6
    assert (stats.upcoming_trip_count, stats.ongoing_trip_count) == (2, 1)
    assert (stats.completed_trip_count, stats.undated_trip_count) == (2, 1)
    # 10/1·10/2·10/3(두 여행이 겹쳐도 한 번) + 11/15·11/16(오늘까지) = 5일
    assert stats.travel_day_count == 5
    assert stats.visited_place_count == 4
    assert stats.region_count == 2

    assert [(r.name, r.place_count, r.trip_count) for r in home.regions] == [
        ("강원", 2, 2),
        ("경북", 1, 1),
    ]
    assert home.next_trip is not None
    assert home.next_trip.title == "경주 진행 중"
    assert home.next_trip.phase == "ongoing" and home.next_trip.days_until is None
    assert home.next_trip.region_name == "경북"  # 여행 지역 근거가 없어 장소 시도로
    assert [(t.title, t.days_until) for t in home.upcoming_trips] == [
        ("부산 곧", 4),
        ("제주 예정", 15),
        ("언젠가 서울", None),
    ]
    assert [t.title for t in home.recent_trips] == ["강릉 하루 더", "강릉 바다"]
    assert home.recent_trips[1].place_count == 3
    assert home.recent_trips[1].region_name == "강원"

    places = [(p.name, p.visited_on.isoformat(), p.region_name) for p in home.recent_places]
    assert places == [
        ("이름만 있는 곳", "2026-11-16", None),
        ("불국사", "2026-11-15", "경북"),
        ("경포해변", "2026-10-03", "강원"),
        ("정동진", "2026-10-02", "강원"),
    ]
    assert home.recent_places[2].trip_title == "강릉 하루 더"


def test_summarize_home_empty_user() -> None:
    home = summarize_home(today=TODAY, trips=[], place_counts={}, visited=[])
    assert home.next_trip is None
    assert home.stats.trip_count == 0 and home.stats.travel_day_count == 0
    assert home.upcoming_trips == [] and home.recent_trips == [] and home.regions == []
