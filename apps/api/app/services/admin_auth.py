from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mixins import kst_now
from app.models.session import UserSession
from app.models.user import User

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
JWT_ALGORITHM = "HS256"


class JwtTokenError(ValueError):
    pass


@dataclass(frozen=True)
class IssuedAuthTokens:
    access_token: str
    access_token_expires_at: datetime
    refresh_token: str
    refresh_token_expires_at: datetime
    session: UserSession


@dataclass(frozen=True)
class RefreshAccessTokenResult:
    access_token: str
    access_token_expires_at: datetime
    user: User
    session: UserSession


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(
    password: str,
    *,
    salt: str | None = None,
    iterations: int = PASSWORD_ITERATIONS,
) -> str:
    resolved_salt = salt or secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        resolved_salt.encode("utf-8"),
        iterations,
    )
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{PASSWORD_SCHEME}${iterations}${resolved_salt}${encoded_digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_text, salt, expected_digest = password_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False

    if scheme != PASSWORD_SCHEME:
        return False

    candidate_hash = hash_password(password, salt=salt, iterations=iterations)
    candidate_digest = candidate_hash.rsplit("$", 1)[1]
    return hmac.compare_digest(candidate_digest, expected_digest)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate_admin(db: Session, *, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not user.is_active or not user.is_admin or user.password_hash is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = kst_now()
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if (
        user is None
        or not user.is_active
        or user.account_status != "active"
        or user.password_hash is None
    ):
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = kst_now()
    return user


def issue_auth_tokens(
    db: Session,
    *,
    user_id: UUID,
    secret_key: str,
    issuer: str,
    access_token_minutes: int,
    refresh_token_days: int,
) -> IssuedAuthTokens:
    now = kst_now()
    refresh_expires_at = now + timedelta(days=refresh_token_days)
    session = UserSession(
        user_id=user_id,
        session_token_hash="pending",
        expires_at=refresh_expires_at,
        last_seen_at=now,
    )
    db.add(session)
    db.flush()

    access_expires_at = _utc_now() + timedelta(minutes=access_token_minutes)
    refresh_expires_at_utc = _utc_now() + timedelta(days=refresh_token_days)
    access_token = encode_jwt(
        {
            "iss": issuer,
            "sub": str(user_id),
            "sid": str(session.id),
            "typ": "access",
            "iat": _jwt_timestamp(_utc_now()),
            "exp": _jwt_timestamp(access_expires_at),
        },
        secret_key=secret_key,
    )
    refresh_token = encode_jwt(
        {
            "iss": issuer,
            "sub": str(user_id),
            "sid": str(session.id),
            "typ": "refresh",
            "iat": _jwt_timestamp(_utc_now()),
            "exp": _jwt_timestamp(refresh_expires_at_utc),
        },
        secret_key=secret_key,
    )
    session.session_token_hash = hash_session_token(refresh_token)
    db.flush()
    return IssuedAuthTokens(
        access_token=access_token,
        access_token_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_token_expires_at=refresh_expires_at_utc,
        session=session,
    )


def get_user_by_access_token(
    db: Session,
    token: str | None,
    *,
    secret_key: str,
    issuer: str,
    require_admin: bool = False,
) -> User | None:
    if not token:
        return None
    try:
        claims = decode_jwt(token, secret_key=secret_key, issuer=issuer, expected_type="access")
        user_id = UUID(require_claim_string(claims, "sub"))
        session_id = UUID(require_claim_string(claims, "sid"))
    except (JwtTokenError, ValueError):
        return None

    now = kst_now()
    session = db.get(UserSession, session_id)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None
    if session.user_id != user_id:
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    if require_admin and not user.is_admin:
        return None
    if not require_admin and user.account_status != "active":
        return None

    session.last_seen_at = now
    db.flush()
    return user


def refresh_access_token(
    db: Session,
    refresh_token: str | None,
    *,
    secret_key: str,
    issuer: str,
    access_token_minutes: int,
    require_admin: bool = False,
) -> RefreshAccessTokenResult | None:
    if not refresh_token:
        return None
    try:
        claims = decode_jwt(
            refresh_token,
            secret_key=secret_key,
            issuer=issuer,
            expected_type="refresh",
        )
        user_id = UUID(require_claim_string(claims, "sub"))
        session_id = UUID(require_claim_string(claims, "sid"))
    except (JwtTokenError, ValueError):
        return None

    now = kst_now()
    session = db.get(UserSession, session_id)
    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at is not None
        or session.expires_at <= now
        or not hmac.compare_digest(session.session_token_hash, hash_session_token(refresh_token))
    ):
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    if require_admin and not user.is_admin:
        return None
    if not require_admin and user.account_status != "active":
        return None

    access_expires_at = _utc_now() + timedelta(minutes=access_token_minutes)
    access_token = encode_jwt(
        {
            "iss": issuer,
            "sub": str(user.id),
            "sid": str(session.id),
            "typ": "access",
            "iat": _jwt_timestamp(_utc_now()),
            "exp": _jwt_timestamp(access_expires_at),
        },
        secret_key=secret_key,
    )
    session.last_seen_at = now
    db.flush()
    return RefreshAccessTokenResult(
        access_token=access_token,
        access_token_expires_at=access_expires_at,
        user=user,
        session=session,
    )


def revoke_refresh_token(db: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return

    session = db.scalar(
        select(UserSession).where(
            UserSession.session_token_hash == hash_session_token(refresh_token)
        )
    )
    if session is None or session.revoked_at is not None:
        return

    session.revoked_at = kst_now()
    db.flush()


def encode_jwt(claims: dict[str, object], *, secret_key: str) -> str:
    header: dict[str, object] = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    signing_input = ".".join(
        [
            _base64url_json(header),
            _base64url_json(claims),
        ]
    )
    signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def decode_jwt(
    token: str,
    *,
    secret_key: str,
    issuer: str,
    expected_type: Literal["access", "refresh"],
) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        raise JwtTokenError("JWT must have three segments.")

    signing_input = f"{parts[0]}.{parts[1]}"
    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    signature = _base64url_decode(parts[2])
    if not hmac.compare_digest(signature, expected_signature):
        raise JwtTokenError("JWT signature is invalid.")

    header = _decode_json_segment(parts[0])
    claims = _decode_json_segment(parts[1])
    if header.get("alg") != JWT_ALGORITHM:
        raise JwtTokenError("JWT algorithm is unsupported.")
    if claims.get("iss") != issuer:
        raise JwtTokenError("JWT issuer is invalid.")
    if claims.get("typ") != expected_type:
        raise JwtTokenError("JWT type is invalid.")
    exp = claims.get("exp")
    if not isinstance(exp, int | float) or exp <= _jwt_timestamp(_utc_now()):
        raise JwtTokenError("JWT is expired.")
    return claims


def require_claim_string(claims: dict[str, object], key: str) -> str:
    value = claims.get(key)
    if not isinstance(value, str):
        raise JwtTokenError(f"JWT claim {key} must be a string.")
    return value


def _base64url_json(value: dict[str, object]) -> str:
    return _base64url_encode(
        json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    )


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except ValueError as exc:
        raise JwtTokenError("JWT segment is not valid base64url.") from exc


def _decode_json_segment(segment: str) -> dict[str, object]:
    try:
        payload = json.loads(_base64url_decode(segment).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JwtTokenError("JWT segment is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise JwtTokenError("JWT segment must be an object.")
    return payload


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _jwt_timestamp(value: datetime) -> int:
    return int(value.timestamp())
