"""Feature API contract regressions — kor_travel_map REST cutover (T-173/174/176/178).

kor-travel-map HTTP client(`app.clients.kor_travel_map`)를 `app.dependency_overrides`로
fake 주입한다. fake는 client가 envelope를 푼 뒤의 **data-level 셰입**(평면 lon/lat,
items/clusters, found/missing, metrics)을 반환한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.clients.kor_travel_map import KorTravelMapUnavailable, get_kor_travel_map_client
from app.main import app

pytestmark = pytest.mark.asyncio


class _FakeKorTravelMapClient:
    """features.py 가 호출하는 메서드만 구현 — kor_travel_map data-level 셰입 반환."""

    def __init__(self) -> None:
        self.calls: dict[str, dict[str, Any]] = {}

    async def features_in_bounds(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["in_bounds"] = kwargs
        return {
            "items": [
                {
                    "feature_id": "f_1168010100_p_abc",
                    "kind": "place",
                    "name": "광안리 해수욕장",
                    "category": "해수욕장",
                    "lon": 129.118,
                    "lat": 35.155,
                    "marker_color": "P-07",
                    "marker_icon": "swimming",
                    "status": "active",
                }
            ],
            "clusters": [
                {"cluster_key": "11680", "feature_count": 47, "lon": 127.04, "lat": 37.52}
            ],
            "cluster_unit": "sigungu",
        }

    async def features_nearby(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["nearby"] = kwargs
        return {
            "origin": {
                "lon": kwargs["lon"],
                "lat": kwargs["lat"],
                "radius_m": kwargs["radius_m"],
            },
            "items": [
                {
                    "feature_id": "f_x_p_1",
                    "kind": "place",
                    "name": "근처 장소",
                    "category": None,
                    "lon": kwargs["lon"],
                    "lat": kwargs["lat"],
                    "status": "active",
                    "distance_m": 123.4,
                }
            ],
            "next_cursor": None,
        }

    async def search_features(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["search"] = kwargs
        return {"items": [], "next_cursor": None}

    async def get_feature(self, feature_id: str) -> dict[str, Any] | None:
        self.calls["get"] = {"feature_id": feature_id}
        if feature_id == "missing":
            return None
        return {
            "feature_id": feature_id,
            "kind": "place",
            "name": "상세 장소",
            "category": "카페",
            "lon": 129.0,
            "lat": 35.0,
            "address": {"road": "부산 광안로 1"},
            "legal_dong_code": "1168010100",
            "sido_code": "11",
            "sigungu_code": "11680",
            "marker_color": "P-07",
            "marker_icon": "cafe",
            "urls": {"homepage": "https://example.test"},
            "detail": {"phones": ["051-000-0000"]},
            "status": "active",
            "updated_at": "2026-06-10T12:00:00+09:00",
        }

    async def feature_weather(self, feature_id: str, *, asof: Any = None) -> dict[str, Any]:
        self.calls["weather"] = {"feature_id": feature_id, "asof": asof}
        return {
            "feature_id": feature_id,
            "asof": "2026-06-10T12:00:00+09:00",
            "latest_at": "2026-06-10T11:00:00+09:00",
            "is_stale": False,
            "source_styles": ["nowcast", "short"],
            "metrics": [
                {
                    "metric_key": "T1H",
                    "metric_name": "기온",
                    "forecast_style": "nowcast",
                    "value_number": 23.0,
                    "unit": "℃",
                }
            ],
        }

    async def categories(
        self, *, include_counts: bool = False, active_only: bool = False
    ) -> dict[str, Any]:
        self.calls["categories"] = {
            "include_counts": include_counts,
            "active_only": active_only,
        }
        return {
            "include_counts": include_counts,
            "items": [
                {
                    "code": "01070100",
                    "label": "해수욕장",
                    "parent_code": "010701",
                    "depth": 3,
                    "path": ["자연", "해안", "해수욕장"],
                    "maki_icon": "swimming",
                    "is_active": True,
                    "sort_order": 5,
                }
            ],
        }


class _UnavailableClient(_FakeKorTravelMapClient):
    async def features_in_bounds(self, **kwargs: Any) -> dict[str, Any]:
        raise KorTravelMapUnavailable("kor-travel-map down")


def _override(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_client, None)


async def test_in_bounds_maps_kor_travel_map_shape(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    fake = _FakeKorTravelMapClient()
    _override(fake)
    try:
        resp = await client.get(
            "/features/in-bounds?bbox=129.0,35.0,129.2,35.2&zoom=12&kinds=place",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["cluster_unit"] == "sigungu"
    assert data["items"][0]["name"] == "광안리 해수욕장"
    assert data["items"][0]["coord"] == {"lon": 129.118, "lat": 35.155}
    assert data["clusters"][0]["cluster_key"] == "11680"
    assert data["clusters"][0]["coord"] == {"lon": 127.04, "lat": 37.52}
    # client 가 min_lon/.../max_items 로 호출됐는지 (구 limit/bbox tuple 폐기)
    assert fake.calls["in_bounds"]["min_lon"] == 129.0
    assert fake.calls["in_bounds"]["max_items"] == 500


async def test_nearby_uses_lon_lat_and_distance(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    fake = _FakeKorTravelMapClient()
    _override(fake)
    try:
        resp = await client.get(
            "/features/nearby?lon=129.118&lat=35.155&radius_m=5000&kinds=place",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body[0]["coord"] == {"lon": 129.118, "lat": 35.155}
    assert body[0]["distance_m"] == 123.4
    assert fake.calls["nearby"]["lon"] == 129.118
    assert fake.calls["nearby"]["page_size"] == 100


async def test_nearby_rejects_legacy_lng_query(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    _override(_FakeKorTravelMapClient())
    try:
        resp = await client.get(
            "/features/nearby?lng=129.118&lat=35.155&radius_m=5000",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 422


async def test_feature_detail_maps_structured_address(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    _override(_FakeKorTravelMapClient())
    try:
        resp = await client.get("/features/f_1168010100_p_abc", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == "상세 장소"
    assert data["address"] == {"road": "부산 광안로 1"}
    assert data["sigungu_code"] == "11680"
    assert data["urls"] == {"homepage": "https://example.test"}


async def test_feature_detail_returns_404_when_missing(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    _override(_FakeKorTravelMapClient())
    try:
        resp = await client.get("/features/missing", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 404


async def test_weather_maps_flat_metrics(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    fake = _FakeKorTravelMapClient()
    _override(fake)
    try:
        resp = await client.get(
            "/features/f_x_p_1/weather?asof=2026-07-01T23:59:59%2B09:00",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert fake.calls["weather"]["asof"].isoformat() == "2026-07-01T23:59:59+09:00"
    data = resp.json()["data"]
    assert data["is_stale"] is False
    assert data["source_styles"] == ["nowcast", "short"]
    assert data["metrics"][0]["metric_key"] == "T1H"
    assert data["metrics"][0]["value_number"] == 23.0


async def test_in_bounds_returns_503_when_kor_travel_map_unavailable(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    _override(_UnavailableClient())
    try:
        resp = await client.get(
            "/features/in-bounds?bbox=129.0,35.0,129.2,35.2&zoom=12",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "FEATURE_SERVICE_UNAVAILABLE"


async def test_categories_maps_catalog(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _email = verified_user
    fake = _FakeKorTravelMapClient()
    _override(fake)
    try:
        resp = await client.get("/features/categories", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert items[0]["code"] == "01070100"
    assert items[0]["label"] == "해수욕장"
    assert items[0]["maki_icon"] == "swimming"
    assert items[0]["path"] == ["자연", "해안", "해수욕장"]
    assert fake.calls["categories"]["active_only"] is True
