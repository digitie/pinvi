"""`/admin/rustfs/*` 객체 관리 통합 테스트 (S3 호출은 monkeypatch) — T-105 #3."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

import app.api.v1.admin.rustfs as rustfs_router

pytestmark = pytest.mark.asyncio


async def _admin(session_factory) -> str:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        user = User(
            email=f"rustfs_{uuid.uuid4().hex[:8]}@tripmate.test",
            password_hash="x",
            nickname="관리자",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.user_id)


async def _seed_attachment(session_factory, *, owner_id: str, storage_key: str) -> None:  # type: ignore[no-untyped-def]
    from app.models.attachment import CuratedPlanAttachment
    from app.models.trip import Trip

    async with session_factory() as db:
        trip = Trip(owner_user_id=uuid.UUID(owner_id), title="ref trip")
        db.add(trip)
        await db.flush()
        db.add(
            CuratedPlanAttachment(
                trip_id=trip.trip_id,
                uploaded_by_user_id=uuid.UUID(owner_id),
                bucket="tripmate-media",
                storage_key=storage_key,
                original_filename="ref.jpg",
                content_type="image/jpeg",
                byte_size=10,
            )
        )
        await db.commit()


async def test_list_rustfs_objects(client, session_factory, auth_cookies, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _admin(session_factory)

    async def fake_list(**kwargs: Any) -> dict[str, Any]:
        return {
            "objects": [{"key": "user-uploads/x.jpg", "size": 10, "etag": '"a"'}],
            "is_truncated": False,
            "next_continuation_token": None,
        }

    monkeypatch.setattr(rustfs_router, "list_objects", fake_list)
    resp = await client.get(
        "/admin/rustfs/objects?prefix=user-uploads/&limit=50", cookies=auth_cookies(admin_id)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["objects"][0]["key"] == "user-uploads/x.jpg"


async def test_delete_referenced_requires_force(
    client, session_factory, auth_cookies, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    admin_id = await _admin(session_factory)
    key = f"user-uploads/{uuid.uuid4().hex}.jpg"
    await _seed_attachment(session_factory, owner_id=admin_id, storage_key=key)

    called: dict[str, bool] = {"deleted": False}

    async def fake_delete(*, key: str) -> None:
        called["deleted"] = True

    monkeypatch.setattr(rustfs_router, "delete_object", fake_delete)

    # 참조 중 + force 없음 → 409, S3 삭제 미호출.
    r1 = await client.request(
        "DELETE", f"/admin/rustfs/objects?key={key}&reason=cleanup", cookies=auth_cookies(admin_id)
    )
    assert r1.status_code == 409, r1.text
    assert r1.json()["error"]["code"] == "OBJECT_REFERENCED"
    assert called["deleted"] is False

    # force=true → 204 + S3 삭제 호출.
    r2 = await client.request(
        "DELETE",
        f"/admin/rustfs/objects?key={key}&reason=cleanup&force=true",
        cookies=auth_cookies(admin_id),
    )
    assert r2.status_code == 204, r2.text
    assert called["deleted"] is True


async def test_non_admin_hidden(client, verified_user, auth_cookies) -> None:  # type: ignore[no-untyped-def]
    user_id, _ = verified_user
    resp = await client.get("/admin/rustfs/objects", cookies=auth_cookies(user_id))
    assert resp.status_code == 404
