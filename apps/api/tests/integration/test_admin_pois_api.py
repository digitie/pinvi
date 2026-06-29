"""Admin POI 관리 API 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.attachment import CuratedPlanAttachment
from app.models.audit import AdminAuditLog
from app.models.comment import TripComment
from app.models.kasi import TripPoiRiseSet
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


async def test_admin_poi_create_writes_audit(
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
    trip_id, _active_poi_id, _broken_poi_id = await _create_poi_fixture(
        session_factory,
        owner_id=owner_id,
        added_by_id=owner_id,
    )
    request_id = uuid.uuid4()

    resp = await client.post(
        "/admin/pois",
        json={
            "trip_id": str(trip_id),
            "day_index": 2,
            "sort_order": "a0",
            "feature_id": "place-gangneung",
            "feature_snapshot": {
                "name": "강릉 커피거리",
                "coord": {"lon": 128.95, "lat": 37.77},
                "address_label": "강원 강릉시",
                "region": {"sigungu_code": "42150"},
            },
            "custom_marker_color": "P-08",
            "custom_marker_icon": "coffee",
            "planned_arrival_at": "2026-07-02T10:00:00+09:00",
            "planned_departure_at": "2026-07-02T11:00:00+09:00",
            "user_note": "운영자 대행 등록",
            "budget_amount": "15000.00",
            "currency": "KRW",
            "user_url": "https://example.com/gangneung",
            "access_reason": "고객센터 요청 대행",
        },
        headers={"X-Request-Id": str(request_id)},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 201, resp.text
    poi = resp.json()["data"]
    poi_id = uuid.UUID(poi["attachment_id"])
    assert poi["trip_id"] == str(trip_id)
    assert poi["day_index"] == 2
    assert poi["feature_label"] == "강릉 커피거리"
    assert poi["added_by_user_id"] == str(admin_id)
    assert poi["added_by_email_masked"] == "a***@example.com"
    assert poi["recent_audit"][0]["action"] == "poi.create"
    assert poi["recent_audit"][0]["access_reason"] == "고객센터 요청 대행"

    async with session_factory() as db:
        stored_poi = await db.scalar(select(TripDayPoi).where(TripDayPoi.attachment_id == poi_id))
        stored_day = await db.scalar(
            select(TripDay).where(TripDay.trip_id == trip_id, TripDay.day_index == 2)
        )
        rise_set = await db.scalar(select(TripPoiRiseSet).where(TripPoiRiseSet.poi_id == poi_id))
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))
        trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id))

    assert stored_poi is not None
    assert stored_poi.added_by_user_id == admin_id
    assert stored_day is not None
    assert stored_day.date == date(2026, 7, 2)
    assert rise_set is not None
    assert audit is not None
    assert audit.action == "poi.create"
    assert audit.resource_id == str(poi_id)
    assert audit.after_state["feature_label"] == "강릉 커피거리"
    assert trip is not None
    assert trip.primary_region_code == "42150"
    assert trip.primary_region_source == "poi_snapshot"


async def test_admin_poi_create_rejects_missing_trip(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin@example.com",
        roles=["user", "admin"],
    )

    resp = await client.post(
        "/admin/pois",
        json={
            "trip_id": str(uuid.uuid4()),
            "day_index": 1,
            "sort_order": "a0",
            "feature_snapshot": {"name": "없는 여행 POI"},
            "access_reason": "여행 없음 검증",
        },
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_admin_poi_create_rolls_back_when_audit_fails(
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
    trip_id, _active_poi_id, _broken_poi_id = await _create_poi_fixture(
        session_factory,
        owner_id=owner_id,
        added_by_id=owner_id,
    )

    async def _fail_append(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("audit failed")

    monkeypatch.setattr(admin_pois_router, "append_admin_audit", _fail_append)

    with pytest.raises(RuntimeError, match="audit failed"):
        await client.post(
            "/admin/pois",
            json={
                "trip_id": str(trip_id),
                "day_index": 2,
                "sort_order": "a9",
                "feature_snapshot": {"name": "감사 실패 POI"},
                "access_reason": "테스트 감사 실패",
            },
            cookies=auth_cookies(str(admin_id)),
        )

    async with session_factory() as db:
        poi = await db.scalar(
            select(TripDayPoi).where(TripDayPoi.feature_snapshot["name"].astext == "감사 실패 POI")
        )
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.action == "poi.create"))

    assert poi is None
    assert audit is None


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


async def test_admin_poi_copy_move_delete_operations_manage_children_and_audit(
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
    copy_request_id = uuid.uuid4()
    move_request_id = uuid.uuid4()
    delete_request_id = uuid.uuid4()

    async with session_factory() as db:
        db.add_all(
            [
                CuratedPlanAttachment(
                    trip_poi_id=active_poi_id,
                    bucket="pinvi-test",
                    storage_key=f"pois/{active_poi_id}/photo.jpg",
                    original_filename="photo.jpg",
                    content_type="image/jpeg",
                    byte_size=100,
                    uploaded_by_user_id=owner_id,
                ),
                TripComment(
                    trip_id=trip_id,
                    author_user_id=owner_id,
                    target_type="poi",
                    target_id=active_poi_id,
                    day_index=1,
                    body="POI 댓글",
                ),
            ]
        )
        await db.commit()

    impact_resp = await client.get(
        f"/admin/pois/{active_poi_id}/operation-impact",
        cookies=auth_cookies(str(admin_id)),
    )

    assert impact_resp.status_code == 200, impact_resp.text
    impact = impact_resp.json()["data"]
    assert impact["counts"]["attachments"] == 1
    orphan = next(
        option
        for option in impact["policy_options"]["attachment_policy"]
        if option["value"] == "orphan"
    )
    assert orphan["allowed"] is False

    copy_resp = await client.post(
        f"/admin/pois/{active_poi_id}/copy",
        json={
            "target_trip_id": str(trip_id),
            "target_day_index": 2,
            "include_attachments": True,
            "access_reason": "POI 복제 테스트",
        },
        headers={"X-Request-Id": str(copy_request_id)},
        cookies=auth_cookies(str(admin_id)),
    )

    assert copy_resp.status_code == 200, copy_resp.text
    copy_result = copy_resp.json()["data"]
    copied_poi_id = uuid.UUID(copy_result["target_id"])
    assert copy_result["action"] == "copy"
    assert copy_result["affected"]["pois"] == 1
    assert copy_result["affected"]["attachments"] == 1

    move_resp = await client.post(
        f"/admin/pois/{active_poi_id}/move",
        json={
            "target_trip_id": str(trip_id),
            "target_day_index": 3,
            "attachment_policy": "move",
            "comment_policy": "move",
            "access_reason": "POI 날짜 이동",
        },
        headers={"X-Request-Id": str(move_request_id)},
        cookies=auth_cookies(str(admin_id)),
    )

    assert move_resp.status_code == 200, move_resp.text
    move_result = move_resp.json()["data"]
    assert move_result["action"] == "move"
    assert move_result["day_index"] == 3
    assert move_result["affected"]["attachments"] == 1
    assert move_result["affected"]["comments"] == 1

    delete_resp = await client.request(
        "DELETE",
        f"/admin/pois/{copied_poi_id}",
        json={
            "attachment_policy": "delete",
            "comment_policy": "delete",
            "access_reason": "복사본 정리",
        },
        headers={"X-Request-Id": str(delete_request_id)},
        cookies=auth_cookies(str(admin_id)),
    )

    assert delete_resp.status_code == 200, delete_resp.text
    delete_result = delete_resp.json()["data"]
    assert delete_result["action"] == "delete"
    assert delete_result["affected"]["pois"] == 1
    assert delete_result["affected"]["attachments"] == 1

    async with session_factory() as db:
        moved_poi = await db.scalar(
            select(TripDayPoi).where(TripDayPoi.attachment_id == active_poi_id)
        )
        copied_poi = await db.scalar(
            select(TripDayPoi).where(TripDayPoi.attachment_id == copied_poi_id)
        )
        moved_comment = await db.scalar(
            select(TripComment).where(TripComment.target_id == active_poi_id)
        )
        copied_attachment = await db.scalar(
            select(CuratedPlanAttachment).where(CuratedPlanAttachment.trip_poi_id == copied_poi_id)
        )
        copy_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == copy_request_id)
        )
        move_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == move_request_id)
        )
        delete_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == delete_request_id)
        )

    assert moved_poi is not None
    assert moved_poi.day_index == 3
    assert moved_comment is not None
    assert moved_comment.day_index == 3
    assert copied_poi is not None
    assert copied_poi.deleted_at is not None
    assert copied_attachment is not None
    assert copied_attachment.deleted_at is not None
    assert copy_audit is not None
    assert copy_audit.action == "poi.copy"
    assert move_audit is not None
    assert move_audit.action == "poi.move"
    assert delete_audit is not None
    assert delete_audit.action == "poi.delete"
