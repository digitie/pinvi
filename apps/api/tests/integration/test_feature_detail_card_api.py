"""`GET /features/{id}/detail-card` 통합 테스트 — kind별 투영 + 옵트인 enrichment(ADR-056)."""

from __future__ import annotations

from typing import Any

import pytest

from app.clients.kakao_local import get_kakao_local_client
from app.clients.kor_travel_map import get_kor_travel_map_client
from app.clients.naver_local import get_naver_local_client
from app.main import app

pytestmark = pytest.mark.asyncio


class _FakeMapClient:
    async def get_feature(self, feature_id: str) -> dict[str, Any] | None:
        if feature_id == "missing":
            return None
        return {
            "feature_id": feature_id,
            "kind": "place",
            "name": "스타벅스 광안리",
            "category": "카페",
            "lon": 129.12,
            "lat": 35.15,
            "address": {"road": "부산 광안로 1"},
            "marker_color": "P-07",
            "marker_icon": "cafe",
            "urls": {"homepage": "https://sb.example"},
            "detail": {"phone": "051-000-0000"},
            "status": "active",
            "updated_at": "2026-06-10T12:00:00+09:00",
        }


class _FakeKakao:
    async def search_keyword(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "documents": [
                {
                    "id": "k1",
                    "place_name": "스타벅스 광안리점",
                    "address_name": "부산 수영구",
                    "x": "129.1201",
                    "y": "35.1501",
                    "phone": "051-111-2222",
                    "place_url": "http://place.map.kakao.com/k1",
                }
            ]
        }


def _override(*, kakao: Any = None, naver: Any = None) -> None:
    app.dependency_overrides[get_kor_travel_map_client] = lambda: _FakeMapClient()
    app.dependency_overrides[get_kakao_local_client] = lambda: kakao
    app.dependency_overrides[get_naver_local_client] = lambda: naver


def _clear() -> None:
    for dep in (get_kor_travel_map_client, get_kakao_local_client, get_naver_local_client):
        app.dependency_overrides.pop(dep, None)


async def test_detail_card_projects_place_without_providers(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    _override()
    try:
        resp = await client.get("/features/place:1/detail-card", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["kind"] == "place"
        assert data["address_line"] == "부산 광안로 1"
        assert data["phone"] == "051-000-0000"
        assert data["homepage_url"] == "https://sb.example"
        # 기본은 외부 호출 없음.
        assert data["enrichment"] == []
        assert data["degraded_providers"] == []
        # 원본 불투명 dict는 노출하지 않는다.
        assert "detail" not in data
        assert "urls" not in data
    finally:
        _clear()


async def test_detail_card_opt_in_enrichment_matches(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    _override(kakao=_FakeKakao())
    try:
        resp = await client.get(
            "/features/place:1/detail-card?providers=kakao", cookies=auth_cookies(user_id)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert len(data["enrichment"]) == 1
        row = data["enrichment"][0]
        assert row["provider"] == "kakao"
        assert row["matched"] is True
        assert row["phone"] == "051-111-2222"
        assert row["provider_url"] == "http://place.map.kakao.com/k1"
    finally:
        _clear()


async def test_detail_card_degrades_when_provider_absent(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    # kakao/naver client 미주입(None) → degrade.
    _override()
    try:
        resp = await client.get(
            "/features/place:1/detail-card?providers=kakao,naver", cookies=auth_cookies(user_id)
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "kakao" in data["degraded_providers"]
        assert "naver" in data["degraded_providers"]
        assert data["enrichment"] == []
    finally:
        _clear()


async def test_detail_card_404_when_missing(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    _override()
    try:
        resp = await client.get("/features/missing/detail-card", cookies=auth_cookies(user_id))
        assert resp.status_code == 404, resp.text
    finally:
        _clear()
