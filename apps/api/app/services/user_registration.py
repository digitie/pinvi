from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.address import AddressCodeStandard
from app.models.mixins import kst_now
from app.models.user import EmailVerificationToken, User, UserConsent
from app.schemas.auth import RegisterUserRequest
from app.services.admin_auth import hash_password, hash_session_token, normalize_email

EMAIL_VERIFICATION_TOKEN_BYTES = 48
EMAIL_VERIFICATION_EXPIRES_HOURS = 24


class DuplicateEmailError(ValueError):
    pass


class ResidenceCodeNotFoundError(ValueError):
    pass


class RequiredConsentMissingError(ValueError):
    pass


class EmailVerificationTokenInvalidError(ValueError):
    pass


@dataclass(frozen=True)
class UserRegistrationResult:
    user: User
    verification_token: str


def register_user(db: Session, payload: RegisterUserRequest) -> UserRegistrationResult:
    email = normalize_email(payload.email)
    if _email_exists(db, email):
        raise DuplicateEmailError(email)
    if not payload.tos_agreed or not payload.privacy_agreed:
        raise RequiredConsentMissingError("tos and privacy consent are required.")

    residence_sigungu_code = _normalize_optional_text(payload.residence_sigungu_code)
    if residence_sigungu_code is not None and not _address_code_exists(db, residence_sigungu_code):
        raise ResidenceCodeNotFoundError(residence_sigungu_code)

    nickname = payload.nickname.strip()
    name = payload.name.strip()
    now = kst_now()
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=nickname,
        email_verified_at=None,
        account_status="pending_email_verification",
        system_role="planner",
        nickname=nickname,
        name=name,
        birth_year_month=_normalize_optional_text(payload.birth_year_month),
        gender=_normalize_optional_text(payload.gender),
        residence_sigungu_code=residence_sigungu_code,
        status="pending_verification",
        is_active=True,
        is_admin=False,
        is_privileged=False,
    )
    db.add(user)
    db.flush()
    for consent_type in _accepted_consent_types(payload):
        db.add(
            UserConsent(
                user_id=user.id,
                consent_type=consent_type,
                version=payload.consent_version,
                agreed_at=now,
            )
        )

    token = secrets.token_urlsafe(EMAIL_VERIFICATION_TOKEN_BYTES)
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            email=email,
            token_hash=hash_session_token(token),
            purpose="register",
            expires_at=now + timedelta(hours=EMAIL_VERIFICATION_EXPIRES_HOURS),
        )
    )
    db.flush()
    return UserRegistrationResult(user=user, verification_token=token)


def verify_email_token(db: Session, token: str) -> User:
    token_hash = hash_session_token(token)
    now = kst_now()
    verification_token = db.scalar(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token_hash == token_hash)
        .where(EmailVerificationToken.consumed_at.is_(None))
        .where(EmailVerificationToken.expires_at > now)
        .limit(1)
    )
    if verification_token is None:
        raise EmailVerificationTokenInvalidError("email verification token is invalid.")

    user = db.get(User, verification_token.user_id)
    if user is None or user.email != verification_token.email:
        raise EmailVerificationTokenInvalidError("email verification token user is invalid.")

    verification_token.consumed_at = now
    user.email_verified_at = now
    user.email_verified = True
    if user.account_status == "pending_email_verification":
        user.account_status = "active"
    if user.status == "pending_verification":
        user.status = "active" if _profile_is_complete(user) else "pending_profile"
    db.flush()
    return user


def _accepted_consent_types(payload: RegisterUserRequest) -> tuple[str, ...]:
    consent_types = ["tos", "privacy"]
    if payload.demographic_use_agreed:
        consent_types.append("demographic_use")
    if payload.location_use_agreed:
        consent_types.append("location_use")
    if payload.marketing_agreed:
        consent_types.append("marketing")
    return tuple(consent_types)


def _profile_is_complete(user: User) -> bool:
    return bool((user.nickname or user.display_name) and user.name)


def _email_exists(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == email).limit(1)) is not None


def _address_code_exists(db: Session, legal_dong_code: str) -> bool:
    return (
        db.scalar(
            select(AddressCodeStandard.legal_dong_code)
            .where(AddressCodeStandard.legal_dong_code == legal_dong_code)
            .where(AddressCodeStandard.is_active.is_(True))
            .limit(1)
        )
        is not None
    )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
