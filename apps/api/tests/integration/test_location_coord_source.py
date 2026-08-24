"""좌표 출처(`coord_source`) 계약과 그에 걸린 동의 게이트 (T-329).

핵심 주장은 하나다 — **지도에서 고른 점은 개인위치정보가 아니다.** 그래서 동의 게이트는 출처가
`device`일 때만 걸리고, 확인자료는 어느 쪽이든 출처를 함께 적는다. 구분이 없던 시절에는 둘 중
하나만 고를 수 있었다: 다 막아서 지도 기능을 깨뜨리거나, 다 열어서 철회한 사용자의 실제 위치를
받거나.
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


async def _rows(session_factory, user_id: str) -> list[LocationAuditOutbox]:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        result = await db.execute(
            select(LocationAuditOutbox)
            .where(LocationAuditOutbox.user_id == uuid.UUID(user_id))
            .order_by(LocationAuditOutbox.outbox_id)
        )
        return list(result.scalars().all())


# --------------------------------------------------------------------------------------
# 지도 클릭은 동의 없이도 통과한다 — 개인위치정보가 아니기 때문이다
# --------------------------------------------------------------------------------------


async def test_map_pick_reverse_geocode_works_without_location_consent(
    client, session_factory, verified_user, auth_cookies
):  # type: ignore[no-untyped-def]
    """동의를 철회한 사용자도 지도에서 점을 찍어 주소를 볼 수 있어야 한다."""
    user_id, _ = verified_user

    res = await client.get(
        "/geo/reverse",
        params={"lon": 126.9780, "lat": 37.5665},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text

    rows = await _rows(session_factory, user_id)
    assert len(rows) == 1
    assert rows[0].purpose == "reverse_geocode"
    assert rows[0].coord_source == "map_pick"


async def test_map_pick_region_lookup_works_without_location_consent(
    client, session_factory, verified_user, auth_cookies
):  # type: ignore[no-untyped-def]
    user_id, _ = verified_user

    res = await client.get(
        "/regions/covering-point",
        params={"lon": 126.9780, "lat": 37.5665},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text

    rows = await _rows(session_factory, user_id)
    assert len(rows) == 1
    assert rows[0].coord_source == "map_pick"


# --------------------------------------------------------------------------------------
# 단말 위치라고 선언하면 동의가 필요하다
# --------------------------------------------------------------------------------------


async def test_device_coord_requires_location_consent(
    client, session_factory, verified_user, auth_cookies
):  # type: ignore[no-untyped-def]
    """`coord_source=device`는 개인위치정보 수집이다 — 동의가 없으면 403이고 기록도 없다."""
    user_id, _ = verified_user

    res = await client.get(
        "/geo/reverse",
        params={"lon": 126.9780, "lat": 37.5665, "coord_source": "device"},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 403, res.text
    assert res.json()["error"]["code"] == "LOCATION_CONSENT_REQUIRED"
    assert await _rows(session_factory, user_id) == []


async def test_device_coord_is_recorded_as_device_when_consented(
    client, session_factory, verified_user, auth_cookies, grant_location_consent
):  # type: ignore[no-untyped-def]
    user_id, _ = verified_user
    await grant_location_consent(user_id)

    res = await client.get(
        "/regions/within-radius",
        params={"lon": 126.9780, "lat": 37.5665, "radius_km": 2, "coord_source": "device"},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text

    rows = await _rows(session_factory, user_id)
    assert len(rows) == 1
    assert rows[0].coord_source == "device"
    assert rows[0].purpose == "region_radius"


async def test_unknown_coord_source_is_rejected(client, verified_user, auth_cookies):  # type: ignore[no-untyped-def]
    """열린 문자열이 아니라 닫힌 열거다 — 모르는 값을 통과시키면 게이트가 무의미해진다."""
    user_id, _ = verified_user

    res = await client.get(
        "/geo/reverse",
        params={"lon": 126.9780, "lat": 37.5665, "coord_source": "somewhere"},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 422, res.text


# --------------------------------------------------------------------------------------
# 서버가 출처를 고정하는 경로 — 선언을 받지 않는다
# --------------------------------------------------------------------------------------


async def test_nearby_is_always_device_regardless_of_query(
    client, session_factory, verified_user, auth_cookies, grant_location_consent
):  # type: ignore[no-untyped-def]
    """ "내 주변"은 endpoint의 의미상 사용자 위치다. `map_pick`이라 우겨도 `device`로 기록된다."""
    user_id, _ = verified_user
    await grant_location_consent(user_id)

    res = await client.get(
        "/features/nearby",
        params={"lon": 126.9780, "lat": 37.5665, "radius_m": 500, "coord_source": "map_pick"},
        cookies=auth_cookies(user_id),
    )
    assert res.status_code == 200, res.text

    rows = await _rows(session_factory, user_id)
    assert len(rows) == 1
    assert rows[0].coord_source == "device"


# --------------------------------------------------------------------------------------
# 해시 체인 — 컬럼이 늘어도 과거 행의 재계산이 어긋나지 않는다
# --------------------------------------------------------------------------------------


async def test_chain_payload_omits_the_key_when_there_is_no_source(session_factory):  # type: ignore[no-untyped-def]
    """출처 없는 행의 content_hash는 컬럼 추가 **이전과 동일한 바이트**로 계산돼야 한다.

    payload가 `sort_keys=True` canonical JSON이라, `"coord_source": null`을 넣으면 과거 행 전체의
    해시가 어긋나 체인 검증이 무너진다. 키를 생략하는 것이 그 유일한 회피다.
    """
    from app.models.audit import LocationAccessLog
    from app.models.user import User
    from app.services.hash_chain import compute_content_hash
    from app.services.location_audit import append_location_log

    async with session_factory() as db:
        user = User(email=f"src_{uuid.uuid4().hex[:8]}@pinvi.test", status="active")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.user_id

    async with session_factory() as db:
        row = await append_location_log(
            db,
            user_id=user_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("37.5665"),
            lng=Decimal("126.9780"),
            request_id=uuid.uuid4(),
            ip_hash="ab" * 32,
        )
        legacy_payload = {
            "user_id": str(row.user_id),
            "occurred_at": row.occurred_at.isoformat(),
            "endpoint": row.endpoint,
            "purpose": row.purpose,
            # 저장 표현(`numeric(9,6)`)과 같은 6자리로 맞춘다 — 체인 재검증의 결정성 조건이다.
            "lat": str(row.lat.quantize(Decimal("0.000001"))),
            "lng": str(row.lng.quantize(Decimal("0.000001"))),
            "request_id": str(row.request_id),
            "ip_hash": row.ip_hash,
        }
        assert row.content_hash == compute_content_hash(row.prev_hash, legacy_payload)
        assert row.coord_source is None

    async with session_factory() as db:
        sourced = await append_location_log(
            db,
            user_id=user_id,
            endpoint="/geo/reverse",
            purpose="reverse_geocode",
            lat=Decimal("37.5665"),
            lng=Decimal("126.9780"),
            request_id=uuid.uuid4(),
            ip_hash="cd" * 32,
            coord_source="map_pick",
        )
        # 출처가 있는 행은 그 값이 해시에 포함된다 — 사후에 출처만 바꿔치기할 수 없다.
        tampered = {
            "user_id": str(sourced.user_id),
            "occurred_at": sourced.occurred_at.isoformat(),
            "endpoint": sourced.endpoint,
            "purpose": sourced.purpose,
            "lat": str(sourced.lat.quantize(Decimal("0.000001"))),
            "lng": str(sourced.lng.quantize(Decimal("0.000001"))),
            "request_id": str(sourced.request_id),
            "ip_hash": sourced.ip_hash,
            "coord_source": "device",
        }
        assert sourced.content_hash != compute_content_hash(sourced.prev_hash, tampered)
        assert sourced.content_hash == compute_content_hash(
            sourced.prev_hash, {**tampered, "coord_source": "map_pick"}
        )
        assert isinstance(sourced, LocationAccessLog)


# --------------------------------------------------------------------------------------
# 외부 의존
# --------------------------------------------------------------------------------------


class _FakeMapClient:
    async def features_nearby(self, **kwargs: Any) -> dict[str, Any]:
        return {"origin": kwargs, "items": [], "next_cursor": None}


class _FakeGeoClient:
    async def reverse(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "candidates": [
                {"address": "서울 중구", "region": {"region_name": "중구", "sig_cd": "11140"}}
            ],
        }

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
