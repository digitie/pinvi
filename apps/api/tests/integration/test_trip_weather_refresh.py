"""`POST /trips/{id}/days/{n}/weather/refresh` — 날씨 위치 해석 캐시 새로고침(2026-11-16 소유자 요청 15).

핵심 단언:

- Map 경로: 캐시 행이 있어도(적중 상태여도) Map `/nearest`를 다시 불러 새 위치 집합으로 덮어쓴다.
- 같은 feature를 60초 안에 다시 누르면 Map을 부르지 않고 `cooldown` + `retry_after_seconds`.
- 좌표·Map 연결이 없는 장소는 `skipped`, 반경 안 위치가 없으면 `no_data`, Map 오류는 `failed`(500 없음).
- 여행 구성원이 아니면 403, 일자에 없는 `poi_id`는 404, service token 없으면 503.
- 플래그 off(직접 경로)는 Map을 부르지 않고 행을 stale로 표시한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.clients.kor_travel_map import KorTravelMapClient, get_optional_kor_travel_map_client
from app.core.config import settings
from app.main import app
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.weather_location_link import WeatherLocationLink
from tests import weather_map_fixtures as fx

pytestmark = pytest.mark.asyncio

_LAT, _LON = 37.5665, 126.978
Handler = Callable[[httpx.Request], httpx.Response]


class _Map:
    def __init__(self, weather: Handler, *, service_token: str = "svc") -> None:
        self.requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if request.url.path.startswith("/v1/service/weather/"):
                return weather(request)
            return httpx.Response(503, json=fx.problem_body(503, "UNAVAILABLE"))

        self.client = KorTravelMapClient(
            httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handle)),
            service_token=service_token,
            max_attempts=1,
            backoff_base_seconds=0.0,
        )

    def nearest_calls(self) -> int:
        return sum(1 for r in self.requests if r.url.path.endswith("/nearest"))


def _handler(*, nearest_status: int = 200, anchor: str = fx.LOC_KMA) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/service/weather/nearest":
            if nearest_status == 404:
                return httpx.Response(404, json=fx.problem_body(404, "NOT_FOUND"))
            if nearest_status != 200:
                return httpx.Response(nearest_status, json=fx.problem_body(nearest_status, "X"))
            return httpx.Response(200, json=fx.bundle_body(fx.kma_bundle(anchor)))
        if path == "/v1/service/weather/locations" and request.method == "GET":
            return httpx.Response(
                200,
                json=fx.list_body([fx.location(anchor, distance_m=300.0)], with_current=False),
            )
        return httpx.Response(404, json={"detail": "Not Found"})

    return handler


@pytest.fixture(autouse=True)
def _restore() -> Iterator[None]:
    original = settings.pinvi_kor_travel_map_weather_enabled
    yield
    settings.pinvi_kor_travel_map_weather_enabled = original
    app.dependency_overrides.pop(get_optional_kor_travel_map_client, None)


def _install(fake: _Map) -> None:
    app.dependency_overrides[get_optional_kor_travel_map_client] = lambda: fake.client


async def _seed(
    session_factory: Any, owner_id: str, *, pois: list[tuple[str | None, bool]]
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """1일차에 `(feature_id, 좌표 있음)` 장소들을 둔다."""
    trip_id = uuid.uuid4()
    owner = uuid.UUID(owner_id)
    async with session_factory() as db:
        db.add(Trip(trip_id=trip_id, owner_user_id=owner, title="날씨 새로고침"))
        db.add(TripDay(trip_id=trip_id, day_index=1, date=date(2026, 11, 20)))
        await db.flush()
        rows = [
            TripDayPoi(
                trip_id=trip_id,
                day_index=1,
                sort_order=f"a{i:02d}",
                feature_id=feature_id,
                feature_snapshot=(
                    {"title": "장소", "coord": {"lon": _LON, "lat": _LAT}}
                    if with_coord
                    else {"title": "좌표 없음"}
                ),
                added_by_user_id=owner,
                currency="KRW",
            )
            for i, (feature_id, with_coord) in enumerate(pois)
        ]
        db.add_all(rows)
        await db.commit()
        return trip_id, [row.attachment_id for row in rows]


async def _stale_map_link(session_factory: Any, feature_id: str, *, age: timedelta) -> None:
    async with session_factory() as db:
        db.add(
            WeatherLocationLink(
                feature_id=feature_id,
                location_id="kma-old-anchor",
                source_location_ids=["kma-old-anchor"],
                lat=_LAT,
                lon=_LON,
                distance_km=1.0,
                measurement_point={"resolved_via": "kor_travel_map", "selection_version": 2},
                resolved_at=datetime.now(UTC) - age,
                stale=False,
            )
        )
        await db.commit()


async def _link(session_factory: Any, feature_id: str) -> WeatherLocationLink | None:
    async with session_factory() as db:
        return await db.scalar(
            select(WeatherLocationLink).where(WeatherLocationLink.feature_id == feature_id)
        )


def _url(trip_id: uuid.UUID) -> str:
    return f"/trips/{trip_id}/days/1/weather/refresh"


async def test_map_path_reresolves_cached_link_then_cools_down(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    fake = _Map(_handler(anchor=fx.LOC_KMA))
    _install(fake)
    user_id, _ = verified_user
    feature_id = f"f_refresh_{uuid.uuid4().hex[:8]}"
    trip_id, _ = await _seed(
        session_factory, user_id, pois=[(feature_id, True), (None, True), ("f_nocoord", False)]
    )
    # 하루 전 해석된 행 — TTL(7일) 안이라 화면 조회는 이 낡은 집합을 그대로 쓴다.
    await _stale_map_link(session_factory, feature_id, age=timedelta(days=1))

    resp = await client.post(_url(trip_id), json={}, cookies=auth_cookies(user_id))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["refreshed"] == 1
    assert data["skipped"] == 2  # feature 없는 장소 + 좌표 없는 장소
    assert data["cooldown"] == 0 and data["failed"] == 0 and data["no_data"] == 0
    assert data["retry_after_seconds"] is None
    assert fake.nearest_calls() == 1
    row = await _link(session_factory, feature_id)
    assert row is not None
    assert row.location_id == fx.LOC_KMA
    assert datetime.now(UTC) - row.resolved_at < timedelta(seconds=30)

    again = await client.post(_url(trip_id), cookies=auth_cookies(user_id))
    assert again.status_code == 200, again.text
    data = again.json()["data"]
    assert data["refreshed"] == 0 and data["cooldown"] == 1
    assert 1 <= data["retry_after_seconds"] <= 60
    assert fake.nearest_calls() == 1  # 쿨다운 중엔 Map을 부르지 않는다


async def test_single_poi_and_error_outcomes(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    user_id, _ = verified_user
    f_a, f_b = f"f_a_{uuid.uuid4().hex[:8]}", f"f_b_{uuid.uuid4().hex[:8]}"
    trip_id, (poi_a, _poi_b) = await _seed(
        session_factory, user_id, pois=[(f_a, True), (f_b, True)]
    )

    _install(_Map(_handler(nearest_status=404)))
    resp = await client.post(
        _url(trip_id), json={"poi_id": str(poi_a)}, cookies=auth_cookies(user_id)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert (data["refreshed"], data["no_data"], data["skipped"]) == (0, 1, 0)
    assert await _link(session_factory, f_a) is None
    assert await _link(session_factory, f_b) is None  # 다른 장소는 건드리지 않는다

    _install(_Map(_handler(nearest_status=503)))
    resp = await client.post(_url(trip_id), cookies=auth_cookies(user_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["failed"] == 2

    missing = await client.post(
        _url(trip_id), json={"poi_id": str(uuid.uuid4())}, cookies=auth_cookies(user_id)
    )
    assert missing.status_code == 404


async def test_non_member_is_forbidden_and_missing_token_is_503(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    from app.models.user import User

    settings.pinvi_kor_travel_map_weather_enabled = True
    user_id, _ = verified_user
    trip_id, _ = await _seed(session_factory, user_id, pois=[(f"f_{uuid.uuid4().hex[:8]}", True)])
    stranger = uuid.uuid4()
    async with session_factory() as db:
        db.add(
            User(
                user_id=stranger,
                email=f"wxr_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=datetime.now(UTC),
            )
        )
        await db.commit()
    fake = _Map(_handler())
    _install(fake)
    denied = await client.post(_url(trip_id), cookies=auth_cookies(str(stranger)))
    assert denied.status_code == 403
    assert fake.nearest_calls() == 0

    _install(_Map(_handler(), service_token=""))
    unavailable = await client.post(_url(trip_id), cookies=auth_cookies(user_id))
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "WEATHER_SERVICE_UNAVAILABLE"


async def test_direct_path_marks_link_stale_without_calling_map(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = False
    fake = _Map(_handler())
    _install(fake)
    user_id, _ = verified_user
    feature_id = f"f_direct_{uuid.uuid4().hex[:8]}"
    trip_id, _ = await _seed(session_factory, user_id, pois=[(feature_id, True)])
    async with session_factory() as db:
        db.add(
            WeatherLocationLink(
                feature_id=feature_id,
                location_id="kma-direct",
                source_location_ids=["kma-direct"],
                lat=_LAT,
                lon=_LON,
                distance_km=1.0,
                measurement_point=None,
                resolved_at=datetime.now(UTC) - timedelta(hours=1),
                stale=False,
            )
        )
        await db.commit()

    resp = await client.post(_url(trip_id), cookies=auth_cookies(user_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["refreshed"] == 1
    assert fake.nearest_calls() == 0
    row = await _link(session_factory, feature_id)
    assert row is not None and row.stale is True
