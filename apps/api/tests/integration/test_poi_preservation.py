"""POI 보존·정렬·출처·일자 이동 회귀 (#629/#630/#639/#652)."""

from __future__ import annotations

import uuid

import pytest

from app.models.attachment import CuratedPlanAttachment
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.services.storage_policy import attachment_bytes_for_trip, attachment_bytes_for_user
from tests.integration.test_pois_reorder import _add_poi, _make_trip
from tests.integration.test_trips_api import _attachment_payload

pytestmark = pytest.mark.asyncio


async def test_reorder_swaps_repeatedly_without_transient_unique_conflicts(
    client, verified_user, auth_cookies
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    pois = [
        await _add_poi(client, cookies, trip_id, sort_order=rank, feature_id=None)
        for rank in ("a0", "a1", "a2")
    ]
    for iteration, order in enumerate(([2, 0, 1], [0, 1, 2], [2, 0, 1])):
        response = await client.post(
            f"/trips/{trip_id}/pois/reorder",
            json={
                "day_index": 1,
                "moves": [
                    {"poi_id": pois[i]["attachment_id"], "new_sort_order": f"a{rank}"}
                    for rank, i in enumerate(order)
                ],
            },
            cookies=cookies,
        )
        assert response.status_code == 200, response.text
        assert {p["version"] for p in response.json()["data"]} == {iteration + 2}
        detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
        assert [p["poi_id"] for p in detail.json()["data"]["days"][0]["pois"]] == [
            pois[i]["attachment_id"] for i in order
        ]
    invalid = await client.post(
        f"/trips/{trip_id}/pois/reorder",
        json={
            "day_index": 1,
            "moves": [{"poi_id": p["attachment_id"], "new_sort_order": "same"} for p in pois],
        },
        cookies=cookies,
    )
    assert invalid.status_code == 409, invalid.text
    assert not any(s in invalid.text for s in ("sqlalchemy", "asyncpg", "UPDATE", "IntegrityError"))
    # 움직이지 않는 POI의 순위를 재사용해 실제 PG UNIQUE 오류·트랜잭션 rollback을 검증한다.
    db_conflict = await client.post(
        f"/trips/{trip_id}/pois/reorder",
        json={
            "day_index": 1,
            "moves": [{"poi_id": pois[0]["attachment_id"], "new_sort_order": "a0"}],
        },
        cookies=cookies,
    )
    assert db_conflict.status_code == 409, db_conflict.text
    assert not any(
        s in db_conflict.text for s in ("sqlalchemy", "asyncpg", "UPDATE", "IntegrityError")
    )

    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert all("reorder_" not in p["sort_order"] for p in detail.json()["data"]["days"][0]["pois"])


async def test_poi_move_preserves_identity_metadata_and_attachments(
    client, verified_user, auth_cookies, session_factory
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post(
        "/trips",
        json={"title": "이동", "start_date": "2026-11-03", "end_date": "2026-11-04"},
        cookies=cookies,
    )
    trip_id = created.json()["data"]["trip_id"]
    poi = await _add_poi(
        client,
        cookies,
        trip_id,
        sort_order="a0",
        feature_id=None,
        user_note="남겨야 할 메모",
        budget_amount="12000",
        feature_snapshot={"name": "수동 장소", "coord": {"lon": 126.978, "lat": 37.566}},
    )
    assert poi["source"] == "manual"
    await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id=None, day_index=2)
    poi_id = poi["attachment_id"]
    attachment = await client.post(
        f"/trips/{trip_id}/pois/{poi_id}/attachments",
        json=_attachment_payload(user_id, "move.jpg", purpose="poi_attachment"),
        cookies=cookies,
    )
    assert attachment.status_code == 201, attachment.text
    moved = await client.patch(
        f"/trips/{trip_id}/pois/{poi_id}",
        json={"day_index": 2},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert moved.status_code == 200, moved.text
    value = moved.json()["data"]
    assert value["attachment_id"] == poi_id
    assert value["day_index"] == 2
    assert value["sort_order"] > "a0"
    assert value["user_note"] == "남겨야 할 메모"
    assert float(value["budget_amount"]) == 12000
    assert value["rise_set"]["locdate"] == "2026-11-04"
    stale_order = await client.post(
        f"/trips/{trip_id}/pois/reorder",
        json={"day_index": 1, "moves": [{"poi_id": poi_id, "new_sort_order": "0001"}]},
        cookies=cookies,
    )
    assert stale_order.status_code == 409, stale_order.text

    files = await client.get(f"/trips/{trip_id}/pois/{poi_id}/attachments", cookies=cookies)
    assert [x["attachment_id"] for x in files.json()["data"]] == [
        attachment.json()["data"]["attachment_id"]
    ]
    stale = await client.patch(
        f"/trips/{trip_id}/pois/{poi_id}",
        json={"day_index": 1},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert stale.status_code == 409
    missing = await client.patch(
        f"/trips/{trip_id}/pois/{poi_id}",
        json={"day_index": 99},
        headers={"If-Match": "2"},
        cookies=cookies,
    )
    assert missing.status_code == 404
    async with session_factory() as db:
        stored = await db.get(TripDayPoi, uuid.UUID(poi_id))
        assert stored.day_index == 2
        assert stored.version == 2


@pytest.mark.parametrize("delete_parent", ["poi", "trip"])
async def test_deleted_parent_excludes_files_and_quota_without_deleting_objects(
    client, verified_user, auth_cookies, session_factory, delete_parent
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id=None)
    poi_id = poi["attachment_id"]
    payload = _attachment_payload(user_id, "retained.jpg", purpose="poi_attachment")
    response = await client.post(
        f"/trips/{trip_id}/pois/{poi_id}/attachments", json=payload, cookies=cookies
    )
    assert response.status_code == 201, response.text
    attachment_id = response.json()["data"]["attachment_id"]
    async with session_factory() as db:
        assert (
            await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == payload["byte_size"]
        )
    if delete_parent == "poi":
        removed = await client.delete(f"/trips/{trip_id}/pois/{poi_id}", cookies=cookies)
    else:
        removed = await client.request(
            "DELETE", f"/trips/{trip_id}", json={"mode": "soft_delete"}, cookies=cookies
        )
    assert removed.status_code == 204, removed.text
    files = await client.get("/users/me/files", cookies=cookies)
    assert files.status_code == 200, files.text
    assert not any(x["attachment_id"] == attachment_id for x in files.json()["data"]["items"])
    download = await client.get(f"/users/me/files/{attachment_id}/download-url", cookies=cookies)
    assert download.status_code == 404, download.text
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 0
        assert await attachment_bytes_for_trip(db, trip_id=uuid.UUID(trip_id)) == 0
        row = await db.get(CuratedPlanAttachment, uuid.UUID(attachment_id))
        assert row is not None and row.deleted_at is None
        assert row.storage_key == payload["storage_key"]
        # 복원하면 동일 메타데이터와 quota가 돌아온다. 객체 삭제는 하지 않는다.
        parent = await db.get(
            TripDayPoi if delete_parent == "poi" else Trip,
            uuid.UUID(poi_id if delete_parent == "poi" else trip_id),
        )
        parent.deleted_at = None
        if delete_parent == "trip":
            parent.status = "draft"
        await db.commit()
        assert (
            await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == payload["byte_size"]
        )


async def test_viewer_cannot_move_or_mutate_pois(
    client, verified_user, auth_cookies, session_factory
):
    from datetime import UTC, datetime

    from app.models.companion import TripCompanion
    from tests.integration.test_trips_api import _create_verified_user

    user_id, _ = verified_user
    owner = auth_cookies(user_id)
    trip_id = await _make_trip(client, owner)
    poi = await _add_poi(client, owner, trip_id, sort_order="a0", feature_id=None)
    viewer_id = await _create_verified_user(session_factory, "viewer-move@example.com")
    async with session_factory() as db:
        db.add(
            TripCompanion(
                trip_id=uuid.UUID(trip_id),
                user_id=uuid.UUID(viewer_id),
                role="viewer",
                invited_at=datetime.now(UTC),
                joined_at=datetime.now(UTC),
            )
        )
        await db.commit()
    cookies = auth_cookies(viewer_id)
    for method, path, body in [
        ("PATCH", f"/{poi['attachment_id']}", {"day_index": 2}),
        ("DELETE", f"/{poi['attachment_id']}", None),
        ("POST", "", {"day_index": 1, "sort_order": "a1"}),
        (
            "POST",
            "/reorder",
            {"day_index": 1, "moves": [{"poi_id": poi["attachment_id"], "new_sort_order": "a1"}]},
        ),
    ]:
        result = await client.request(
            method,
            f"/trips/{trip_id}/pois{path}",
            json=body,
            headers={"If-Match": "1"},
            cookies=cookies,
        )
        assert result.status_code == 403, result.text


async def test_day_delete_and_poi_move_serialize_without_cascade_loss(
    client, verified_user, auth_cookies, session_factory, monkeypatch
) -> None:
    import asyncio

    from app.services import trip as trip_service
    from app.services.poi import PoiNotFoundError, get_poi, update_poi

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post(
        "/trips",
        json={"title": "이동 삭제 경합", "start_date": "2026-11-03", "end_date": "2026-11-04"},
        cookies=cookies,
    )
    trip_id = uuid.UUID(created.json()["data"]["trip_id"])
    poi = await _add_poi(client, cookies, str(trip_id), sort_order="a0", feature_id=None)
    poi_id = uuid.UUID(poi["attachment_id"])
    started = asyncio.Event()
    release = asyncio.Event()
    original_get_day = trip_service.get_trip_day

    async def paused_get_day(db, **kwargs):
        day = await original_get_day(db, **kwargs)
        started.set()
        await release.wait()
        return day

    monkeypatch.setattr(trip_service, "get_trip_day", paused_get_day)

    async def remove_day():
        async with session_factory() as db:
            return await trip_service.delete_trip_day(
                db, trip_id=trip_id, day_index=2, expected_version=1
            )

    async def move_poi():
        async with session_factory() as db:
            row = await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
            return await update_poi(db, poi=row, expected_version=1, patch={"day_index": 2})

    deletion = asyncio.create_task(remove_day())
    await asyncio.wait_for(started.wait(), 3)
    movement = asyncio.create_task(move_poi())
    try:
        # 삭제가 부모 lock을 가진 동안 이동은 해당 일자를 통과할 수 없다.
        done, _ = await asyncio.wait({movement}, timeout=0.2)
        assert not done
    finally:
        release.set()
    assert await deletion == 0
    with pytest.raises(PoiNotFoundError):
        await movement
    async with session_factory() as db:
        row = await db.get(TripDayPoi, poi_id)
        assert row is not None and row.deleted_at is None and row.day_index == 1
