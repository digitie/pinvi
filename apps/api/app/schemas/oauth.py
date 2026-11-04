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
    # 255 = `oauth_login_states.return_to_path` varchar(255) — 넘으면 INSERT가 500으로 죽는다.
    return_to: str = Field(default="/", max_length=255, pattern=r"^/[^\s\\]*$")
    mode: Literal["login", "link"] = "login"

    @field_validator("return_to")
    @classmethod
    def _relative_return_path(cls, value: str) -> str:
        # 브라우저는 `..`·`%2e%2e` 세그먼트를 정규화하므로 `/a/..//evil`도 `//evil`이 된다 —
        # 웹 `safeLoginReturnTo`와 같은 규칙으로 path 부분의 빈·점 세그먼트를 거부한다.
        path = value.split("?", 1)[0].split("#", 1)[0]
        dot_segments = {".", "..", "%2e", "%2e%2e", ".%2e", "%2e."}
        if "//" in path or any(seg.lower() in dot_segments for seg in path.split("/")[1:]):
            raise ValueError("복귀 경로는 같은 출처의 앱 경로여야 합니다.")
        return value


class OAuthStartResponse(BaseModel):
    authorize_url: str


class OAuthLinkRequest(BaseModel):
    return_to: str = Field(default="/profile", pattern=r"^/[\w/_\-?=&]*$")
