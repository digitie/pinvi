"""OAuth schema — `docs/api/auth.md` §6 / `docs/integrations/social-login.md`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

OAuthProvider = Literal["google", "naver", "kakao"]


class OAuthProviderInfo(BaseModel):
    provider: OAuthProvider
    enabled: bool


class OAuthProvidersResponse(BaseModel):
    providers: list[OAuthProviderInfo]


class OAuthStartRequest(BaseModel):
    return_to: str = Field(default="/", max_length=2048, pattern=r"^/[^\s\\]*$")
    mode: Literal["login", "link"] = "login"

    @field_validator("return_to")
    @classmethod
    def _relative_return_path(cls, value: str) -> str:
        if value.startswith("//"):
            raise ValueError("복귀 경로는 같은 출처의 앱 경로여야 합니다.")
        return value


class OAuthStartResponse(BaseModel):
    authorize_url: str


class OAuthLinkRequest(BaseModel):
    return_to: str = Field(default="/profile", pattern=r"^/[\w/_\-?=&]*$")
