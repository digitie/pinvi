from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import create_app
from app.models.etl import EtlRunLog
from app.models.user import User
from app.services.admin_auth import hash_password


def test_admin_login_me_and_logout_flow(db_session: Session) -> None:
    _ensure_default_admin(db_session)
    client = _build_client(db_session)

    login_response = client.post(
        "/admin/auth/login",
        json={"email": "admin@ad.min", "password": "admin"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["email"] == "admin@ad.min"
    assert client.cookies.get("tripmate_session")

    me_response = client.get("/admin/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["is_admin"] is True

    logout_response = client.post("/admin/auth/logout")

    assert logout_response.status_code == 200
    assert client.get("/admin/auth/me").status_code == 401


def test_admin_login_rejects_non_admin_and_wrong_password(db_session: Session) -> None:
    _ensure_default_admin(db_session)
    _add_user(db_session, email="planner@example.com", password="admin", is_admin=False)
    client = _build_client(db_session)

    non_admin_response = client.post(
        "/admin/auth/login",
        json={"email": "planner@example.com", "password": "admin"},
    )
    wrong_password_response = client.post(
        "/admin/auth/login",
        json={"email": "admin@ad.min", "password": "wrong"},
    )

    assert non_admin_response.status_code == 401
    assert wrong_password_response.status_code == 401


def test_admin_dataset_list_exposes_etl_tables_and_hides_user_tables(db_session: Session) -> None:
    _ensure_default_admin(db_session)
    client = _build_client(db_session)
    _login(client)

    response = client.get("/admin/datasets")

    assert response.status_code == 200
    payload = response.json()
    table_names = {dataset["table_name"] for dataset in payload["datasets"]}
    assert "etl_run_logs" in table_names
    assert "fuel_serving_avg_price" in table_names
    assert "ocean_activity_index_locations" in table_names
    assert "ocean_activity_index_source_records" in table_names
    assert "ocean_activity_index_forecasts" in table_names
    assert "weather_serving_short_term" in table_names
    assert "users" not in table_names
    assert "sessions" not in table_names
    assert payload["default_page_size"] == 100
    assert payload["page_size_options"] == [50, 100, 200, 500]


def test_admin_dataset_rows_support_search_filter_sort_and_paging(
    db_session: Session,
) -> None:
    _ensure_default_admin(db_session)
    db_session.add_all(
        [
            _etl_log("weather_short_term", "failed", "weather-1"),
            _etl_log("fuel_avg_price", "success", "fuel-1"),
            _etl_log("weather_mid_term", "success", "weather-2"),
        ]
    )
    db_session.flush()
    client = _build_client(db_session)
    _login(client)

    response = client.get(
        "/admin/datasets/etl_run_logs/rows",
        params={
            "search": "weather",
            "filter.status": "success",
            "sort_by": "dataset_key",
            "sort_dir": "asc",
            "limit": 50,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 50
    assert payload["total"] == 1
    assert [row["dataset_key"] for row in payload["rows"]] == ["weather_mid_term"]


def test_admin_dataset_rows_reject_unknown_table(db_session: Session) -> None:
    _ensure_default_admin(db_session)
    client = _build_client(db_session)
    _login(client)

    response = client.get("/admin/datasets/users/rows")

    assert response.status_code == 404


def test_admin_users_list_and_update_signup_user(db_session: Session) -> None:
    _ensure_default_admin(db_session)
    client = _build_client(db_session)
    register_response = client.post(
        "/auth/register",
        json={
            "email": "planner@example.com",
            "password": "strong-password-1",
            "nickname": "여행자",
            "name": "홍길동",
        },
    )
    _login(client)

    list_response = client.get("/admin/users", params={"search": "planner"})

    assert register_response.status_code == 201
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    user_id = payload["users"][0]["id"]
    assert payload["users"][0]["account_status"] == "pending_email_verification"
    assert payload["users"][0]["email_verified_at"] is None

    update_response = client.patch(
        f"/admin/users/{user_id}",
        json={
            "account_status": "active",
            "system_role": "planner",
            "email_verified": True,
            "nickname": "새 여행자",
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["account_status"] == "active"
    assert updated["system_role"] == "planner"
    assert updated["nickname"] == "새 여행자"
    assert updated["display_name"] == "새 여행자"
    assert updated["email_verified_at"] is not None


def test_admin_users_prevents_self_demotion(db_session: Session) -> None:
    admin_user = _ensure_default_admin(db_session)
    client = _build_client(db_session)
    _login(client)

    response = client.patch(
        f"/admin/users/{admin_user.id}",
        json={"system_role": "planner"},
    )

    assert response.status_code == 400


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _add_user(
    db_session: Session,
    *,
    email: str,
    password: str,
    is_admin: bool,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=email,
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
    return _add_user(db_session, email="admin@ad.min", password="admin", is_admin=True)


def _login(client: TestClient) -> None:
    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@ad.min", "password": "admin"},
    )
    assert response.status_code == 200


def _etl_log(dataset_key: str, status: str, run_key: str) -> EtlRunLog:
    return EtlRunLog(
        dataset_key=dataset_key,
        run_key=run_key,
        run_type="manual",
        status=status,
        attempt_count=1,
        max_attempts=3,
        retry_interval_seconds=300,
        extra={},
    )
