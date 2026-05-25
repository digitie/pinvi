"""OAuth schema — `docs/api/auth.md` §6 / `docs/integrations/social-login.md`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OAuthProvider = Literal["google", "naver", "kakao"]


class OAuthProvidersResponse(BaseModel):
    providers: list[dict[str, str | bool]]


class OAuthStartRequest(BaseModel):
    return_to: str = Field(default="/", pattern=r"^/[\w/_\-?=&]*$")
    mode: Literal["login", "link"] = "login"


class OAuthLinkRequest(BaseModel):
    return_to: str = Field(default="/profile", pattern=r"^/[\w/_\-?=&]*$")
