"""`/geo/*` + `/regions/*` 라우터 통합 테스트 (kor-travel-geo client는 stub 주입)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


class _FakeKorTravelGeoClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def reverse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("reverse", kwargs))
        return {
            "status": "ok",
            "candidates": [
                {
                    "address": "부산 수영구 광안동",
                    "region": {"region_name": "광안동", "sig_cd": "26500"},
                }
            ],
        }

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search", kwargs))
        return {"status": "ok", "total": 1, "candidates": [{"address": "테헤란로"}]}

    async def regions_within_radius(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("regions", kwargs))
        return {
            "status": "ok",
            "center": {"lon": 129.0, "lat": 35.0},
            "radius_km": 2.0,
            "sido": [],
            "sigungu": [{"code": "26500", "name": "수영구", "relation": "overlaps"}],
            "emd": [{"code": "2650053000", "name": "광안동", "relation": "contains"}],
        }

    async def geocode(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("geocode", kwargs))
        return {"status": "ok", "candidates": [{"point": {"x": 129.1, "y": 35.1}}]}


@pytest.fixture
def fake_geo_client() -> Iterator[_FakeKorTravelGeoClient]:
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.main import app

    fake = _FakeKorTravelGeoClient()
    app.dependency_overrides[get_kor_travel_geo_client] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_kor_travel_geo_client, None)


async def test_geo_reverse_returns_candidates(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/geo/reverse?lon=129.118&lat=35.155&radius_m=200",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "ok"
    assert data["candidates"][0]["address"] == "부산 수영구 광안동"
    assert fake_geo_client.calls[0][0] == "reverse"
    assert fake_geo_client.calls[0][1] == {"lon": 129.118, "lat": 35.155, "radius_m": 200}


async def test_regions_within_radius_returns_grouped_levels(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/regions/within-radius?lon=129.0&lat=35.0&radius_km=2.0",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["radius_km"] == 2.0
    assert data["emd"][0]["code"] == "2650053000"
    assert data["emd"][0]["relation"] == "contains"
    assert data["sigungu"][0]["name"] == "수영구"
    # 라우터가 v2 계약(radius_km + levels[]) 그대로 전달하는지 확인.
    assert fake_geo_client.calls[-1] == (
        "regions",
        {"lon": 129.0, "lat": 35.0, "radius_km": 2.0, "levels": ["sigungu", "emd"]},
    )


async def test_geo_reverse_rejects_out_of_korea(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/geo/reverse?lon=10.0&lat=50.0",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 422, resp.text


async def test_geo_requires_auth(client: Any) -> None:
    resp = await client.get("/geo/reverse?lon=129.0&lat=35.0")
    assert resp.status_code == 401


async def test_geo_503_when_client_missing(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    # lifespan이 ASGITransport에서 실행되지 않아 app.state.kor_travel_geo_client = 미설정 → 503.
    user_id, _ = verified_user
    resp = await client.get(
        "/geo/search?query=테헤란로",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "GEOCODING_SERVICE_UNAVAILABLE"


async def test_regions_covering_point_returns_region(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/regions/covering-point?lon=129.118&lat=35.155",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["boundary_level"] == "emd"
    assert data["region"]["region_name"] == "광안동"


async def test_regions_covering_point_404_when_no_region(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.main import app

    class _NoRegion:
        async def reverse(self, **kwargs: Any) -> dict[str, Any]:
            return {"status": "ok", "candidates": [{"address": "주소만"}]}

    app.dependency_overrides[get_kor_travel_geo_client] = lambda: _NoRegion()
    try:
        user_id, _ = verified_user
        resp = await client.get(
            "/regions/covering-point?lon=129.0&lat=35.0",
            cookies=auth_cookies(user_id),
        )
        assert resp.status_code == 404, resp.text
    finally:
        app.dependency_overrides.pop(get_kor_travel_geo_client, None)


class _FakeKorTravelMapClient:
    def __init__(self, *, raise_error: bool = False, item_count: int = 1) -> None:
        self.raise_error = raise_error
        self.item_count = item_count

    async def search_features(self, **kwargs: Any) -> dict[str, Any]:
        if self.raise_error:
            from app.clients.kor_travel_map import KorTravelMapUnavailable

            raise KorTravelMapUnavailable("down")
        items = [
            {"feature_id": f"f_{i}", "name": f"광안 feature {i}", "lon": 129.1, "lat": 35.1}
            for i in range(self.item_count)
        ]
        return {"items": items, "next_cursor": None}


class _FakeKakaoLocalClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def search_keyword(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "documents": [
                {
                    "id": "k1",
                    "place_name": "카카오 카페",
                    "address_name": "부산 수영구",
                    "x": "129.12",
                    "y": "35.15",
                    "place_url": "http://place.map.kakao.com/k1",
                    "phone": "051-000-0000",
                }
            ]
        }


class _FakeNaverLocalClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def search_local(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "items": [
                {
                    "title": "<b>네이버</b> 식당",
                    "address": "부산 수영구",
                    "mapx": "1291200000",
                    "mapy": "351500000",
                    "link": "https://map.naver.com/p/n1",
                }
            ]
        }


def _override_search_clients(
    kor_travel_map: Any,
    kor_travel_geo: Any,
    *,
    kakao: Any = None,
    naver: Any = None,
) -> None:
    from app.clients.kakao_local import get_kakao_local_client
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.clients.kor_travel_map import get_kor_travel_map_client
    from app.clients.naver_local import get_naver_local_client
    from app.main import app

    app.dependency_overrides[get_kor_travel_map_client] = lambda: kor_travel_map
    app.dependency_overrides[get_kor_travel_geo_client] = lambda: kor_travel_geo
    app.dependency_overrides[get_kakao_local_client] = lambda: kakao
    app.dependency_overrides[get_naver_local_client] = lambda: naver


def _clear_search_clients() -> None:
    from app.clients.kakao_local import get_kakao_local_client
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.clients.kor_travel_map import get_kor_travel_map_client
    from app.clients.naver_local import get_naver_local_client
    from app.main import app

    for dep in (
        get_kor_travel_map_client,
        get_kor_travel_geo_client,
        get_kakao_local_client,
        get_naver_local_client,
    ):
        app.dependency_overrides.pop(dep, None)


async def test_unified_search_merges_all_sources(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    _override_search_clients(
        _FakeKorTravelMapClient(),
        _FakeKorTravelGeoClient(),
        kakao=_FakeKakaoLocalClient(),
        naver=_FakeNaverLocalClient(),
    )
    try:
        resp = await client.get("/search?q=광안", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        by_source: dict[str, list[dict[str, Any]]] = {}
        for r in data["results"]:
            by_source.setdefault(r["source"], []).append(r)
        assert by_source["feature"][0]["feature_id"] == "f_0"
        assert by_source["address"][0]["name"] == "테헤란로"
        assert by_source["kakao"][0]["name"] == "카카오 카페"
        assert by_source["naver"][0]["name"] == "네이버 식당"  # <b> strip
        # 정렬: internal(feature/address) → kakao → naver.
        sources = [r["source"] for r in data["results"]]
        assert sources.index("kakao") < sources.index("naver")
        assert sources.index("feature") < sources.index("kakao")
        assert data["degraded_sources"] == []
    finally:
        _clear_search_clients()


async def test_unified_search_internal_first_short_circuits_providers(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    kakao, naver = _FakeKakaoLocalClient(), _FakeNaverLocalClient()
    # 내부 feature 5건 ≥ K(5) → provider 미호출.
    _override_search_clients(
        _FakeKorTravelMapClient(item_count=5),
        _FakeKorTravelGeoClient(),
        kakao=kakao,
        naver=naver,
    )
    try:
        resp = await client.get("/search?q=광안", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert kakao.calls == []  # 호출되지 않음
        assert naver.calls == []
        assert data["degraded_sources"] == []  # 미호출은 degrade 아님
    finally:
        _clear_search_clients()


async def test_unified_search_degrades_on_feature_outage(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    _override_search_clients(
        _FakeKorTravelMapClient(raise_error=True),
        _FakeKorTravelGeoClient(),
        kakao=_FakeKakaoLocalClient(),
        naver=_FakeNaverLocalClient(),
    )
    try:
        resp = await client.get("/search?q=광안", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "features" in data["degraded_sources"]
        assert not any(r["source"] == "feature" for r in data["results"])
        assert any(r["source"] == "address" for r in data["results"])
    finally:
        _clear_search_clients()


async def test_unified_search_degrades_when_providers_absent(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    # kakao/naver client None(비활성/미기동) → hard fail 아니라 degrade.
    _override_search_clients(_FakeKorTravelMapClient(), _FakeKorTravelGeoClient())
    try:
        resp = await client.get("/search?q=광안", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "kakao" in data["degraded_sources"]
        assert "naver" in data["degraded_sources"]
        assert any(r["source"] == "feature" for r in data["results"])
    finally:
        _clear_search_clients()


async def test_unified_search_near_me_passes_coord_to_kakao_only(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    kakao = _FakeKakaoLocalClient()
    _override_search_clients(
        _FakeKorTravelMapClient(),
        _FakeKorTravelGeoClient(),
        kakao=kakao,
        naver=_FakeNaverLocalClient(),
    )
    try:
        resp = await client.get("/search?q=카페&lat=37.5&lon=127.0", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        # 좌표가 Kakao에 x=lon, y=lat로 전달된다(Naver는 좌표 파라미터 없음).
        assert kakao.calls[0]["x"] == 127.0
        assert kakao.calls[0]["y"] == 37.5
    finally:
        _clear_search_clients()


async def _search_audit_rows(session_factory: Any) -> list[Any]:
    from sqlalchemy import select

    from app.models.audit import LocationAuditOutbox

    async with session_factory() as db:
        return list(
            (
                await db.execute(
                    select(LocationAuditOutbox).where(LocationAuditOutbox.endpoint == "/search")
                )
            ).scalars()
        )


async def test_unified_search_keyword_only_not_audited(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    """좌표 없는 키워드 검색은 위치정보 제3자 제공이 아니므로 감사 기록을 남기지 않는다(§9)."""
    user_id, _ = verified_user
    _override_search_clients(
        _FakeKorTravelMapClient(),
        _FakeKorTravelGeoClient(),
        kakao=_FakeKakaoLocalClient(),
        naver=_FakeNaverLocalClient(),
    )
    try:
        resp = await client.get("/search?q=카페", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        assert await _search_audit_rows(session_factory) == []
    finally:
        _clear_search_clients()


async def test_unified_search_near_me_disclosure_is_audited(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    """실제로 Kakao에 좌표를 제공하면 third_party_place_search 감사 기록이 남는다."""
    user_id, _ = verified_user
    _override_search_clients(
        _FakeKorTravelMapClient(),
        _FakeKorTravelGeoClient(),
        kakao=_FakeKakaoLocalClient(),
        naver=_FakeNaverLocalClient(),
    )
    try:
        resp = await client.get("/search?q=카페&lat=37.5&lon=127.0", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        rows = await _search_audit_rows(session_factory)
        assert len(rows) == 1
        assert rows[0].purpose == "third_party_place_search"
        assert rows[0].lat is not None and rows[0].lng is not None
    finally:
        _clear_search_clients()


async def test_unified_search_near_me_short_circuit_not_audited(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    """near-me라도 내부 결과 ≥ K로 Kakao를 호출하지 않으면 좌표는 제공되지 않아 감사도 없다."""
    user_id, _ = verified_user
    kakao = _FakeKakaoLocalClient()
    _override_search_clients(
        _FakeKorTravelMapClient(item_count=5),  # ≥ K → short-circuit
        _FakeKorTravelGeoClient(),
        kakao=kakao,
        naver=_FakeNaverLocalClient(),
    )
    try:
        resp = await client.get("/search?q=카페&lat=37.5&lon=127.0", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        assert kakao.calls == []  # 좌표가 Kakao에 전달되지 않음
        assert await _search_audit_rows(session_factory) == []
    finally:
        _clear_search_clients()
