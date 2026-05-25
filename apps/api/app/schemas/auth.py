"""Auth Pydantic schema — `packages/schemas/src/auth.ts` Zod와 동기."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    nickname: str = Field(min_length=1, max_length=80)


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


class AuthUser(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    nickname: str | None
    avatar_url: str | None
    status: Literal["pending_verification", "pending_profile", "active", "disabled"]
    roles: list[Literal["user", "admin", "operator", "cpo"]]
    email_verified_at: datetime | None
