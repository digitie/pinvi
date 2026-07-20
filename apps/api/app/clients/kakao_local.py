"""Kakao Local client — 장소 키워드 검색(표시 전용) — `docs/integrations/kakao-naver-local.md`.

ADR-054: Kakao Local은 **표시 전용 보조 provider**다. 응답의 provider 파생 콘텐츠(전화/주소/
카테고리 등)는 저장·재전달하지 않는다. `kor_travel_geo.py` client 패턴을 미러한다(factory +
`api_call_event_hooks` + 수동 지수 백오프 + lifespan + `app.state` + Depends). 인증은 기존
OAuth REST 키를 `Authorization: KakaoAK` 헤더로 재사용한다(신규 Kakao 키 없음).
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

_MAX_SIZE = 15  # Kakao keyword 페이지당 상한.
_MAX_RADIUS_M = 20000  # Kakao radius 상한(m).


class KakaoLocalError(Exception):
    """Kakao Local 호출 실패의 베이스."""


class KakaoLocalUnavailable(KakaoLocalError):
    """타임아웃 / 연결 실패 / 5xx(재시도 소진) / 키 미설정 — degrade 대상."""


class KakaoLocalClient:
    """Kakao Local 전송 전용(httpx.AsyncClient 1개). 표시 전용 — 콘텐츠 미저장."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        rest_api_key: str,
        max_attempts: int = 2,
        backoff_base_seconds: float = 0.2,
    ) -> None:
        self._http = http
        self._key = (rest_api_key or "").strip()
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

    async def search_keyword(
        self,
        *,
        query: str,
        size: int,
        x: float | None = None,
        y: float | None = None,
        radius: int | None = None,
    ) -> dict[str, Any]:
        """키워드 장소 검색. 좌표(x/y)는 "내 주변 검색" 동의 뒤에만 전달한다(§9)."""
        params: dict[str, Any] = {"query": query, "size": max(1, min(size, _MAX_SIZE))}
        if x is not None and y is not None:
            params |= {
                "x": x,
                "y": y,
                "radius": min(radius or _MAX_RADIUS_M, _MAX_RADIUS_M),
                "sort": "distance",
            }
        return await self._get("/v2/local/search/keyword.json", params)

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """transient(타임아웃/연결/5xx)만 지수 백오프 재시도, 4xx는 즉시 실패."""
        headers = self._auth_headers()
        last: KakaoLocalUnavailable | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = await self._http.get(path, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KakaoLocalUnavailable(f"Kakao Local 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                    last = KakaoLocalUnavailable(f"Kakao Local {resp.status_code} ({path})")
                elif resp.status_code >= status.HTTP_400_BAD_REQUEST:
                    # 4xx(키 무효/쿼터 초과 포함)는 degrade로 취급하고 재시도하지 않는다.
                    raise KakaoLocalUnavailable(f"Kakao Local {resp.status_code} ({path})")
                else:
                    body = resp.json()
                    if not isinstance(body, dict):
                        raise KakaoLocalUnavailable(f"Kakao Local 예상치 못한 응답({path})")
                    return body
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
        logger.warning("kakao_local.unavailable", extra={"path": path})
        raise last or KakaoLocalUnavailable(f"Kakao Local 요청 실패({path})")

    def _auth_headers(self) -> dict[str, str]:
        if not self._key:
            raise KakaoLocalUnavailable("Kakao REST 키가 설정되지 않았습니다.")
        return {"Authorization": f"KakaoAK {self._key}"}


def create_kakao_local_client(app_settings: Settings) -> KakaoLocalClient:
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kakao_local_base_url,
        timeout=app_settings.pinvi_place_provider_timeout_seconds,
        event_hooks=api_call_event_hooks(db_session.async_session_factory, provider="kakao_local"),
    )
    return KakaoLocalClient(
        http,
        rest_api_key=app_settings.pinvi_kakao_oauth_rest_api_key,
        max_attempts=app_settings.pinvi_place_provider_max_attempts,
    )


@asynccontextmanager
async def kakao_local_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    # provider disable 시 client를 만들지 않는다 → Depends가 degrade로 처리(§7).
    if not settings.pinvi_kakao_local_enabled:
        app.state.kakao_local_client = None
        yield
        return
    client = create_kakao_local_client(settings)
    app.state.kakao_local_client = client
    logger.info("kakao_local.client_ready", extra={"base_url": settings.pinvi_kakao_local_base_url})
    try:
        yield
    finally:
        await client.aclose()
        app.state.kakao_local_client = None


def get_kakao_local_client(request: Request) -> KakaoLocalClient | None:
    """client가 없으면(disable/미기동) None → `/search`가 degrade로 처리(hard fail 아님)."""
    client = getattr(request.app.state, "kakao_local_client", None)
    return client if isinstance(client, KakaoLocalClient) else None


KakaoLocalClientDep = Annotated[KakaoLocalClient | None, Depends(get_kakao_local_client)]
