"""Feature API contract regressions — kor_travel_map REST cutover (T-173/174/176/178).

kor-travel-map HTTP client(`app.clients.kor_travel_map`)를 `app.dependency_overrides`로
fake 주입한다. fake는 client가 envelope를 푼 뒤의 **data-level 셰입**(평면 lon/lat,
items/clusters, found/missing, metrics)을 반환한다.
"""

from __future__ import annotations

from datetime import timedelta
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
            "updated_at": "2026-06-10T12:00:00+09:00",
        }

    async def feature_weather(
        self, feature_id: str, *, asof: Any = None, known_at: Any = None
    ) -> dict[str, Any]:
        # 시그니처는 실제 client(`clients/kor_travel_map.py feature_weather`)와 같아야 한다 —
        # kwarg가 빠져 있으면 라우터가 새 인자를 넘기기 시작해도 fake에서만 TypeError로 늦게 터진다.
        self.calls["weather"] = {"feature_id": feature_id, "asof": asof, "known_at": known_at}
        # Map bitemporal cutover(`6650aa71`) 이후 카드에는 `asof`가 없고 `selected_at`이 있다.
        return {
            "feature_id": feature_id,
            "selected_at": "2026-06-10T12:00:00+09:00",
            "refresh_after": "2026-06-10T13:00:00+09:00",
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

    async def categories(self, *, include_counts: bool = False) -> dict[str, Any]:
        # 시그니처는 실제 client와 같다 — Map `/v1/categories`는 `include_counts` 하나만
        # 받는다(`active_only`는 T-VN-04 F-1에서 삭제). `active_only`는 라우터가 응답
        # `is_active`로 직접 거른다.
        self.calls["categories"] = {"include_counts": include_counts}
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
                },
                {
                    "code": "99990000",
                    "label": "폐기 카테고리",
                    "parent_code": None,
                    "depth": 1,
                    "path": ["폐기 카테고리"],
                    "maki_icon": "marker",
                    "is_active": False,
                    "sort_order": 999,
                },
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
    # Map 3축 cutover(`1f2bdc3a`)로 사라진 `status`는 공개 응답 키에도 없다(T-VN-42).
    assert "status" not in data["items"][0]
    assert data["clusters"][0]["cluster_key"] == "11680"
    assert data["clusters"][0]["coord"] == {"lon": 127.04, "lat": 37.52}
    # client 가 min_lon/.../max_items 로 호출됐는지 (구 limit/bbox tuple 폐기)
    assert fake.calls["in_bounds"]["min_lon"] == 129.0
    assert fake.calls["in_bounds"]["max_items"] == 500


async def test_nearby_uses_lon_lat_and_distance(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    grant_location_consent: Any,
) -> None:
    user_id, _email = verified_user
    # 좌표 endpoint는 위치 동의를 요구한다(T-327).
    await grant_location_consent(user_id)
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
    assert "status" not in body[0]
    assert fake.calls["nearby"]["lon"] == 129.118
    assert fake.calls["nearby"]["page_size"] == 100


async def test_nearby_rejects_legacy_lng_query(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    grant_location_consent: Any,
) -> None:
    user_id, _email = verified_user
    # 좌표 endpoint는 위치 동의를 요구한다(T-327).
    await grant_location_consent(user_id)
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
    assert "status" not in data


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
    # Pinvi 공개 필드 `asof`의 소스는 Map `selected_at`이다(Map `6650aa71`).
    assert data["asof"] == "2026-06-10T12:00:00+09:00"
    assert data["is_stale"] is False
    assert data["source_styles"] == ["nowcast", "short"]
    assert data["metrics"][0]["metric_key"] == "T1H"
    assert data["metrics"][0]["value_number"] == 23.0
    # knowledge time은 라우터가 넘기지 않는다 — client가 "지금"을 채운다(client docstring 참조).
    assert fake.calls["weather"]["known_at"] is None


async def test_weather_naive_asof_is_read_as_kst_not_utc(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    """offset 없는 `?asof=`는 KST로 해석한다 — UTC로 읽으면 9시간 어긋난 시점이 조용히 돌아온다.

    transport는 naive를 거절하므로(`clients/kor_travel_map.py _require_aware_datetime`)
    보정은 시간대 의미를 아는 이 경계 한 곳에서만 일어난다(`features.py normalize_asof_query`).
    """
    user_id, _email = verified_user
    fake = _FakeKorTravelMapClient()
    _override(fake)
    try:
        resp = await client.get(
            "/features/f_x_p_1/weather?asof=2026-07-01T23:59:59",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    passed = fake.calls["weather"]["asof"]
    assert passed.utcoffset() == timedelta(hours=9)
    assert passed.isoformat() == "2026-07-01T23:59:59+09:00"


async def test_weather_aware_asof_keeps_caller_offset(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    """명시된 offset은 덮어쓰지 않는다(`Z`도 그대로 UTC로 나간다)."""
    user_id, _email = verified_user
    fake = _FakeKorTravelMapClient()
    _override(fake)
    try:
        resp = await client.get(
            "/features/f_x_p_1/weather?asof=2026-07-01T23:59:59Z",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert fake.calls["weather"]["asof"].utcoffset() == timedelta(0)


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
    # 기본 `active_only=true`는 **Pinvi가** 적용한다 — upstream은 그 query를 더는 받지 않는다.
    assert [item["code"] for item in items] == ["01070100"]
    assert fake.calls["categories"] == {"include_counts": False}


async def test_categories_active_only_is_applied_locally_not_delegated_upstream(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    """`active_only`는 Pinvi가 `is_active`로 거른다 — 상류로 넘기면 조용히 버려진다.

    Map `/v1/categories`가 선언하는 query는 `include_counts` 하나뿐이고(T-VN-04 F-1에서
    `active_only` 삭제), FastAPI는 모르는 query를 422가 아니라 **조용히 버린다**. 그래서
    예전처럼 위임하면 `active_only=true`가 전량 응답을 돌려주면서 필터가 걸린 척했다.
    여기서는 (a) upstream 요청에 그 query가 없고, (b) `true/false`가 실제로 다른 목록을
    만든다는 것을 함께 고정한다.
    """
    user_id, _email = verified_user
    fake = _FakeKorTravelMapClient()
    _override(fake)
    try:
        active = await client.get(
            "/features/categories?active_only=true", cookies=auth_cookies(user_id)
        )
        every = await client.get(
            "/features/categories?active_only=false", cookies=auth_cookies(user_id)
        )
    finally:
        _clear()

    assert active.status_code == 200, active.text
    assert every.status_code == 200, every.text
    assert [item["code"] for item in active.json()["data"]] == ["01070100"]
    assert [item["code"] for item in every.json()["data"]] == ["01070100", "99990000"]
    # 어느 쪽이든 upstream에는 `active_only`가 나가지 않는다(fake 시그니처가 실제 client와
    # 같으므로 라우터가 다시 위임하면 TypeError로 즉시 red가 된다).
    assert fake.calls["categories"] == {"include_counts": False}
