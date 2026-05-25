"""Argon2 + JWT 단위 테스트."""

from __future__ import annotations

import time

import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("secret-pw-12345")
    assert verify_password("secret-pw-12345", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_password_hash_argon2_format() -> None:
    hashed = hash_password("another-pw-67890")
    assert hashed.startswith("$argon2id$")


def test_access_token_roundtrip() -> None:
    token = create_access_token(subject="user-123", extra={"roles": ["user"]})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["roles"] == ["user"]
    assert payload["typ"] == "access"


def test_access_token_expiry() -> None:
    token = create_access_token(subject="user-expire", expires_minutes=0)
    time.sleep(1.1)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_opaque_token_length() -> None:
    token = generate_opaque_token(32)
    assert len(token) >= 43  # 32 bytes → 43 char URL-safe base64
