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
        response = await client.delete(
            f"/trips/{trip_id}/pois/{poi['attachment_id']}", cookies=cookies
        )
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
        json=_attachment_payload(user_id, byte_size=50),
        cookies=cookies,
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
    created = await client.post(
        base, json=_attachment_payload(user_id, byte_size=60), cookies=cookies
    )
    assert created.status_code == 201, created.text
    response = await client.delete(
        f"{base}/{created.json()['data']['attachment_id']}", cookies=cookies
    )
    assert response.status_code == 204
    denied = await client.post(
        base, json=_attachment_payload(user_id, byte_size=50), cookies=cookies
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "ATTACHMENT_QUOTA_EXCEEDED"


@pytest.mark.parametrize("deletion_route", ["user", "admin_delete", "admin_move"])
@pytest.mark.parametrize("scope", ["day", "poi", "deleted_poi"])
@pytest.mark.parametrize("held", [False, True])
async def test_hard_deleted_day_keeps_attachment_charge(
    client, verified_user, auth_cookies, session_factory, scope, deletion_route, held, monkeypatch
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
    if scope != "day":
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
    if held:
        from datetime import UTC, datetime

        from app.models.attachment import CuratedPlanAttachment

        async with session_factory() as db:
            row = await db.get(
                CuratedPlanAttachment, uuid.UUID(uploaded.json()["data"]["attachment_id"])
            )
            row.deleted_at = datetime.now(UTC)
            row.moderation_hold = True
            await db.commit()
    if scope == "deleted_poi":
        removed = await client.delete(
            f"/trips/{trip_id}/pois/{poi['attachment_id']}", cookies=cookies
        )
        assert removed.status_code == 204
    if deletion_route == "user":
        deleted = await client.delete(
            f"/trips/{trip_id}/days/1",
            params={"force": scope == "poi"},
            headers={"If-Match": "1"},
            cookies=cookies,
        )
        assert deleted.status_code == 204, deleted.text
    else:
        from app.services.admin_trip_operations import delete_admin_day, move_admin_day

        target = await _make_trip(client, cookies) if deletion_route == "admin_move" else None
        async with session_factory() as db:
            if target:
                await move_admin_day(
                    db,
                    source_trip_id=uuid.UUID(trip_id),
                    day_index=1,
                    target_trip_id=uuid.UUID(target),
                    target_day_index=1,
                    poi_policy="delete",
                    attachment_policy="delete",
                    comment_policy="delete",
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
        json=_attachment_payload(user_id, byte_size=50),
        cookies=cookies,
    )
    assert denied.status_code == 409, denied.text
    from app.services import attachment_retention as gc

    calls = []

    async def delete(bucket, key):
        calls.append(key)

    monkeypatch.setattr(gc, "delete_attachment_object", delete)
    if held:
        # 일자 삭제는 moderation hold를 풀지 않는다(2026-11-06 소유자 결정).
        async with session_factory() as db:
            result = await gc.execute_attachment_retention(db)
            assert result["objects_deleted"] == 0 and calls == []
            assert result["status"]["held_attachments"] == 1
            assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 60
        from app.models.attachment import CuratedPlanAttachment
        from app.models.moderation import ContentReport
        from app.services.moderation import _restore_target

        async with session_factory() as db:
            await _restore_target(
                db,
                ContentReport(
                    target_type="attachment",
                    target_id=uuid.UUID(uploaded.json()["data"]["attachment_id"]),
                    reason_code="other",
                    reason_text="resolved",
                    status="hidden",
                ),
            )
            await db.commit()
            row = await db.get(
                CuratedPlanAttachment, uuid.UUID(uploaded.json()["data"]["attachment_id"])
            )
            assert not row.moderation_hold and row.deleted_at is not None
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_deleted"] == 1 and len(calls) == 1
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 0


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
        json=_attachment_payload(user_id, byte_size=60),
        cookies=cookies,
    )
    assert uploaded.status_code == 201, uploaded.text
    await _add_poi(client, cookies, source, sort_order="a0", feature_id=None)
    target = await _make_trip(client, cookies) if mode == "merge" else None
    if target:
        first = await client.post(
            f"/trips/{target}/attachments",
            json=_attachment_payload(user_id, byte_size=60),
            cookies=cookies,
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
        json={"scope": "all", "target_trip_id": target},
        cookies=cookies,
    )
    assert result.status_code == 409, result.text
    assert result.json()["error"]["code"] == "ATTACHMENT_QUOTA_EXCEEDED"
    async with session_factory() as db:
        assert [
            await db.scalar(select(func.count()).select_from(model)) for model in models
        ] == before
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == (
            120 if target else 60
        )


async def test_concurrent_copies_share_actor_quota_capacity(
    client, verified_user, auth_cookies, session_factory
):
    import asyncio

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    source = await _make_trip(client, cookies)
    first = await client.post(
        f"/trips/{source}/attachments",
        json=_attachment_payload(user_id, byte_size=60),
        cookies=cookies,
    )
    assert first.status_code == 201
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.user_attachment_quota_bytes_override = 160
        await db.commit()
    replies = await asyncio.gather(
        *[
            client.post(f"/trips/{source}/copy", json={"scope": "all"}, cookies=cookies)
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in replies) == [201, 409], [r.text for r in replies]
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 120


@pytest.mark.parametrize("scope", ["day", "poi"])
@pytest.mark.parametrize("capacity", ["trip", "user", "allowed"])
async def test_admin_partial_copy_obeys_actual_uploader_capacity(
    client, verified_user, auth_cookies, session_factory, scope, capacity
):
    from sqlalchemy import func, select

    from app.models.attachment import CuratedPlanAttachment
    from app.models.poi import TripDayPoi
    from app.models.trip_day import TripDay
    from app.services.admin_trip_operations import (
        AdminTripOperationConflictError,
        copy_admin_day,
        copy_admin_poi,
    )
    from tests.integration.test_admin_trips_api import _create_user

    owner_id, _ = verified_user
    owner = auth_cookies(owner_id)
    admin_id = await _create_user(
        session_factory, email="capacity-admin@example.com", roles=["user", "admin"]
    )
    admin = auth_cookies(str(admin_id))
    created = await client.post(
        "/trips",
        json={"title": "partial copy", "start_date": "2026-11-10", "end_date": "2026-11-10"},
        cookies=owner,
    )
    source = created.json()["data"]["trip_id"]
    target = await _make_trip(client, owner)
    poi = None
    if scope == "poi":
        poi = await _add_poi(client, owner, source, sort_order="a0", feature_id=None)
        path = f"/trips/{source}/pois/{poi['attachment_id']}/attachments"
        purpose = "poi_attachment"
    else:
        path = f"/trips/{source}/days/1/attachments"
        purpose = "trip_day_attachment"
    attached = await client.post(
        path, json=_attachment_payload(owner_id, byte_size=60, purpose=purpose), cookies=owner
    )
    assert attached.status_code == 201, attached.text
    if capacity == "user":
        admin_trip = await _make_trip(client, admin)
        path = f"/trips/{admin_trip}/attachments"
        payload_user = str(admin_id)
        current_cookies = admin
    else:
        path = f"/trips/{target}/attachments"
        payload_user = owner_id
        current_cookies = owner
    attached = await client.post(
        path, json=_attachment_payload(payload_user, byte_size=60), cookies=current_cookies
    )
    assert attached.status_code == 201, attached.text
    async with session_factory() as db:
        uploader = await db.get(User, admin_id)
        uploader.trip_attachment_quota_bytes_override = 100 if capacity == "trip" else 200
        uploader.user_attachment_quota_bytes_override = 100 if capacity == "user" else 200
        await db.commit()
        models = (TripDay, TripDayPoi, CuratedPlanAttachment)
        before = [await db.scalar(select(func.count()).select_from(model)) for model in models]

        async def operation():
            if poi:
                return await copy_admin_poi(
                    db,
                    poi_id=uuid.UUID(poi["attachment_id"]),
                    target_trip_id=uuid.UUID(target),
                    target_day_index=2,
                    admin_user_id=admin_id,
                    include_attachments=True,
                )
            return await copy_admin_day(
                db,
                source_trip_id=uuid.UUID(source),
                day_index=1,
                target_trip_id=uuid.UUID(target),
                target_day_index=2,
                admin_user_id=admin_id,
                include_pois=True,
                include_attachments=True,
            )

        if capacity != "allowed":
            with pytest.raises(AdminTripOperationConflictError):
                await operation()
            await db.rollback()
            assert [
                await db.scalar(select(func.count()).select_from(model)) for model in models
            ] == before
        else:
            await operation()
            await db.commit()
            assert await attachment_bytes_for_trip(db, trip_id=uuid.UUID(target)) == 120
            assert await attachment_bytes_for_user(db, user_id=admin_id) == 60


@pytest.mark.parametrize("move_kind", ["day", "poi"])
async def test_attachment_revalidates_poi_after_admin_moves_it_to_private_trip(
    client, verified_user, auth_cookies, session_factory, monkeypatch, move_kind
):
    import asyncio

    from sqlalchemy import func, select

    import app.api.v1.trips as routes
    from app.models.attachment import CuratedPlanAttachment
    from app.services.admin_trip_operations import move_admin_day, move_admin_poi
    from tests.integration.test_admin_trips_api import _create_user

    source_user, _ = verified_user
    cookies = auth_cookies(source_user)
    source = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, source, sort_order="a0", feature_id=None)
    target_user = await _create_user(session_factory, email="private-target@example.com")
    target = await _make_trip(client, auth_cookies(str(target_user)))
    validated = asyncio.Event()
    resume = asyncio.Event()
    real_create = routes.create_attachment

    async def pause_after_route_validation(*args, **kwargs):
        validated.set()
        await resume.wait()
        return await real_create(*args, **kwargs)

    monkeypatch.setattr(routes, "create_attachment", pause_after_route_validation)
    upload = asyncio.create_task(
        client.post(
            f"/trips/{source}/pois/{poi['attachment_id']}/attachments",
            json=_attachment_payload(source_user, byte_size=60, purpose="poi_attachment"),
            cookies=cookies,
        )
    )
    try:
        await asyncio.wait_for(validated.wait(), timeout=10)
        async with session_factory() as db:
            if move_kind == "day":
                await move_admin_day(
                    db,
                    source_trip_id=uuid.UUID(source),
                    day_index=1,
                    target_trip_id=uuid.UUID(target),
                    target_day_index=1,
                    poi_policy="move",
                    attachment_policy="move",
                    comment_policy="move",
                )
            else:
                await move_admin_poi(
                    db,
                    poi_id=uuid.UUID(poi["attachment_id"]),
                    target_trip_id=uuid.UUID(target),
                    target_day_index=1,
                    attachment_policy="move",
                    comment_policy="move",
                )
            await db.commit()
    finally:
        resume.set()
    result = await asyncio.wait_for(upload, timeout=10)
    assert result.status_code == 422, result.text
    assert result.json()["error"]["code"] == "INVALID_ATTACHMENT_STORAGE_REF"
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(CuratedPlanAttachment)) == 0
        assert await attachment_bytes_for_trip(db, trip_id=uuid.UUID(target)) == 0
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(source_user)) == 0


