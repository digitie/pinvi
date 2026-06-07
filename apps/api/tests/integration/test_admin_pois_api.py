"""Admin POI 관리 API 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.audit import AdminAuditLog
from app.models.poi import TripDayPoi
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


async def _create_poi_fixture(
    session_factory,
    *,
    owner_id: uuid.UUID,
    added_by_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    now = datetime.now(UTC)
    trip_id = uuid.uuid4()
    active_poi_id = uuid.uuid4()
    broken_poi_id = uuid.uuid4()
    async with session_factory() as db:
        trip = Trip(
            trip_id=trip_id,
            owner_user_id=owner_id,
            title="부산 가족 여행",
            description="POI 운영 확인",
            region_hint="부산",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
            visibility="private",
            status="planned",
        )
        db.add(trip)
        await db.flush()
        db.add(
            TripDay(
                trip_id=trip.trip_id,
                day_index=1,
                date=date(2026, 7, 1),
                title="1일차",
            )
        )
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    attachment_id=active_poi_id,
                    trip_id=trip.trip_id,
                    day_index=1,
                    sort_order="a0",
                    feature_id="place-haeundae",
                    feature_snapshot={
                        "name": "해운대 해수욕장",
                        "category": "beach",
                    },
                    added_by_user_id=added_by_id,
                    planned_arrival_at=now + timedelta(hours=1),
                    planned_departure_at=now + timedelta(hours=2),
                    user_note="점심 전에 도착",
                    budget_amount=Decimal("12000.00"),
                    actual_amount=Decimal("10000.00"),
                    currency="KRW",
                    user_url="https://example.com/haeundae",
                ),
                TripDayPoi(
                    attachment_id=broken_poi_id,
                    trip_id=trip.trip_id,
                    day_index=1,
                    sort_order="a1",
                    feature_id="place-gwangalli",
                    feature_snapshot={"title": "광안리 야경"},
                    feature_link_broken_at=now,
                    added_by_user_id=owner_id,
                ),
            ]
        )
        await db.commit()
        return trip.trip_id, active_poi_id, broken_poi_id


async def test_admin_pois_list_filters_and_masks_emails(
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
    added_by_id = await _create_user(session_factory, email="planner@example.com")
    trip_id, active_poi_id, _broken_poi_id = await _create_poi_fixture(
        session_factory,
        owner_id=owner_id,
        added_by_id=added_by_id,
    )

    resp = await client.get(
        "/admin/pois?q=해운대&has_broken_link=false",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["total"] == 1
    poi = body["items"][0]
    assert poi["attachment_id"] == str(active_poi_id)
    assert poi["trip_id"] == str(trip_id)
    assert poi["trip_title"] == "부산 가족 여행"
    assert poi["owner_email_masked"] == "o***@example.com"
    assert poi["feature_label"] == "해운대 해수욕장"
    assert poi["feature_link_broken_at"] is None
    assert "owner@example.com" not in resp.text
    assert "planner@example.com" not in resp.text


async def test_admin_pois_list_broken_filter(
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
    added_by_id = await _create_user(session_factory, email="planner@example.com")
    _trip_id, _active_poi_id, broken_poi_id = await _create_poi_fixture(
        session_factory,
        owner_id=owner_id,
        added_by_id=added_by_id,
    )

    resp = await client.get(
        "/admin/pois?has_broken_link=true",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["total"] == 1
    poi = body["items"][0]
    assert poi["attachment_id"] == str(broken_poi_id)
    assert poi["feature_label"] == "광안리 야경"
    assert poi["feature_link_broken_at"] is not None


async def test_admin_poi_detail_returns_snapshot_and_added_by_mask(
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
    added_by_id = await _create_user(session_factory, email="planner@example.com")
    _trip_id, active_poi_id, _broken_poi_id = await _create_poi_fixture(
        session_factory,
        owner_id=owner_id,
        added_by_id=added_by_id,
    )

    resp = await client.get(
        f"/admin/pois/{active_poi_id}",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    poi = resp.json()["data"]
    assert poi["attachment_id"] == str(active_poi_id)
    assert poi["added_by_email_masked"] == "p***@example.com"
    assert poi["feature_snapshot"]["name"] == "해운대 해수욕장"
    assert poi["user_note"] == "점심 전에 도착"
    assert poi["recent_audit"] == []
    assert "planner@example.com" not in resp.text


async def test_admin_poi_link_status_update_writes_audit(
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
    added_by_id = await _create_user(session_factory, email="planner@example.com")
    _trip_id, active_poi_id, _broken_poi_id = await _create_poi_fixture(
        session_factory,
        owner_id=owner_id,
        added_by_id=added_by_id,
    )
    request_id = uuid.uuid4()

    resp = await client.patch(
        f"/admin/pois/{active_poi_id}/link-status",
        json={"broken": True, "access_reason": "feature_id 점검 결과 끊김"},
        headers={"X-Request-Id": str(request_id)},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    poi = resp.json()["data"]
    assert poi["feature_link_broken_at"] is not None
    assert poi["version"] == 2
    assert poi["recent_audit"][0]["action"] == "poi.update_link_status"
    assert poi["recent_audit"][0]["access_reason"] == "feature_id 점검 결과 끊김"

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))
        stored_poi = await db.scalar(
            select(TripDayPoi).where(TripDayPoi.attachment_id == active_poi_id)
        )

    assert audit is not None
    assert audit.actor_user_id == admin_id
    assert audit.resource_type == "poi"
    assert audit.resource_id == str(active_poi_id)
    assert audit.before_state == {"feature_link_broken_at": None}
    assert audit.after_state["feature_link_broken_at"] is not None
    assert stored_poi is not None
    assert stored_poi.feature_link_broken_at is not None


async def test_admin_poi_link_status_rolls_back_when_audit_fails(
    client,
    session_factory,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.v1.admin.pois as admin_pois_router

    admin_id = await _create_user(
        session_factory,
        email="admin@example.com",
        roles=["user", "admin"],
    )
    owner_id = await _create_user(session_factory, email="owner@example.com")
    added_by_id = await _create_user(session_factory, email="planner@example.com")
    _trip_id, active_poi_id, _broken_poi_id = await _create_poi_fixture(
        session_factory,
        owner_id=owner_id,
        added_by_id=added_by_id,
    )

    async def _fail_append(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("audit failed")

    monkeypatch.setattr(admin_pois_router, "append_admin_audit", _fail_append)

    with pytest.raises(RuntimeError, match="audit failed"):
        await client.patch(
            f"/admin/pois/{active_poi_id}/link-status",
            json={"broken": True, "access_reason": "테스트 감사 실패"},
            cookies=auth_cookies(str(admin_id)),
        )

    async with session_factory() as db:
        poi = await db.scalar(select(TripDayPoi).where(TripDayPoi.attachment_id == active_poi_id))
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.resource_id == str(active_poi_id))
        )

    assert poi is not None
    assert poi.feature_link_broken_at is None
    assert poi.version == 1
    assert audit is None
