from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RegisterUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    birth_year_month: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    gender: str | None = Field(
        default=None,
        pattern=r"^(female|male|non_binary|no_answer)$",
    )
    residence_sigungu_code: str | None = Field(default=None, pattern=r"^[0-9]{10}$")


class RegisteredUserResponse(BaseModel):
    id: UUID
    email: str
    nickname: str
    name: str
    account_status: str
    system_role: str
    email_verification_required: bool
    verification_email_dispatched: bool


class RegisterUserResponse(BaseModel):
    user: RegisteredUserResponse


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class AuthenticatedUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    nickname: str | None
    name: str | None
    account_status: str
    system_role: str
    email_verified_at: datetime | None
    is_admin: bool
    is_privileged: bool


class LoginResponse(BaseModel):
    user: AuthenticatedUserResponse


class LogoutResponse(BaseModel):
    status: str
