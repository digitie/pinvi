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
    r = await client.post(f"/trips/{trip}/attachments", cookies=cookies,
                          json=_attachment_payload(user_id, byte_size=60))
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def _trash(session_factory, trip_id, days):
    async with session_factory() as db:
        trip = await db.get(Trip, uuid.UUID(trip_id))
        trip.deleted_at = datetime.now(UTC) - timedelta(days=days)
        trip.status = "archived"
        await db.commit()


@pytest.mark.parametrize("days,status", [(29,200),(30,410),(31,410)])
async def test_restore_has_thirty_day_deadline(client, verified_user, auth_cookies, session_factory, days, status):
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
    file = await _file(client,cookies,user_id,trip)
    removed = await client.delete(f"/trips/{trip}/attachments/{file['attachment_id']}", cookies=cookies)
    assert removed.status_code == 204
    calls = []

    async def delete(bucket,key):
        async with session_factory() as observer:
            row = await observer.get(AttachmentGcObject,(bucket,key))
            assert row is not None and row.deleted_at is None
            assert await attachment_bytes_for_user(observer,user_id=uuid.UUID(user_id)) == 60
        calls.append(key)

    monkeypatch.setattr(gc,"delete_attachment_object",delete)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
    assert result["objects_deleted"] == 1 and len(calls) == 1
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db,user_id=uuid.UUID(user_id)) == 0
        row = await db.get(CuratedPlanAttachment,uuid.UUID(file["attachment_id"]))
        assert row.purged_at is not None


async def test_failed_object_delete_is_durable_and_retryable(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client,cookies)
    file = await _file(client,cookies,user_id,trip)
    await client.delete(f"/trips/{trip}/attachments/{file['attachment_id']}",cookies=cookies)

    async def failed(bucket,key):
        raise ClientError({"Error":{"Code":"AccessDenied","Message":"private never expose"}}, "DeleteObject")
    monkeypatch.setattr(gc,"delete_attachment_object",failed)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_failed"] == 1
        assert await attachment_bytes_for_user(db,user_id=uuid.UUID(user_id)) == 60
        row = await db.get(AttachmentGcObject,(file["bucket"],file["storage_key"]))
        assert row.last_error_code == "AccessDenied" and row.attempts == 1

    async def success(bucket,key):
        return None
    monkeypatch.setattr(gc,"delete_attachment_object",success)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["objects_deleted"] == 1
        row = await db.get(AttachmentGcObject,(file["bucket"],file["storage_key"]))
        assert row.attempts == 2 and row.last_error_code is None
        assert await attachment_bytes_for_user(db,user_id=uuid.UUID(user_id)) == 0


async def test_expired_source_purge_preserves_live_copy_object(
    client, verified_user, auth_cookies, session_factory, monkeypatch
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip = await _make_trip(client,cookies)
    await _file(client,cookies,user_id,trip)
    copy = await client.post(f"/trips/{trip}/copy",json={"scope":"all"},cookies=cookies)
    assert copy.status_code == 201, copy.text
    other = copy.json()["data"]["trip"]["trip_id"]
    await _trash(session_factory,trip,31)
    calls = []

    async def delete(bucket,key):
        calls.append(key)
    monkeypatch.setattr(gc,"delete_attachment_object",delete)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["trips_deleted"] == 1 and calls == []
        assert await db.get(Trip,uuid.UUID(trip)) is None
        assert await attachment_bytes_for_user(db,user_id=uuid.UUID(user_id)) == 60
    await _trash(session_factory,other,31)
    async with session_factory() as db:
        result = await gc.execute_attachment_retention(db)
        assert result["trips_deleted"] == 1 and len(calls) == 1
        assert await attachment_bytes_for_user(db,user_id=uuid.UUID(user_id)) == 0


async def _upload_url(client,cookies,size=60):
    result = await client.post("/storage/upload-urls", cookies=cookies, json={
        "purpose":"trip_attachment","filename":"retained.jpg","content_type":"image/jpeg","content_length":size,
    })
    assert result.status_code == 200, result.text
    return result.json()["data"]


async def _put(client,url,size=60):
    from urllib.parse import urlsplit
    return await client.put(urlsplit(url).path,content=b"x"*size,headers={"content-type":"image/jpeg"})


async def test_upload_reservation_transfers_once_and_failed_registration_keeps_charge(
    client,verified_user,auth_cookies,session_factory,monkeypatch
):
    from app.api.v1 import storage
    from app.models.storage_lifecycle import AttachmentUploadIntent
    from app.models.user import User
    user_id,_ = verified_user
    cookies=auth_cookies(user_id)
    trip=await _make_trip(client,cookies)
    async with session_factory() as db:
        user=await db.get(User,uuid.UUID(user_id))
        user.user_attachment_quota_bytes_override=100
        user.trip_attachment_quota_bytes_override=50
        await db.commit()
    up=await _upload_url(client,cookies)
    blocked=await client.post("/storage/upload-urls",cookies=cookies,json={
        "purpose":"trip_attachment","filename":"second.jpg","content_type":"image/jpeg","content_length":50,
    })
    assert blocked.status_code==409,blocked.text
    monkeypatch.setattr(storage,"put_storage_object",lambda **kwargs:None)
    assert (await _put(client,up["upload_url"])).status_code==204
    payload={**_attachment_payload(user_id,byte_size=60),"bucket":up["bucket"],"storage_key":up["storage_key"]}
    bad=await client.post(f"/trips/{trip}/attachments",json=payload,cookies=cookies)
    assert bad.status_code==409,bad.text
    async with session_factory() as db:
        intent=await db.get(AttachmentUploadIntent,(up["bucket"],up["storage_key"]))
        assert intent.registered_at is None
        assert await attachment_bytes_for_user(db,user_id=uuid.UUID(user_id))==60
        user=await db.get(User,uuid.UUID(user_id))
        user.trip_attachment_quota_bytes_override=100
        await db.commit()
    good=await client.post(f"/trips/{trip}/attachments",json=payload,cookies=cookies)
    assert good.status_code==201,good.text
    assert (await _put(client,up["upload_url"])).status_code==422
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db,user_id=uuid.UUID(user_id))==60


