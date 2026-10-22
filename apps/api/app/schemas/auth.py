"""Auth Pydantic schema — `packages/schemas/src/auth.ts` Zod와 동기."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from pydantic.networks import validate_email

from app.schemas.consent import REQUIRED_CONSENTS, ConsentItem


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    nickname: str = Field(min_length=1, max_length=80)
    consents: list[ConsentItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_required_consents(self) -> RegisterRequest:
        provided: set[str] = set()
        for item in self.consents:
            if item.consent_type in provided:
                raise ValueError(f"동의 항목 중복: {item.consent_type}")
            provided.add(item.consent_type)

        missing = REQUIRED_CONSENTS - provided
        if missing:
            raise ValueError(f"필수 동의 누락: {sorted(missing)}")
        return self


class UserResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    status: Literal[
        "pending_verification",
        "pending_profile",
        "active",
        "disabled",
        "pending_delete",
        "deleted",
    ]
    email_verified_at: datetime | None


class RegisterResponse(BaseModel):
    user: UserResponse
    verification_email_dispatched: bool


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=43, max_length=43)


class VerifyEmailResendRequest(BaseModel):
    email: EmailStr


class VerifyEmailResendResponse(BaseModel):
    accepted: bool = True


# 이메일이 아닌 로그인 ID. 가입 경로(`RegisterRequest`)는 여전히 이메일만 받으므로 이런 ID를
# 가진 계정은 `pinvi-admin-bootstrap`의 고정 계정 파일로만 생긴다.
LOGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]{2,31}$")


def normalize_login_identifier(value: str) -> str:
    """이메일이면 `EmailStr`과 같은 정규화를, 아니면 고정 로그인 ID 형식만 허용한다."""

    if "@" not in value and LOGIN_ID_PATTERN.fullmatch(value):
        return value
    return validate_email(value)[1]


class LoginRequest(BaseModel):
    # 필드 이름은 기존 계약(`email`)을 유지한다. 값은 이메일 또는 고정 로그인 ID다.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _login_identifier(cls, value: str) -> str:
        return normalize_login_identifier(value)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    accepted: bool = True


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=43, max_length=43)
    new_password: str = Field(min_length=8, max_length=200)


class AuthUserOAuthIdentity(BaseModel):
    provider: Literal["google", "naver", "kakao"]
    provider_email: str | None
    provider_email_verified: bool | None
    display_name: str | None
    linked_at: datetime
    last_login_at: datetime | None


class AuthUser(BaseModel):
    user_id: uuid.UUID
    email: str
    nickname: str | None
    avatar_url: str | None
    avatar_kind: Literal["default", "upload", "external"] = "default"
    avatar_content_type: str | None = None
    avatar_byte_size: int | None = None
    avatar_updated_at: datetime | None = None
    has_avatar: bool = False
    status: Literal[
        "pending_verification",
        "pending_profile",
        "active",
        "disabled",
        "pending_delete",
        "deleted",
    ]
    roles: list[Literal["user", "admin", "operator", "cpo"]]
    email_verified_at: datetime | None
    has_password: bool
    oauth_identities: list[AuthUserOAuthIdentity] = Field(default_factory=list)
