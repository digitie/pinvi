"""회원가입 흐름 — `docs/api/auth.md` §2.

이메일 가입 + 필수 약관 동의 저장 + verify email queue.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
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
from app.models.user_consent import UserConsent
from app.models.user_email_verification import UserEmailVerification
from app.schemas.consent import ConsentItem
from app.services.auth_session import revoke_active_user_sessions
from app.services.email_service import enqueue_password_reset_email, enqueue_verification_email

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


@dataclass
class PasswordResetRequestResult:
    reset_email_dispatched: bool


@dataclass
class ResendVerificationResult:
    verification_email_dispatched: bool


SIGNUP_VERIFICATION_TTL_HOURS = 24
BLOCKED_AUTH_STATUSES = {"disabled", "pending_delete", "deleted"}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    nickname: str,
    consents: list[ConsentItem],
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

    now = datetime.now(UTC)
    for item in consents:
        db.add(
            UserConsent(
                user_id=user.user_id,
                consent_type=item.consent_type,
                version=item.version,
                agreed_at=now,
            )
        )

    raw_token = generate_opaque_token(32)
    verification = UserEmailVerification(
        user_id=user.user_id,
        token_hash=_hash_token(raw_token),
        purpose="signup",
        expires_at=now + timedelta(hours=24),
    )
    db.add(verification)
    dispatched = await enqueue_verification_email(
        db,
        user_id=user.user_id,
        to_email=email,
        token=raw_token,
    )
    await db.commit()
    await db.refresh(user)

    log.info(
        "user.registered",
        user_id=str(user.user_id),
        verification_email_dispatched=dispatched,
    )
    return RegistrationResult(user=user, verification_email_dispatched=dispatched)


async def request_password_reset(db: AsyncSession, *, email: str) -> PasswordResetRequestResult:
    """비밀번호 재설정 메일 요청.

    user enumeration을 막기 위해 호출자는 이 결과를 응답에 노출하지 않는다.
    """

    user = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None or user.email_verified_at is None or user.status in BLOCKED_AUTH_STATUSES:
        return PasswordResetRequestResult(reset_email_dispatched=False)

    now = datetime.now(UTC)
    await db.execute(
        update(UserEmailVerification)
        .where(
            UserEmailVerification.user_id == user.user_id,
            UserEmailVerification.purpose == "password_reset",
            UserEmailVerification.used_at.is_(None),
        )
        .values(used_at=now)
    )

    raw_token = generate_opaque_token(32)
    db.add(
        UserEmailVerification(
            user_id=user.user_id,
            token_hash=_hash_token(raw_token),
            purpose="password_reset",
            expires_at=now + timedelta(hours=1),
        )
    )
    dispatched = await enqueue_password_reset_email(
        db,
        user_id=user.user_id,
        to_email=user.email,
        token=raw_token,
    )
    await db.commit()
    return PasswordResetRequestResult(reset_email_dispatched=dispatched)


async def resend_verification_email(db: AsyncSession, *, email: str) -> ResendVerificationResult:
    """미인증 사용자에게 가입 인증 메일(재인증 링크)을 재발송한다.

    `authenticate`가 `EmailNotVerifiedError`를 던진 로그인 경로(비밀번호 검증 통과 후)와
    명시적 재발송 endpoint가 공유한다. user enumeration을 막기 위해 endpoint 호출자는
    dispatched 결과를 노출하지 않는다(로그인 경로는 비밀번호로 소유가 증명되어 노출 가능).

    cooldown(`pinvi_email_verification_resend_cooldown_seconds`) 안에서는 재발송하지 않아
    반복 로그인/클릭으로 인한 중복 메일을 막는다.
    """

    user = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None or user.email_verified_at is not None or user.status in BLOCKED_AUTH_STATUSES:
        return ResendVerificationResult(verification_email_dispatched=False)

    now = datetime.now(UTC)
    cooldown = timedelta(seconds=settings.pinvi_email_verification_resend_cooldown_seconds)
    latest = await db.scalar(
        select(UserEmailVerification)
        .where(
            UserEmailVerification.user_id == user.user_id,
            UserEmailVerification.purpose == "signup",
        )
        .order_by(UserEmailVerification.created_at.desc())
        .limit(1)
    )
    if latest is not None and now - latest.created_at < cooldown:
        log.info("auth.verification_resend_throttled", user_id=str(user.user_id))
        return ResendVerificationResult(verification_email_dispatched=False)

    await db.execute(
        update(UserEmailVerification)
        .where(
            UserEmailVerification.user_id == user.user_id,
            UserEmailVerification.purpose == "signup",
            UserEmailVerification.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = generate_opaque_token(32)
    db.add(
        UserEmailVerification(
            user_id=user.user_id,
            token_hash=_hash_token(raw_token),
            purpose="signup",
            expires_at=now + timedelta(hours=SIGNUP_VERIFICATION_TTL_HOURS),
        )
    )
    dispatched = await enqueue_verification_email(
        db,
        user_id=user.user_id,
        to_email=user.email,
        token=raw_token,
        expires_in_hours=SIGNUP_VERIFICATION_TTL_HOURS,
    )
    await db.commit()
    log.info(
        "auth.verification_resent",
        user_id=str(user.user_id),
        verification_email_dispatched=dispatched,
    )
    return ResendVerificationResult(verification_email_dispatched=dispatched)


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> User:
    token_hash = _hash_token(token)
    row = await db.scalar(
        select(UserEmailVerification).where(
            UserEmailVerification.token_hash == token_hash,
            UserEmailVerification.purpose == "password_reset",
            UserEmailVerification.used_at.is_(None),
        )
    )
    if row is None:
        raise VerificationTokenInvalidError("토큰이 잘못되었습니다.")
    if row.expires_at < datetime.now(UTC):
        raise VerificationTokenInvalidError("토큰이 만료되었습니다.")

    user = await db.scalar(select(User).where(User.user_id == row.user_id))
    if user is None or user.email_verified_at is None or user.status in BLOCKED_AUTH_STATUSES:
        raise VerificationTokenInvalidError("토큰이 잘못되었습니다.")

    now = datetime.now(UTC)
    user.password_hash = hash_password(new_password)
    user.access_token_version = (user.access_token_version or 0) + 1
    row.used_at = now
    await revoke_active_user_sessions(db, user_id=user.user_id, revoked_at=now)
    await db.commit()
    await db.refresh(user)
    return user


async def verify_email(db: AsyncSession, *, token: str) -> User:
    token_hash = _hash_token(token)
    row = await db.scalar(
        select(UserEmailVerification).where(
            UserEmailVerification.token_hash == token_hash,
            UserEmailVerification.purpose == "signup",
            UserEmailVerification.used_at.is_(None),
        )
    )
    if row is None:
        raise VerificationTokenInvalidError("토큰이 잘못되었습니다.")
    if row.expires_at < datetime.now(UTC):
        raise VerificationTokenInvalidError("토큰이 만료되었습니다.")

    user = await db.scalar(select(User).where(User.user_id == row.user_id))
    if user is None or user.status in BLOCKED_AUTH_STATUSES:
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
    if user.status in BLOCKED_AUTH_STATUSES:
        raise InvalidCredentialsError("이메일 또는 비밀번호가 올바르지 않습니다.")
    return user


def make_user_id_from_subject(subject: str) -> uuid.UUID:
    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise InvalidTokenError("sub claim is not a uuid") from exc
