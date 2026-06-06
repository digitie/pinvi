"""Admin 여행 관리 API 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AdminAuditLog
from app.models.companion import TripCompanion
from app.models.poi import TripDayPoi
from app.models.share_link import TripShareLink
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory,
    *,
    email: str,
    nickname: str | None = None,
    roles: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash="x",
            nickname=nickname,
            status="active",
            roles=roles or ["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _create_trip_fixture(
    session_factory,
    *,
    owner_id: uuid.UUID,
    title: str = "부산 가족 여행",
    region_hint: str = "부산",
    status: str = "planned",
    visibility: str = "private",
) -> uuid.UUID:
    now = datetime.now(UTC)
    async with session_factory() as db:
        trip = Trip(
            owner_user_id=owner_id,
            title=title,
            description="운영자가 확인할 여행 상세",
            region_hint=region_hint,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
            visibility=visibility,
            status=status,
        )
        db.add(trip)
        await db.flush()
        db.add_all(
            [
                TripDay(
                    trip_id=trip.trip_id,
                    day_index=1,
                    date=date(2026, 7, 1),
                    title="1일차",
                ),
                TripDay(
                    trip_id=trip.trip_id,
                    day_index=2,
                    date=date(2026, 7, 2),
                    title="2일차",
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    trip_id=trip.trip_id,
                    day_index=1,
                    sort_order="a0",
                    feature_id="feature-place-1",
                    feature_snapshot={"name": "해운대"},
                    added_by_user_id=owner_id,
                ),
                TripCompanion(
                    trip_id=trip.trip_id,
                    invited_email="friend@example.com",
                    invited_nickname="친구",
                    role="editor",
                    invited_at=now,
                    joined_at=None,
                ),
                TripShareLink(
                    trip_id=trip.trip_id,
                    token_hash=f"token-{uuid.uuid4().hex}",
                    created_by_user_id=owner_id,
                    visibility="view_only",
                    expires_at=now + timedelta(days=7),
                ),
            ]
        )
        await db.commit()
        return trip.trip_id


async def test_admin_trips_list_filters_counts_and_masks_owner(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin@example.com",
        nickname="관리자",
        roles=["user", "admin"],
    )
    owner_id = await _create_user(
        session_factory,
        email="owner@example.com",
        nickname="소유자",
    )
    await _create_trip_fixture(session_factory, owner_id=owner_id)
    await _create_trip_fixture(
        session_factory,
        owner_id=owner_id,
        title="제주 완료 여행",
        region_hint="제주",
        status="completed",
        visibility="public",
    )

    resp = await client.get(
        "/admin/trips?q=부산&status_filter=planned&visibility_filter=private",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["total"] == 1
    trip = body["items"][0]
    assert trip["title"] == "부산 가족 여행"
    assert trip["owner_email_masked"] == "o***@example.com"
    assert "owner@example.com" not in resp.text
    assert trip["day_count"] == 2
    assert trip["poi_count"] == 1
    assert trip["companion_count"] == 1
    assert trip["share_link_count"] == 1


async def test_admin_trip_detail_returns_companions_share_links_and_audit(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin@example.com",
        roles=["user", "admin"],
    )
    owner_id = await _create_user(session_factory, email="owner@example.com")
    trip_id = await _create_trip_fixture(session_factory, owner_id=owner_id)

    resp = await client.get(
        f"/admin/trips/{trip_id}",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    trip = resp.json()["data"]
    assert trip["trip_id"] == str(trip_id)
    assert trip["description"] == "운영자가 확인할 여행 상세"
    assert trip["companions"][0]["invited_email_masked"] == "f***@example.com"
    assert trip["companions"][0]["role"] == "editor"
    assert trip["share_links"][0]["visibility"] == "view_only"
    assert trip["recent_audit"] == []


async def test_admin_trip_status_update_writes_audit(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin@example.com",
        roles=["user", "admin"],
    )
    owner_id = await _create_user(session_factory, email="owner@example.com")
    trip_id = await _create_trip_fixture(session_factory, owner_id=owner_id)
    request_id = uuid.uuid4()

    resp = await client.patch(
        f"/admin/trips/{trip_id}/status",
        json={"status": "archived", "access_reason": "운영 정책 위반 처리"},
        headers={"X-Request-Id": str(request_id)},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    trip = resp.json()["data"]
    assert trip["status"] == "archived"
    assert trip["version"] == 2
    assert trip["recent_audit"][0]["action"] == "trip.update_status"
    assert trip["recent_audit"][0]["access_reason"] == "운영 정책 위반 처리"

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))

    assert audit is not None
    assert audit.actor_user_id == admin_id
    assert audit.resource_type == "trip"
    assert audit.resource_id == str(trip_id)
    assert audit.before_state == {"status": "planned"}
    assert audit.after_state == {"status": "archived"}
