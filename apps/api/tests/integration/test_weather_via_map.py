"""weather 읽기의 Map 경로 — `PINVI_KOR_TRAVEL_MAP_WEATHER_ENABLED` (ADR-077, Map ADR-114 W7).

핵심 단언:

- 플래그 off(기본)면 Map weather 표면을 **부르지 않는다**(카드·trip view·지도 marker 모두 직접 경로).
- 플래그 on이면 해석은 `/nearest`(캐시 `weather_location_links` 공유), 카드·trip은 `POST /locations/batch`,
  marker는 `/locations?include_current=true`(영역)를 읽고 공개 응답 셰입은 그대로다. 특보만 weather 직접이다.
- Map이 부분을 못 읽으면(`not_loaded`·`unavailable`) 그 부분만 빠지고, 전부 못 읽으면 카드는 빈 카드·trip은
  `unavailable`이다(500 없음, 지어낸 `no_data` 없음).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.clients.kor_travel_map import (
    KorTravelMapClient,
    get_kor_travel_map_client,
    get_optional_kor_travel_map_client,
)
from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient
from app.clients.kor_travel_weather import (
    WeatherMarkerOut,
    WeatherValueOut,
    get_optional_kor_travel_weather_client,
)
from app.core.config import settings
from app.core.time import KST
from app.main import app
from app.models.weather_location_link import WeatherLocationLink
from app.services.weather_location_resolver import WeatherLocationFound, WeatherLocationNoData
from app.services.weather_map_resolver import resolve_weather_location_via_map
from tests import weather_map_fixtures as fx

pytestmark = pytest.mark.asyncio

_LAT, _LON = 37.5665, 126.978
WeatherHandler = Callable[[httpx.Request], httpx.Response]


class _Map:
    """실제 `KorTravelMapClient` + MockTransport. feature 상세는 좌표만, feature batch는 503(무관), weather는 handler."""

    def __init__(self, weather: WeatherHandler) -> None:
        self.requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            path = request.url.path
            if path.startswith("/v1/service/weather/"):
                return weather(request)
            if request.method == "GET" and path.startswith("/v1/features/"):
                feature_id = path.rsplit("/", 1)[-1]
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "feature_id": feature_id,
                            "kind": "place",
                            "lon": _LON,
                            "lat": _LAT,
                        },
                        "meta": {"duration_ms": 1},
                    },
                )
            return httpx.Response(503, json=fx.problem_body(503, "UNAVAILABLE"))

        self.client = KorTravelMapClient(
            httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handle)),
            service_token="svc",
            max_attempts=1,
            backoff_base_seconds=0.0,
        )

    def weather_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.startswith("/v1/service/weather/")]

    def batch_location_ids(self) -> list[list[str]]:
        return [
            json.loads(r.content)["location_ids"]
            for r in self.weather_requests()
            if r.url.path.endswith("/batch")
        ]


def _alert(location_id: str) -> WeatherValueOut:
    now = datetime.now(UTC)
    return WeatherValueOut(
        value_id="alert-1",
        location_id=location_id,
        provider="python-kma-api",
        dataset_key="kma_alerts",
        weather_domain="weather_alert",
        forecast_style="observed",
        metric_key="ALERT",
        target_at=now,
        normalization_version="kma-v1",
        collected_at=now,
        source_record_key="sr-alert",
        value_text="호우주의보",
        severity="advisory",
        known_at=now,
    )


class _Weather:
    """kor-travel-weather 대역 — 플래그 on에서는 `markers`(특보)만 불려야 한다."""

    def __init__(self, *, alerts_for: str | None = None) -> None:
        self.alerts_for = alerts_for
        self.calls: list[str] = []

    async def markers(self, location_ids: list[str]) -> tuple[WeatherMarkerOut, ...]:
        self.calls.append("markers")
        return tuple(
            WeatherMarkerOut(
                location_id=loc,
                alerts=(_alert(loc),) if loc == self.alerts_for else (),
            )
            for loc in location_ids
        )

    def __getattr__(self, name: str) -> Any:  # resolve·latest·forecast·nearby는 불리면 안 된다
        raise AssertionError(f"플래그 on에서 kor-travel-weather {name} 호출")


def _near_body(*pairs: tuple[str, float]) -> dict[str, Any]:
    return fx.list_body(
        [fx.location(loc, distance_m=distance) for loc, distance in pairs], with_current=False
    )


_SPLIT_NEAR = (
    (fx.LOC_AIR, 270.0),
    (fx.LOC_KMA, 1200.0),
    ("airkorea-other-station", 2000.0),
    (fx.LOC_EXT, 3400.0),
    ("kma-grid-far", 9000.0),
)


def _nearest_then_batch(
    *,
    nearest: dict[str, Any] | None = None,
    batch: Callable[[list[str]], httpx.Response] | None = None,
    near: tuple[tuple[str, float], ...] = ((fx.LOC_KMA, 100.0),),
) -> WeatherHandler:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/service/weather/nearest":
            return httpx.Response(200, json=fx.bundle_body(nearest or fx.kma_bundle()))
        if path == "/v1/service/weather/locations" and request.method == "GET":
            return httpx.Response(200, json=_near_body(*near))
        if path == "/v1/service/weather/locations/batch":
            ids = json.loads(request.content)["location_ids"]
            if batch is not None:
                return batch(ids)
            return httpx.Response(200, json=fx.batch_body([fx.kma_bundle(loc) for loc in ids]))
        return httpx.Response(404, json={"detail": "Not Found"})

    return handler


@pytest.fixture(autouse=True)
def _restore() -> Iterator[None]:
    original = (
        settings.pinvi_kor_travel_map_weather_enabled,
        settings.pinvi_kor_travel_weather_map_markers_enabled,
    )
    yield
    (
        settings.pinvi_kor_travel_map_weather_enabled,
        settings.pinvi_kor_travel_weather_map_markers_enabled,
    ) = original
    for dep in (
        get_kor_travel_map_client,
        get_optional_kor_travel_map_client,
        get_optional_kor_travel_weather_client,
    ):
        app.dependency_overrides.pop(dep, None)


def _install(fake: _Map, weather: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_client] = lambda: fake.client
    app.dependency_overrides[get_optional_kor_travel_map_client] = lambda: fake.client
    app.dependency_overrides[get_optional_kor_travel_weather_client] = lambda: weather


# ── 해석기 ───────────────────────────────────────────────────────────────────────────


def _resolver_handler(
    *,
    nearest: Callable[[], dict[str, Any]] = fx.nearest_split_bundle,
    near: tuple[tuple[str, float], ...] = _SPLIT_NEAR,
    min_radius_m: float = 0.0,
    calls: list[httpx.Request] | None = None,
) -> WeatherHandler:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        path = request.url.path
        if path == "/v1/service/weather/nearest":
            if float(request.url.params["radius_m"]) < min_radius_m:
                return httpx.Response(404, json=fx.problem_body(404, "NOT_FOUND"))
            return httpx.Response(200, json=fx.bundle_body(nearest()))
        if path == "/v1/service/weather/locations":
            return httpx.Response(200, json=_near_body(*near))
        return httpx.Response(404, json={"detail": "Not Found"})

    return handler


def _resolver_client(fake: _Map) -> KorTravelMapWeatherClient:
    return KorTravelMapWeatherClient(fake.client)


async def _link(session_factory: Any, feature_id: str) -> WeatherLocationLink:
    async with session_factory() as db:
        row = (
            await db.execute(
                select(WeatherLocationLink).where(WeatherLocationLink.feature_id == feature_id)
            )
        ).scalar_one()
        return row


def _no_core_failure() -> dict[str, Any]:
    data = fx.nearest_split_bundle()
    data["forecasts"]["ultra_short"] = fx.forecast_section("ultra_short", "no_data")
    return data


async def test_resolver_builds_direct_path_superset_and_escalates_radius(
    session_factory: Any,
) -> None:
    """대표 = 가장 가까운 측정소, + 그 둘레(5.27 km) 안의 측정소 아닌 위치, + 부분별 source(직접 `/resolve` 상위 집합)."""
    calls: list[httpx.Request] = []
    fake = _Map(_resolver_handler(nearest=_no_core_failure, min_radius_m=50_000, calls=calls))
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    async with session_factory() as db:
        result = await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=_resolver_client(fake)
        )
    # 다른 측정소(airkorea-other-station)와 둘레 밖(kma-grid-far)은 빠진다 — 직접 경로와 같은 규칙.
    assert result == WeatherLocationFound(fx.LOC_AIR, (fx.LOC_AIR, fx.LOC_KMA, fx.LOC_EXT))
    nearest_calls = [r for r in calls if r.url.path.endswith("/nearest")]
    assert [r.url.params["radius_m"] for r in nearest_calls] == ["20000.0", "50000.0"]
    # 해석이 쓰는 부분만 명시해서 묻는다.
    assert nearest_calls[-1].url.params.get_list("sections") == [
        "current",
        "forecasts",
        "daily_summaries",
    ]
    [listing] = [r for r in calls if r.url.path == "/v1/service/weather/locations"]
    assert (listing.url.params["radius_m"], listing.url.params["limit"]) == ("50000.0", "500")

    row = await _link(session_factory, feature_id)
    assert row.stale is False  # 실패한 부분은 daily_summaries(핵심 아님)뿐
    assert row.distance_km == pytest.approx(0.27)
    assert row.measurement_point == {"resolved_via": "kor_travel_map"}

    # 캐시 적중 — Map을 다시 부르지 않는다.
    async with session_factory() as db:
        again = await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=_resolver_client(fake)
        )
    assert again == result
    assert len(calls) == 3


async def test_resolver_without_any_station_anchors_on_the_nearest_location(
    session_factory: Any,
) -> None:
    fake = _Map(
        _resolver_handler(
            nearest=fx.kma_bundle, near=((fx.LOC_KMA, 800.0), ("kma-grid-61-127", 4000.0))
        )
    )
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    async with session_factory() as db:
        result = await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=_resolver_client(fake)
        )
    assert result == WeatherLocationFound(fx.LOC_KMA, (fx.LOC_KMA, "kma-grid-61-127"))


async def test_core_section_failure_marks_stale_with_15_minute_backoff(
    session_factory: Any,
) -> None:
    calls: list[httpx.Request] = []
    fake = _Map(_resolver_handler(calls=calls))  # ultra_short not_loaded = 핵심 부분 실패
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    client = _resolver_client(fake)
    async with session_factory() as db:
        await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=client
        )
        # 15분 안에는 stale 행을 그대로 쓴다 — 재해석 폭주 없음.
        for _ in range(3):
            await resolve_weather_location_via_map(
                db, feature_id=feature_id, lat=_LAT, lon=_LON, client=client
            )
    assert len(calls) == 2
    assert (await _link(session_factory, feature_id)).stale is True

    async with session_factory() as db:
        row = await db.get(WeatherLocationLink, feature_id)
        assert row is not None
        row.resolved_at = datetime.now(UTC) - timedelta(minutes=16)
        await db.commit()
        await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=client
        )
    assert len(calls) == 4


async def test_old_rows_are_re_resolved_after_the_ttl(session_factory: Any) -> None:
    calls: list[httpx.Request] = []
    fake = _Map(_resolver_handler(nearest=_no_core_failure, calls=calls))
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    client = _resolver_client(fake)
    async with session_factory() as db:
        await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=client
        )
        row = await db.get(WeatherLocationLink, feature_id)
        assert row is not None
        row.resolved_at = datetime.now(UTC) - timedelta(days=8)
        await db.commit()
        await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=client
        )
    assert len(calls) == 4
    row = await _link(session_factory, feature_id)
    assert datetime.now(UTC) - row.resolved_at < timedelta(minutes=1)


async def test_paths_do_not_reuse_each_others_rows(session_factory: Any) -> None:
    """플래그를 끄면 직접 경로가 Map 행을 다시 해석하고, 켜면 Map 경로가 직접 경로 행을 다시 해석한다."""
    from app.clients.kor_travel_weather import (
        CoordinateRequestOut,
        LocationOut,
        ResolvedWeatherOut,
    )
    from app.services.weather_location_resolver import resolve_weather_location

    class _Direct:
        def __init__(self) -> None:
            self.calls = 0

        async def resolve(self, *, lat: float, lon: float, radius_km: float | None = None) -> Any:
            self.calls += 1
            location = LocationOut(
                location_id="direct-anchor", name="x", latitude=lat, longitude=lon, enabled=True
            )
            return ResolvedWeatherOut(
                requested=CoordinateRequestOut(latitude=lat, longitude=lon),
                location=location,
                distance_km=0.1,
                source_locations=(location,),
            )

    calls: list[httpx.Request] = []
    fake = _Map(_resolver_handler(nearest=_no_core_failure, calls=calls))
    direct = _Direct()
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    async with session_factory() as db:
        await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=_resolver_client(fake)
        )
    async with session_factory() as db:
        found = await resolve_weather_location(
            db,
            feature_id=feature_id,
            lat=_LAT,
            lon=_LON,
            client=direct,  # type: ignore[arg-type]
        )
    assert found == WeatherLocationFound("direct-anchor", ("direct-anchor",))
    assert direct.calls == 1
    assert (await _link(session_factory, feature_id)).measurement_point is None
    async with session_factory() as db:
        again = await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=_resolver_client(fake)
        )
    assert again.location_id == fx.LOC_AIR  # type: ignore[union-attr]
    assert len([r for r in calls if r.url.path.endswith("/nearest")]) == 2


async def test_concurrent_first_resolve_does_not_conflict(session_factory: Any) -> None:
    """같은 feature의 첫 해석이 두 세션에서 동시에 와도 upsert라 IntegrityError가 없다."""
    fake = _Map(_resolver_handler(nearest=_no_core_failure))
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    client = _resolver_client(fake)
    async with session_factory() as db_a, session_factory() as db_b:
        assert await db_a.get(WeatherLocationLink, feature_id) is None
        assert await db_b.get(WeatherLocationLink, feature_id) is None
        results = await asyncio.gather(
            resolve_weather_location_via_map(
                db_a, feature_id=feature_id, lat=_LAT, lon=_LON, client=client
            ),
            resolve_weather_location_via_map(
                db_b, feature_id=feature_id, lat=_LAT, lon=_LON, client=client
            ),
        )
    assert results[0] == results[1]
    assert (await _link(session_factory, feature_id)).location_id == fx.LOC_AIR


async def test_resolver_no_location_within_100km_is_no_data(session_factory: Any) -> None:
    fake = _Map(lambda r: httpx.Response(404, json=fx.problem_body(404, "NOT_FOUND")))
    feature_id = f"f_{uuid.uuid4().hex[:8]}"
    async with session_factory() as db:
        result = await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=_LAT, lon=_LON, client=_resolver_client(fake)
        )
        assert isinstance(result, WeatherLocationNoData)
        assert await db.get(WeatherLocationLink, feature_id) is None
    assert [r.url.params["radius_m"] for r in fake.weather_requests()] == [
        "20000.0",
        "50000.0",
        "100000.0",
    ]


async def test_resolve_many_runs_misses_concurrently_and_isolates_failures(
    session_factory: Any,
) -> None:
    from app.services.weather_map_resolver import resolve_many_via_map

    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def slow_nearest(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        if request.url.params["lat"].startswith("35"):
            return httpx.Response(503, json=fx.problem_body(503, "WEATHER_STATE_NOT_LOADED"))
        return httpx.Response(200, json=fx.bundle_body(_no_core_failure()))

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/nearest"):
            return await slow_nearest(request)
        return httpx.Response(200, json=_near_body(*_SPLIT_NEAR))

    client = KorTravelMapClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        service_token="svc",
        max_attempts=1,
    )
    coords = {f"fm_{i}_{uuid.uuid4().hex[:6]}": (37.5 + i / 1000, 126.9) for i in range(6)}
    bad = f"fm_bad_{uuid.uuid4().hex[:6]}"
    coords[bad] = (35.1, 129.0)
    async with session_factory() as db:
        results = await resolve_many_via_map(
            db, coords, client=KorTravelMapWeatherClient(client), concurrency=3
        )
    assert 1 < peak <= 3
    assert isinstance(results[bad], Exception)
    assert all(isinstance(results[fid], WeatherLocationFound) for fid in coords if fid != bad)


# ── 단건 카드 ─────────────────────────────────────────────────────────────────────────


async def test_flag_off_card_never_calls_map_weather(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = False
    fake = _Map(_nearest_then_batch())

    class _Direct:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def resolve(self, **kwargs: Any) -> Any:
            self.calls.append("resolve")
            from app.clients.kor_travel_weather import KorTravelWeatherNotFound

            raise KorTravelWeatherNotFound(
                "none", status_code=404, code="HTTP_ERROR", detail="없음"
            )

    direct = _Direct()
    _install(fake, direct)
    resp = await client.get(
        f"/features/f_off_{uuid.uuid4().hex[:6]}/weather", cookies=auth_cookies(verified_user[0])
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["metrics"] == []
    assert fake.weather_requests() == []
    assert direct.calls == ["resolve", "resolve", "resolve"]


async def test_flag_on_card_reads_map_batch_and_alerts_from_weather(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    fake = _Map(_nearest_then_batch(nearest=fx.nearest_split_bundle(), near=_SPLIT_NEAR))
    weather = _Weather(alerts_for=fx.LOC_KMA)
    _install(fake, weather)
    resp = await client.get(
        f"/features/f_on_{uuid.uuid4().hex[:6]}/weather", cookies=auth_cookies(verified_user[0])
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    keys = {(m["metric_key"], m["forecast_style"]) for m in data["metrics"]}
    # 관측(T1H·REH) + 초단기(T1H·RN1) + 단기(TMP·POP) — KMA 위치 묶음 + 특보(advisory).
    assert {("T1H", "observed"), ("REH", "observed"), ("TMP", "short"), ("POP", "short")} <= keys
    assert ("ALERT", "advisory") in keys
    assert set(data["source_styles"]) >= {"observed", "short", "ultra_short", "advisory"}
    assert data["latest_at"] is not None
    # 해석이 고른 source 위치 전체를 한 배치로 읽는다(대표 + 부분별 source).
    assert fake.batch_location_ids() == [[fx.LOC_AIR, fx.LOC_KMA, fx.LOC_EXT]]
    batch_body = json.loads(fake.weather_requests()[-1].content)
    assert batch_body["sections"] == ["current", "forecasts"]
    assert weather.calls == ["markers"]


async def test_flag_on_card_degrades_per_section(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    """관측 부분이 `unavailable`이어도 예보로 카드를 채운다(부분별 강등)."""
    settings.pinvi_kor_travel_map_weather_enabled = True

    def batch(ids: list[str]) -> httpx.Response:
        data = fx.kma_bundle(ids[0])
        data["current"] = fx.current_section("unavailable")
        data["forecasts"]["ultra_short"] = fx.forecast_section("ultra_short", "not_loaded")
        return httpx.Response(200, json=fx.batch_body([data]))

    fake = _Map(_nearest_then_batch(nearest=fx.kma_bundle(), batch=batch))
    _install(fake, None)  # weather 직접 client가 없어도 Map 경로는 동작한다(특보만 빠진다).
    resp = await client.get(
        f"/features/f_deg_{uuid.uuid4().hex[:6]}/weather", cookies=auth_cookies(verified_user[0])
    )
    assert resp.status_code == 200, resp.text
    styles = {m["forecast_style"] for m in resp.json()["data"]["metrics"]}
    assert styles == {"short"}


async def test_flag_on_card_with_map_down_is_empty_card_not_500(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    fake = _Map(
        lambda r: httpx.Response(503, json=fx.problem_body(503, "WEATHER_STATE_UNAVAILABLE"))
    )
    _install(fake, _Weather())
    resp = await client.get(
        f"/features/f_down_{uuid.uuid4().hex[:6]}/weather", cookies=auth_cookies(verified_user[0])
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["metrics"] == []


# ── 지도 marker ───────────────────────────────────────────────────────────────────────

_BBOX = "126.9,37.4,127.1,37.6"


async def test_markers_flag_on_read_map_and_flag_off_does_not(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_weather_map_markers_enabled = True
    body = fx.list_body([fx.location(observations=[fx.observation("T1H", 21.5, unit="deg_c")])])
    fake = _Map(lambda r: httpx.Response(200, json=body))

    class _Nearby:
        def __init__(self) -> None:
            self.calls = 0

        async def nearby(self, **kwargs: Any) -> tuple[Any, ...]:
            self.calls += 1
            return ()

    direct = _Nearby()
    _install(fake, direct)
    url = f"/weather/markers-in-bounds?bbox={_BBOX}&zoom=10"

    settings.pinvi_kor_travel_map_weather_enabled = False
    off = await client.get(url, cookies=auth_cookies(verified_user[0]))
    assert off.status_code == 200, off.text
    assert off.json()["data"]["items"] == []
    assert fake.weather_requests() == []
    assert direct.calls == 1

    settings.pinvi_kor_travel_map_weather_enabled = True
    on = await client.get(url, cookies=auth_cookies(verified_user[0]))
    assert on.status_code == 200, on.text
    [item] = on.json()["data"]["items"]
    assert (item["location_id"], item["temperature_c"], item["condition"]) == (
        fx.LOC_KMA,
        21.5,
        "cloudy",
    )
    assert direct.calls == 1
    assert [r.url.path for r in fake.weather_requests()] == ["/v1/service/weather/locations"]


async def test_markers_flag_on_map_down_is_503(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_weather_map_markers_enabled = True
    settings.pinvi_kor_travel_map_weather_enabled = True
    fake = _Map(
        lambda r: httpx.Response(503, json=fx.problem_body(503, "WEATHER_STATE_NOT_LOADED"))
    )
    _install(fake, None)
    resp = await client.get(
        f"/weather/markers-in-bounds?bbox={_BBOX}&zoom=10", cookies=auth_cookies(verified_user[0])
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WEATHER_SERVICE_UNAVAILABLE"


# ── trip view ────────────────────────────────────────────────────────────────────────


async def _trip_view(
    session_factory: Any,
    *,
    pois: list[tuple[int, date, str]],
    map_client: KorTravelMapClient | None,
    weather_client: Any,
) -> dict[str, Any]:
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
    days = {day_index: eff for day_index, eff, _fid in pois}
    async with session_factory() as db:
        db.add(
            User(
                user_id=user_id,
                email=f"wxmap_{uuid.uuid4().hex[:8]}@pinvi.test",
                status="active",
                email_verified_at=now,
            )
        )
        await db.flush()
        trip = Trip(trip_id=trip_id, owner_user_id=user_id, title="ADR-077 테스트 여행")
        db.add(trip)
        db.add_all([TripDay(trip_id=trip_id, day_index=di, date=eff) for di, eff in days.items()])
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    trip_id=trip_id,
                    day_index=day_index,
                    sort_order=f"a{i:02d}",
                    feature_id=feature_id,
                    feature_snapshot={"title": "저장본", "coord": {"lon": _LON, "lat": _LAT}},
                    added_by_user_id=user_id,
                    currency="KRW",
                )
                for i, (day_index, _eff, feature_id) in enumerate(pois)
            ]
        )
        await db.commit()
        await db.refresh(trip)
        view = await build_trip_view(
            db, trip=trip, kor_travel_map_client=map_client, weather_client=weather_client
        )
    feature_cache.clear()
    return view


def _day(view: dict[str, Any], day_index: int) -> dict[str, Any]:
    return next(d for d in view["days"] if d["day_index"] == day_index)


async def test_trip_view_flag_on_uses_map_batch_for_today_and_past_days(
    session_factory: Any,
) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    today = datetime.now(KST).date()
    yesterday = today - timedelta(days=1)
    fake = _Map(_nearest_then_batch())
    weather = _Weather()
    f_today, f_past = f"ft_{uuid.uuid4().hex[:8]}", f"fp_{uuid.uuid4().hex[:8]}"
    view = await _trip_view(
        session_factory,
        pois=[(1, today, f_today), (2, yesterday, f_past)],
        map_client=fake.client,
        weather_client=weather,
    )

    today_state = _day(view, 1)["weather_by_feature_id"][f_today]
    assert today_state["state"] == "found"
    card = _day(view, 1)["weather_cards"][today_state["card_key"]]
    assert card["metrics"], card

    past_state = _day(view, 2)["weather_by_feature_id"][f_past]
    assert past_state["state"] == "found"
    past_card = _day(view, 2)["weather_cards"][past_state["card_key"]]
    past_keys = {(m["metric_key"], m["timeline_bucket"]) for m in past_card["metrics"]}
    # 지난 날짜는 세 구간 요약(아침)으로 채운다.
    assert ("SLOT_TEMP_MIN", "morning") in past_keys
    assert ("SLOT_TEMP_MAX", "morning") in past_keys
    assert {m["forecast_style"] for m in past_card["metrics"]} >= {"daily_summary"}

    bodies = [
        json.loads(r.content) for r in fake.weather_requests() if r.url.path.endswith("/batch")
    ]
    assert len(bodies) == 1
    assert bodies[0]["sections"] == ["current", "forecasts", "daily_summaries"]
    assert weather.calls == ["markers"]


async def test_trip_view_flag_on_map_batch_down_is_unavailable_not_no_data(
    session_factory: Any,
) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    today = datetime.now(KST).date()

    def batch(ids: list[str]) -> httpx.Response:
        return httpx.Response(503, json=fx.problem_body(503, "WEATHER_STATE_UNAVAILABLE"))

    fake = _Map(_nearest_then_batch(batch=batch))
    feature_id = f"fd_{uuid.uuid4().hex[:8]}"
    view = await _trip_view(
        session_factory, pois=[(1, today, feature_id)], map_client=fake.client, weather_client=None
    )
    assert _day(view, 1)["weather_by_feature_id"][feature_id] == {"state": "unavailable"}


async def test_trip_view_flag_on_all_sections_empty_is_no_data(session_factory: Any) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    future = datetime.now(KST).date() + timedelta(days=20)

    def batch(ids: list[str]) -> httpx.Response:
        empty = fx.bundle(
            ids[0],
            current=fx.current_section("no_data"),
            forecasts={
                s: fx.forecast_section(s, "no_data")
                for s in ("ultra_short", "short", "mid", "external")
            },
        )
        return httpx.Response(200, json=fx.batch_body([empty]))

    nearest = fx.bundle(fx.LOC_KMA, current=fx.current_section("no_data"))
    fake = _Map(_nearest_then_batch(nearest=nearest, batch=batch))
    feature_id = f"fe_{uuid.uuid4().hex[:8]}"
    view = await _trip_view(
        session_factory, pois=[(1, future, feature_id)], map_client=fake.client, weather_client=None
    )
    assert _day(view, 1)["weather_by_feature_id"][feature_id] == {"state": "no_data"}


async def test_trip_view_flag_on_without_map_client_is_unavailable(session_factory: Any) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    feature_id = f"fn_{uuid.uuid4().hex[:8]}"
    view = await _trip_view(
        session_factory,
        pois=[(1, datetime.now(KST).date(), feature_id)],
        map_client=None,
        weather_client=_Weather(),
    )
    assert _day(view, 1)["weather_by_feature_id"][feature_id] == {"state": "unavailable"}


async def test_trip_view_flag_off_never_calls_map_weather(session_factory: Any) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = False
    fake = _Map(_nearest_then_batch())

    class _NoAnchor:
        async def resolve(self, **kwargs: Any) -> Any:
            from app.clients.kor_travel_weather import KorTravelWeatherNotFound

            raise KorTravelWeatherNotFound(
                "none", status_code=404, code="HTTP_ERROR", detail="없음"
            )

    feature_id = f"fo_{uuid.uuid4().hex[:8]}"
    view = await _trip_view(
        session_factory,
        pois=[(1, datetime.now(KST).date(), feature_id)],
        map_client=fake.client,
        weather_client=_NoAnchor(),
    )
    assert _day(view, 1)["weather_by_feature_id"][feature_id] == {"state": "no_data"}
    assert fake.weather_requests() == []


# ── 실패 의미 일치(ADR-077 리뷰 반영) ─────────────────────────────────────────────────


async def test_card_flag_on_without_service_token_is_503_like_missing_weather_client(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    fake = _Map(_nearest_then_batch())
    fake.client._service_token = ""  # Manager가 token을 넘기지 않은 배포
    _install(fake, _Weather())
    resp = await client.get(
        f"/features/f_tok_{uuid.uuid4().hex[:6]}/weather", cookies=auth_cookies(verified_user[0])
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WEATHER_SERVICE_UNAVAILABLE"
    assert fake.weather_requests() == []


async def test_markers_flag_on_current_not_loaded_is_503_not_empty(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_weather_map_markers_enabled = True
    settings.pinvi_kor_travel_map_weather_enabled = True
    # 위치는 있으나 관측 데이터셋을 읽지 못함 — Map은 current_freshness=null·observations 없음으로 준다.
    body = fx.list_body([fx.location()], with_current=False)
    fake = _Map(lambda r: httpx.Response(200, json=body))
    _install(fake, None)
    resp = await client.get(
        f"/weather/markers-in-bounds?bbox={_BBOX}&zoom=10", cookies=auth_cookies(verified_user[0])
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WEATHER_SERVICE_UNAVAILABLE"


async def test_trip_view_flag_on_without_service_token_is_unavailable(session_factory: Any) -> None:
    settings.pinvi_kor_travel_map_weather_enabled = True
    fake = _Map(_nearest_then_batch())
    fake.client._service_token = ""
    feature_id = f"ft_{uuid.uuid4().hex[:8]}"
    view = await _trip_view(
        session_factory,
        pois=[(1, datetime.now(KST).date(), feature_id)],
        map_client=fake.client,
        weather_client=_Weather(),
    )
    assert _day(view, 1)["weather_by_feature_id"][feature_id] == {"state": "unavailable"}
    assert fake.weather_requests() == []
