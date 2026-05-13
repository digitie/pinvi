from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import create_app
from app.models.user import User
from app.services.admin_auth import hash_password


def test_admin_entities_crud_links_search_and_map_fields(db_session: Session) -> None:
    _ensure_default_admin(db_session)
    client = _build_client(db_session)
    _login(client)

    user_response = client.post(
        "/admin/entities/users",
        json={
            "values": {
                "email": "planner-crud@example.com",
                "password": "strong-password-1",
                "nickname": "CRUD 여행자",
                "name": "관리자 테스트",
                "account_status": "active",
                "system_role": "planner",
                "email_verified": True,
            }
        },
    )

    assert user_response.status_code == 201
    user_item = user_response.json()["item"]
    user_id = user_item["id"]
    assert user_item["fields"]["email_verified"] is True
    assert {link["entity"] for link in user_item["links"]} == {"trips", "pois"}

    feature_response = client.post(
        "/admin/entities/features",
        json={
            "values": {
                "feature_id": "admin:test-beach",
                "kind": "place",
                "name": "관리자 테스트 해변",
                "category": "beach",
                "status": "active",
                "longitude": 129.16,
                "latitude": 35.16,
                "address_road": "부산광역시 해운대구",
                "marker_color": "#0f766e",
                "urls": {"kakao": "https://map.kakao.com"},
                "detail": {"provider": "admin"},
                "raw_refs": [{"provider": "khoa", "dataset_key": "beach_profile"}],
            }
        },
    )

    assert feature_response.status_code == 201
    feature_item = feature_response.json()["item"]
    assert feature_item["map"] == {"latitude": 35.16, "longitude": 129.16}
    assert feature_item["fields"]["raw_refs"][0]["provider"] == "khoa"

    trip_response = client.post(
        "/admin/entities/trips",
        json={
            "values": {
                "user_id": user_id,
                "title": "관리자 CRUD 여행",
                "destination": "부산",
                "start_date": "2026-06-01",
                "end_date": "2026-06-02",
                "planning_status": "draft",
                "fuel_types": "gasoline,diesel",
            }
        },
    )

    assert trip_response.status_code == 201
    trip_item = trip_response.json()["item"]
    trip_id = trip_item["id"]
    assert trip_item["fields"]["day_count"] == 2
    assert trip_item["fields"]["owner_email"] == "planner-crud@example.com"

    poi_response = client.post(
        "/admin/entities/pois",
        json={
            "values": {
                "trip_id": trip_id,
                "day_index": 1,
                "feature_id": "admin:test-beach",
                "added_by_user_id": user_id,
                "memo": "지도와 링크 확인",
                "budget": 12000,
                "currency": "KRW",
            }
        },
    )

    assert poi_response.status_code == 201
    poi_item = poi_response.json()["item"]
    poi_id = poi_item["id"]
    assert poi_item["fields"]["feature_name"] == "관리자 테스트 해변"
    assert poi_item["map"] == {"latitude": 35.16, "longitude": 129.16}
    assert {link["entity"] for link in poi_item["links"]} == {"trips", "users", "features"}

    trip_list = client.get("/admin/entities/trips", params={"user_id": user_id})
    feature_list = client.get("/admin/entities/features", params={"search": "해변"})
    poi_list = client.get("/admin/entities/pois", params={"feature_id": "admin:test-beach"})

    assert trip_list.status_code == 200
    assert feature_list.status_code == 200
    assert poi_list.status_code == 200
    assert trip_list.json()["total"] == 1
    assert feature_list.json()["items"][0]["id"] == "admin:test-beach"
    assert poi_list.json()["total"] == 1

    user_detail = client.get(f"/admin/entities/users/{user_id}").json()
    feature_detail = client.get("/admin/entities/features/admin:test-beach").json()

    assert user_detail["related"][0]["entity"] == "trips"
    assert user_detail["related"][0]["count"] == 1
    assert feature_detail["related"][0]["query"] == {"feature_id": "admin:test-beach"}

    update_response = client.patch(
        "/admin/entities/features/admin:test-beach",
        json={"values": {"name": "수정된 테스트 해변", "status": "hidden"}},
    )

    assert update_response.status_code == 200
    assert update_response.json()["item"]["label"] == "수정된 테스트 해변"
    assert update_response.json()["item"]["status"] == "hidden"

    delete_response = client.delete(f"/admin/entities/pois/{poi_id}")
    empty_poi_list = client.get("/admin/entities/pois", params={"feature_id": "admin:test-beach"})

    assert delete_response.status_code == 200
    assert delete_response.json() == {"entity": "pois", "id": poi_id, "status": "deleted"}
    assert empty_poi_list.json()["total"] == 0


def test_admin_entities_prevent_self_delete(db_session: Session) -> None:
    admin_user = _ensure_default_admin(db_session)
    client = _build_client(db_session)
    _login(client)

    response = client.delete(f"/admin/entities/users/{admin_user.id}")

    assert response.status_code == 422


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _ensure_default_admin(db_session: Session) -> User:
    existing_user = db_session.query(User).filter(User.email == "admin@ad.min").one_or_none()
    if existing_user is not None:
        existing_user.password_hash = hash_password("admin")
        existing_user.is_active = True
        existing_user.is_admin = True
        existing_user.is_privileged = True
        existing_user.account_status = "active"
        existing_user.system_role = "admin"
        existing_user.nickname = existing_user.display_name
        existing_user.name = existing_user.display_name
        db_session.flush()
        return existing_user

    user = User(
        email="admin@ad.min",
        password_hash=hash_password("admin"),
        display_name="admin@ad.min",
        account_status="active",
        system_role="admin",
        nickname="admin@ad.min",
        name="admin@ad.min",
        is_active=True,
        is_admin=True,
        is_privileged=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _login(client: TestClient) -> None:
    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@ad.min", "password": "admin"},
    )
    assert response.status_code == 200
