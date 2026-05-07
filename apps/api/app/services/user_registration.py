from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.address import AddressCodeStandard
from app.models.mixins import kst_now
from app.models.user import EmailVerificationToken, User
from app.schemas.auth import RegisterUserRequest
from app.services.admin_auth import hash_password, hash_session_token, normalize_email

EMAIL_VERIFICATION_TOKEN_BYTES = 48
EMAIL_VERIFICATION_EXPIRES_HOURS = 24


class DuplicateEmailError(ValueError):
    pass


class ResidenceCodeNotFoundError(ValueError):
    pass


def register_user(db: Session, payload: RegisterUserRequest) -> User:
    email = normalize_email(payload.email)
    if _email_exists(db, email):
        raise DuplicateEmailError(email)

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
        is_active=True,
        is_admin=False,
        is_privileged=False,
    )
    db.add(user)
    db.flush()

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
    return user


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
