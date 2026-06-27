"""POI reorder 통합 — LexoRank + COLLATE "C" UNIQUE (SPEC V8 E-6, SPRINT-2 DoD)."""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.asyncio


async def _make_trip(client, cookies) -> str:
    resp = await client.post("/trips", json={"title": "POI 여행"}, cookies=cookies)
    assert resp.status_code == 201
    return resp.json()["data"]["trip_id"]


async def _add_poi(
    client,
    cookies,
    trip_id,
    *,
    sort_order,
    feature_id,
    day_index=1,
    **overrides,
) -> dict:
    resp = await client.post(
        f"/trips/{trip_id}/pois",
        json={
            "day_index": day_index,
            "sort_order": sort_order,
            "feature_id": feature_id,
            **overrides,
        },
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_add_and_reorder_pois(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)

    p1 = await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id="f_1")
    p2 = await _add_poi(client, cookies, trip_id, sort_order="a1", feature_id="f_2")
    p3 = await _add_poi(client, cookies, trip_id, sort_order="a2", feature_id="f_3")

    # p3 을 p1 과 p2 사이로 이동 (a0 < a05 < a1)
    resp = await client.post(
        f"/trips/{trip_id}/pois/reorder",
        json={"moves": [{"poi_id": p3["attachment_id"], "new_sort_order": "a05"}]},
        cookies=cookies,
    )
    assert resp.status_code == 200, resp.text
    updated = {p["attachment_id"]: p for p in resp.json()["data"]}
    assert updated[p3["attachment_id"]]["sort_order"] == "a05"
    assert updated[p3["attachment_id"]]["version"] == 2

    # 사용하지 않은 변수 경고 방지
    assert p1["sort_order"] == "a0"
    assert p2["sort_order"] == "a1"


async def test_sort_order_unique_conflict(client, verified_user, auth_cookies) -> None:
    """같은 (trip, day, sort_order) → COLLATE "C" UNIQUE 위반 → 409."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)

    await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id="f_1")
    # 같은 sort_order 로 두 번째 POI 생성 시도 → UNIQUE 위반
    resp = await client.post(
        f"/trips/{trip_id}/pois",
        json={"day_index": 1, "sort_order": "a0", "feature_id": "f_dup"},
        cookies=cookies,
    )
    assert resp.status_code == 409, resp.text


async def test_poi_budget_fields_round_trip(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)

    created = await _add_poi(
        client,
        cookies,
        trip_id,
        sort_order="b0",
        feature_id="budgeted",
        budget_amount="12000.50",
        actual_amount="9000.00",
        currency="USD",
        user_url="https://example.com/menu",
    )
    assert Decimal(str(created["budget_amount"])) == Decimal("12000.50")
    assert Decimal(str(created["actual_amount"])) == Decimal("9000.00")
    assert created["currency"] == "USD"
    assert created["user_url"] == "https://example.com/menu"

    updated = await client.patch(
        f"/trips/{trip_id}/pois/{created['attachment_id']}",
        headers={"If-Match": "1"},
        json={
            "budget_amount": "15000.00",
            "actual_amount": "11000.00",
            "currency": "KRW",
        },
        cookies=cookies,
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert Decimal(str(data["budget_amount"])) == Decimal("15000.00")
    assert Decimal(str(data["actual_amount"])) == Decimal("11000.00")
    assert data["currency"] == "KRW"
    assert data["version"] == 2

    invalid = await client.post(
        f"/trips/{trip_id}/pois",
        json={
            "day_index": 1,
            "sort_order": "b1",
            "feature_id": "invalid-budget",
            "budget_amount": "-1.00",
        },
        cookies=cookies,
    )
    assert invalid.status_code == 422


async def test_poi_update_stale_version_returns_conflict(
    client, verified_user, auth_cookies
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    created = await _add_poi(client, cookies, trip_id, sort_order="c0", feature_id="conflict")

    first = await client.patch(
        f"/trips/{trip_id}/pois/{created['attachment_id']}",
        headers={"If-Match": "1"},
        json={"user_note": "서버 메모"},
        cookies=cookies,
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["version"] == 2

    stale = await client.patch(
        f"/trips/{trip_id}/pois/{created['attachment_id']}",
        headers={"If-Match": "1"},
        json={"user_note": "내 메모"},
        cookies=cookies,
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert "동시 편집 충돌" in stale.json()["error"]["message"]


async def test_poi_snapshot_fills_empty_trip_primary_region(
    client, verified_user, auth_cookies
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)

    await _add_poi(
        client,
        cookies,
        trip_id,
        sort_order="r0",
        feature_id="regioned",
        feature_snapshot={"name": "광안리", "region": {"sigungu_code": "26110"}},
    )

    trip = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert trip.status_code == 200, trip.text
    data = trip.json()["data"]
    assert data["trip"]["primary_region_code"] == "26110"
    assert data["trip"]["primary_region_source"] == "poi_snapshot"
    assert data["broken_feature_count"] == 0
    assert data["days"][0]["day_index"] == 1
    poi = data["days"][0]["pois"][0]
    assert poi["feature_id"] == "regioned"
    assert poi["title"] == "광안리"
    assert poi["feature"]["name"] == "광안리"


async def test_collate_c_ordering(client, verified_user, auth_cookies, session_factory) -> None:
    """대문자/숫자/소문자 혼합 정렬이 ASCII (COLLATE "C") 순서를 따르는지."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)

    # ASCII: '0'(0x30) < 'A'(0x41) < 'a'(0x61)
    await _add_poi(client, cookies, trip_id, sort_order="0x", feature_id="digit")
    await _add_poi(client, cookies, trip_id, sort_order="Ax", feature_id="upper")
    await _add_poi(client, cookies, trip_id, sort_order="ax", feature_id="lower")

    import uuid

    from sqlalchemy import text

    async with session_factory() as db:
        rows = await db.execute(
            text(
                "SELECT feature_id FROM app.trip_day_pois "
                'WHERE trip_id = :tid ORDER BY sort_order COLLATE "C"'
            ),
            {"tid": uuid.UUID(trip_id)},
        )
        order = [r[0] for r in rows]
    assert order == ["digit", "upper", "lower"]
