"""#667: 비공개로 숨긴 첨부도 물리 보존 중에는 저장 공간을 차지한다."""

from __future__ import annotations

import uuid

import pytest

from app.models.user import User
from app.services.storage_policy import attachment_bytes_for_trip, attachment_bytes_for_user
from tests.integration.test_pois_reorder import _add_poi, _make_trip
from tests.integration.test_trips_api import _attachment_payload

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("deleted", ["trip", "poi", "attachment"])
async def test_deleted_but_retained_file_cannot_release_user_quota(
    client, verified_user, auth_cookies, session_factory, deleted
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.user_attachment_quota_bytes_override = 100
        await db.commit()
    if deleted == "poi":
        poi = await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id=None)
        base = f"/trips/{trip_id}/pois/{poi['attachment_id']}/attachments"
        purpose = "poi_attachment"
    else:
        base = f"/trips/{trip_id}/attachments"
        purpose = "trip_attachment"
    created = await client.post(
        base, json=_attachment_payload(user_id, byte_size=60, purpose=purpose), cookies=cookies
    )
    assert created.status_code == 201, created.text
    attachment_id = created.json()["data"]["attachment_id"]
    if deleted == "trip":
        response = await client.request(
            "DELETE", f"/trips/{trip_id}", json={"mode": "soft_delete"}, cookies=cookies
        )
    elif deleted == "poi":
        response = await client.delete(f"/trips/{trip_id}/pois/{poi['attachment_id']}", cookies=cookies)
    else:
        response = await client.delete(f"{base}/{attachment_id}", cookies=cookies)
    assert response.status_code == 204, response.text
    files = await client.get("/users/me/files", cookies=cookies)
    assert not any(row["attachment_id"] == attachment_id for row in files.json()["data"]["items"])
    download = await client.get(f"/users/me/files/{attachment_id}/download-url", cookies=cookies)
    assert download.status_code == 404
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 60
        assert await attachment_bytes_for_trip(db, trip_id=uuid.UUID(trip_id)) == 60
    second_trip = await _make_trip(client, cookies)
    denied = await client.post(
        f"/trips/{second_trip}/attachments",
        json=_attachment_payload(user_id, byte_size=50), cookies=cookies,
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "ATTACHMENT_QUOTA_EXCEEDED"


async def test_directly_deleted_file_still_occupies_its_trip_quota(
    client, verified_user, auth_cookies, session_factory
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.trip_attachment_quota_bytes_override = 100
        await db.commit()
    base = f"/trips/{trip_id}/attachments"
    created = await client.post(base, json=_attachment_payload(user_id, byte_size=60), cookies=cookies)
    assert created.status_code == 201, created.text
    response = await client.delete(f"{base}/{created.json()['data']['attachment_id']}", cookies=cookies)
    assert response.status_code == 204
    denied = await client.post(base, json=_attachment_payload(user_id, byte_size=50), cookies=cookies)
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "ATTACHMENT_QUOTA_EXCEEDED"


@pytest.mark.parametrize("deletion_route", ["user", "admin_delete", "admin_move"])
@pytest.mark.parametrize("scope", ["day", "poi"])
async def test_hard_deleted_day_keeps_attachment_charge(
    client, verified_user, auth_cookies, session_factory, scope, deletion_route
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post(
        "/trips",
        json={"title": "retained day", "start_date": "2026-11-10", "end_date": "2026-11-10"},
        cookies=cookies,
    )
    assert created.status_code == 201
    trip_id = created.json()["data"]["trip_id"]
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.user_attachment_quota_bytes_override = 100
        await db.commit()
    if scope == "poi":
        poi = await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id=None)
        path = f"/trips/{trip_id}/pois/{poi['attachment_id']}/attachments"
        purpose = "poi_attachment"
    else:
        path = f"/trips/{trip_id}/days/1/attachments"
        purpose = "trip_day_attachment"
    uploaded = await client.post(
        path, json=_attachment_payload(user_id, byte_size=60, purpose=purpose), cookies=cookies
    )
    assert uploaded.status_code == 201, uploaded.text
    if deletion_route == "user":
        deleted = await client.delete(
            f"/trips/{trip_id}/days/1",
            params={"force": scope == "poi"},
            headers={"If-Match": "1"}, cookies=cookies,
        )
        assert deleted.status_code == 204, deleted.text
    else:
        from app.services.admin_trip_operations import delete_admin_day, move_admin_day

        target = await _make_trip(client, cookies) if deletion_route == "admin_move" else None
        async with session_factory() as db:
            if target:
                await move_admin_day(
                    db, source_trip_id=uuid.UUID(trip_id), day_index=1,
                    target_trip_id=uuid.UUID(target), target_day_index=1,
                    poi_policy="delete", attachment_policy="delete", comment_policy="delete",
                )
            else:
                await delete_admin_day(db, trip_id=uuid.UUID(trip_id), day_index=1)
            await db.commit()
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 60
        assert await attachment_bytes_for_trip(db, trip_id=uuid.UUID(trip_id)) == 60
    library = await client.get("/users/me/files", cookies=cookies)
    assert library.json()["data"]["total"] == 0
    next_trip = await _make_trip(client, cookies)
    denied = await client.post(
        f"/trips/{next_trip}/attachments",
        json=_attachment_payload(user_id, byte_size=50), cookies=cookies,
    )
    assert denied.status_code == 409, denied.text


@pytest.mark.parametrize("mode", ["new", "merge"])
async def test_copy_cannot_add_charged_rows_above_quota_and_rolls_back(
    client, verified_user, auth_cookies, session_factory, mode
):
    from sqlalchemy import func, select

    from app.models.attachment import CuratedPlanAttachment
    from app.models.poi import TripDayPoi
    from app.models.trip import Trip
    from app.models.trip_day import TripDay

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    source = await _make_trip(client, cookies)
    uploaded = await client.post(
        f"/trips/{source}/attachments",
        json=_attachment_payload(user_id, byte_size=60), cookies=cookies,
    )
    assert uploaded.status_code == 201, uploaded.text
    await _add_poi(client, cookies, source, sort_order="a0", feature_id=None)
    target = await _make_trip(client, cookies) if mode == "merge" else None
    if target:
        first = await client.post(
            f"/trips/{target}/attachments",
            json=_attachment_payload(user_id, byte_size=60), cookies=cookies,
        )
        assert first.status_code == 201, first.text
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        if mode == "new":
            user.user_attachment_quota_bytes_override = 100
        else:
            user.trip_attachment_quota_bytes_override = 100
        await db.commit()
        models = (Trip, TripDay, TripDayPoi, CuratedPlanAttachment)
        before = [await db.scalar(select(func.count()).select_from(model)) for model in models]
    result = await client.post(
        f"/trips/{source}/copy",
        json={"scope": "all", "target_trip_id": target}, cookies=cookies,
    )
    assert result.status_code == 409, result.text
    assert result.json()["error"]["code"] == "ATTACHMENT_QUOTA_EXCEEDED"
    async with session_factory() as db:
        assert [await db.scalar(select(func.count()).select_from(model)) for model in models] == before
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == (120 if target else 60)


async def test_concurrent_copies_share_actor_quota_capacity(
    client, verified_user, auth_cookies, session_factory
):
    import asyncio

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    source = await _make_trip(client, cookies)
    first = await client.post(
        f"/trips/{source}/attachments",
        json=_attachment_payload(user_id, byte_size=60), cookies=cookies,
    )
    assert first.status_code == 201
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.user_attachment_quota_bytes_override = 160
        await db.commit()
    replies = await asyncio.gather(*[
        client.post(f"/trips/{source}/copy", json={"scope": "all"}, cookies=cookies)
        for _ in range(2)
    ])
    assert sorted(r.status_code for r in replies) == [201, 409], [r.text for r in replies]
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 120
