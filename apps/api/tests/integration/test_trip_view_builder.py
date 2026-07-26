"""Trip 상세 view builder feature_id 계약 회귀 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient, KorTravelMapUnavailable

pytestmark = pytest.mark.asyncio


class _StringFeatureClient:
    def __init__(self) -> None:
        self.requested_ids: list[str] = []

    async def get_features(self, feature_ids: list[str]) -> dict[str, Any]:
        self.requested_ids = list(feature_ids)
        return {
            "found": {
                "place:abc123@raw": {
                    "feature_id": "place:abc123@raw",
                    "name": "최신 경복궁",
                    "marker_color": "P-01",
                    "marker_icon": "monument",
                }
            },
            "missing": [],
        }


class _BatchOutcomeFeatureClient:
    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error

    async def get_features(self, feature_ids: list[str]) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


async def test_build_trip_view_batches_opaque_feature_ids(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.kasi import TripPoiRiseSet
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.trip_view_builder import build_trip_view

    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        user = User(
            user_id=user_id,
            email=f"builder_{uuid.uuid4().hex[:8]}@pinvi.test",
            status="active",
            email_verified_at=now,
        )
        db.add(user)
        await db.flush()

        trip = Trip(
            trip_id=trip_id,
            owner_user_id=user_id,
            title="서울 여행",
        )
        day = TripDay(trip_id=trip_id, day_index=1, title="1일차")
        db.add_all([trip, day])
        await db.flush()

        poi = TripDayPoi(
            trip_id=trip_id,
            day_index=1,
            sort_order="a0",
            feature_id="place:abc123@raw",
            feature_snapshot={"title": "저장된 경복궁"},
            added_by_user_id=user_id,
            currency="KRW",
        )
        db.add(poi)
        await db.flush()
        db.add(
            TripPoiRiseSet(
                poi_id=poi.attachment_id,
                locdate=date(2026, 5, 6),
                status="success",
                sunrise_at=datetime(2026, 5, 6, 5, 30, tzinfo=UTC),
                sunset_at=datetime(2026, 5, 6, 19, 30, tzinfo=UTC),
            )
        )
        await db.commit()
        await db.refresh(trip)

        kor_travel_map_client = _StringFeatureClient()
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=kor_travel_map_client)

    assert kor_travel_map_client.requested_ids == ["place:abc123@raw"]
    assert view["broken_feature_count"] == 0
    built_poi = view["days"][0]["pois"][0]
    assert built_poi["feature_id"] == "place:abc123@raw"
    assert built_poi["feature_resolution_state"] == "found"
    assert built_poi["title"] == "최신 경복궁"
    assert built_poi["rise_set"]["status"] == "success"
    assert built_poi["rise_set"]["locdate"] == date(2026, 5, 6)
    assert built_poi["rise_set"]["sunrise_at"] == datetime(2026, 5, 6, 5, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("response", "error", "expected_state"),
    [
        ({"found": {}, "missing": ["place:missing"]}, None, "missing"),
        (None, KorTravelMapUnavailable("kor-travel-map unavailable"), "unverified"),
    ],
    ids=["authoritative-missing", "transport-failure"],
)
async def test_build_trip_view_exposes_missing_and_transport_unverified(
    session_factory,  # type: ignore[no-untyped-def]
    response: dict[str, Any] | None,
    error: Exception | None,
    expected_state: str,
) -> None:
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.trip_view_builder import build_trip_view

    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"batch_outcome_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        trip = Trip(trip_id=trip_id, owner_user_id=user_id, title="배치 상태 여행")
        db.add_all([trip, TripDay(trip_id=trip_id, day_index=1, title="1일차")])
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=1,
                    sort_order=sort_order,
                    feature_id="place:missing",
                    feature_snapshot={"title": "저장된 장소"},
                    added_by_user_id=user_id,
                    currency="KRW",
                )
                for sort_order in ("a0", "a1")
            ]
        )
        await db.commit()
        await db.refresh(trip)

        client = _BatchOutcomeFeatureClient(response=response, error=error)
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=client)

    built_pois = view["days"][0]["pois"]
    assert [poi["title"] for poi in built_pois] == ["저장된 장소", "저장된 장소"]
    assert {poi["feature_resolution_state"] for poi in built_pois} == {expected_state}
    # count의 제품 의미는 unique feature가 아니라 영향을 받는 여행 POI 수다.
    assert view["broken_feature_count"] == (2 if expected_state == "missing" else 0)


async def test_build_trip_view_skips_null_feature_ids(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.trip_view_builder import build_trip_view

    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"null_feature_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        trip = Trip(trip_id=trip_id, owner_user_id=user_id, title="자유 장소 여행")
        db.add_all([trip, TripDay(trip_id=trip_id, day_index=1, title="1일차")])
        await db.flush()
        db.add(
            TripDayPoi(
                trip_id=trip_id,
                day_index=1,
                sort_order="a0",
                feature_id=None,
                feature_snapshot={"name": "지도 밖 메모 장소"},
                added_by_user_id=user_id,
                currency="KRW",
            )
        )
        await db.commit()
        await db.refresh(trip)

        kor_travel_map_client = _StringFeatureClient()
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=kor_travel_map_client)

    assert kor_travel_map_client.requested_ids == []
    assert view["broken_feature_count"] == 0
    built_poi = view["days"][0]["pois"][0]
    assert built_poi["feature_id"] is None
    assert built_poi["feature_resolution_state"] == "not_linked"
    assert built_poi["title"] == "지도 밖 메모 장소"


async def test_build_trip_view_includes_public_holidays(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.kasi import KasiSpecialDay
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.trip_view_builder import build_trip_view

    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"holiday_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        trip = Trip(trip_id=trip_id, owner_user_id=user_id, title="공휴일 여행")
        db.add_all(
            [
                trip,
                TripDay(trip_id=trip_id, day_index=1, date=date(2026, 8, 15), title="광복절"),
                TripDay(trip_id=trip_id, day_index=2, date=date(2026, 8, 16), title="둘째 날"),
                KasiSpecialDay(
                    dataset="holidays",
                    sol_date=date(2026, 8, 15),
                    name="광복절",
                    sequence="1",
                    is_holiday=True,
                ),
                KasiSpecialDay(
                    dataset="anniversaries",
                    sol_date=date(2026, 8, 15),
                    name="광복절 기념일",
                    sequence="2",
                    is_holiday=False,
                ),
            ]
        )
        await db.commit()
        await db.refresh(trip)

        view = await build_trip_view(db, trip=trip, kor_travel_map_client=None)

    assert view["days"][0]["holidays"] == [
        {"date": date(2026, 8, 15), "name": "광복절", "dataset": "holidays"}
    ]
    assert view["days"][1]["holidays"] == []


async def test_build_trip_view_day_presentation(session_factory) -> None:  # type: ignore[no-untyped-def]
    """ADR-055: effective_date 파생 + out_of_range + 일자색/display 색."""
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.trip_view_builder import build_trip_view

    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"pres_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        # 2일 여행. day 3은 기간 밖(파생 effective_date로 검증). date는 모두 override 없음(NULL).
        trip = Trip(
            trip_id=trip_id,
            owner_user_id=user_id,
            title="표시 모델",
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 11),
        )
        db.add_all(
            [
                trip,
                TripDay(trip_id=trip_id, day_index=1, marker_color="P-10"),  # 색 override
                TripDay(trip_id=trip_id, day_index=2),  # override 없음 → 기본 P-02
                TripDay(trip_id=trip_id, day_index=3),  # 기간 밖
            ]
        )
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=1,
                    sort_order="a0",
                    feature_id=None,
                    feature_snapshot={"name": "커스텀 색"},
                    custom_marker_color="P-05",
                    added_by_user_id=user_id,
                    currency="KRW",
                ),
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=1,
                    sort_order="a1",
                    feature_id=None,
                    feature_snapshot={"name": "일자색 상속"},
                    added_by_user_id=user_id,
                    currency="KRW",
                ),
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=2,
                    sort_order="a0",
                    feature_id=None,
                    feature_snapshot={"name": "기본 일자색"},
                    added_by_user_id=user_id,
                    currency="KRW",
                ),
            ]
        )
        await db.commit()
        await db.refresh(trip)

        view = await build_trip_view(db, trip=trip, kor_travel_map_client=None)

    days = {d["day_index"]: d for d in view["days"]}
    assert days[1]["date"] is None
    assert days[1]["effective_date"] == date(2026, 6, 10)
    assert days[1]["out_of_range"] is False
    assert days[1]["marker_color"] == "P-10"
    assert days[2]["effective_date"] == date(2026, 6, 11)
    assert days[2]["marker_color"] is None
    assert days[3]["effective_date"] == date(2026, 6, 12)
    assert days[3]["out_of_range"] is True

    # POI display_marker_color: custom(POI) > 일자 override > 일자 기본색.
    assert days[1]["pois"][0]["display_marker_color"] == "P-05"  # POI custom
    assert days[1]["pois"][1]["display_marker_color"] == "P-10"  # day1 override 상속
    assert days[2]["pois"][0]["display_marker_color"] == "P-02"  # day2 기본색


class _CountingFeatureClient:
    def __init__(self) -> None:
        self.call_count = 0
        self.last_requested: list[str] = []

    async def get_features(self, feature_ids: list[str]) -> dict[str, Any]:
        self.call_count += 1
        self.last_requested = list(feature_ids)
        return {
            "found": {
                "place:cache1@raw": {
                    "feature_id": "place:cache1@raw",
                    "name": "캐시된 장소",
                    "marker_color": "P-02",
                }
            },
            "missing": [],
        }


async def test_build_trip_view_uses_feature_cache(session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.feature_cache import feature_cache
    from app.services.trip_view_builder import build_trip_view

    feature_cache.clear()
    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"cache_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        db.add_all(
            [
                Trip(trip_id=trip_id, owner_user_id=user_id, title="캐시 여행"),
                TripDay(trip_id=trip_id, day_index=1, title="1일차"),
            ]
        )
        await db.flush()
        db.add(
            TripDayPoi(
                trip_id=trip_id,
                day_index=1,
                sort_order="a0",
                feature_id="place:cache1@raw",
                feature_snapshot={"title": "저장본"},
                added_by_user_id=user_id,
                currency="KRW",
            )
        )
        await db.commit()
        await db.refresh(trip := await db.get(Trip, trip_id))

        client = _CountingFeatureClient()
        first = await build_trip_view(db, trip=trip, kor_travel_map_client=client)
        second = await build_trip_view(db, trip=trip, kor_travel_map_client=client)

    # 1번째는 fetch, 2번째는 캐시 hit → get_features 추가 호출 없음.
    assert client.call_count == 1
    assert first["days"][0]["pois"][0]["title"] == "캐시된 장소"
    assert first["days"][0]["pois"][0]["feature_resolution_state"] == "found"
    assert second["days"][0]["pois"][0]["feature_resolution_state"] == "found"
    assert second["days"][0]["pois"][0]["title"] == "캐시된 장소"


async def test_build_trip_view_distinguishes_cache_hit_from_uncached_outage(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.services.feature_cache import feature_cache
    from app.services.trip_view_builder import build_trip_view

    class _UnavailableClient:
        def __init__(self) -> None:
            self.requested_ids: list[str] = []

        async def get_features(self, feature_ids: list[str]) -> dict[str, Any]:
            self.requested_ids = list(feature_ids)
            raise KorTravelMapUnavailable("transport down")

    feature_cache.clear()
    feature_cache.put_many(
        {
            "place:cached": {
                "feature_id": "place:cached",
                "name": "캐시 확인 장소",
                "marker_color": "P-01",
            }
        }
    )
    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"mixed_cache_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        trip = Trip(trip_id=trip_id, owner_user_id=user_id, title="캐시 혼합 여행")
        db.add_all([trip, TripDay(trip_id=trip_id, day_index=1, title="1일차")])
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=1,
                    sort_order="a0",
                    feature_id="place:cached",
                    feature_snapshot={"title": "캐시 이전 저장본"},
                    added_by_user_id=user_id,
                    currency="KRW",
                ),
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=1,
                    sort_order="a1",
                    feature_id="place:uncached",
                    feature_snapshot={"title": "미확인 저장본"},
                    added_by_user_id=user_id,
                    currency="KRW",
                ),
            ]
        )
        await db.commit()
        await db.refresh(trip)

        client = _UnavailableClient()
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=client)

    pois_by_id = {poi["feature_id"]: poi for poi in view["days"][0]["pois"]}
    assert client.requested_ids == ["place:uncached"]
    assert pois_by_id["place:cached"]["title"] == "캐시 확인 장소"
    assert pois_by_id["place:cached"]["feature_resolution_state"] == "found"
    assert pois_by_id["place:uncached"]["title"] == "미확인 저장본"
    assert pois_by_id["place:uncached"]["feature_resolution_state"] == "unverified"
    assert view["broken_feature_count"] == 0
    feature_cache.clear()


@pytest.mark.parametrize(
    "upstream_case",
    ["mismatched-id", "nan", "infinity", "overflow", "401", "403", "404", "422"],
)
async def test_real_client_contract_and_http_errors_return_typed_unverified_snapshot(
    session_factory,  # type: ignore[no-untyped-def]
    upstream_case: str,
) -> None:
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay
    from app.models.user import User
    from app.schemas.trip import TripView
    from app.services.feature_cache import feature_cache
    from app.services.trip_view_builder import build_trip_view

    def handler(request: httpx.Request) -> httpx.Response:
        if upstream_case.isdigit():
            return httpx.Response(
                int(upstream_case),
                json={"code": "BATCH_UPSTREAM_ERROR", "title": "batch upstream error"},
            )
        if upstream_case == "mismatched-id":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "found": {
                            "place:contract": {
                                "feature_id": "place:other",
                                "name": "잘못 주입된 장소",
                            }
                        },
                        "missing": [],
                    },
                    "meta": {},
                },
            )
        raw_number = {"nan": "NaN", "infinity": "Infinity", "overflow": "1e400"}[upstream_case]
        return httpx.Response(
            200,
            content=(
                '{"data":{"found":{"place:contract":{"feature_id":"place:contract",'
                '"name":"비유한 좌표","lon":'
                f"{raw_number}"
                '}},"missing":[]},"meta":{}}'
            ).encode(),
            headers={"content-type": "application/json"},
        )

    feature_cache.clear()
    user_id = uuid.uuid4()
    trip_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"malformed_batch_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        trip = Trip(trip_id=trip_id, owner_user_id=user_id, title="계약 오류 여행")
        db.add_all([trip, TripDay(trip_id=trip_id, day_index=1, title="1일차")])
        await db.flush()
        db.add(
            TripDayPoi(
                trip_id=trip_id,
                day_index=1,
                sort_order="a0",
                feature_id="place:contract",
                feature_snapshot={"title": "안전한 저장본"},
                added_by_user_id=user_id,
                currency="KRW",
            )
        )
        await db.commit()
        await db.refresh(trip)

        http = httpx.AsyncClient(
            base_url="http://kor_travel_map.test",
            transport=httpx.MockTransport(handler),
        )
        client = KorTravelMapClient(http, max_attempts=1)
        view = await build_trip_view(db, trip=trip, kor_travel_map_client=client)
        await client.aclose()

    typed_view = TripView.model_validate(view)
    built_poi = typed_view.days[0].pois[0]
    assert built_poi.title == "안전한 저장본"
    assert built_poi.feature_resolution_state == "unverified"
    assert typed_view.broken_feature_count == 0
    cached, misses = feature_cache.get_many(["place:contract"])
    assert cached == {}
    assert misses == ["place:contract"]
