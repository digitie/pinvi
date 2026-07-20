"""Naver Local client — 지역 검색(표시 전용) — `docs/integrations/kakao-naver-local.md`.

ADR-054: Naver Local은 **표시 전용 보조 provider**다. provider 파생 콘텐츠는 저장·재전달하지
않는다. Kakao와 달리 좌표(radius) 파라미터가 없어 키워드로만 조회하고, `display`는 최대 5다.
인증은 검색 API 전용 신규 앱의 `X-Naver-Client-Id`/`X-Naver-Client-Secret` 헤더(§6, SecretStr).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Request, status

from app.core.config import Settings, settings
from app.db import session as db_session
from app.middleware.api_call_logging import api_call_event_hooks

logger = logging.getLogger(__name__)

_MAX_DISPLAY = 5  # Naver Local 결과 수 상한.


class NaverLocalError(Exception):
    """Naver Local 호출 실패의 베이스."""


class NaverLocalUnavailable(NaverLocalError):
    """타임아웃 / 연결 실패 / 5xx(재시도 소진) / credential 미설정 — degrade 대상."""


class NaverLocalClient:
    """Naver Local 전송 전용(httpx.AsyncClient 1개). 표시 전용 — 콘텐츠 미저장."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        client_id: str,
        client_secret: str,
        max_attempts: int = 2,
        backoff_base_seconds: float = 0.2,
    ) -> None:
        self._http = http
        self._client_id = (client_id or "").strip()
        self._client_secret = (client_secret or "").strip()
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

    async def search_local(self, *, query: str, display: int) -> dict[str, Any]:
        """지역(장소) 검색. 좌표 파라미터 없음(§3.2) — 키워드로만 조회."""
        params = {"query": query, "display": max(1, min(display, _MAX_DISPLAY))}
        return await self._get("/v1/search/local.json", params)

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """transient(타임아웃/연결/5xx)만 지수 백오프 재시도, 4xx는 즉시 실패."""
        headers = self._auth_headers()
        last: NaverLocalUnavailable | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = await self._http.get(path, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = NaverLocalUnavailable(f"Naver Local 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                    last = NaverLocalUnavailable(f"Naver Local {resp.status_code} ({path})")
                elif resp.status_code >= status.HTTP_400_BAD_REQUEST:
                    raise NaverLocalUnavailable(f"Naver Local {resp.status_code} ({path})")
                else:
                    body = resp.json()
                    if not isinstance(body, dict):
                        raise NaverLocalUnavailable(f"Naver Local 예상치 못한 응답({path})")
                    return body
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
        logger.warning("naver_local.unavailable", extra={"path": path})
        raise last or NaverLocalUnavailable(f"Naver Local 요청 실패({path})")

    def _auth_headers(self) -> dict[str, str]:
        if not self._client_id or not self._client_secret:
            raise NaverLocalUnavailable("Naver Search credential이 설정되지 않았습니다.")
        return {
            "X-Naver-Client-Id": self._client_id,
            "X-Naver-Client-Secret": self._client_secret,
        }


def create_naver_local_client(app_settings: Settings) -> NaverLocalClient:
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_naver_local_base_url,
        timeout=app_settings.pinvi_place_provider_timeout_seconds,
        event_hooks=api_call_event_hooks(db_session.async_session_factory, provider="naver_local"),
    )
    return NaverLocalClient(
        http,
        client_id=app_settings.pinvi_naver_search_client_id.get_secret_value(),
        client_secret=app_settings.pinvi_naver_search_client_secret.get_secret_value(),
        max_attempts=app_settings.pinvi_place_provider_max_attempts,
    )


@asynccontextmanager
async def naver_local_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not settings.pinvi_naver_local_enabled:
        app.state.naver_local_client = None
        yield
        return
    client = create_naver_local_client(settings)
    app.state.naver_local_client = client
    logger.info("naver_local.client_ready", extra={"base_url": settings.pinvi_naver_local_base_url})
    try:
        yield
    finally:
        await client.aclose()
        app.state.naver_local_client = None


def get_naver_local_client(request: Request) -> NaverLocalClient | None:
    """client가 없으면(disable/미기동) None → `/search`가 degrade로 처리(hard fail 아님)."""
    client = getattr(request.app.state, "naver_local_client", None)
    return client if isinstance(client, NaverLocalClient) else None


NaverLocalClientDep = Annotated[NaverLocalClient | None, Depends(get_naver_local_client)]
