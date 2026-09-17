"""Admin `GET /admin/features/{id}/weather-values` — `kor-travel-weather` 전환 flag
(T-364/P5, ADR-068).

flag가 꺼져 있으면(기본값) 기존 `kor_travel_map_admin` 경로를 그대로 쓴다는 것은
`test_admin_features_api.py`의 기존 weather-values 테스트가 이미 고정한다. 여기서는
flag on일 때의 **새 경로**를 검증한다: admin feature 상세(`get_feature_detail`)로
좌표를 얻고 `weather_card.resolve_and_collect_deduped_values` → admin 전용 metric으로
투영한다. T-362와 달리 POI 문맥이 없으므로(bare `feature_id`) T-363의 "feature batch와
완전 분리" 원칙은 적용되지 않는다(설계 `admin_weather_values.py` 모듈 docstring).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

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
from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.asyncio

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
    """`get_feature_detail`/`get_feature_weather`만 구현."""

    def __init__(
        self, *, lon: float | None = _FEATURE_LON, lat: float | None = _FEATURE_LAT
    ) -> None:
        self.lon = lon
        self.lat = lat
        self.calls: dict[str, Any] = {}

    async def get_feature_detail(self, feature_id: str) -> dict[str, Any]:
        self.calls["detail"] = feature_id
        return _admin_detail(feature_id, lon=self.lon, lat=self.lat)

    async def get_feature_weather(self, feature_id: str) -> dict[str, Any]:
        """flag off 테스트 전용 — 구 경로가 여전히 호출되는지 확인하는 용도."""
        self.calls["weather"] = feature_id
        return {
            "feature_id": feature_id,
            "selected_at": "2026-06-12T10:00:00+09:00",
            "is_stale": False,
            "source_styles": ["nowcast"],
            "metrics": [
                {
                    "metric_key": "T1H",
                    "forecast_style": "nowcast",
                    "provider_dataset_id": 41,
                    "dataset_key": "kma_vilage_forecast",
                    "dataset_display_name": "기상청 단기예보",
                    "known_at": "2026-06-12T09:35:00+09:00",
                    "value_number": 23.0,
                }
            ],
        }


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
        self, *, lat: float, lon: float, radius_km: float | None = None
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


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)
    app.dependency_overrides.pop(get_optional_kor_travel_weather_client, None)


@pytest.fixture(autouse=True)
def _reset_flag() -> Any:
    original = settings.pinvi_kor_travel_weather_admin_enabled
    yield
    settings.pinvi_kor_travel_weather_admin_enabled = original


async def test_flag_off_uses_kor_travel_map_admin_and_ignores_weather_client(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    from app.models.user import User

    async with session_factory() as db:
        admin = User(
            email="admin_flag_off@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        admin_id = admin.user_id

    settings.pinvi_kor_travel_weather_admin_enabled = False
    admin_client = _FakeAdminClient()
    weather_client = _FakeWeatherClient()
    _override(admin_client, weather_client)
    try:
        resp = await client.get(
            "/admin/features/f_flag_off/weather-values", cookies=auth_cookies(str(admin_id))
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert admin_client.calls["weather"] == "f_flag_off"
    assert "detail" not in admin_client.calls
    assert weather_client.calls["resolve"] == []


async def test_flag_on_resolves_coord_via_admin_detail_and_builds_values(
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

    settings.pinvi_kor_travel_weather_admin_enabled = True
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


async def test_flag_on_supports_asof_within_retention(
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

    settings.pinvi_kor_travel_weather_admin_enabled = True
    admin_client = _FakeAdminClient()
    weather_client = _FakeWeatherClient()
    _override(admin_client, weather_client)
    try:
        resp = await client.get(
            "/admin/features/f_asof/weather-values",
            params={"asof": datetime.now(UTC).isoformat()},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert weather_client.calls["resolve"] != []


async def test_flag_on_past_asof_beyond_retention_returns_empty_items(
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

    settings.pinvi_kor_travel_weather_admin_enabled = True
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


async def test_flag_on_feature_without_coord_returns_empty_items(
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

    settings.pinvi_kor_travel_weather_admin_enabled = True
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


async def test_flag_on_no_anchor_returns_empty_items(
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

    settings.pinvi_kor_travel_weather_admin_enabled = True
    admin_client = _FakeAdminClient()
    weather_client = _FakeWeatherClient(no_match=True)
    _override(admin_client, weather_client)
    try:
        resp = await client.get(
            "/admin/features/f_no_anchor/weather-values", cookies=auth_cookies(str(admin_id))
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["items"] == []


async def test_flag_on_weather_service_unavailable_returns_503(
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

    settings.pinvi_kor_travel_weather_admin_enabled = True
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


async def test_flag_on_feature_not_found_maps_404(
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

    settings.pinvi_kor_travel_weather_admin_enabled = True
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
