"""위치 감사 미들웨어가 **실제로 일어난 위치 사용만** 기록하는지 (T-330).

`docs/compliance/lbs-act.md` §3의 확인자료는 "언제 누구의 위치를 무엇에 썼는가"의 증거다.
기록이 실제와 어긋나면 두 방향 모두 손상이다 — 일어난 사용이 빠지면 증거가 없고, 일어나지 않은
사용이 실리면 증거가 거짓이 된다. 이 파일은 양쪽을 각각 고정한다.

미들웨어는 좌표를 **핸들러가 선언한 것**(`request.state.location_audit_coord`)에서만 읽는다.
query string을 추측하지 않는다 — 추측은 핸들러가 무시한 파라미터까지 "사용했다"고 적는다.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.kor_travel_geo import get_kor_travel_geo_client
from app.clients.kor_travel_map import get_kor_travel_map_client
from app.main import app
from app.models.audit import LocationAuditOutbox

pytestmark = pytest.mark.asyncio


async def _outbox_rows(session_factory, user_id: str) -> list[LocationAuditOutbox]:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        result = await db.execute(
            select(LocationAuditOutbox)
            .where(LocationAuditOutbox.user_id == uuid.UUID(user_id))
            .order_by(LocationAuditOutbox.outbox_id)
        )
        return list(result.scalars().all())


# --------------------------------------------------------------------------------------
# 일어난 사용은 반드시 남는다
# --------------------------------------------------------------------------------------


async def test_nearby_records_the_coordinate_the_handler_used(
    client, session_factory, verified_user, auth_cookies, grant_location_consent
):  # type: ignore[no-untyped-def]
    """`/features/nearby`는 사용자 자신의 위치를 쓰므로 좌표가 그대로 확인자료에 남아야 한다."""
    user_id, _ = verified_user
    await grant_location_consent(user_id)

    res = await client.get(
        "/features/nearby",
        params={"lon": 126.9780, "lat": 37.5665, "radius_m": 500},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text

    rows = await _outbox_rows(session_factory, user_id)
    assert len(rows) == 1
    assert rows[0].purpose == "nearby_attractions"
    assert rows[0].endpoint == "/features/nearby"
    assert rows[0].lat == Decimal("37.566500")
    assert rows[0].lng == Decimal("126.978000")


async def test_regions_covering_point_records_the_coordinate(
    client, session_factory, verified_user, auth_cookies, grant_location_consent
):  # type: ignore[no-untyped-def]
    user_id, _ = verified_user
    await grant_location_consent(user_id)

    res = await client.get(
        "/regions/covering-point",
        params={"lon": 126.9780, "lat": 37.5665},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text

    rows = await _outbox_rows(session_factory, user_id)
    assert len(rows) == 1
    assert rows[0].purpose == "region_covering"
    assert rows[0].lat == Decimal("37.566500")


async def test_regions_within_radius_records_the_coordinate(
    client, session_factory, verified_user, auth_cookies, grant_location_consent
):  # type: ignore[no-untyped-def]
    user_id, _ = verified_user
    await grant_location_consent(user_id)

    res = await client.get(
        "/regions/within-radius",
        params={"lon": 126.9780, "lat": 37.5665, "radius_km": 2},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text

    rows = await _outbox_rows(session_factory, user_id)
    assert len(rows) == 1
    assert rows[0].purpose == "region_radius"


# --------------------------------------------------------------------------------------
# 일어나지 않은 사용은 남지 않는다
# --------------------------------------------------------------------------------------


async def test_search_with_only_lat_records_nothing(
    client, session_factory, verified_user, auth_cookies
):  # type: ignore[no-untyped-def]
    """`lat`만으로는 near-me가 성립하지 않는다 — 제3자 제공이 없었으므로 기록도 없어야 한다.

    수정 전에는 `lng=NULL`인 반쪽 행이 `third_party_place_search`로 남았다. 일어나지 않은
    Kakao 제공을 기록하는 거짓 확인자료다.
    """
    user_id, _ = verified_user

    res = await client.get(
        "/search",
        params={"q": "카페", "lat": 37.5665},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text
    assert await _outbox_rows(session_factory, user_id) == []


async def test_search_with_lng_alias_records_nothing(
    client, session_factory, verified_user, auth_cookies
):  # type: ignore[no-untyped-def]
    """핸들러는 `lon`만 받는다. `lng` 별칭은 핸들러가 무시하므로 near-me가 아니다.

    좌표 쌍이 **완전**하기 때문에 "완전성 검사"만으로는 못 막는 케이스다 — 미들웨어가 query를
    추측하지 않아야만 막힌다.
    """
    user_id, _ = verified_user

    res = await client.get(
        "/search",
        params={"q": "카페", "lat": 37.5665, "lng": 126.9780},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text
    assert await _outbox_rows(session_factory, user_id) == []


async def test_in_bounds_never_records_user_location(
    client, session_factory, verified_user, auth_cookies
):  # type: ignore[no-untyped-def]
    """지도 뷰포트는 **사용자의 위치가 아니다**. 좌표 query를 덧붙여도 확인자료가 되지 않는다."""
    user_id, _ = verified_user

    res = await client.get(
        "/features/in-bounds",
        params={
            "bbox": "126.9,37.5,127.0,37.6",
            "zoom": 14,
            "lat": 37.5665,
            "lng": 126.9780,
        },
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text
    assert await _outbox_rows(session_factory, user_id) == []


async def test_unparseable_extra_coord_query_does_not_break_the_response(
    client, session_factory, verified_user, auth_cookies, grant_location_consent
):  # type: ignore[no-untyped-def]
    """`?lng=abc`는 핸들러가 무시하는 파라미터다. 감사 때문에 200이 500이 되어선 안 된다.

    수정 전에는 미들웨어가 이를 `Decimal("abc")`로 파싱하려다 `InvalidOperation`을 던졌고,
    `except ValueError`는 그것을 잡지 못했다(`InvalidOperation`은 `ArithmeticError` 계열이다).
    """
    user_id, _ = verified_user
    await grant_location_consent(user_id)

    res = await client.get(
        "/features/nearby",
        params={"lon": 126.9780, "lat": 37.5665, "radius_m": 500, "lng": "abc"},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text

    rows = await _outbox_rows(session_factory, user_id)
    assert len(rows) == 1
    # 기록된 좌표는 핸들러가 쓴 lon이지, query에 끼어든 쓰레기가 아니다.
    assert rows[0].lng == Decimal("126.978000")


async def test_extra_coord_query_cannot_override_the_handler_coordinate(
    client, session_factory, verified_user, auth_cookies, grant_location_consent
):  # type: ignore[no-untyped-def]
    """`lng` 별칭이 `lon`보다 먼저 읽히던 탓에, 확인자료가 핸들러와 다른 좌표를 적었다."""
    user_id, _ = verified_user
    await grant_location_consent(user_id)

    res = await client.get(
        "/features/nearby",
        params={"lon": 126.9780, "lat": 37.5665, "radius_m": 500, "lng": 999},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text

    rows = await _outbox_rows(session_factory, user_id)
    assert len(rows) == 1
    assert rows[0].lng == Decimal("126.978000")


# --------------------------------------------------------------------------------------
# 외부 의존 — 감사 경로만 보기 위해 상류 응답을 고정한다 (저장소 관례: dependency_overrides)
# --------------------------------------------------------------------------------------


class _FakeMapClient:
    async def features_nearby(self, **kwargs: Any) -> dict[str, Any]:
        return {"origin": kwargs, "items": [], "next_cursor": None}

    async def features_in_bounds(self, **kwargs: Any) -> dict[str, Any]:
        return {"items": [], "clusters": [], "cluster_unit": "sigungu"}

    async def search_features(self, **kwargs: Any) -> dict[str, Any]:
        return {"items": []}


class _FakeGeoClient:
    async def reverse(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "candidates": [
                {"address": "서울 중구", "region": {"region_name": "중구", "sig_cd": "11140"}}
            ],
        }

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        return {"candidates": []}

    async def regions_within_radius(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "center": {"lon": kwargs["lon"], "lat": kwargs["lat"]},
            "radius_km": kwargs.get("radius_km", 3.0),
            "sido": [],
            "sigungu": [{"code": "11140", "name": "중구", "relation": "contains"}],
            "emd": [],
        }


@pytest.fixture(autouse=True)
def _stub_upstreams() -> Iterator[None]:
    app.dependency_overrides[get_kor_travel_map_client] = _FakeMapClient
    app.dependency_overrides[get_kor_travel_geo_client] = _FakeGeoClient
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_kor_travel_map_client, None)
        app.dependency_overrides.pop(get_kor_travel_geo_client, None)
