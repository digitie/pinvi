"""kraddr-geo v2 REST client (geocoding/주소/행정구역) — `docs/integrations/kraddr-geo.md`.

ADR-025: 사용자 대면 geocoding은 `python-kraddr-geo`의 v2 REST API를 직접 HTTP 호출한다.
in-process import / DB 직접 접근을 사용자 경로에서 쓰지 않는다. 좌표는 항상 `(lon, lat)`.

응답 최상위는 krtour-map과 달리 `{status, candidates[], ...}` 형태(envelope `data` 없음).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)


class KraddrGeoError(Exception):
    """kraddr-geo 호출 실패의 베이스."""


class KraddrGeoUnavailable(KraddrGeoError):
    """타임아웃 / 연결 실패 / 5xx (재시도 소진)."""


class KraddrGeoBadRequest(KraddrGeoError):
    """4xx 요청 오류."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code
        super().__init__(message)


class KraddrGeoClient:
    """kraddr-geo v2 REST 전송 전용 client (httpx.AsyncClient 1개)."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.2,
    ) -> None:
        self._http = http
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """transient(타임아웃/연결/5xx) 시 지수 백오프 재시도 후 최상위 dict 반환."""
        last: KraddrGeoUnavailable | None = None
        body = {k: v for k, v in payload.items() if v is not None}
        for attempt in range(self._max_attempts):
            try:
                resp = await self._http.post(path, json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KraddrGeoUnavailable(f"kraddr-geo 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                    last = KraddrGeoUnavailable(f"kraddr-geo {resp.status_code} ({path})")
                else:
                    return self._unwrap(resp)
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
        logger.warning("kraddr_geo.unavailable", extra={"path": path})
        raise last or KraddrGeoUnavailable(f"kraddr-geo 요청 실패({path})")

    @staticmethod
    def _unwrap(resp: httpx.Response) -> dict[str, Any]:
        sc = resp.status_code
        if sc >= status.HTTP_400_BAD_REQUEST:
            raise KraddrGeoBadRequest(f"kraddr-geo {sc}", code=_error_code(resp))
        body = resp.json()
        if not isinstance(body, dict):
            raise KraddrGeoError(f"예상치 못한 응답 셰입({resp.request.url.path})")
        return body

    # ── v2 endpoint (docs/integrations/kraddr-geo.md §3) ───────────────────

    async def geocode(
        self,
        *,
        query: str,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """주소 → 좌표. data = {status, query_id, input, candidates[]}."""
        return await self._post(
            "/v2/geocode",
            {"query": query, "sig_cd": sig_cd, "bjd_cd": bjd_cd, "limit": limit},
        )

    async def reverse(
        self,
        *,
        lon: float,
        lat: float,
        radius_m: int | None = None,
        include_region: bool = True,
        include_zipcode: bool = True,
    ) -> dict[str, Any]:
        """좌표 → 주소/행정구역. data = {status, candidates[]}."""
        return await self._post(
            "/v2/reverse",
            {
                "lon": lon,
                "lat": lat,
                "radius_m": radius_m,
                "include_region": include_region,
                "include_zipcode": include_zipcode,
            },
        )

    async def search(
        self,
        *,
        query: str,
        kind: str | None = None,
        sig_cd: str | None = None,
        page: int | None = None,
        size: int | None = None,
    ) -> dict[str, Any]:
        """주소/도로명/행정구역/장소 검색(자동완성). data = {status, total, candidates[]}."""
        return await self._post(
            "/v2/search",
            {"query": query, "type": kind, "sig_cd": sig_cd, "page": page, "size": size},
        )

    async def regions_within_radius(
        self,
        *,
        lon: float,
        lat: float,
        radius_m: int,
        boundary_level: str | None = None,
    ) -> dict[str, Any]:
        """좌표 반경 내 행정구역 후보. data = {status, candidates[]}."""
        return await self._post(
            "/v2/regions/within-radius",
            {
                "lon": lon,
                "lat": lat,
                "radius_m": radius_m,
                "boundary_level": boundary_level,
            },
        )

    async def healthz(self) -> dict[str, Any]:
        resp = await self._http.get("/v1/healthz")
        body = resp.json()
        return body if isinstance(body, dict) else {"status": "unknown"}


def _error_code(resp: httpx.Response) -> str | None:
    try:
        payload = resp.json()
    except ValueError:
        return None
    if isinstance(payload, Mapping):
        for key in ("code", "error_code"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        error = payload.get("error")
        if isinstance(error, Mapping) and isinstance(error.get("code"), str):
            return str(error["code"])
    return None


def create_kraddr_geo_client(app_settings: Settings) -> KraddrGeoClient:
    http = httpx.AsyncClient(
        base_url=app_settings.tripmate_kraddr_geo_base_url,
        timeout=app_settings.tripmate_kraddr_geo_timeout_seconds,
    )
    return KraddrGeoClient(http, max_attempts=app_settings.tripmate_kraddr_geo_max_attempts)


@asynccontextmanager
async def kraddr_geo_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = create_kraddr_geo_client(settings)
    app.state.kraddr_geo_client = client
    logger.info(
        "kraddr_geo.client_ready", extra={"base_url": settings.tripmate_kraddr_geo_base_url}
    )
    try:
        yield
    finally:
        await client.aclose()
        app.state.kraddr_geo_client = None


def get_kraddr_geo_client(request: Request) -> KraddrGeoClient:
    client = getattr(request.app.state, "kraddr_geo_client", None)
    if not isinstance(client, KraddrGeoClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "GEOCODING_SERVICE_UNAVAILABLE",
                "message": "geocoding 서비스가 일시적으로 사용 불가합니다.",
            },
        )
    return client


KraddrGeoClientDep = Annotated[KraddrGeoClient, Depends(get_kraddr_geo_client)]
