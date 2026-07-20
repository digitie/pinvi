"""외부 pick → feature-request 파이프라인 통합 테스트 (ADR-054, T-303).

external_ref POI auto-fire / 전역 dedup / best-effort / 승인 reconciliation / 즉시 연결.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
from app.main import app
from app.models.feature_suggestion import FeatureSuggestion
from app.models.poi import TripDayPoi

pytestmark = pytest.mark.asyncio


class _FakeAdminClient:
    """kor-travel-map admin change API fake — applied 상태 + 고정 feature_id 반환."""

    def __init__(self, feature_id: str = "f_recon_1") -> None:
        self.feature_id = feature_id

    async def create_feature(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "request_id": "krq-1",
            "status": "applied",
            "review_mode": "immediate",
            "action": "create",
        }


async def _make_trip(client: Any, cookies: dict[str, str]) -> str:
    resp = await client.post("/trips", json={"title": "부산 여행"}, cookies=cookies)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["trip_id"])


def _external_poi_payload(
    *, sort_order: str, external_id: str, provider: str = "kakao"
) -> dict[str, Any]:
    return {
        "day_index": 1,
        "sort_order": sort_order,
        "source": provider,
        "external_ref": {
            "provider": provider,
            "external_id": external_id,
            "deep_link_url": f"http://place.map.{provider}.com/{external_id}",
        },
        "feature_snapshot": {"name": "스타벅스 광안리", "coord": {"lon": 129.12, "lat": 35.15}},
    }


async def _suggestion_count(session_factory: Any, external_id: str) -> int:
    async with session_factory() as db:
        return int(
            await db.scalar(
                select(func.count(FeatureSuggestion.request_id)).where(
                    FeatureSuggestion.external_ref["external_id"].astext == external_id
                )
            )
            or 0
        )


async def test_external_pick_stores_ref_and_auto_fires_suggestion(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)

    resp = await client.post(
        f"/trips/{trip_id}/pois",
        json=_external_poi_payload(sort_order="a0", external_id="k100"),
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    # POI가 source/external_ref를 저장하고, 아직 feature에 연결되지 않았다.
    assert data["source"] == "kakao"
    assert data["external_ref"]["external_id"] == "k100"
    assert data["feature_id"] is None

    # best-effort auto-fire로 pending 제안 1건 생성(source=kakao, external_ref).
    async with session_factory() as db:
        suggestion = await db.scalar(
            select(FeatureSuggestion).where(
                FeatureSuggestion.external_ref["external_id"].astext == "k100"
            )
        )
    assert suggestion is not None
    assert suggestion.source == "kakao"
    assert suggestion.status == "pending"
    assert suggestion.name == "스타벅스 광안리"


async def test_global_dedup_across_users(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    from datetime import UTC, datetime

    from app.models.user import User

    user1_id, _ = verified_user
    cookies1 = auth_cookies(user1_id)
    trip1 = await _make_trip(client, cookies1)

    # 두 번째 사용자.
    async with session_factory() as db:
        u2 = User(
            email=f"u2_{uuid.uuid4().hex[:8]}@pinvi.test",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(u2)
        await db.commit()
        await db.refresh(u2)
        user2_id = str(u2.user_id)
    cookies2 = auth_cookies(user2_id)
    trip2 = await _make_trip(client, cookies2)

    # 두 사용자가 같은 외부 장소(k200)를 각자 POI로 추가.
    r1 = await client.post(
        f"/trips/{trip1}/pois",
        json=_external_poi_payload(sort_order="a0", external_id="k200"),
        cookies=cookies1,
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        f"/trips/{trip2}/pois",
        json=_external_poi_payload(sort_order="a0", external_id="k200"),
        cookies=cookies2,
    )
    assert r2.status_code == 201, r2.text

    # 전역 dedup — 제안은 1건만.
    assert await _suggestion_count(session_factory, "k200") == 1


async def test_auto_fire_best_effort_when_snapshot_missing_coord(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)

    payload = _external_poi_payload(sort_order="a0", external_id="k300")
    payload["feature_snapshot"] = {"name": "좌표 없는 장소"}  # coord 누락

    resp = await client.post(f"/trips/{trip_id}/pois", json=payload, cookies=cookies)
    # POI 생성은 성공(auto-fire 실패해도 되돌리지 않음).
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["external_ref"]["external_id"] == "k300"
    # coord가 없어 제안은 만들어지지 않는다.
    assert await _suggestion_count(session_factory, "k300") == 0


async def test_approve_reconciles_linked_pois(
    client: Any,
    session_factory: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)

    # 외부 pick POI → pending 제안 auto-fire.
    poi_resp = await client.post(
        f"/trips/{trip_id}/pois",
        json=_external_poi_payload(sort_order="a0", external_id="k400"),
        cookies=cookies,
    )
    assert poi_resp.status_code == 201, poi_resp.text
    poi_id = poi_resp.json()["data"]["attachment_id"]

    async with session_factory() as db:
        suggestion = await db.scalar(
            select(FeatureSuggestion).where(
                FeatureSuggestion.external_ref["external_id"].astext == "k400"
            )
        )
        assert suggestion is not None
        req_id = suggestion.request_id
        # 승인 권한 admin 사용자.
        from app.models.user import User

        admin = await db.scalar(select(User).where(User.user_id == uuid.UUID(user_id)))
        assert admin is not None
        admin.roles = ["user", "admin"]
        await db.commit()

    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: _FakeAdminClient(
        feature_id="f_k400"
    )
    try:
        resp = await client.post(
            f"/admin/feature-requests/{req_id}/approve",
            json={
                "access_reason": "실재 확인",
                "category": "01070100",
                "marker_color": "P-07",
                "marker_icon": "cafe",
            },
            headers={"X-Request-Id": str(uuid.uuid4())},
            cookies=cookies,
        )
    finally:
        app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["kor_travel_map_ref"]["feature_id"] == "f_k400"
    assert resp.json()["data"]["kor_travel_map_ref"]["reconciled_poi_count"] == 1

    # reconciliation으로 POI가 새 feature_id에 연결됐다.
    async with session_factory() as db:
        poi = await db.scalar(
            select(TripDayPoi).where(TripDayPoi.attachment_id == uuid.UUID(poi_id))
        )
    assert poi is not None
    assert poi.feature_id == "f_k400"


async def test_manual_request_feature_external_ref_global_dedup(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    body = {
        "type": "new_place",
        "kind": "place",
        "title": "네이버 픽 장소",
        "coord": {"lon": 129.1, "lat": 35.1},
        "source": "naver",
        "external_ref": {"provider": "naver", "external_id": "n500"},
    }
    r1 = await client.post("/features/requests", json=body, cookies=cookies)
    assert r1.status_code in (200, 201), r1.text
    r2 = await client.post("/features/requests", json=body, cookies=cookies)
    assert r2.status_code in (200, 201), r2.text
    # 같은 external_ref → 두 번째는 첫 제안을 dedup으로 반환(전역 1건).
    assert r1.json()["data"]["request_id"] == r2.json()["data"]["request_id"]
    assert await _suggestion_count(session_factory, "n500") == 1
