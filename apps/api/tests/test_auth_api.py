from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from app.models.address import AddressCodeStandard
from app.models.mixins import kst_now
from app.models.session import UserSession
from app.models.user import EmailVerificationToken, User, UserConsent
from app.services.admin_auth import hash_password, verify_password
from app.services.email_delivery import EmailVerificationMessage


def test_register_creates_pending_user_and_email_verification_token(
    db_session: Session,
) -> None:
    _seed_sigungu_code(db_session)
    client = _build_client(db_session)

    response = client.post(
        "/auth/register",
        json={
            "email": " Planner@Example.COM ",
            "password": "strong-password-1",
            "nickname": "여행자",
            "name": "홍길동",
            "birth_year_month": "199001",
            "gender": "no_answer",
            "residence_sigungu_code": "1111000000",
            "tos_agreed": True,
            "privacy_agreed": True,
            "demographic_use_agreed": True,
            "location_use_agreed": True,
            "marketing_agreed": False,
            "consent_version": "2026-05-13",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["email"] == "planner@example.com"
    assert payload["user"]["account_status"] == "pending_email_verification"
    assert payload["user"]["status"] == "pending_verification"
    assert payload["user"]["system_role"] == "planner"
    assert payload["user"]["email_verification_required"] is True
    assert payload["user"]["verification_email_dispatched"] is False

    user = db_session.scalar(select(User).where(User.email == "planner@example.com"))
    token = db_session.scalar(select(EmailVerificationToken))
    consents = db_session.scalars(select(UserConsent).order_by(UserConsent.consent_type)).all()

    assert user is not None
    assert user.nickname == "여행자"
    assert user.name == "홍길동"
    assert user.display_name == "여행자"
    assert user.residence_sigungu_code == "1111000000"
    assert user.password_hash is not None
    assert user.password_hash != "strong-password-1"
    assert verify_password("strong-password-1", user.password_hash)
    assert token is not None
    assert token.email == "planner@example.com"
    assert token.purpose == "register"
    assert len(token.token_hash) == 64
    assert [consent.consent_type for consent in consents] == [
        "demographic_use",
        "location_use",
        "privacy",
        "tos",
    ]


def test_register_rejects_duplicate_email(db_session: Session) -> None:
    client = _build_client(db_session)
    request_payload = {
        "email": "planner@example.com",
        "password": "strong-password-1",
        "nickname": "여행자",
        "name": "홍길동",
        "tos_agreed": True,
        "privacy_agreed": True,
        "consent_version": "2026-05-13",
    }

    first_response = client.post("/auth/register", json=request_payload)
    duplicate_response = client.post(
        "/auth/register",
        json={**request_payload, "email": "PLANNER@example.com"},
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_register_rejects_unknown_residence_code(db_session: Session) -> None:
    client = _build_client(db_session)

    response = client.post(
        "/auth/register",
        json={
            "email": "planner@example.com",
            "password": "strong-password-1",
            "nickname": "여행자",
            "name": "홍길동",
            "residence_sigungu_code": "9999999999",
            "tos_agreed": True,
            "privacy_agreed": True,
            "consent_version": "2026-05-13",
        },
    )

    assert response.status_code == 422


def test_register_requires_terms_and_privacy_consents(db_session: Session) -> None:
    client = _build_client(db_session)

    response = client.post(
        "/auth/register",
        json={
            "email": "planner@example.com",
            "password": "strong-password-1",
            "nickname": "여행자",
            "name": "홍길동",
            "tos_agreed": True,
            "privacy_agreed": False,
            "consent_version": "2026-05-13",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Terms and privacy consent are required."


def test_active_user_login_me_and_logout_flow(db_session: Session) -> None:
    user = _add_active_user(db_session)
    client = _build_client(db_session)

    login_response = client.post(
        "/auth/login",
        json={"email": " PLANNER@Example.COM ", "password": "strong-password-1"},
    )

    assert login_response.status_code == 200
    payload = login_response.json()
    assert payload["user"]["email"] == "planner@example.com"
    assert payload["token_type"] == "Bearer"
    assert payload["access_token_expires_at"]
    assert payload["refresh_token_expires_at"]
    assert client.cookies.get("tripmate_access")
    assert client.cookies.get("tripmate_refresh")

    session = db_session.scalar(select(UserSession))
    assert session is not None
    assert session.session_token_hash != client.cookies.get("tripmate_refresh")

    refresh_response = client.post("/auth/refresh")

    assert refresh_response.status_code == 200
    assert refresh_response.json()["user"]["email"] == "planner@example.com"
    assert client.cookies.get("tripmate_access")

    me_response = client.get("/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["id"] == str(user.id)
    assert me_response.json()["system_role"] == "planner"

    logout_response = client.post("/auth/logout")

    assert logout_response.status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_login_rejects_pending_email_verification_user(db_session: Session) -> None:
    client = _build_client(db_session)
    register_response = client.post(
        "/auth/register",
        json={
            "email": "planner@example.com",
            "password": "strong-password-1",
            "nickname": "여행자",
            "name": "홍길동",
            "tos_agreed": True,
            "privacy_agreed": True,
            "consent_version": "2026-05-13",
        },
    )

    login_response = client.post(
        "/auth/login",
        json={"email": "planner@example.com", "password": "strong-password-1"},
    )

    assert register_response.status_code == 201
    assert login_response.status_code == 401


def test_verify_email_token_activates_pending_user(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def capture_verification_email(
        message: EmailVerificationMessage,
        *,
        settings: Settings,
    ) -> bool:
        captured["token"] = message.token
        return True

    monkeypatch.setattr(
        "app.api.routes.auth.send_verification_email",
        capture_verification_email,
    )
    client = _build_client(db_session)

    register_response = client.post(
        "/auth/register",
        json={
            "email": "planner@example.com",
            "password": "strong-password-1",
            "nickname": "여행자",
            "name": "홍길동",
            "tos_agreed": True,
            "privacy_agreed": True,
            "consent_version": "2026-05-13",
        },
    )
    verify_response = client.post("/auth/verify-email", json={"token": captured["token"]})

    assert register_response.status_code == 201
    assert register_response.json()["user"]["verification_email_dispatched"] is True
    assert verify_response.status_code == 200
    assert verify_response.json()["status"] == "ok"
    assert verify_response.json()["user"]["account_status"] == "active"
    assert verify_response.json()["user"]["status"] == "active"

    user = db_session.scalar(select(User).where(User.email == "planner@example.com"))
    token = db_session.scalar(select(EmailVerificationToken))
    assert user is not None
    assert user.email_verified is True
    assert user.email_verified_at is not None
    assert user.account_status == "active"
    assert user.status == "active"
    assert token is not None
    assert token.consumed_at is not None


def test_oauth_provider_start_does_not_auto_match_email(db_session: Session) -> None:
    client = _build_client(db_session)

    providers_response = client.get("/auth/oauth/providers")
    start_response = client.get("/auth/oauth/google/start", follow_redirects=False)

    assert providers_response.status_code == 200
    providers = providers_response.json()["providers"]
    assert {provider["provider"] for provider in providers} == {"google", "naver", "kakao"}
    assert all(provider["enabled"] is False for provider in providers)
    assert {
        provider["email_match_policy"] for provider in providers
    } == {"verified_email_requires_explicit_link"}
    assert start_response.status_code == 303
    assert "oauth_error=temporary_failure" in start_response.headers["location"]
    assert "provider=google" in start_response.headers["location"]


def _build_client(db_session: Session) -> TestClient:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _add_active_user(db_session: Session) -> User:
    user = User(
        email="planner@example.com",
        password_hash=hash_password("strong-password-1"),
        display_name="여행자",
        email_verified_at=kst_now(),
        email_verified=True,
        account_status="active",
        status="active",
        system_role="planner",
        nickname="여행자",
        name="홍길동",
        is_active=True,
        is_admin=False,
        is_privileged=False,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _seed_sigungu_code(session: Session) -> None:
    session.add(
        AddressCodeStandard(
            legal_dong_code="1111000000",
            code_level="sigungu",
            code_name="종로구",
            sido_code="1100000000",
            sigungu_code="1111000000",
            sido_name="서울특별시",
            sigungu_name="종로구",
            legal_eupmyeondong_name=None,
            legal_ri_name=None,
            full_legal_dong_name="서울특별시 종로구",
            source_effective_date="20260401",
            source_change_reason_code="00",
            source_provider="test",
            source_status="active",
            source_file_name="test.csv",
            source_year_month="202604",
            source_file_hash="hash",
            source_sort_order=None,
            source_created_date=None,
            source_deleted_date=None,
            previous_legal_dong_code=None,
            is_discontinued=False,
            is_active=True,
        )
    )
    session.flush()
