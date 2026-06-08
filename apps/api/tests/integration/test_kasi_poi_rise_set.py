"""POI 생성 시 KASI 출몰시각 상태 row 생성."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _make_trip(client, cookies, *, with_dates: bool) -> str:
    payload = {"title": "KASI 여행"}
    if with_dates:
        payload |= {"start_date": "2026-05-05", "end_date": "2026-05-07"}
    resp = await client.post("/trips", json=payload, cookies=cookies)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["trip_id"]


async def test_create_poi_with_date_and_coord_marks_rise_set_pending_fetch(
    client,
    verified_user,
    auth_cookies,
    session_factory,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies, with_dates=True)

    resp = await client.post(
        f"/trips/{trip_id}/pois",
        json={
            "day_index": 2,
            "sort_order": "a0",
            "feature_id": "f_kasi_ready",
            "feature_snapshot": {"lon": 127.1, "lat": 37.5},
        },
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    poi_data = resp.json()["data"]
    poi_id = poi_data["attachment_id"]
    assert poi_data["rise_set"]["status"] == "pending_fetch"
    assert poi_data["rise_set"]["locdate"] == "2026-05-06"
    assert poi_data["rise_set"]["sunrise_at"] is None
    assert poi_data["rise_set"]["fetched_at"] is None

    async with session_factory() as db:
        row = (
            await db.execute(
                text(
                    "SELECT locdate, longitude, latitude, status "
                    "FROM app.trip_poi_rise_sets WHERE poi_id = :poi_id"
                ),
                {"poi_id": poi_id},
            )
        ).one()

    assert row.locdate == date(2026, 5, 6)
    assert row.longitude == 127.1
    assert row.latitude == 37.5
    assert row.status == "pending_fetch"

    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert detail.status_code == 200, detail.text
    detail_poi = detail.json()["data"]["days"][0]["pois"][0]
    assert detail_poi["poi_id"] == poi_id
    assert detail_poi["rise_set"]["status"] == "pending_fetch"
    assert detail_poi["rise_set"]["locdate"] == "2026-05-06"


async def test_create_poi_without_day_date_marks_rise_set_pending_date(
    client,
    verified_user,
    auth_cookies,
    session_factory,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies, with_dates=False)

    resp = await client.post(
        f"/trips/{trip_id}/pois",
        json={
            "day_index": 1,
            "sort_order": "a0",
            "feature_id": "f_kasi_no_date",
            "feature_snapshot": {"lon": 127.1, "lat": 37.5},
        },
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    poi_data = resp.json()["data"]
    poi_id = poi_data["attachment_id"]
    assert poi_data["rise_set"]["status"] == "pending_date"
    assert poi_data["rise_set"]["locdate"] is None

    async with session_factory() as db:
        row = (
            await db.execute(
                text(
                    "SELECT locdate, longitude, latitude, status FROM app.trip_poi_rise_sets WHERE poi_id = :poi_id"
                ),
                {"poi_id": poi_id},
            )
        ).one()

    assert row.locdate is None
    assert row.longitude is None
    assert row.latitude is None
    assert row.status == "pending_date"