async def test_expired_unregistered_upload_is_collected_and_late_reference_denied(
    client,verified_user,auth_cookies,session_factory,monkeypatch
):
    from app.models.storage_lifecycle import AttachmentUploadIntent
    user_id,_=verified_user
    cookies=auth_cookies(user_id)
    trip=await _make_trip(client,cookies)
    up=await _upload_url(client,cookies)
    async with session_factory() as db:
        intent=await db.get(AttachmentUploadIntent,(up["bucket"],up["storage_key"]))
        intent.expires_at=datetime.now(UTC)-timedelta(seconds=1)
        await db.commit()
    calls=[]
    async def delete(bucket,key): calls.append(key)
    monkeypatch.setattr(gc,"delete_attachment_object",delete)
    async with session_factory() as db:
        result=await gc.execute_attachment_retention(db)
        assert result["objects_deleted"]==1 and calls==[up["storage_key"]]
        assert await attachment_bytes_for_user(db,user_id=uuid.UUID(user_id))==0
    payload={**_attachment_payload(user_id,byte_size=60),"bucket":up["bucket"],"storage_key":up["storage_key"]}
    late=await client.post(f"/trips/{trip}/attachments",cookies=cookies,json=payload)
    assert late.status_code==422,late.text


@pytest.mark.parametrize("kind",["trip","attachment"])
async def test_moderation_cannot_restore_purge_started_target(
    client,verified_user,auth_cookies,session_factory,monkeypatch,kind
):
    from app.models.moderation import ContentReport
    from app.services.moderation import ContentReportTransitionError, _restore_target
    user_id,_=verified_user
    cookies=auth_cookies(user_id)
    trip=await _make_trip(client,cookies)
    file=await _file(client,cookies,user_id,trip)
    if kind=="trip":
        await _trash(session_factory,trip,31)
        async with session_factory() as db:
            await gc._stage(db,datetime.now(UTC),20)
        target_id=uuid.UUID(trip)
    else:
        await client.delete(f"/trips/{trip}/attachments/{file['attachment_id']}",cookies=cookies)
        async with session_factory() as db:
            await gc._stage(db,datetime.now(UTC),20)
        target_id=uuid.UUID(file["attachment_id"])
    report=ContentReport(target_type=kind,target_id=target_id,target_snapshot={"status":"draft","visibility":"public"})
    async with session_factory() as db:
        with pytest.raises(ContentReportTransitionError):
            await _restore_target(db,report)
        await db.rollback()


async def test_cancelled_put_keeps_object_lock_until_actual_write_finishes(
    client,verified_user,auth_cookies,session_factory,monkeypatch
):
    import asyncio
    import threading

    from app.api.v1 import storage
    from app.models.storage_lifecycle import AttachmentUploadIntent

    user_id,_=verified_user
    cookies=auth_cookies(user_id)
    up=await _upload_url(client,cookies)
    async with session_factory() as db:
        row=await db.get(AttachmentUploadIntent,(up["bucket"],up["storage_key"]))
        row.expires_at=datetime.now(UTC)-timedelta(seconds=1)
        await db.commit()
    started=threading.Event()
    finish=threading.Event()
    objects={}
    def slow_put(**kwargs):
        started.set()
        assert finish.wait(10)
        objects[up["storage_key"]]=kwargs["body"]
    async def delete(bucket,key): objects.pop(key,None)
    monkeypatch.setattr(storage,"put_storage_object",slow_put)
    monkeypatch.setattr(gc,"delete_attachment_object",delete)
    put=asyncio.create_task(_put(client,up["upload_url"]))
    try:
        assert await asyncio.to_thread(started.wait,10)
        put.cancel()
        await asyncio.sleep(0.05)
        assert not put.done()
        async with session_factory() as db:
            result=await gc.execute_attachment_retention(db)
            assert result["objects_deleted"]==0
            assert await db.get(AttachmentGcObject,(up["bucket"],up["storage_key"])) is None
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await put
    async with session_factory() as db:
        result=await gc.execute_attachment_retention(db)
        assert result["objects_deleted"]==1 and not objects
