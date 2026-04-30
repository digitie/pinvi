from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import create_app
from app.models.tour import TourServingPublicCulturalFestival
from app.models.trip import Trip, TripDay, TripPlanItem
from app.models.user import User
from app.services.admin_auth import hash_password

KST = ZoneInfo("Asia/Seoul")


def test_authenticated_owner_adds_festival_to_trip_day(db_session: Session) -> None:
    user = _active_user(db_session, "planner@example.com")
    trip, trip_day = _trip_with_day(db_session, user)
    festival = _festival()
    db_session.add(festival)
    db_session.flush()
    client = _build_client(db_session)
    _login(client, "planner@example.com")

    response = client.post(
        f"/trips/{trip.id}/days/{trip_day.id}/items",
        json={
            "resource_type": "festival",
            "festival_id": str(festival.id),
            "note": "저녁 공연 보기",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["resource_type"] == "festival"
    assert payload["festival_id"] == str(festival.id)
    assert payload["title_snapshot"] == "서울 봄 축제"
    assert payload["address_snapshot"] == "서울특별시 종로구 세종대로 1"
    assert payload["longitude"] == "126.97800000"
    assert payload["latitude"] == "37.56650000"
    assert payload["sort_order"] == 1

    item = db_session.scalar(select(TripPlanItem))
    assert item is not None
    assert item.trip_day_id == trip_day.id
    assert item.festival_id == festival.id


def test_trip_plan_item_rejects_non_owner(db_session: Session) -> None:
    owner = _active_user(db_session, "owner@example.com")
    other = _active_user(db_session, "other@example.com")
    trip, trip_day = _trip_with_day(db_session, owner)
    festival = _festival()
    db_session.add(festival)
    db_session.flush()
    client = _build_client(db_session)
    _login(client, other.email)

    response = client.post(
        f"/trips/{trip.id}/days/{trip_day.id}/items",
        json={"resource_type": "festival", "festival_id": str(festival.id)},
    )

    assert response.status_code == 403


def test_trip_plan_item_requires_matching_resource_identifier(db_session: Session) -> None:
    user = _active_user(db_session, "planner@example.com")
    trip, trip_day = _trip_with_day(db_session, user)
    client = _build_client(db_session)
    _login(client, user.email)

    response = client.post(
        f"/trips/{trip.id}/days/{trip_day.id}/items",
        json={"resource_type": "festival", "title_snapshot": "이름만 있는 축제"},
    )

    assert response.status_code == 422


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "strong-password-1"},
    )
    assert response.status_code == 200


def _active_user(db_session: Session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("strong-password-1"),
        display_name=email,
        email_verified_at=datetime(2026, 4, 28, 9, 0, tzinfo=KST),
        account_status="active",
        system_role="planner",
        nickname=email,
        name=email,
        is_active=True,
        is_admin=False,
        is_privileged=False,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _trip_with_day(db_session: Session, user: User) -> tuple[Trip, TripDay]:
    trip = Trip(
        user_id=user.id,
        title="봄 여행",
        destination="서울",
        start_date=date(2026, 5, 3),
        end_date=date(2026, 5, 3),
        planning_status="planning",
    )
    db_session.add(trip)
    db_session.flush()
    trip_day = TripDay(trip_id=trip.id, day_index=1, date=date(2026, 5, 3))
    db_session.add(trip_day)
    db_session.flush()
    return trip, trip_day


def _festival() -> TourServingPublicCulturalFestival:
    return TourServingPublicCulturalFestival(
        provider="data_go_kr",
        source_record_id="spring",
        place_join_key="data_go_kr:public_cultural_festival:spring",
        festival_name="서울 봄 축제",
        normalized_festival_name="서울 봄 축제",
        venue_name="광장",
        event_start_date=date(2026, 5, 1),
        event_end_date=date(2026, 5, 5),
        event_status="upcoming",
        festival_content="봄 축제",
        mnnst_name=None,
        auspc_instt_name=None,
        suprt_instt_name=None,
        phone_number=None,
        homepage_url=None,
        related_info=None,
        road_address="서울특별시 종로구 세종대로 1",
        jibun_address=None,
        address_snapshot="서울특별시 종로구 세종대로 1",
        longitude=Decimal("126.97800000"),
        latitude=Decimal("37.56650000"),
        geom=None,
        legal_dong_code=None,
        road_name_code=None,
        road_address_management_no=None,
        sigungu_code="1111000000",
        sido_code="1100000000",
        address_mapping_method="test",
        provider_institution_code=None,
        provider_institution_name=None,
        reference_date=date(2026, 4, 1),
        raw_payload={},
        collected_at=datetime(2026, 4, 28, 9, 0, tzinfo=KST),
        is_active=True,
    )
