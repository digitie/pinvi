"""Pydantic schema 단위 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest, VerifyEmailRequest


def test_register_request_valid() -> None:
    req = RegisterRequest(email="user@example.com", password="secret-pw-12345", nickname="user")
    assert req.email == "user@example.com"


def test_register_request_short_password() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password="short", nickname="user")


def test_register_request_invalid_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="secret-pw-12345", nickname="user")


def test_verify_email_request_token_length() -> None:
    with pytest.raises(ValidationError):
        VerifyEmailRequest(token="short")


def test_login_request_valid() -> None:
    req = LoginRequest(email="user@example.com", password="x")
    assert req.password == "x"
