"""Auth Pydantic schema — `packages/schemas/src/auth.ts` Zod와 동기."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

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
    status: Literal["pending_verification", "pending_profile", "active", "disabled"]
    email_verified_at: datetime | None


class RegisterResponse(BaseModel):
    user: UserResponse
    verification_email_dispatched: bool


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=43, max_length=43)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


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
    status: Literal["pending_verification", "pending_profile", "active", "disabled"]
    roles: list[Literal["user", "admin", "operator", "cpo"]]
    email_verified_at: datetime | None
    has_password: bool
    oauth_identities: list[AuthUserOAuthIdentity] = Field(default_factory=list)
