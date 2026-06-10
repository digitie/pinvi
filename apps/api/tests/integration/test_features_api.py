"""Feature API contract regressions."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


class _NearbyFeatureClient:
    def __init__(self) -> None:
        self.seen: dict[str, Any] = {}

    async def features_nearby(
        self,
        *,
        lon: float,
        lat: float,
        radius_m: int,
        kinds: list[str],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.seen = {
            "lon": lon,
            "lat": lat,
            "radius_m": radius_m,
            "kinds": kinds,
            "limit": limit,
        }
        return [
            {
                "feature_id": "place:nearby",
                "kind": "place",
                "title": "근처 장소",
                "coord": {"longitude": lon, "latitude": lat},
                "marker_color": "P-01",
                "marker_icon": "marker",
            }
        ]


async def test_features_nearby_uses_lon_lat_query(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    from app.etl_bridge import krtour_map

    user_id, _email = verified_user
    fake = _NearbyFeatureClient()
    krtour_map._set_client(fake)
    try:
        resp = await client.get(
            "/features/nearby?lon=129.118&lat=35.155&radius_m=5000&kinds=place",
            cookies=auth_cookies(user_id),
        )
    finally:
        krtour_map._set_client(None)

    assert resp.status_code == 200, resp.text
    assert fake.seen["lon"] == 129.118
    assert fake.seen["lat"] == 35.155
    assert resp.json()["data"][0]["coord"] == {"lon": 129.118, "lat": 35.155}


async def test_features_nearby_rejects_legacy_lng_query(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    from app.etl_bridge import krtour_map

    user_id, _email = verified_user
    krtour_map._set_client(_NearbyFeatureClient())
    try:
        resp = await client.get(
            "/features/nearby?lng=129.118&lat=35.155&radius_m=5000",
            cookies=auth_cookies(user_id),
        )
    finally:
        krtour_map._set_client(None)

    assert resp.status_code == 422
