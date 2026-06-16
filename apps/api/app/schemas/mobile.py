"""모바일 전용 API schema (`apps/mobile` Expo 앱 지원)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.auth import AuthUser


class MobileVWorldTokenResponse(BaseModel):
    """서버 발급 VWorld 지도 키 (ADR-043).

    모바일 앱은 키를 번들하지 않고 인증 후 이 응답으로 받는다. 앱은 `api_key`를
    `maplibre-vworld-react`의 `tileUrlTransform`으로 타일 URL에 주입하고,
    `ttl_seconds` 경과 후 재요청한다.
    """

    api_key: str
    key_source: Literal["server-issued"] = "server-issued"
    ttl_seconds: int


class MobileAuthResponse(BaseModel):
    """모바일 인증 토큰 발급 응답 (login / verify-email / refresh).

    웹은 httpOnly cookie로 access/refresh 토큰을 받지만(ADR-032), 모바일은 cookie를 쓰지
    못하므로 **본문으로 토큰을 받아 SecureStore에 보관**한다(expo-implementation-plan §5 #2).
    `access_token`은 `Authorization: Bearer`로, `refresh_token`은 `/mobile/auth/refresh`에 쓴다.
    """

    user: AuthUser
    access_token: str
    refresh_token: str
    expires_at: datetime


class MobileRefreshRequest(BaseModel):
    """모바일 refresh/logout — cookie 대신 본문 refresh token."""

    refresh_token: str
