"""일자 날짜·메모 및 여행 휴지통 복원 회귀 (#633/#640/#649)."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.models.trip import Trip
from app.models.user import User
from tests.integration.test_pois_reorder import _add_poi
from tests.integration.test_trips_api import _attachment_payload, _create_verified_user

pytestmark = pytest.mark.asyncio


async def _trip(client, cookies, *, end_date="2026-11-04"):
    result = await client.post(
        "/trips",
        json={
            "title": "일자와 복원",
            "start_date": "2026-11-03",
            "end_date": end_date,
            "visibility": "public",
        },
        cookies=cookies,
    )
    assert result.status_code == 201, result.text
    return result.json()["data"]["trip_id"]


async def test_derived_dates_conflict_and_note_survives_shared_view(
    client, verified_user, auth_cookies
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    invalid = await client.patch(
        f"/trips/{trip_id}/days/2",
        json={"date": "2026-11-03", "note": "저장되면 안 됨"},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["error"]["message"] == "이미 1일차에서 쓰는 날짜입니다."
    note = await client.patch(
        f"/trips/{trip_id}/days/1",
        json={"note": "첫째 날 메모\n맛집 예약", "date": None},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert note.status_code == 200, note.text
    share = await client.post(f"/trips/{trip_id}/share-tokens", json={}, cookies=cookies)
    token = share.json()["data"]["token"]
    view = await client.get(f"/trips/{trip_id}/shared/{token}", cookies=cookies)
    assert view.status_code == 200, view.text
    days = view.json()["data"]["days"]
    assert days[0]["note"] == "첫째 날 메모\n맛집 예약"
    assert days[1]["note"] is None and days[1]["version"] == 1
    assert days[1]["date"] is None and days[1]["effective_date"] == "2026-11-04"


async def test_clearing_override_checks_derived_date_and_version_first(
    client, verified_user, auth_cookies
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies, end_date="2026-11-05")
    deleted = await client.delete(
        f"/trips/{trip_id}/days/3", headers={"If-Match": "1"}, cookies=cookies
    )
    assert deleted.status_code == 204
    for day, value in [(2, "2026-11-05"), (1, "2026-11-04")]:
        updated = await client.patch(
            f"/trips/{trip_id}/days/{day}",
            json={"date": value},
            headers={"If-Match": "1"},
            cookies=cookies,
        )
        assert updated.status_code == 200, updated.text
    reset = await client.patch(
        f"/trips/{trip_id}/days/2", json={"date": None}, headers={"If-Match": "2"}, cookies=cookies
    )
    assert reset.status_code == 422, reset.text
    stale = await client.patch(
        f"/trips/{trip_id}/days/2", json={"date": None}, headers={"If-Match": "1"}, cookies=cookies
    )
    assert stale.status_code == 409, stale.text


async def test_concurrent_day_dates_cannot_become_duplicates(client, verified_user, auth_cookies):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies, end_date="2026-11-05")
    result = await client.delete(
        f"/trips/{trip_id}/days/2", headers={"If-Match": "1"}, cookies=cookies
    )
    assert result.status_code == 204
    results = await asyncio.gather(
        *[
            client.patch(
                f"/trips/{trip_id}/days/{day}",
                json={"date": "2026-11-04"},
                headers={"If-Match": "1"},
                cookies=cookies,
            )
            for day in (1, 3)
        ]
    )
    assert sorted(r.status_code for r in results) == [200, 422], [r.text for r in results]


async def test_owner_trash_restore_preserves_days_pois_files_and_sharing(
    client, verified_user, auth_cookies, session_factory
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    poi = await _add_poi(
        client,
        cookies,
        trip_id,
        sort_order="a0",
        feature_id=None,
        user_note="장소 메모",
        budget_amount="12000",
    )
    poi_id = poi["attachment_id"]
    attachment = await client.post(
        f"/trips/{trip_id}/pois/{poi_id}/attachments",
        json=_attachment_payload(user_id, "restore.jpg", purpose="poi_attachment"),
        cookies=cookies,
    )
    assert attachment.status_code == 201, attachment.text
    share = await client.post(f"/trips/{trip_id}/share-tokens", json={}, cookies=cookies)
    token = share.json()["data"]["token"]
    removed = await client.request(
        "DELETE", f"/trips/{trip_id}", json={"mode": "soft_delete"}, cookies=cookies
    )
    assert removed.status_code == 204
    hidden = await client.get(f"/trips/{trip_id}/shared/{token}", cookies=cookies)
    assert hidden.status_code == 404
    trash = await client.get("/trips?bucket=all&trashed=true", cookies=cookies)
    assert trash.status_code == 200, trash.text
    assert [x["trip_id"] for x in trash.json()["data"]] == [trip_id]
    other_id = await _create_verified_user(session_factory, "trash-outsider@example.com")
    other = auth_cookies(other_id)
    outsider_list = await client.get("/trips?bucket=all&trashed=true", cookies=other)
    assert outsider_list.json()["data"] == []
    denied = await client.post(f"/trips/{trip_id}/restore", cookies=other)
    assert denied.status_code == 404, denied.text
    restored = await client.post(f"/trips/{trip_id}/restore", cookies=cookies)
    assert restored.status_code == 200, restored.text
    assert restored.json()["data"]["status"] == "draft"
    assert restored.json()["data"]["visibility"] == "public"
    view = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert len(view.json()["data"]["days"]) == 2
    stored_poi = view.json()["data"]["days"][0]["pois"][0]
    assert stored_poi["poi_id"] == poi_id and stored_poi["user_note"] == "장소 메모"
    files = await client.get("/users/me/files", cookies=cookies)
    assert files.json()["data"]["total"] == 1
    re_shared = await client.get(f"/trips/{trip_id}/shared/{token}", cookies=cookies)
    assert re_shared.status_code == 200
    repeated = await client.post(f"/trips/{trip_id}/restore", cookies=cookies)
    assert repeated.status_code == 404


async def test_restore_does_not_add_storage_even_if_current_quota_is_lower(
    client, verified_user, auth_cookies, session_factory
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    attached = await client.post(
        f"/trips/{trip_id}/attachments", json=_attachment_payload(user_id), cookies=cookies
    )
    assert attached.status_code == 201
    removed = await client.request(
        "DELETE", f"/trips/{trip_id}", json={"mode": "soft_delete"}, cookies=cookies
    )
    assert removed.status_code == 204
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.user_attachment_quota_bytes_override = 100
        await db.commit()
    restored = await client.post(f"/trips/{trip_id}/restore", cookies=cookies)
    assert restored.status_code == 200, restored.text
    async with session_factory() as db:
        trip = await db.get(Trip, uuid.UUID(trip_id))
        assert trip.deleted_at is None and trip.status == "draft"


async def test_concurrent_restores_preserve_already_charged_bytes(
    client, verified_user, auth_cookies, session_factory
):
    from app.services.storage_policy import attachment_bytes_for_user

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_ids = []
    for _ in range(2):
        trip_id = await _trip(client, cookies)
        trip_ids.append(trip_id)
        file = await client.post(
            f"/trips/{trip_id}/attachments",
            json=_attachment_payload(user_id, byte_size=60),
            cookies=cookies,
        )
        assert file.status_code == 201, file.text
        deleted = await client.request(
            "DELETE", f"/trips/{trip_id}", json={"mode": "soft_delete"}, cookies=cookies
        )
        assert deleted.status_code == 204
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.user_attachment_quota_bytes_override = 100
        await db.commit()
    results = await asyncio.gather(
        *[client.post(f"/trips/{trip_id}/restore", cookies=cookies) for trip_id in trip_ids]
    )
    assert sorted(r.status_code for r in results) == [200, 200], [r.text for r in results]
    async with session_factory() as db:
        assert await attachment_bytes_for_user(db, user_id=uuid.UUID(user_id)) == 120


async def test_restore_preserves_collaborator_charge_without_new_storage(
    client, verified_user, auth_cookies, session_factory
):
    from datetime import UTC, datetime

    from app.models.companion import TripCompanion

    owner_id, _ = verified_user
    owner = auth_cookies(owner_id)
    trip_id = await _trip(client, owner)
    uploader_id = await _create_verified_user(session_factory, "trash-uploader@example.com")
    uploader = auth_cookies(uploader_id)
    async with session_factory() as db:
        db.add(
            TripCompanion(
                trip_id=uuid.UUID(trip_id),
                user_id=uuid.UUID(uploader_id),
                role="editor",
                invited_at=datetime.now(UTC),
                joined_at=datetime.now(UTC),
            )
        )
        await db.commit()
    uploaded = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(uploader_id, byte_size=60),
        cookies=uploader,
    )
    assert uploaded.status_code == 201, uploaded.text
    deleted = await client.request(
        "DELETE", f"/trips/{trip_id}", json={"mode": "soft_delete"}, cookies=owner
    )
    assert deleted.status_code == 204
    other_trip_id = await _trip(client, uploader)
    own_file = await client.post(
        f"/trips/{other_trip_id}/attachments",
        json=_attachment_payload(uploader_id, byte_size=60),
        cookies=uploader,
    )
    assert own_file.status_code == 201, own_file.text
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(uploader_id))
        user.user_attachment_quota_bytes_override = 100
        await db.commit()
    restored = await client.post(f"/trips/{trip_id}/restore", cookies=owner)
    assert restored.status_code == 200, restored.text
    async with session_factory() as db:
        trip = await db.get(Trip, uuid.UUID(trip_id))
        assert trip.deleted_at is None
    denied = await client.post(
        f"/trips/{other_trip_id}/attachments",
        json=_attachment_payload(uploader_id, byte_size=1),
        cookies=uploader,
    )
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "ATTACHMENT_QUOTA_EXCEEDED"


async def test_poi_auto_day_creation_cannot_duplicate_derived_date(
    client, verified_user, auth_cookies
):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    deleted = await client.delete(
        f"/trips/{trip_id}/days/2", headers={"If-Match": "1"}, cookies=cookies
    )
    assert deleted.status_code == 204
    override = await client.patch(
        f"/trips/{trip_id}/days/1",
        json={"date": "2026-11-04"},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert override.status_code == 200, override.text
    auto_create = await client.post(
        f"/trips/{trip_id}/pois", json={"day_index": 2, "sort_order": "a0"}, cookies=cookies
    )
    assert auto_create.status_code == 422, auto_create.text
    view = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert len(view.json()["data"]["days"]) == 1


async def test_admin_poi_auto_day_validation_is_422_not_500(
    client, verified_user, auth_cookies, session_factory
):
    from tests.integration.test_admin_pois_api import _create_user

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _trip(client, cookies)
    deleted = await client.delete(
        f"/trips/{trip_id}/days/2", headers={"If-Match": "1"}, cookies=cookies
    )
    assert deleted.status_code == 204
    changed = await client.patch(
        f"/trips/{trip_id}/days/1",
        json={"date": "2026-11-04"},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert changed.status_code == 200
    admin_id = await _create_user(session_factory, email="days-admin@example.com", roles=["admin"])
    created = await client.post(
        "/admin/pois",
        json={
            "trip_id": trip_id,
            "day_index": 2,
            "sort_order": "a0",
            "access_reason": "날짜 검증",
        },
        cookies=auth_cookies(str(admin_id)),
    )
    assert created.status_code == 422, created.text
    assert created.json()["error"]["code"] == "VALIDATION_ERROR"
    assert created.json()["error"]["message"] == "이미 1일차에서 쓰는 날짜입니다."
