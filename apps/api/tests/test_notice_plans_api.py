from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import create_app
from app.models.trip import Trip, TripDay, TripPoi
from app.models.user import User
from app.services.admin_auth import hash_password

KST = ZoneInfo("Asia/Seoul")


def test_admin_notice_plan_can_be_copied_to_periodless_user_trip(
    db_session: Session,
) -> None:
    admin = _user(db_session, "admin@ad.min", is_admin=True)
    planner = _user(db_session, "planner@example.com")
    client = _build_client(db_session)
    _login_admin(client, admin.email)

    create_response = client.post(
        "/admin/notice-plans",
        json={
            "slug": "heritage-tour",
            "title": "국가유산투어",
            "category": "heritage",
            "summary": "관리자 추천 국가유산 코스",
            "source_name": "TripMate Admin",
            "is_published": True,
            "pois": [
                {
                    "day_index": 1,
                    "sort_order": "0001",
                    "feature_id": "heritage:seoul:1",
                    "snapshot": {"name": "경복궁", "provider": "python-krheritage-api"},
                    "memo": "오전 방문 추천",
                    "currency": "KRW",
                }
            ],
        },
    )

    assert create_response.status_code == 201
    plan = create_response.json()
    assert plan["starts_on"] is None
    assert plan["ends_on"] is None

    _login_user(client, planner.email)
    list_response = client.get("/notice-plans")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    copy_response = client.post(f"/notice-plans/{plan['id']}/copy", json={})

    assert copy_response.status_code == 200
    trip = db_session.get(Trip, copy_response.json()["target_trip_id"])
    assert trip is not None
    assert trip.user_id == planner.id
    assert trip.start_date is None
    assert trip.end_date is None

    trip_day = db_session.scalar(select(TripDay).where(TripDay.trip_id == trip.id))
    assert trip_day is not None
    assert trip_day.day_index == 1
    assert trip_day.date is None

    poi = db_session.scalar(select(TripPoi).where(TripPoi.trip_id == trip.id))
    assert poi is not None
    assert poi.feature_id is None
    assert poi.feature_link_broken_at is not None
    assert poi.snapshot["notice_feature_id"] == "heritage:seoul:1"
    assert poi.snapshot["copied_from"] == "notice_plan"
    assert poi.snapshot["name"] == "경복궁"


def test_unpublished_notice_plan_is_admin_only(db_session: Session) -> None:
    admin = _user(db_session, "admin@ad.min", is_admin=True)
    planner = _user(db_session, "planner@example.com")
    client = _build_client(db_session)
    _login_admin(client, admin.email)

    create_response = client.post(
        "/admin/notice-plans",
        json={
            "slug": "hidden-arboretum",
            "title": "수목원 투어",
            "category": "arboretum",
            "is_published": False,
        },
    )
    assert create_response.status_code == 201
    plan_id = create_response.json()["id"]

    _login_user(client, planner.email)
    assert client.get("/notice-plans").json()["total"] == 0
    assert client.get(f"/notice-plans/{plan_id}").status_code == 404


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _user(db_session: Session, email: str, *, is_admin: bool = False) -> User:
    existing = db_session.scalar(select(User).where(User.email == email))
    if existing is not None:
        existing.password_hash = hash_password("strong-password-1")
        existing.account_status = "active"
        existing.system_role = "admin" if is_admin else "planner"
        existing.is_active = True
        existing.is_admin = is_admin
        existing.is_privileged = is_admin
        existing.email_verified_at = datetime(2026, 5, 21, 9, 0, tzinfo=KST)
        db_session.flush()
        return existing

    user = User(
        email=email,
        password_hash=hash_password("strong-password-1"),
        display_name=email,
        email_verified_at=datetime(2026, 5, 21, 9, 0, tzinfo=KST),
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