@pytest.mark.parametrize("scope", ["day", "poi"])
async def test_admin_move_preserves_active_destination_and_retired_private_charge(
    client, verified_user, auth_cookies, session_factory, scope
):
    from app.models.attachment import CuratedPlanAttachment
    from app.services.admin_trip_operations import move_admin_day

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post(
        "/trips",
        json={"title": "move source", "start_date": "2026-11-10", "end_date": "2026-11-10"},
        cookies=cookies,
    )
    source = created.json()["data"]["trip_id"]
    target = await _make_trip(client, cookies)
    if scope == "poi":
        poi = await _add_poi(client, cookies, source, sort_order="a0", feature_id=None)
        path = f"/trips/{source}/pois/{poi['attachment_id']}/attachments"
        purpose = "poi_attachment"
    else:
        path = f"/trips/{source}/days/1/attachments"
        purpose = "trip_day_attachment"
    active = await client.post(
        path, json=_attachment_payload(user_id, byte_size=40, purpose=purpose), cookies=cookies
    )
    retired = await client.post(
        path, json=_attachment_payload(user_id, byte_size=20, purpose=purpose), cookies=cookies
    )
    assert active.status_code == retired.status_code == 201
    active_id = active.json()["data"]["attachment_id"]
    retired_id = retired.json()["data"]["attachment_id"]
    removed = await client.delete(f"{path}/{retired_id}", cookies=cookies)
    assert removed.status_code == 204
    async with session_factory() as db:
        old = await db.get(CuratedPlanAttachment, uuid.UUID(retired_id))
        deleted_at = old.deleted_at
        await move_admin_day(
            db,
            source_trip_id=uuid.UUID(source),
            day_index=1,
            target_trip_id=uuid.UUID(target),
            target_day_index=2,
            poi_policy="move",
            attachment_policy="move",
            comment_policy="move",
        )
        await db.commit()
    async with session_factory() as db:
        old = await db.get(CuratedPlanAttachment, uuid.UUID(retired_id))
        assert old.deleted_at == deleted_at
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 60
        assert await attachment_bytes_for_trip(db, trip_id=uuid.UUID(source)) == (
            20 if scope == "day" else 0
        )
        assert await attachment_bytes_for_trip(db, trip_id=uuid.UUID(target)) == (
            40 if scope == "day" else 60
        )
    files = await client.get("/users/me/files", cookies=cookies)
    ids = {row["attachment_id"] for row in files.json()["data"]["items"]}
    assert active_id in ids and retired_id not in ids
    download = await client.get(f"/users/me/files/{retired_id}/download-url", cookies=cookies)
    assert download.status_code == 404
