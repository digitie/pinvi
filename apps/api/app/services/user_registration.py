"""회원가입 흐름 — `docs/api/auth.md` §2.

Sprint 1: 일반 가입 + verify. 소셜 / 동의 / 위치 audit는 Sprint 2에서.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    InvalidTokenError,
    generate_opaque_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.models.user_email_verification import UserEmailVerification
from app.services.email_service import send_verification_email

log = get_logger("auth")


class UserRegistrationError(Exception):
    code: str = "INTERNAL_ERROR"


class EmailAlreadyUsedError(UserRegistrationError):
    code = "EMAIL_ALREADY_USED"


class EmailNotVerifiedError(UserRegistrationError):
    code = "EMAIL_NOT_VERIFIED"


class InvalidCredentialsError(UserRegistrationError):
    code = "AUTH_INVALID_CREDENTIALS"


class VerificationTokenInvalidError(UserRegistrationError):
    code = "VALIDATION_ERROR"


@dataclass
class RegistrationResult:
    user: User
    verification_email_dispatched: bool


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    nickname: str,
) -> RegistrationResult:
    existing = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if existing is not None:
        raise EmailAlreadyUsedError("이미 가입된 이메일입니다.")

    user = User(
        email=email,
        password_hash=hash_password(password),
        nickname=nickname,
        status="pending_verification",
    )
    db.add(user)
    await db.flush()  # user_id 발급

    raw_token = generate_opaque_token(32)
    verification = UserEmailVerification(
        user_id=user.user_id,
        token_hash=_hash_token(raw_token),
        purpose="signup",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db.add(verification)
    await db.commit()
    await db.refresh(user)

    verify_url = (
        f"{settings.tripmate_web_base_url}{settings.tripmate_email_verification_path}"
        f"?token={raw_token}"
    )
    dispatched = await send_verification_email(to_email=email, verify_url=verify_url)
    log.info(
        "user.registered",
        user_id=str(user.user_id),
        verification_email_dispatched=dispatched,
    )
    return RegistrationResult(user=user, verification_email_dispatched=dispatched)


async def verify_email(db: AsyncSession, *, token: str) -> User:
    token_hash = _hash_token(token)
    row = await db.scalar(
        select(UserEmailVerification).where(
            UserEmailVerification.token_hash == token_hash,
            UserEmailVerification.used_at.is_(None),
        )
    )
    if row is None:
        raise VerificationTokenInvalidError("토큰이 잘못되었습니다.")
    if row.expires_at < datetime.now(UTC):
        raise VerificationTokenInvalidError("토큰이 만료되었습니다.")

    user = await db.scalar(select(User).where(User.user_id == row.user_id))
    if user is None:
        raise VerificationTokenInvalidError("사용자가 존재하지 않습니다.")

    now = datetime.now(UTC)
    user.email_verified_at = now
    user.status = "pending_profile"
    row.used_at = now
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None or not user.password_hash:
        raise InvalidCredentialsError("이메일 또는 비밀번호가 올바르지 않습니다.")
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("이메일 또는 비밀번호가 올바르지 않습니다.")
    if user.email_verified_at is None:
        raise EmailNotVerifiedError("이메일 인증이 필요합니다.")
    if user.status == "disabled":
        raise InvalidCredentialsError("이메일 또는 비밀번호가 올바르지 않습니다.")
    return user


def make_user_id_from_subject(subject: str) -> uuid.UUID:
    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise InvalidTokenError("sub claim is not a uuid") from exc
