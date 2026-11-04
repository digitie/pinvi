"""OAuth schema — `docs/api/auth.md` §6 / `docs/integrations/social-login.md`."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import unquote_plus

from pydantic import BaseModel, Field, field_validator

from app.core.redaction import SENSITIVE_QUERY_KEYS

OAuthProvider = Literal["google", "naver", "kakao"]


class OAuthProviderInfo(BaseModel):
    provider: OAuthProvider
    enabled: bool


class OAuthProvidersResponse(BaseModel):
    providers: list[OAuthProviderInfo]


# 웹 공유 화면 `/shared/{tripId}/{token}` — 두 번째 segment가 공유 토큰이다(#671).
_SHARED_RETURN_RE = re.compile(r"^/shared/([^/?#]+)(?:[/?#]|$)")
_STORAGE_RETURN_RE = re.compile(r"^/(?:api/v1/)?storage(?:[/?#]|$)")
#: 웹 `safeLoginReturnTo`의 비밀 query 이름 — 로그 가리기 이름에 OAuth·공유 토큰 이름을 더한 것.
_SECRET_RETURN_QUERY_KEYS = SENSITIVE_QUERY_KEYS | {"code", "state", "share_token"}


def redact_return_path(value: str) -> str:
    """복귀 경로에서 공유·저장소 토큰과 비밀 query를 지운다(#671).

    `return_to_path`는 DB(`oauth_login_states`)에 남고 callback redirect의 `Location`으로 접근 로그에
    찍힌다. 웹은 이미 지워서 보내지만(`safeLoginReturnTo`) 서버도 같은 규칙으로 한 번 더 지운다.
    """
    shared = _SHARED_RETURN_RE.match(value)
    if shared:
        return f"/shared/{shared.group(1)}"
    if _STORAGE_RETURN_RE.match(value):
        return "/"
    path, hash_sep, fragment = value.partition("#")
    base, query_sep, query = path.partition("?")
    if not query_sep:
        return value
    # 비밀 쌍만 빼고 나머지 원문은 다시 인코딩하지 않는다 — 길이는 줄기만 한다(varchar(255) 계약).
    parts = query.split("&")
    kept = [
        part
        for part in parts
        if unquote_plus(part.partition("=")[0]).lower() not in _SECRET_RETURN_QUERY_KEYS
    ]
    if len(kept) == len(parts):
        return value
    rebuilt = base + (f"?{'&'.join(kept)}" if kept else "")
    return rebuilt + (hash_sep + fragment if hash_sep else "")


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
        return redact_return_path(value)


class OAuthStartResponse(BaseModel):
    authorize_url: str


class OAuthLinkRequest(BaseModel):
    return_to: str = Field(default="/profile", pattern=r"^/[\w/_\-?=&]*$")

    @field_validator("return_to")
    @classmethod
    def _redact_tokens(cls, value: str) -> str:
        return redact_return_path(value)
