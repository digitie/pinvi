from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import create_app
from app.models.trip import PlanPoiAttachment, Trip, TripDay, TripPoi
from app.models.user import User
from app.services.admin_auth import hash_password
from app.services.file_storage import RustfsObject, RustfsObjectListing, RustfsStorage

KST = ZoneInfo("Asia/Seoul")


def test_user_can_attach_files_to_trip_and_poi(db_session: Session) -> None:
    user = _user(db_session, "planner@example.com")
    trip, poi = _trip_with_poi(db_session, user)
    client = _build_client(db_session)
    _login_user(client, user.email)

    trip_response = client.post(
        f"/trips/{trip.id}/attachments",
        json=_attachment_payload("plan.pdf", "user-uploads/plan_attachment/a.pdf"),
    )

    assert trip_response.status_code == 201
    trip_payload = trip_response.json()
    assert trip_payload["trip_id"] == str(trip.id)
    assert trip_payload["trip_poi_id"] is None

    poi_response = client.post(
        f"/trips/{trip.id}/pois/{poi.id}/attachments",
        json=_attachment_payload("poi.jpg", "user-uploads/poi_attachment/a.jpg"),
    )

    assert poi_response.status_code == 201
    assert poi_response.json()["trip_poi_id"] == str(poi.id)

    list_response = client.get(f"/trips/{trip.id}/attachments")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    delete_response = client.delete(f"/trips/{trip.id}/attachments/{trip_payload['id']}")
    assert delete_response.status_code == 204
    deleted = db_session.get(PlanPoiAttachment, trip_payload["id"])
    assert deleted is not None
    assert deleted.deleted_at is not None


def test_notice_attachments_are_copied_to_user_trip(db_session: Session) -> None:
    admin = _user(db_session, "admin@example.com", is_admin=True)
    user = _user(db_session, "planner@example.com")
    client = _build_client(db_session)
    _login_admin(client, admin.email)

    plan_response = client.post(
        "/admin/notice-plans",
        json={
            "slug": "heritage-files",
            "title": "국가유산투어",
            "category": "heritage",
            "is_published": True,
            "pois": [
                {
                    "day_index": 1,
                    "sort_order": "0001",
                    "snapshot": {"name": "경복궁"},
                }
            ],
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()
    poi = plan["pois"][0]

    plan_attachment_response = client.post(
        f"/admin/notice-plans/{plan['id']}/attachments",
        json=_attachment_payload("guide.pdf", "user-uploads/notice_plan_attachment/guide.pdf"),
    )
    assert plan_attachment_response.status_code == 201

    poi_attachment_response = client.post(
        f"/admin/notice-plans/{plan['id']}/pois/{poi['id']}/attachments",
        json=_attachment_payload("spot.jpg", "user-uploads/notice_poi_attachment/spot.jpg"),
    )
    assert poi_attachment_response.status_code == 201

    _login_user(client, user.email)
    copy_response = client.post(f"/notice-plans/{plan['id']}/copy", json={})
    assert copy_response.status_code == 200
    target_trip_id = UUID(copy_response.json()["target_trip_id"])
    copied_poi_id = UUID(copy_response.json()["copied_poi_ids"][0])

    trip_attachment = db_session.scalar(
        select(PlanPoiAttachment).where(PlanPoiAttachment.trip_id == target_trip_id)
    )
    assert trip_attachment is not None
    assert str(trip_attachment.source_attachment_id) == plan_attachment_response.json()["id"]
    assert trip_attachment.storage_key.endswith("guide.pdf")

    poi_attachment = db_session.scalar(
        select(PlanPoiAttachment).where(PlanPoiAttachment.trip_poi_id == copied_poi_id)
    )
    assert poi_attachment is not None
    assert str(poi_attachment.source_attachment_id) == poi_attachment_response.json()["id"]
    assert poi_attachment.storage_key.endswith("spot.jpg")


def test_admin_can_list_and_delete_rustfs_objects(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = _user(db_session, "admin@example.com", is_admin=True)
    client = _build_client(db_session)
    _login_admin(client, admin.email)
    deleted: list[str] = []

    def fake_list_objects(
        self: RustfsStorage,
        *,
        prefix: str = "",
        max_keys: int = 100,
        continuation_token: str | None = None,
        bucket: str | None = None,
    ) -> RustfsObjectListing:
        return RustfsObjectListing(
            bucket=bucket or self.bucket,
            prefix=prefix,
            objects=(
                RustfsObject(
                    key=f"{prefix}sample.pdf",
                    size=1234,
                    last_modified=datetime(2026, 5, 22, 9, 0, tzinfo=KST),
                    etag="abc",
                    storage_class="STANDARD",
                ),
            ),
            is_truncated=False,
            next_continuation_token=continuation_token,
        )

    def fake_delete_object(
        self: RustfsStorage,
        storage_key: str,
        *,
        bucket: str | None = None,
    ) -> None:
        deleted.append(storage_key)

    monkeypatch.setattr(RustfsStorage, "list_objects", fake_list_objects)
    monkeypatch.setattr(RustfsStorage, "delete_object", fake_delete_object)

    response = client.get("/admin/rustfs/objects?prefix=user-uploads/&limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["objects"][0]["key"] == "user-uploads/sample.pdf"

    delete_response = client.delete("/admin/rustfs/objects?key=user-uploads/sample.pdf")
    assert delete_response.status_code == 204
    assert deleted == ["user-uploads/sample.pdf"]


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _user(db_session: Session, email: str, *, is_admin: bool = False) -> User:
    user = User(
        email=email,
        password_hash=hash_password("strong-password-1"),
        display_name=email,
        email_verified_at=datetime(2026, 5, 22, 9, 0, tzinfo=KST),
        account_status="active",
        system_role="admin" if is_admin else "planner",
        nickname=email,
        name=email,
        is_active=True,
        is_admin=is_admin,
        is_privileged=is_admin,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _trip_with_poi(db_session: Session, user: User) -> tuple[Trip, TripPoi]:
    trip = Trip(
        user_id=user.id,
        leader_id=user.id,
        title="서울 여행",
        name="서울 여행",
        destination="서울",
        fuel_types=[],
        planning_status="planning",
    )
    db_session.add(trip)
    db_session.flush()
    db_session.add(TripDay(trip_id=trip.id, day_index=1, date=None))
    poi = TripPoi(
        trip_id=trip.id,
        day_index=1,
        sort_order="0001",
        snapshot={"name": "경복궁"},
        added_by_user_id=user.id,
        currency="KRW",
        version=1,
    )
    db_session.add(poi)
    db_session.flush()
    return trip, poi


def _attachment_payload(filename: str, storage_key: str) -> dict[str, object]:
    content_type = "application/pdf" if filename.endswith(".pdf") else "image/jpeg"
    return {
        "bucket": "tripmate-media",
        "storage_key": storage_key,
        "original_filename": filename,
        "content_type": content_type,
        "byte_size": 1234,
        "public_url": None,
        "role": "document" if content_type == "application/pdf" else "image",
        "sort_order": 0,
    }


def _login_admin(client: TestClient, email: str) -> None:
    response = client.post(
        "/admin/auth/login",
        json={"email": email, "password": "strong-password-1"},
    )
    assert response.status_code == 200


def _login_user(client: TestClient, email: str) -> None:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "strong-password-1"},
    )
    assert response.status_code == 200
