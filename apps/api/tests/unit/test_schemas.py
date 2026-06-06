"""Pydantic schema 단위 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest, VerifyEmailRequest


def _register_consents() -> list[dict[str, str]]:
    return [
        {"consent_type": "tos", "version": "v1.0"},
        {"consent_type": "privacy", "version": "v1.0"},
        {"consent_type": "lbs_tos", "version": "v1.0"},
        {"consent_type": "location_collection", "version": "v1.0"},
    ]


def test_register_request_valid() -> None:
    req = RegisterRequest(
        email="user@example.com",
        password="secret-pw-12345",
        nickname="user",
        consents=_register_consents(),
    )
    assert req.email == "user@example.com"


def test_register_request_short_password() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com",
            password="short",
            nickname="user",
            consents=_register_consents(),
        )


def test_register_request_invalid_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="not-an-email",
            password="secret-pw-12345",
            nickname="user",
            consents=_register_consents(),
        )


def test_register_request_requires_all_consents() -> None:
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(
            email="user@example.com",
            password="secret-pw-12345",
            nickname="user",
            consents=[{"consent_type": "tos", "version": "v1.0"}],
        )
    assert "필수 동의 누락" in str(exc.value)


def test_register_request_rejects_duplicate_consent() -> None:
    with pytest.raises(ValidationError) as exc:
        RegisterRequest(
            email="user@example.com",
            password="secret-pw-12345",
            nickname="user",
            consents=[*_register_consents(), {"consent_type": "tos", "version": "v1.0"}],
        )
    assert "동의 항목 중복" in str(exc.value)


def test_verify_email_request_token_length() -> None:
    with pytest.raises(ValidationError):
        VerifyEmailRequest(token="short")


def test_login_request_valid() -> None:
    req = LoginRequest(email="user@example.com", password="x")
    assert req.password == "x"
