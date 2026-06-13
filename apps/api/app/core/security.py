"""Argon2id 비밀번호 해시 + JWT 토큰 발급/검증.

`docs/integrations/sentry.md`의 PII 마스킹과 함께 사용.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Argon2id — SPEC V8 N-2
_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto", argon2__type="ID")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:  # passlib 내부 예외 광범위
        return False


# JWT
_ALGORITHM = "HS256"


def create_access_token(
    *,
    subject: str,
    extra: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    token_minutes = (
        settings.pinvi_access_token_minutes if expires_minutes is None else expires_minutes
    )
    expire = datetime.now(UTC) + timedelta(minutes=token_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "typ": "access",
    }
    if extra:
        payload.update(extra)
    return cast(str, jwt.encode(payload, settings.pinvi_jwt_secret_key, algorithm=_ALGORITHM))


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.pinvi_jwt_secret_key, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    return cast(dict[str, Any], payload)


class InvalidTokenError(Exception):
    """JWT 서명 검증 실패 / 만료 / 형식 오류."""


def generate_opaque_token(byte_length: int = 32) -> str:
    """URL-safe base64. refresh 토큰 + email verify 토큰에 사용."""
    return secrets.token_urlsafe(byte_length)
