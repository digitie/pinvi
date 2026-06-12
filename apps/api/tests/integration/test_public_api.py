"""Public API 통합 테스트 — krtour `/v1/public/*` 소비 표면."""

from __future__ import annotations

from typing import Any

import pytest

from app.clients.krtour_map import KrtourMapUnavailable, get_krtour_map_client
from app.main import app

pytestmark = pytest.mark.asyncio


class _FakeKrtourPublicClient:
    """public.py가 호출하는 krtour data-level 메서드만 구현."""

    def __init__(self) -> None:
        self.calls: dict[str, dict[str, Any]] = {}

    async def public_beaches(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["beaches"] = kwargs
        return {
            "items": [
                {
                    "feature_id": "f_2611000000_p_beach",
                    "display_name": "광안리 해수욕장",
                    "address": {"road": "부산 수영구 광안해변로"},
                    "road_address": "부산 수영구 광안해변로",
                    "sido_code": "26",
                    "sigungu_code": "26110",
                    "lon": 129.118,
                    "lat": 35.155,
                    "source_providers": ["khoa", "kma"],
                    "beach_width_m": 80.0,
                    "beach_length_m": 1400.0,
                    "beach_material": "모래",
                    "upcoming_index_forecasts": [],
                    "updated_at": "2026-06-12T00:00:00+09:00",
                }
            ],
            "next_cursor": "next-beach",
            "total": 1,
        }

    async def public_beach_markers(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["beach_markers"] = kwargs
        return {
            "layer_key": "beach",
            "display_name": "해수욕장",
            "marker_icon": "swimming",
            "marker_color": "P-07",
            "items": [
                {
                    "feature_id": "f_2611000000_p_beach",
                    "name": "광안리 해수욕장",
                    "lon": 129.118,
                    "lat": 35.155,
                    "sigungu_code": "26110",
                }
            ],
        }

    async def get_public_beach(
        self,
        feature_id: str,
        *,
        include_quality: bool = False,
        include_forecast: bool = False,
    ) -> dict[str, Any] | None:
        self.calls["beach_detail"] = {
            "feature_id": feature_id,
            "include_quality": include_quality,
            "include_forecast": include_forecast,
        }
        if feature_id == "missing":
            return None
        return {
            "feature_id": feature_id,
            "display_name": "광안리 해수욕장",
            "address": {},
            "source_providers": ["khoa"],
            "updated_at": "2026-06-12T00:00:00+09:00",
            "upcoming_index_forecasts": [],
        }

    async def public_festivals_monthly(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["festivals"] = kwargs
        return {
            "months": [{"year": 2026, "month": 6, "count": 1}],
            "items": [
                {
                    "feature_id": "f_2611000000_e_festival",
                    "festival_name": "부산 바다축제",
                    "event_status": "scheduled",
                    "event_start_date": "2026-06-15",
                    "event_end_date": "2026-06-18",
                    "venue_name": "광안리 해수욕장",
                    "address": {},
                    "source_providers": ["datagokr"],
                    "updated_at": "2026-06-12T00:00:00+09:00",
                }
            ],
            "next_cursor": None,
            "total": 1,
        }

    async def public_festival_markers(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["festival_markers"] = kwargs
        return {
            "layer_key": "festival",
            "display_name": "축제",
            "marker_icon": "star",
            "marker_color": "P-11",
            "items": [
                {
                    "feature_id": "f_2611000000_e_festival",
                    "name": "부산 바다축제",
                    "lon": 129.118,
                    "lat": 35.155,
                }
            ],
        }

    async def get_public_festival(self, feature_id: str) -> dict[str, Any] | None:
        self.calls["festival_detail"] = {"feature_id": feature_id}
        if feature_id == "missing":
            return None
        return {
            "feature_id": feature_id,
            "festival_name": "부산 바다축제",
            "event_status": "scheduled",
            "address": {},
            "source_providers": ["datagokr"],
            "updated_at": "2026-06-12T00:00:00+09:00",
        }


class _UnavailablePublicClient(_FakeKrtourPublicClient):
    async def public_beaches(self, **kwargs: Any) -> dict[str, Any]:
        raise KrtourMapUnavailable("krtour-map down")


def _override(fake: Any) -> None:
    app.dependency_overrides[get_krtour_map_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_krtour_map_client, None)


async def test_public_beaches_is_unauthenticated_and_maps_meta(client: Any) -> None:
    fake = _FakeKrtourPublicClient()
    _override(fake)
    try:
        resp = await client.get(
            "/public/beaches?sido_code=26&sigungu_code=26110&q=광안리&page_size=20"
            "&include_quality=true&include_forecast=true"
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.headers["Cache-Control"] == "public, max-age=300"
    body = resp.json()
    assert body["data"]["items"][0]["display_name"] == "광안리 해수욕장"
    assert body["data"]["items"][0]["beach_material"] == "모래"
    assert body["meta"] == {
        "cursor": "next-beach",
        "has_more": True,
        "total": 1,
        "page": None,
        "limit": 20,
        "version": None,
    }
    assert fake.calls["beaches"]["q"] == "광안리"
    assert fake.calls["beaches"]["include_quality"] is True


async def test_public_markers_validate_bbox_and_map_items(client: Any) -> None:
    fake = _FakeKrtourPublicClient()
    _override(fake)
    try:
        invalid = await client.get("/public/beaches/map-markers?min_lon=129&min_lat=35")
        resp = await client.get(
            "/public/beaches/map-markers?"
            "min_lon=129&min_lat=35&max_lon=129.2&max_lat=35.2&max_items=100"
        )
    finally:
        _clear()

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["layer_key"] == "beach"
    assert data["items"][0]["name"] == "광안리 해수욕장"
    assert fake.calls["beach_markers"]["max_items"] == 100


async def test_public_festivals_monthly_and_detail(client: Any) -> None:
    fake = _FakeKrtourPublicClient()
    _override(fake)
    try:
        monthly = await client.get("/public/festivals/monthly?year=2026&month=6&page_size=12")
        detail = await client.get("/public/festivals/f_2611000000_e_festival")
        missing = await client.get("/public/festivals/missing")
    finally:
        _clear()

    assert monthly.status_code == 200, monthly.text
    assert monthly.json()["data"]["months"] == [{"year": 2026, "month": 6, "count": 1}]
    assert monthly.json()["data"]["items"][0]["festival_name"] == "부산 바다축제"
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["event_status"] == "scheduled"
    assert missing.status_code == 404


async def test_public_maps_krtour_unavailable_to_503(client: Any) -> None:
    _override(_UnavailablePublicClient())
    try:
        resp = await client.get("/public/beaches")
    finally:
        _clear()

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "FEATURE_SERVICE_UNAVAILABLE"
