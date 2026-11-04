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
