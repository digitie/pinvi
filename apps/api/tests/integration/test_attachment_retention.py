"""#667: 실제 PostgreSQL 수명·공유 참조·영속 삭제 재시도."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from botocore.exceptions import ClientError

from app.models.attachment import CuratedPlanAttachment
from app.models.storage_lifecycle import AttachmentGcObject
from app.models.trip import Trip
from app.services import attachment_retention as gc
from app.services.storage_policy import attachment_bytes_for_user
from tests.integration.test_pois_reorder import _make_trip
from tests.integration.test_trips_api import _attachment_payload

pytestmark = pytest.mark.asyncio


async def _file(client, cookies, user_id, trip):
    r = await client.post(
        f"/trips/{trip}/attachments",
        cookies=cookies,
        json=_attachment_payload(user_id, byte_size=60),
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _trash(session_factory, trip_id, days):
    async with session_factory() as db:
        trip = await db.get(Trip, uuid.UUID(trip_id))
        trip.deleted_at = datetime.now(UTC) - timedelta(days=days)
        trip.status = "archived"
        await db.commit()


@pytest.mark.parametrize("days,status", [(29, 200), (30, 410), (31, 410)])
async def test_restore_has_thirty_day_deadline(
    client, verified_user, auth_cookies, session_factory, days, status
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    await _trash(session_factory, trip, days)
    result = await client.post(f"/trips/{trip}/restore", cookies=cookies)
    assert result.status_code == status, result.text


async def test_delete_is_after_tombstone_commit_and_then_releases_charge(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    file = await _file(client, cookies, user_id, trip)
    removed = await client.delete(
        f"/trips/{trip}/attachments/{file['attachment_id']}", cookies=cookies
    )
    assert removed.status_code == 204
    calls = []

    async def delete(bucket, key):
        async with session_factory() as observer:
            row = await observer.get(AttachmentGcObject, (bucket, key))
            assert row is not None and row.deleted_at is None
            assert await attachment_bytes_for_user(observer, user_id=uuid.UUID(user_id)) == 60
        calls.append(key)

    monkeypatch.setattr(gc, "delete_attachment_object", delete)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
    assert result["objects_deleted"] == 1 and len(calls) == 1
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 0
        row = await db.get(CuratedPlanAttachment, uuid.UUID(file["attachment_id"]))
        assert row.purged_at is not None


async def test_failed_object_delete_is_durable_and_retryable(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    file = await _file(client, cookies, user_id, trip)
    await client.delete(f"/trips/{trip}/attachments/{file['attachment_id']}", cookies=cookies)

    async def failed(bucket, key):
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "private never expose"}}, "DeleteObject"
        )

    monkeypatch.setattr(gc, "delete_attachment_object", failed)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_failed"] == 1
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 60
        row = await db.get(AttachmentGcObject, (file["bucket"], file["storage_key"]))
        assert row.last_error_code == "AccessDenied:DeleteObject" and row.attempts == 1

    async def success(bucket, key):
        return None

    monkeypatch.setattr(gc, "delete_attachment_object", success)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_deleted"] == 1
        row = await db.get(AttachmentGcObject, (file["bucket"], file["storage_key"]))
        assert row.attempts == 2 and row.last_error_code is None
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 0


async def test_expired_source_purge_preserves_live_copy_object(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    await _file(client, cookies, user_id, trip)
    copy = await client.post(f"/trips/{trip}/copy", json={"scope": "all"}, cookies=cookies)
    assert copy.status_code == 201, copy.text
    other = copy.json()["data"]["trip"]["trip_id"]
    await _trash(session_factory, trip, 31)
    calls = []

    async def delete(bucket, key):
        calls.append(key)

    monkeypatch.setattr(gc, "delete_attachment_object", delete)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["trips_deleted"] == 1 and calls == []
        assert await db.get(Trip, uuid.UUID(trip)) is None
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 60
    await _trash(session_factory, other, 31)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["trips_deleted"] == 1 and len(calls) == 1
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 0


async def _upload_url(client, cookies, size=60):
    result = await client.post(
        "/storage/upload-urls",
        cookies=cookies,
        json={
            "purpose": "trip_attachment",
            "filename": "retained.jpg",
            "content_type": "image/jpeg",
            "content_length": size,
        },
    )
    assert result.status_code == 200, result.text
    return result.json()["data"]


async def _put(client, url, size=60):
    from urllib.parse import urlsplit

    return await client.put(
        urlsplit(url).path, content=b"x" * size, headers={"content-type": "image/jpeg"}
    )


async def test_upload_reservation_transfers_once_and_failed_registration_keeps_charge(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    from app.api.v1 import storage
    from app.models.storage_lifecycle import AttachmentUploadIntent
    from app.models.user import User

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.user_attachment_quota_bytes_override = 100
        user.trip_attachment_quota_bytes_override = 50
        await db.commit()
    up = await _upload_url(client, cookies)
    blocked = await client.post(
        "/storage/upload-urls",
        cookies=cookies,
        json={
            "purpose": "trip_attachment",
            "filename": "second.jpg",
            "content_type": "image/jpeg",
            "content_length": 50,
        },
    )
    assert blocked.status_code == 409, blocked.text
    monkeypatch.setattr(storage, "put_storage_object", lambda **kwargs: None)
    assert (await _put(client, up["upload_url"])).status_code == 204
    payload = {
        **_attachment_payload(user_id, byte_size=60),
        "bucket": up["bucket"],
        "storage_key": up["storage_key"],
    }
    bad = await client.post(f"/trips/{trip}/attachments", json=payload, cookies=cookies)
    assert bad.status_code == 409, bad.text
    async with session_factory() as db:
        intent = await db.get(AttachmentUploadIntent, (up["bucket"], up["storage_key"]))
        assert intent.registered_at is None
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 60
        user = await db.get(User, uuid.UUID(user_id))
        user.trip_attachment_quota_bytes_override = 100
        await db.commit()
    good = await client.post(f"/trips/{trip}/attachments", json=payload, cookies=cookies)
    assert good.status_code == 201, good.text
    assert (await _put(client, up["upload_url"])).status_code == 422
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 60


async def test_expired_unregistered_upload_is_collected_and_late_reference_denied(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    from app.models.storage_lifecycle import AttachmentUploadIntent

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    up = await _upload_url(client, cookies)
    async with session_factory() as db:
        intent = await db.get(AttachmentUploadIntent, (up["bucket"], up["storage_key"]))
        intent.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    calls = []

    async def delete(bucket, key):
        calls.append(key)

    monkeypatch.setattr(gc, "delete_attachment_object", delete)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_deleted"] == 1 and calls == [up["storage_key"]]
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 0
    payload = {
        **_attachment_payload(user_id, byte_size=60),
        "bucket": up["bucket"],
        "storage_key": up["storage_key"],
    }
    late = await client.post(f"/trips/{trip}/attachments", cookies=cookies, json=payload)
    assert late.status_code == 422, late.text


@pytest.mark.parametrize("kind", ["trip", "attachment"])
async def test_moderation_cannot_restore_purge_started_target(
    client, verified_user, auth_cookies, session_factory, monkeypatch, kind
):
    from app.models.moderation import ContentReport
    from app.services.moderation import ContentReportTransitionError, _restore_target

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    file = await _file(client, cookies, user_id, trip)
    if kind == "trip":
        await _trash(session_factory, trip, 31)
        async with session_factory() as db:
            await gc._stage(db, datetime.now(UTC), 20)
        target_id = uuid.UUID(trip)
    else:
        await client.delete(f"/trips/{trip}/attachments/{file['attachment_id']}", cookies=cookies)
        async with session_factory() as db:
            await gc._stage(db, datetime.now(UTC), 20)
        target_id = uuid.UUID(file["attachment_id"])
    report = ContentReport(
        target_type=kind,
        target_id=target_id,
        target_snapshot={"status": "draft", "visibility": "public"},
    )
    async with session_factory() as db:
        with pytest.raises(ContentReportTransitionError):
            await _restore_target(db, report)
        await db.rollback()


async def test_cancelled_put_keeps_object_lock_until_actual_write_finishes(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    import asyncio
    import threading

    from app.api.v1 import storage
    from app.models.storage_lifecycle import AttachmentUploadIntent

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    up = await _upload_url(client, cookies)
    started, finish = threading.Event(), threading.Event()
    objects = {}

    def slow_put(**kwargs):
        started.set()
        assert finish.wait(10)
        objects[up["storage_key"]] = kwargs["body"]

    async def delete(bucket, key):
        objects.pop(key, None)

    monkeypatch.setattr(storage, "put_storage_object", slow_put)
    monkeypatch.setattr(gc, "delete_attachment_object", delete)
    put = asyncio.create_task(_put(client, up["upload_url"]))
    try:
        assert await asyncio.to_thread(started.wait, 10)
        async with session_factory() as db:
            row = await db.get(AttachmentUploadIntent, (up["bucket"], up["storage_key"]))
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            row.write_started_at = datetime.now(UTC) - timedelta(minutes=31)
            await db.commit()
        put.cancel()
        await asyncio.sleep(0.05)
        assert not put.done()
        async with session_factory() as db:
            result = await gc.execute_attachment_retention(db)
            assert result["objects_deleted"] == 0
            assert await db.get(AttachmentGcObject, (up["bucket"], up["storage_key"])) is None
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await put
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_deleted"] == 1 and not objects


async def test_one_shot_put_start_survives_crash_before_network(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    from app.api.v1 import storage
    from app.models.storage_lifecycle import AttachmentUploadIntent

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    up = await _upload_url(client, cookies)
    guard = storage.assert_objects_writable
    calls = 0
    sent = []

    async def interrupt(db, objects):
        nonlocal calls
        await guard(db, objects)
        calls += 1
        if calls == 2:
            raise RuntimeError("fixture process stopped after durable start")

    monkeypatch.setattr(storage, "assert_objects_writable", interrupt)
    monkeypatch.setattr(storage, "put_storage_object", lambda **kw: sent.append(kw))
    first = await _put(client, up["upload_url"])
    assert first.status_code == 503 and not sent
    monkeypatch.setattr(storage, "assert_objects_writable", guard)
    second = await _put(client, up["upload_url"])
    assert second.status_code == 422 and second.json()["error"]["code"] == "UPLOAD_ALREADY_STARTED"
    async with session_factory() as db:
        intent = await db.get(AttachmentUploadIntent, (up["bucket"], up["storage_key"]))
        assert intent.write_started_at is not None and intent.uploaded_bytes is None


async def test_lost_completion_cannot_register_and_late_bytes_are_recollected(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api.v1 import storage
    from app.models.storage_lifecycle import AttachmentUploadIntent

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    up = await _upload_url(client, cookies)
    objects = {}
    monkeypatch.setattr(
        storage, "put_storage_object", lambda **kw: objects.update({up["storage_key"]: kw["body"]})
    )
    real_commit = AsyncSession.commit
    calls = 0

    async def fail_completion(db):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fixture completion record lost")
        await real_commit(db)

    monkeypatch.setattr(AsyncSession, "commit", fail_completion)
    result = await _put(client, up["upload_url"])
    assert result.status_code == 503 and up["storage_key"] in objects
    monkeypatch.setattr(AsyncSession, "commit", real_commit)
    payload = {
        **_attachment_payload(user_id, byte_size=60),
        "bucket": up["bucket"],
        "storage_key": up["storage_key"],
    }
    refused = await client.post(f"/trips/{trip}/attachments", cookies=cookies, json=payload)
    assert refused.status_code == 422, refused.text
    async with session_factory() as db:
        intent = await db.get(AttachmentUploadIntent, (up["bucket"], up["storage_key"]))
        intent.expires_at = datetime.now(UTC) - timedelta(minutes=31)
        intent.write_started_at = datetime.now(UTC) - timedelta(minutes=31)
        await db.commit()

    async def delete(bucket, key):
        objects.pop(key, None)

    monkeypatch.setattr(gc, "delete_attachment_object", delete)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_deleted"] == 1 and not objects
    objects[up["storage_key"]] = b"late old server write"
    async with session_factory() as db:
        row = await db.get(AttachmentGcObject, (up["bucket"], up["storage_key"]))
        row.last_verified_at = datetime.now(UTC) - timedelta(hours=2)
        await db.commit()
        result = await gc.execute_attachment_retention(db)
        assert result["objects_verified"] == 1 and not objects
    refused = await client.post(f"/trips/{trip}/attachments", cookies=cookies, json=payload)
    assert refused.status_code == 422


async def test_same_key_concurrent_put_sends_once(client, verified_user, auth_cookies, monkeypatch):
    import asyncio
    import threading

    from app.api.v1 import storage

    user_id, _ = verified_user
    up = await _upload_url(client, auth_cookies(user_id))
    started, finish = threading.Event(), threading.Event()
    sent = []

    def put(**kwargs):
        sent.append(kwargs["body"])
        started.set()
        assert finish.wait(10)

    monkeypatch.setattr(storage, "put_storage_object", put)
    first = asyncio.create_task(_put(client, up["upload_url"]))
    try:
        assert await asyncio.to_thread(started.wait, 10)
        second = asyncio.create_task(_put(client, up["upload_url"]))
        await asyncio.sleep(0.05)
    finally:
        finish.set()
    a, b = await asyncio.gather(first, second)
    assert a.status_code == 204 and b.status_code == 422 and len(sent) == 1


async def test_admin_full_copy_maps_tombstone_to_conflict_and_rolls_back(
    client, verified_user, auth_cookies, session_factory
):
    from sqlalchemy import func, select

    from app.models.user import User

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    file = await _file(client, cookies, user_id, trip)
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.roles = ["user", "admin"]
        db.add(AttachmentGcObject(bucket=file["bucket"], storage_key=file["storage_key"]))
        await db.commit()
        before = await db.scalar(select(func.count()).select_from(Trip))
    result = await client.post(
        f"/admin/trips/{trip}/copy",
        cookies=cookies,
        json={
            "scope": "all",
            "access_reason": "GC tombstone conflict verification",
        },
    )
    assert result.status_code == 409, result.text
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Trip)) == before


async def test_moderation_hold_survives_appeal_review_reject_until_restore(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    from app.models.moderation import ContentReport
    from app.schemas.moderation import ContentModerationActionRequest, ContentReportAppealRequest
    from app.services.moderation import appeal_content_report, moderate_content_report

    user_id, _ = verified_user
    uid = uuid.UUID(user_id)
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    file = await _file(client, cookies, user_id, trip)
    async with session_factory() as db:
        report = ContentReport(
            target_type="attachment",
            target_id=uuid.UUID(file["attachment_id"]),
            target_trip_id=uuid.UUID(trip),
            target_owner_user_id=uid,
            reporter_user_id=uid,
            reason_code="other",
            reason_text="retain reversible moderation",
            status="reviewing",
        )
        db.add(report)
        await db.commit()
        report_id = report.report_id
    body = ContentModerationActionRequest(
        access_reason="retention regression", resolution_summary="review fixture"
    )
    async with session_factory() as db:
        await moderate_content_report(
            db, report_id=report_id, actor_user_id=uid, action="hide", body=body
        )
        await db.commit()
    deleted = []

    async def delete(bucket, key):
        deleted.append(key)

    monkeypatch.setattr(gc, "delete_attachment_object", delete)

    async def check_hold():
        async with session_factory() as db:
            result = await gc.execute_attachment_retention(db)
            assert result["objects_deleted"] == 0 and result["status"]["held_attachments"] == 1
            assert await attachment_bytes_for_user(db, user_id=uid) == 60

    await check_hold()
    async with session_factory() as db:
        await appeal_content_report(
            db,
            report_id=report_id,
            actor_user_id=uid,
            body=ContentReportAppealRequest(appeal_reason="please restore"),
        )
        await db.commit()
    await check_hold()
    for action in ["review", "reject"]:
        async with session_factory() as db:
            await moderate_content_report(
                db, report_id=report_id, actor_user_id=uid, action=action, body=body
            )
            await db.commit()
        await check_hold()
    async with session_factory() as db:
        await appeal_content_report(
            db,
            report_id=report_id,
            actor_user_id=uid,
            body=ContentReportAppealRequest(appeal_reason="please restore again"),
        )
        await moderate_content_report(
            db, report_id=report_id, actor_user_id=uid, action="restore", body=body
        )
        await db.commit()
        row = await db.get(CuratedPlanAttachment, uuid.UUID(file["attachment_id"]))
        assert row.deleted_at is None and not row.moderation_hold
    assert not deleted
    await client.delete(f"/trips/{trip}/attachments/{file['attachment_id']}", cookies=cookies)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_deleted"] == 1 and len(deleted) == 1


async def test_busy_report_fk_cleanup_is_retryable_and_preserves_lock_timeout(
    client, verified_user, auth_cookies, session_factory
):
    from sqlalchemy import select, text

    from app.models.moderation import ContentReport

    user_id, _ = verified_user
    trip = await _make_trip(client, auth_cookies(user_id))
    await _trash(session_factory, trip, 31)
    async with session_factory() as db:
        report = ContentReport(
            target_type="trip",
            target_id=uuid.UUID(trip),
            target_trip_id=uuid.UUID(trip),
            reason_code="other",
            reason_text="busy report",
            status="received",
        )
        db.add(report)
        await db.commit()
        rid = report.report_id
    async with session_factory() as held:
        await held.scalar(
            select(ContentReport).where(ContentReport.report_id == rid).with_for_update()
        )
        async with session_factory() as db:
            prior = await db.scalar(text("SHOW lock_timeout"))
            result = await gc.execute_attachment_retention(db)
            assert result["trips_deleted"] == 0 and result["trip_cleanup_errors"] == ["TRIP_BUSY"]
            assert await db.scalar(text("SHOW lock_timeout")) == prior
        await held.rollback()
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["trips_deleted"] == 1
        report = await db.get(ContentReport, rid)
        assert report is not None and report.target_trip_id is None


async def test_expired_lease_old_failure_cannot_overwrite_new_success(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    import asyncio

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    file = await _file(client, cookies, user_id, trip)
    await client.delete(f"/trips/{trip}/attachments/{file['attachment_id']}", cookies=cookies)
    ready, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def delete(bucket, key):
        nonlocal calls
        calls += 1
        if calls == 1:
            ready.set()
            await release.wait()
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")

    monkeypatch.setattr(gc, "delete_attachment_object", delete)

    async def first_run():
        async with session_factory() as db:
            return await gc.execute_attachment_retention(db)

    first = asyncio.create_task(first_run())
    try:
        await asyncio.wait_for(ready.wait(), 10)
        async with session_factory() as db:
            row = await db.get(AttachmentGcObject, (file["bucket"], file["storage_key"]))
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
        async with session_factory() as db:
            second = await gc.execute_attachment_retention(db)
            assert second["objects_deleted"] == 1
    finally:
        release.set()
    await asyncio.wait_for(first, 10)
    async with session_factory() as db:
        row = await db.get(AttachmentGcObject, (file["bucket"], file["storage_key"]))
        assert row.deleted_at is not None and row.attempts == 2 and row.last_error_code is None


async def test_shared_source_disappearing_before_copy_fence_is_clean_conflict(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    import asyncio

    from app.services import trip as service

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    source = await _make_trip(client, cookies)
    await _file(client, cookies, user_id, source)
    live = await client.post(f"/trips/{source}/copy", json={"scope": "all"}, cookies=cookies)
    assert live.status_code == 201
    ready, release = asyncio.Event(), asyncio.Event()
    real = service.assert_copy_sources_writable

    async def paused(db, attachments):
        ready.set()
        await release.wait()
        await real(db, attachments)

    monkeypatch.setattr(service, "assert_copy_sources_writable", paused)
    pending = asyncio.create_task(
        client.post(f"/trips/{source}/copy", json={"scope": "all"}, cookies=cookies)
    )
    try:
        await asyncio.wait_for(ready.wait(), 10)
        await _trash(session_factory, source, 31)
        async with session_factory() as db:
            result = await gc.execute_attachment_retention(db)
            assert result["trips_deleted"] == 1 and result["objects_deleted"] == 0
    finally:
        release.set()
    response = await asyncio.wait_for(pending, 10)
    assert response.status_code == 422, response.text
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 60


async def test_notice_and_trip_copy_take_shared_object_set_in_global_order(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    import asyncio
    import contextvars

    from sqlalchemy import select

    from app.models.curated_plan import CuratedPlanPoi
    from app.services import notice_plan, storage_lifecycle, trip
    from tests.integration.test_admin_trips_api import _create_user
    from tests.integration.test_notice_plan_copy import _admin_id, _seed_plan

    user_id, _ = verified_user
    plan_id = await _seed_plan(session_factory)
    admin = await _admin_id(session_factory)
    other = await _create_user(session_factory, email="other-copy@example.com")
    other_source = await _make_trip(client, auth_cookies(str(other)))
    keys = ["shared/z.png", "shared/a.png"]
    async with session_factory() as db:
        pois = list(
            await db.scalars(
                select(CuratedPlanPoi)
                .where(CuratedPlanPoi.curated_plan_id == plan_id)
                .order_by(CuratedPlanPoi.day_index, CuratedPlanPoi.sort_order)
            )
        )
        for poi, key in zip(pois[: len(keys)], keys, strict=True):
            for kwargs in [
                {"curated_poi_id": poi.curated_poi_id, "uploaded_by_user_id": admin},
                {"trip_id": uuid.UUID(other_source), "uploaded_by_user_id": other},
            ]:
                db.add(
                    CuratedPlanAttachment(
                        bucket="pinvi-media",
                        storage_key=key,
                        byte_size=1,
                        original_filename="shared.png",
                        content_type="image/png",
                        **kwargs,
                    )
                )
        await db.commit()
    label = contextvars.ContextVar("copy_label", default="")
    real_lock = storage_lifecycle.lock_object
    seq = {"notice": [], "trip": []}
    ready = asyncio.Event()
    other_ready = asyncio.Event()
    release = asyncio.Event()

    async def lock(db, bucket, key, *, try_only=False):
        result = await real_lock(db, bucket, key, try_only=try_only)
        who = label.get()
        if who:
            seq[who].append(key)
            if who == "notice" and len(seq[who]) == 1:
                ready.set()
                await release.wait()
            if who == "trip" and len(seq[who]) == 1:
                other_ready.set()
        return result

    monkeypatch.setattr(storage_lifecycle, "lock_object", lock)
    for module, who in [(notice_plan, "notice"), (trip, "trip")]:
        real = module.assert_copy_sources_writable

        async def wrapped(db, attachments, real=real, who=who):
            token = label.set(who)
            try:
                await real(db, attachments)
            finally:
                label.reset(token)

        monkeypatch.setattr(module, "assert_copy_sources_writable", wrapped)
    notice = asyncio.create_task(
        client.post(
            f"/notice-plans/{plan_id}/copy",
            json={"trip_title": "ordered"},
            cookies=auth_cookies(user_id),
        )
    )
    try:
        await asyncio.wait_for(ready.wait(), 10)
        public = asyncio.create_task(
            client.post(
                f"/trips/{other_source}/copy",
                json={"scope": "all"},
                cookies=auth_cookies(str(other)),
            )
        )
        if seq["notice"][0] != sorted(keys)[0]:
            await asyncio.wait_for(other_ready.wait(), 10)
        else:
            await asyncio.sleep(0.05)
    finally:
        release.set()
    results = await asyncio.wait_for(asyncio.gather(notice, public), 10)
    assert [r.status_code for r in results] == [201, 201], [r.text for r in results]
    assert seq["notice"] == seq["trip"] == sorted(keys)


async def test_0103_moderation_backfill_uses_action_history_conservatively(
    client, verified_user, auth_cookies, session_factory
):
    import ast
    from pathlib import Path

    from sqlalchemy import text

    from app.models.moderation import ContentModerationAction, ContentReport

    user_id, _ = verified_user
    uid = uuid.UUID(user_id)
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    now = datetime.now(UTC)
    cases = [
        ("rejected", [("reject", 0)], False),
        ("appealed", [("hide", 0), ("appeal", 1)], True),
        ("rejected", [("hide", 0), ("restore", 1), ("reject", 2)], True),
        ("hidden", [("hide", 0), ("restore", 3)], True),
        ("appealed", [("hide", 0), ("restore", 0)], True),
        ("restored", [("hide", 0)], False),
        ("reviewing", [("takedown", 0), ("review", 1)], True),
    ]
    expected = {}
    for status, actions, hold in cases:
        file = await _file(client, cookies, user_id, trip)
        aid = uuid.UUID(file["attachment_id"])
        async with session_factory() as db:
            row = await db.get(CuratedPlanAttachment, aid)
            row.deleted_at = now
            report = ContentReport(
                target_type="attachment",
                target_id=aid,
                target_trip_id=uuid.UUID(trip),
                target_owner_user_id=uid,
                reporter_user_id=uid,
                reason_code="other",
                reason_text="historical decision",
                status=status,
                actioned_at=now,
            )
            db.add(report)
            await db.flush()
            for action, seconds in actions:
                db.add(
                    ContentModerationAction(
                        report_id=report.report_id,
                        actor_user_id=uid,
                        action=action,
                        action_reason="historical action",
                        created_at=now + timedelta(seconds=seconds),
                    )
                )
            await db.commit()
        expected[aid] = hold
    migration = (
        Path(__file__).resolve().parents[2]  # noqa: ASYNC240 — 로컬 fixture 경로만 해석
        / "alembic/versions/20261105_0103_attachment_retention.py"
    )
    tree = ast.parse(migration.read_text())
    sql = next(
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and "UPDATE app.curated_plan_attachments" in str(node.args[0].value)
    )
    async with session_factory() as db:
        await db.execute(text(sql))
        await db.commit()
        for aid, hold in expected.items():
            row = await db.get(CuratedPlanAttachment, aid, populate_existing=True)
            assert row.moderation_hold is hold


async def test_expired_parent_overrides_moderation_hold(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    file = await _file(client, cookies, user_id, trip)
    async with session_factory() as db:
        row = await db.get(CuratedPlanAttachment, uuid.UUID(file["attachment_id"]))
        row.deleted_at = datetime.now(UTC)
        row.moderation_hold = True
        await db.commit()
    await _trash(session_factory, trip, 31)
    calls = []

    async def delete(bucket, key):
        calls.append(key)

    monkeypatch.setattr(gc, "delete_attachment_object", delete)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_deleted"] == 1 and result["trips_deleted"] == 1
        assert calls == [file["storage_key"]]


@pytest.mark.parametrize(
    "roles,read_status,write_status,can_execute",
    [
        (["user"], 404, 404, False),
        (["user", "operator"], 200, 404, False),
        (["user", "admin"], 200, 200, True),
        (["user", "cpo"], 200, 200, True),
    ],
)
async def test_storage_retention_role_boundary(
    client, auth_cookies, session_factory, roles, read_status, write_status, can_execute
):
    from tests.integration.test_admin_retention_api import _create_user

    uid = await _create_user(session_factory, roles=roles, email_prefix="storage-retention")
    cookies = auth_cookies(str(uid))
    read = await client.get("/admin/storage-retention", cookies=cookies)
    assert read.status_code == read_status, read.text
    if read_status == 200:
        assert read.json()["data"]["can_execute"] is can_execute
    write = await client.post(
        "/admin/storage-retention/execute",
        cookies=cookies,
        json={
            "access_reason": "role boundary regression",
            "confirm_phrase": "DELETE EXPIRED FILES",
        },
    )
    assert write.status_code == write_status, write.text


@pytest.mark.parametrize(
    "reason,phrase",
    [
        ("    ", "DELETE EXPIRED FILES"),
        ("abc", "DELETE EXPIRED FILES"),
        ("valid reason", "DELETE"),
    ],
)
async def test_invalid_storage_cleanup_confirmation_has_no_audit_or_effect(
    client, auth_cookies, session_factory, reason, phrase
):
    from sqlalchemy import func, select

    from app.models.audit import AdminAuditLog
    from tests.integration.test_admin_retention_api import _create_user

    uid = await _create_user(
        session_factory, roles=["user", "admin"], email_prefix="storage-confirm"
    )
    response = await client.post(
        "/admin/storage-retention/execute",
        cookies=auth_cookies(str(uid)),
        json={"access_reason": reason, "confirm_phrase": phrase},
    )
    assert response.status_code == 422, response.text
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(AdminAuditLog)) == 0
        assert await db.scalar(select(func.count()).select_from(AttachmentGcObject)) == 0


async def test_retention_request_audit_is_committed_before_storage_delete(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    from sqlalchemy import select

    from app.models.audit import AdminAuditLog
    from tests.integration.test_admin_retention_api import _create_user

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    file = await _file(client, cookies, user_id, trip)
    await client.delete(f"/trips/{trip}/attachments/{file['attachment_id']}", cookies=cookies)
    admin = await _create_user(
        session_factory, roles=["user", "admin"], email_prefix="storage-audit"
    )

    async def denied(bucket, key):
        async with session_factory() as observer:
            rows = list(await observer.scalars(select(AdminAuditLog)))
            assert len(rows) == 1
            assert rows[0].action == "storage.retention_requested"
            assert rows[0].access_reason == "bounded cleanup regression"
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "private storage detail"}}, "DeleteObject"
        )

    monkeypatch.setattr(gc, "delete_attachment_object", denied)
    response = await client.post(
        "/admin/storage-retention/execute",
        cookies=auth_cookies(str(admin)),
        json={
            "access_reason": "  bounded cleanup regression  ",
            "confirm_phrase": "DELETE EXPIRED FILES",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["objects_failed"] == 1
    assert (
        "AccessDenied:DeleteObject" in response.text
        and "private storage detail" not in response.text
    )
    async with session_factory() as db:
        rows = list(await db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.log_id)))
        assert [r.action for r in rows] == [
            "storage.retention_requested",
            "storage.retention_completed",
        ]
        assert rows[0].resource_id == rows[1].resource_id
        assert rows[1].prev_hash == rows[0].content_hash


async def test_verification_rotates_by_last_attempt_not_lifetime_delete_attempts(
    session_factory, monkeypatch
):
    now = datetime.now(UTC)
    async with session_factory() as db:
        for key, attempts, age in [("old-high", 1000, 5), ("new-low-a", 0, 3), ("new-low-b", 0, 2)]:
            db.add(
                AttachmentGcObject(
                    bucket="pinvi-media",
                    storage_key=key,
                    attempts=attempts,
                    queued_at=now - timedelta(hours=age + 1),
                    deleted_at=now - timedelta(hours=age),
                    last_verified_at=now - timedelta(hours=age),
                )
            )
        await db.commit()
    calls = []

    async def unavailable(bucket, key):
        calls.append(key)
        raise ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")

    monkeypatch.setattr(gc, "delete_attachment_object", unavailable)
    async with session_factory() as db:
        first = await gc.execute_attachment_retention(db)
    assert calls == ["old-high", "new-low-a"]
    assert first["verification_failed"] == 2
    calls.clear()
    async with session_factory() as db:
        second = await gc.execute_attachment_retention(db)
    assert calls == ["new-low-b"]
    assert second["verification_failed"] == 1


async def test_admin_library_does_not_offer_collected_poi_object(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    from tests.integration.test_admin_retention_api import _create_user
    from tests.integration.test_pois_reorder import _add_poi

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip, sort_order="a0", feature_id=None)
    file = await client.post(
        f"/trips/{trip}/pois/{poi['attachment_id']}/attachments",
        json=_attachment_payload(user_id, byte_size=60, purpose="poi_attachment"),
        cookies=cookies,
    )
    assert file.status_code == 201, file.text
    aid = file.json()["data"]["attachment_id"]
    await client.delete(f"/trips/{trip}/pois/{poi['attachment_id']}", cookies=cookies)

    async def delete(bucket, key):
        return None

    monkeypatch.setattr(gc, "delete_attachment_object", delete)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_deleted"] == 1
    admin = await _create_user(
        session_factory, roles=["user", "admin"], email_prefix="purged-library"
    )
    admin_cookies = auth_cookies(str(admin))
    response = await client.get("/admin/files", cookies=admin_cookies)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] == 0
    download = await client.get(f"/admin/files/{aid}/download-url", cookies=admin_cookies)
    assert download.status_code == 404, download.text


async def test_deleted_poi_then_hard_deleted_day_cannot_restore_detached_file(
    client, verified_user, auth_cookies, session_factory
):
    from app.models.moderation import ContentReport
    from app.services.moderation import ContentReportTransitionError, _restore_target
    from tests.integration.test_pois_reorder import _add_poi

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip, sort_order="a0", feature_id=None)
    response = await client.post(
        f"/trips/{trip}/pois/{poi['attachment_id']}/attachments",
        json=_attachment_payload(user_id, byte_size=60, purpose="poi_attachment"),
        cookies=cookies,
    )
    assert response.status_code == 201, response.text
    aid = uuid.UUID(response.json()["data"]["attachment_id"])
    async with session_factory() as db:
        row = await db.get(CuratedPlanAttachment, aid)
        row.deleted_at = datetime.now(UTC)
        row.moderation_hold = True
        await db.commit()
    await client.delete(f"/trips/{trip}/pois/{poi['attachment_id']}", cookies=cookies)
    removed = await client.delete(
        f"/trips/{trip}/days/1", headers={"If-Match": "1"}, cookies=cookies
    )
    assert removed.status_code == 204, removed.text
    report = ContentReport(
        target_type="attachment",
        target_id=aid,
        target_trip_id=uuid.UUID(trip),
        reason_code="other",
        reason_text="lost parent",
        status="hidden",
    )
    async with session_factory() as db:
        with pytest.raises(ContentReportTransitionError):
            await _restore_target(db, report)
        await db.rollback()
        row = await db.get(CuratedPlanAttachment, aid)
        assert row.deleted_at is not None
    files = await client.get("/users/me/files", cookies=cookies)
    assert files.json()["data"]["total"] == 0


@pytest.mark.parametrize("creator", ["trip", "admin_trip", "admin_day", "admin_poi"])
@pytest.mark.parametrize("already_deleted", [False, True])
async def test_all_trip_copy_paths_reject_permanent_object_marker(
    client, verified_user, auth_cookies, session_factory, creator, already_deleted
):
    from sqlalchemy import func, select

    from app.models.user import User
    from app.services.admin_trip_operations import (
        AdminTripOperationConflictError,
        copy_admin_day,
        copy_admin_poi,
    )
    from tests.integration.test_pois_reorder import _add_poi

    user_id, _ = verified_user
    uid = uuid.UUID(user_id)
    cookies = auth_cookies(user_id)
    source = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, source, sort_order="a0", feature_id=None)
    response = await client.post(
        f"/trips/{source}/pois/{poi['attachment_id']}/attachments",
        json=_attachment_payload(user_id, byte_size=60, purpose="poi_attachment"),
        cookies=cookies,
    )
    assert response.status_code == 201, response.text
    file = response.json()["data"]
    target = await _make_trip(client, cookies)
    async with session_factory() as db:
        user = await db.get(User, uid)
        user.roles = ["user", "admin"]
        db.add(
            AttachmentGcObject(
                bucket=file["bucket"],
                storage_key=file["storage_key"],
                deleted_at=datetime.now(UTC) if already_deleted else None,
            )
        )
        await db.commit()
        before = await db.scalar(select(func.count()).select_from(CuratedPlanAttachment))
    if creator in {"trip", "admin_trip"}:
        body = {"scope": "all"}
        prefix = "/admin" if creator == "admin_trip" else ""
        if prefix:
            body["access_reason"] = "object lifecycle guard"
        result = await client.post(f"{prefix}/trips/{source}/copy", json=body, cookies=cookies)
        assert result.status_code == (409 if prefix else 422), result.text
    else:
        async with session_factory() as db:
            with pytest.raises(AdminTripOperationConflictError):
                if creator == "admin_day":
                    await copy_admin_day(
                        db,
                        source_trip_id=uuid.UUID(source),
                        day_index=1,
                        target_trip_id=uuid.UUID(target),
                        target_day_index=2,
                        admin_user_id=uid,
                        include_pois=True,
                        include_attachments=True,
                    )
                else:
                    await copy_admin_poi(
                        db,
                        poi_id=uuid.UUID(poi["attachment_id"]),
                        target_trip_id=uuid.UUID(target),
                        target_day_index=2,
                        admin_user_id=uid,
                        include_attachments=True,
                    )
            await db.rollback()
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(CuratedPlanAttachment)) == before


@pytest.mark.parametrize("scope", ["plan", "poi"])
async def test_curated_attachment_registration_rejects_permanent_marker(
    client, verified_user, auth_cookies, session_factory, scope
):
    from app.models.user import User
    from tests.integration.test_admin_curated_attachments_api import _body, _seed_plan_poi

    user_id, _ = verified_user
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.roles = ["user", "admin"]
        await db.commit()
    plan, poi = await _seed_plan_poi(session_factory, admin_id=user_id)
    body = _body(user_id, purpose=f"curated_{scope}_attachment")
    async with session_factory() as db:
        db.add(AttachmentGcObject(bucket=body["bucket"], storage_key=body["storage_key"]))
        await db.commit()
    suffix = f"/pois/{poi}" if scope == "poi" else ""
    response = await client.post(
        f"/admin/notice-plans/{plan}{suffix}/attachments", json=body, cookies=auth_cookies(user_id)
    )
    assert response.status_code == 422, response.text


async def test_notice_plan_copy_rejects_pending_object_and_rolls_back_new_trip(
    client, verified_user, auth_cookies, session_factory
):
    from sqlalchemy import func, select

    from app.models.curated_plan import CuratedPlanPoi
    from tests.integration.test_notice_plan_copy import _admin_id, _seed_plan

    user_id, _ = verified_user
    plan = await _seed_plan(session_factory)
    admin = await _admin_id(session_factory)
    async with session_factory() as db:
        poi = await db.scalar(select(CuratedPlanPoi).where(CuratedPlanPoi.curated_plan_id == plan))
        db.add(
            CuratedPlanAttachment(
                curated_poi_id=poi.curated_poi_id,
                uploaded_by_user_id=admin,
                bucket="pinvi-media",
                storage_key="retired/notice.png",
                byte_size=1,
                original_filename="notice.png",
                content_type="image/png",
            )
        )
        db.add(AttachmentGcObject(bucket="pinvi-media", storage_key="retired/notice.png"))
        await db.commit()
        before = await db.scalar(select(func.count()).select_from(Trip))
    response = await client.post(
        f"/notice-plans/{plan}/copy",
        json={"trip_title": "cannot resurrect object"},
        cookies=auth_cookies(user_id),
    )
    assert response.status_code == 409, response.text
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Trip)) == before


async def test_cold_settings_url_and_attachment_do_not_invert_user_lock(
    client, verified_user, auth_cookies, monkeypatch
):
    import asyncio

    from app.api.v1 import storage
    from app.services import storage_policy

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client, cookies)
    settings_ready = asyncio.Event()
    registration_ready = asyncio.Event()
    release = asyncio.Event()
    real = storage_policy.get_storage_settings

    async def url_settings(db, **kwargs):
        row = await real(db, **kwargs)
        settings_ready.set()
        await release.wait()
        return row

    async def registration_settings(db, **kwargs):
        registration_ready.set()
        return await real(db, **kwargs)

    monkeypatch.setattr(storage, "get_storage_settings", url_settings)
    monkeypatch.setattr(storage_policy, "get_storage_settings", registration_settings)
    url = asyncio.create_task(
        client.post(
            "/storage/upload-urls",
            cookies=cookies,
            json={
                "purpose": "trip_attachment",
                "filename": "cold.jpg",
                "content_type": "image/jpeg",
                "content_length": 1,
            },
        )
    )
    registration = None
    try:
        await asyncio.wait_for(settings_ready.wait(), 10)
        registration = asyncio.create_task(
            client.post(
                f"/trips/{trip}/attachments",
                cookies=cookies,
                json=_attachment_payload(user_id, byte_size=1),
            )
        )
        await asyncio.wait_for(registration_ready.wait(), 10)
    finally:
        release.set()
    assert registration is not None
    responses = await asyncio.wait_for(
        asyncio.gather(url, registration, return_exceptions=True), 15
    )
    assert [
        getattr(response, "status_code", type(response).__name__) for response in responses
    ] == [200, 201]


async def test_runtime_retention_acl_probe_rejects_select_only_role(session_factory):
    from sqlalchemy import text

    from tests.integration.test_m05_migrator_login_lifecycle import (
        _app_feature_runtime_privileges_sql,
    )

    role = "retention_select_" + uuid.uuid4().hex[:16]
    async with session_factory() as db:
        try:
            await db.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
            await db.execute(text(f'GRANT USAGE ON SCHEMA app TO "{role}"'))
            await db.execute(
                text(
                    f"GRANT SELECT ON app.attachment_upload_intents, app.attachment_gc_objects, "
                    "app.telegram_notification_preferences, app.telegram_notifications, "
                    f'app.telegram_notification_deliveries, app.telegram_weather_observations TO "{role}"'
                )
            )
            result = (await db.execute(text(_app_feature_runtime_privileges_sql(role)))).one()
            assert tuple(result) == ("false",) * 6
        finally:
            await db.rollback()
