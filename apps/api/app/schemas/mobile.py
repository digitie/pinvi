"""모바일 전용 API 응답 schema (`apps/mobile` Expo 앱 지원)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MobileVWorldTokenResponse(BaseModel):
    """서버 발급 VWorld 지도 키 (ADR-043).

    모바일 앱은 키를 번들하지 않고 인증 후 이 응답으로 받는다. 앱은 `api_key`를
    `maplibre-vworld-react`의 `tileUrlTransform`으로 타일 URL에 주입하고,
    `ttl_seconds` 경과 후 재요청한다.
    """

    api_key: str
    key_source: Literal["server-issued"] = "server-issued"
    ttl_seconds: int
