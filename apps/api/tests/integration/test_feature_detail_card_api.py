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
    """Map user 표면(`FeatureDetailResponse`)을 흉내내는 fake.

    기본 payload에는 `status`가 **없다** — Map 3축 feature state cutover(`1f2bdc3a feat(api):
    complete feature state cutover`)로 user 표면에서 삭제됐고 대체 필드가 없다. `extra`로
    구 스냅샷/오염된 upstream을 재현해 "새어 나오지 않음"을 검사한다.
    """

    def __init__(self, *, extra: dict[str, Any] | None = None) -> None:
        self._extra = extra or {}

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
            "updated_at": "2026-06-10T12:00:00+09:00",
            **self._extra,
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


def _override(*, kakao: Any = None, naver: Any = None, map_extra: Any = None) -> None:
    app.dependency_overrides[get_kor_travel_map_client] = lambda: _FakeMapClient(extra=map_extra)
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
        # Map user 표면에 `status`가 없다(3축 cutover `1f2bdc3a`) → 계약상 남은 필드는 항상 null.
        assert data["status"] is None
    finally:
        _clear()


async def test_detail_card_never_leaks_upstream_status(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    """upstream payload에 `status`가 섞여 있어도 공개 응답으로 새어 나가지 않는다.

    fixture에서 키를 빼는 것만으로는 회귀를 못 잡는다 — `feature_detail.build_detail_card`의
    투영을 되돌려도 없는 키를 읽어 계속 null이 나오기 때문이다. 여기서는 구 스냅샷처럼
    `status`를 일부러 넣고 그래도 null임을 wire 레벨에서 고정한다(되돌리면 red).
    """
    user_id, _ = verified_user
    _override(map_extra={"status": "active"})
    try:
        resp = await client.get("/features/place:1/detail-card", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "status" in data  # web/mobile 계약상 키는 유지된다(제거는 후속 cutover)
        assert data["status"] is None
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
