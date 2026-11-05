"""Admin `GET /admin/features/{id}/weather-values` — `kor-travel-weather` location 축
(ADR-068, T-364/T-365).

admin feature 상세(`get_feature_detail`)로 좌표를 얻고
`weather_card.resolve_and_collect_deduped_values` → admin 전용 metric으로 투영한다
(구 `kor_travel_map_admin` 경로는 T-365에서 제거됐다). T-362와 달리 POI 문맥이
없으므로(bare `feature_id`) T-363의 "feature batch와 완전 분리" 원칙은 적용되지
않는다(설계 `admin_weather_values.py` 모듈 docstring).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio

from app.clients.kor_travel_map import KorTravelMapFeatureNotFound
from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
from app.clients.kor_travel_weather import (
    CoordinateRequestOut,
    KorTravelWeatherNotFound,
    LocationOut,
    MeasurementPointOut,
    ResolvedWeatherOut,
    WeatherValueOut,
    get_optional_kor_travel_weather_client,
)
from app.main import app
from app.services.weather_resolve_worker import (
    close_weather_resolve_worker,
    get_weather_resolve_worker,
)

pytestmark = pytest.mark.asyncio

_background_clients: list[Any] = []


@pytest_asyncio.fixture(autouse=True)
async def _close_background_resolvers(session_factory: Any) -> AsyncIterator[None]:
    # session_factory 선행/후행을 보장해 worker를 테스트별 DB engine보다 먼저 종료한다.
    yield
    for weather_client in _background_clients:
        await close_weather_resolve_worker(weather_client)
    _background_clients.clear()


_FEATURE_LAT, _FEATURE_LON = 35.158, 129.163


def _admin_detail(feature_id: str, *, lon: float | None, lat: float | None) -> dict[str, Any]:
    return {
        "feature": {
            "feature_id": feature_id,
            "feature_uuid": feature_id,
            "kind": "place",
            "name": "해운대 카페",
            "category": "01070100",
            "lifecycle_state": "active",
            "publication_state": "published",
            "quality_state": "valid",
            "lon": lon,
            "lat": lat,
            "address": {},
            "detail": {},
            "urls": {},
            "raw_refs": [],
            "row_revision": 1,
            "created_at": "2026-06-11T00:00:00+09:00",
            "updated_at": "2026-06-12T00:00:00+09:00",
        },
        "sources": [],
        "issues": [],
        "overrides": [],
        "state_transitions": [],
        "versions": [],
        "change_requests": [],
        "curations": [],
    }


class _FakeAdminClient:
    """`get_feature_detail`만 구현."""

    def __init__(
        self, *, lon: float | None = _FEATURE_LON, lat: float | None = _FEATURE_LAT
    ) -> None:
        self.lon = lon
        self.lat = lat
        self.calls: dict[str, Any] = {}

    async def get_feature_detail(self, feature_id: str) -> dict[str, Any]:
        self.calls["detail"] = feature_id
        return _admin_detail(feature_id, lon=self.lon, lat=self.lat)


def _weather_value(
    *,
    location_id: str,
    metric_key: str,
    value_number: float | None = None,
    forecast_style: str = "observed",
    weather_domain: str = "weather",
    unit: str | None = "deg_c",
    provider: str = "python-kma-api",
    target_at: datetime,
) -> WeatherValueOut:
    return WeatherValueOut(
        value_id=f"wv-{location_id}-{metric_key}",
        location_id=location_id,
        provider=provider,
        dataset_key="kma_short_forecast",
        weather_domain=weather_domain,
        forecast_style=forecast_style,
        metric_key=metric_key,
        target_at=target_at,
        normalization_version="kma-v1",
        collected_at=datetime.now(UTC),
        source_record_key="sr-1",
        value_number=value_number,
        unit=unit,
        known_at=datetime.now(UTC),
    )


class _FakeWeatherClient:
    """`resolve`/`latest`/`forecast`만 구현 — `KorTravelWeatherClient`와 같은 시그니처."""

    def __init__(
        self,
        *,
        location_id: str = "loc-1",
        no_match: bool = False,
        values_by_location: dict[str, tuple[WeatherValueOut, ...]] | None = None,
    ) -> None:
        self.location_id = location_id
        self.no_match = no_match
        self.values_by_location = values_by_location or {}
        self.calls: dict[str, list[Any]] = {"resolve": [], "latest": [], "forecast": []}

    async def resolve(
        self,
        *,
        lat: float,
        lon: float,
        radius_km: float | None = None,
        read_timeout_seconds: float | None = None,
    ) -> ResolvedWeatherOut:
        self.calls["resolve"].append({"lat": lat, "lon": lon, "radius_km": radius_km})
        if self.no_match:
            raise KorTravelWeatherNotFound(
                "no anchor", status_code=404, code="HTTP_ERROR", detail="없음"
            )
        location = LocationOut(
            location_id=self.location_id, name="해운대", latitude=lat, longitude=lon, enabled=True
        )
        return ResolvedWeatherOut(
            requested=CoordinateRequestOut(latitude=lat, longitude=lon),
            location=location,
            distance_km=0.1,
            measurement_point=MeasurementPointOut(
                provider="python-airkorea-api",
                station_name="해운대",
                latitude=lat,
                longitude=lon,
                distance_km=0.1,
            ),
            source_locations=(location,),
        )

    async def latest(
        self, location_id: str, *, limit: int | None = None
    ) -> tuple[WeatherValueOut, ...]:
        self.calls["latest"].append({"location_id": location_id, "limit": limit})
        return self.values_by_location.get(location_id, ())

    async def forecast(
        self,
        location_id: str,
        *,
        from_: datetime | None = None,
        to: datetime | None = None,
        dataset_key: str | None = None,
        metric_key: str | None = None,
        history: bool = False,
        limit: int | None = None,
    ) -> tuple[WeatherValueOut, ...]:
        self.calls["forecast"].append({"location_id": location_id, "from_": from_, "to": to})
        return ()


def _override(admin_client: Any, weather_client: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: admin_client
    app.dependency_overrides[get_optional_kor_travel_weather_client] = lambda: weather_client
    if weather_client is not None:
        _background_clients.append(weather_client)


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)
    app.dependency_overrides.pop(get_optional_kor_travel_weather_client, None)


async def test_resolves_coord_via_admin_detail_and_builds_values(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    from app.models.user import User

    async with session_factory() as db:
        admin = User(
            email="admin_flag_on@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        admin_id = admin.user_id

    now = datetime.now(UTC)
    admin_client = _FakeAdminClient()
    weather_client = _FakeWeatherClient(
        values_by_location={
            "loc-1": (
                _weather_value(
                    location_id="loc-1", metric_key="TEMP", value_number=21.5, target_at=now
                ),
            )
        }
    )
    _override(admin_client, weather_client)
    try:
        cold = await client.get(
            "/admin/features/f_new_1/weather-values", cookies=auth_cookies(str(admin_id))
        )
        assert cold.status_code == 200, cold.text
        assert cold.json()["data"]["items"] == []
        assert weather_client.calls["latest"] == []
        assert weather_client.calls["forecast"] == []
        await get_weather_resolve_worker(weather_client).drain()
        resp = await client.get(
            "/admin/features/f_new_1/weather-values", cookies=auth_cookies(str(admin_id))
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert admin_client.calls["detail"] == "f_new_1"
    assert "weather" not in admin_client.calls  # 구 경로는 더 이상 호출되지 않는다
    item = data["items"][0]
    assert item["metric_key"] == "T1H"  # TEMP -> T1H(observed) 정규화, T-362와 동일 규칙
    # T-364 핵심 — 대응물 없는 두 필드는 항상 null이다(지어내지 않는다).
    assert item["provider_dataset_id"] is None
    assert item["dataset_display_name"] is None
    assert item["dataset_key"] == "kma_short_forecast"
    assert item["known_at"] is not None
    assert weather_client.calls["resolve"][0]["lat"] == _FEATURE_LAT
    assert weather_client.calls["resolve"][0]["lon"] == _FEATURE_LON


async def test_supports_asof_within_retention(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    """구 경로는 asof를 422로 거절하지만 새 경로는 T-362와 같은 규칙으로 지원한다."""
    from app.models.user import User

    async with session_factory() as db:
        admin = User(
            email="admin_asof@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        admin_id = admin.user_id

    admin_client = _FakeAdminClient()
    weather_client = _FakeWeatherClient()
    _override(admin_client, weather_client)
    try:
        cold = await client.get(
            "/admin/features/f_asof/weather-values",
            params={"asof": datetime.now(UTC).isoformat()},
            cookies=auth_cookies(str(admin_id)),
        )
        assert cold.status_code == 200, cold.text
        assert cold.json()["data"]["items"] == []
        await get_weather_resolve_worker(weather_client).drain()
        resp = await client.get(
            "/admin/features/f_asof/weather-values",
            params={"asof": datetime.now(UTC).isoformat()},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert weather_client.calls["resolve"] != []


async def test_past_asof_beyond_retention_returns_empty_items(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    from app.models.user import User

    async with session_factory() as db:
        admin = User(
            email="admin_past@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        admin_id = admin.user_id

    admin_client = _FakeAdminClient()
    weather_client = _FakeWeatherClient()
    past = datetime.now(UTC) - timedelta(days=10)
    _override(admin_client, weather_client)
    try:
        resp = await client.get(
            "/admin/features/f_past/weather-values",
            params={"asof": past.isoformat()},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []
    assert weather_client.calls["resolve"] == []  # 과거로 판정되면 해석 자체를 시도하지 않는다


async def test_feature_without_coord_returns_empty_items(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    from app.models.user import User

    async with session_factory() as db:
        admin = User(
            email="admin_nocoord@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        admin_id = admin.user_id

    admin_client = _FakeAdminClient(lon=None, lat=None)
    weather_client = _FakeWeatherClient()
    _override(admin_client, weather_client)
    try:
        resp = await client.get(
            "/admin/features/f_no_coord/weather-values", cookies=auth_cookies(str(admin_id))
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []
    assert weather_client.calls["resolve"] == []


async def test_no_anchor_returns_empty_items(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    from app.models.user import User

    async with session_factory() as db:
        admin = User(
            email="admin_noanchor@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        admin_id = admin.user_id

    admin_client = _FakeAdminClient()
    weather_client = _FakeWeatherClient(no_match=True)
    _override(admin_client, weather_client)
    try:
        cold = await client.get(
            "/admin/features/f_no_anchor/weather-values", cookies=auth_cookies(str(admin_id))
        )
        assert cold.status_code == 200, cold.text
        assert cold.json()["data"]["items"] == []
        await get_weather_resolve_worker(weather_client).drain()
        resp = await client.get(
            "/admin/features/f_no_anchor/weather-values", cookies=auth_cookies(str(admin_id))
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []


async def test_weather_service_unavailable_returns_503(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    from app.models.user import User

    async with session_factory() as db:
        admin = User(
            email="admin_unavail@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        admin_id = admin.user_id

    admin_client = _FakeAdminClient()
    _override(admin_client, None)
    try:
        resp = await client.get(
            "/admin/features/f_unavail/weather-values", cookies=auth_cookies(str(admin_id))
        )
    finally:
        _clear()

    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == "WEATHER_SERVICE_UNAVAILABLE"


async def test_feature_not_found_maps_404(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    from app.models.user import User

    async with session_factory() as db:
        admin = User(
            email="admin_404@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        admin_id = admin.user_id

    class _NotFoundAdminClient(_FakeAdminClient):
        async def get_feature_detail(self, feature_id: str) -> dict[str, Any]:
            raise KorTravelMapFeatureNotFound("not found")

    admin_client = _NotFoundAdminClient()
    weather_client = _FakeWeatherClient()
    _override(admin_client, weather_client)
    try:
        resp = await client.get(
            "/admin/features/f_missing/weather-values", cookies=auth_cookies(str(admin_id))
        )
    finally:
        _clear()

    assert resp.status_code == 404, resp.text


@pytest.mark.parametrize("stale", [False, True])
async def test_admin_map_mode_uses_same_source_without_direct_client(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    verified_user: tuple[str, str],
    monkeypatch: Any,
    stale: bool,
) -> None:
    import uuid

    import httpx

    from app.clients.kor_travel_map import KorTravelMapClient, get_optional_kor_travel_map_client
    from app.core.config import settings
    from app.models.user import User
    from tests import weather_map_fixtures as fx

    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(verified_user[0]))
        assert user is not None
        user.roles = ["user", "admin"]
        await db.commit()
    monkeypatch.setattr(settings, "pinvi_kor_travel_map_weather_enabled", True)
    paths: list[str] = []
    bundle = fx.kma_bundle()
    bundle["current"]["freshness"]["stale"] = stale
    for part in bundle["forecasts"].values():
        if part and part.get("freshness"):
            part["freshness"]["stale"] = stale

    def handle(req: httpx.Request) -> httpx.Response:
        paths.append(req.url.path)
        assert req.headers.get("X-Kor-Travel-Map-Service-Token") == "fixture-only"
        if req.url.path.endswith("/nearest"):
            return httpx.Response(200, json=fx.bundle_body(bundle))
        if req.url.path.endswith("/locations"):
            return httpx.Response(200, json=fx.list_body([fx.location()]))
        if req.url.path.endswith("/locations/batch"):
            return httpx.Response(200, json=fx.batch_body([bundle]))
        raise AssertionError(req.url.path)

    short = bundle["forecasts"]["short"]["groups"][0]
    bundle["forecasts"]["short"]["groups"].append(
        fx.forecast_group(
            {"TEMP": [99.0, 99.0, 99.0]}, provider="openweathermap", target_at=short["target_at"]
        )
    )

    class PrivateAdmin(_FakeAdminClient):
        async def get_feature_detail(self, feature_id: str) -> dict[str, Any]:
            result = await super().get_feature_detail(feature_id)
            result["feature"]["publication_state"] = "suppressed"
            return result

    admin = PrivateAdmin()
    _override(admin, None)
    async with httpx.AsyncClient(
        base_url="http://map.test", transport=httpx.MockTransport(handle)
    ) as transport:
        map_client = KorTravelMapClient(transport, service_token="fixture-only", max_attempts=1)
        app.dependency_overrides[get_optional_kor_travel_map_client] = lambda: map_client
        try:
            resp = await client.get(
                "/admin/features/private-feature/weather-values",
                cookies=auth_cookies(verified_user[0]),
            )
        finally:
            _clear()
            app.dependency_overrides.pop(get_optional_kor_travel_map_client, None)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"]
    assert data["is_stale"] is stale
    assert data["latest_at"] is not None
    assert all(item["dataset_key"] is None for item in data["items"])
    assert all(item["provider_dataset_id"] is None for item in data["items"])
    assert all(item["known_at"] is not None for item in data["items"])
    first_target = datetime.fromisoformat(short["target_at"][0])
    aliases = [
        row
        for row in data["items"]
        if row["metric_key"] == "TMP" and datetime.fromisoformat(row["valid_at"]) == first_target
    ]
    assert len(aliases) == 2
    assert {row["provider"] for row in aliases} == {"python-kma-api", "openweathermap"}
    assert admin.calls == {"detail": "private-feature"}
    assert "/v1/service/weather/locations/batch" in paths


async def test_admin_direct_preserves_selected_source_stale(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    verified_user: tuple[str, str],
    monkeypatch: Any,
) -> None:
    import uuid

    from app.core.config import settings
    from app.models.user import User

    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(verified_user[0]))
        assert user is not None
        user.roles = ["user", "admin"]
        await db.commit()
    monkeypatch.setattr(settings, "pinvi_kor_travel_map_weather_enabled", False)
    now = datetime.now(UTC)
    value = _weather_value(location_id="loc-1", metric_key="TEMP", value_number=12, target_at=now)
    weather = _FakeWeatherClient(values_by_location={"loc-1": (replace(value, source_stale=True),)})
    _override(_FakeAdminClient(), weather)
    try:
        cold = await client.get(
            "/admin/features/f-stale/weather-values", cookies=auth_cookies(verified_user[0])
        )
        assert cold.status_code == 200, cold.text
        assert cold.json()["data"]["items"] == []
        assert weather.calls["latest"] == []
        assert weather.calls["forecast"] == []
        await get_weather_resolve_worker(weather).drain()
        resp = await client.get(
            "/admin/features/f-stale/weather-values", cookies=auth_cookies(verified_user[0])
        )
    finally:
        _clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_stale"] is True
    assert resp.json()["data"]["items"][0]["dataset_key"] == "kma_short_forecast"


async def test_admin_map_mode_does_not_fallback_without_map_client(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    verified_user: tuple[str, str],
    monkeypatch: Any,
) -> None:
    import uuid

    from app.clients.kor_travel_map import get_optional_kor_travel_map_client
    from app.core.config import settings
    from app.models.user import User

    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(verified_user[0]))
        assert user is not None
        user.roles = ["user", "admin"]
        await db.commit()
    monkeypatch.setattr(settings, "pinvi_kor_travel_map_weather_enabled", True)
    admin = _FakeAdminClient()
    weather = _FakeWeatherClient()
    _override(admin, weather)
    app.dependency_overrides[get_optional_kor_travel_map_client] = lambda: None
    try:
        resp = await client.get(
            "/admin/features/f-no-map/weather-values", cookies=auth_cookies(verified_user[0])
        )
    finally:
        _clear()
        app.dependency_overrides.pop(get_optional_kor_travel_map_client, None)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "WEATHER_SERVICE_UNAVAILABLE"
    assert admin.calls == {}
    assert weather.calls == {"resolve": [], "latest": [], "forecast": []}


async def test_admin_weather_regular_user_remains_hidden(
    client: Any, auth_cookies: Any, verified_user: tuple[str, str]
) -> None:
    admin = _FakeAdminClient()
    _override(admin, _FakeWeatherClient())
    try:
        resp = await client.get(
            "/admin/features/f-private/weather-values", cookies=auth_cookies(verified_user[0])
        )
    finally:
        _clear()
    assert resp.status_code == 404
    assert admin.calls == {}
