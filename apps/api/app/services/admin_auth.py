from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mixins import kst_now
from app.models.session import UserSession
from app.models.user import User

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
SESSION_TOKEN_BYTES = 48


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
    if user is None or not user.is_active or not user.is_admin:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = kst_now()
    return user


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not user.is_active or user.account_status != "active":
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = kst_now()
    return user


def create_session_token(
    db: Session,
    *,
    user_id: UUID,
    expires_in_hours: int,
) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    now = kst_now()
    session = UserSession(
        user_id=user_id,
        session_token_hash=hash_session_token(token),
        expires_at=now + timedelta(hours=expires_in_hours),
        last_seen_at=now,
    )
    db.add(session)
    db.flush()
    return token, session


def get_admin_user_by_session_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None

    now = kst_now()
    session = db.scalar(
        select(UserSession)
        .join(User)
        .where(UserSession.session_token_hash == hash_session_token(token))
        .where(UserSession.revoked_at.is_(None))
        .where(UserSession.expires_at > now)
        .where(User.is_active.is_(True))
        .where(User.is_admin.is_(True))
    )
    if session is None:
        return None

    session.last_seen_at = now
    db.flush()
    return session.user


def get_user_by_session_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None

    now = kst_now()
    session = db.scalar(
        select(UserSession)
        .join(User)
        .where(UserSession.session_token_hash == hash_session_token(token))
        .where(UserSession.revoked_at.is_(None))
        .where(UserSession.expires_at > now)
        .where(User.is_active.is_(True))
        .where(User.account_status == "active")
    )
    if session is None:
        return None

    session.last_seen_at = now
    db.flush()
    return session.user


def revoke_session_token(db: Session, token: str | None) -> None:
    if not token:
        return

    session = db.scalar(
        select(UserSession).where(UserSession.session_token_hash == hash_session_token(token))
    )
    if session is None or session.revoked_at is not None:
        return

    session.revoked_at = kst_now()
    db.flush()
