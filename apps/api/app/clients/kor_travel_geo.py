"""kor-travel-geo v2 REST client (geocoding/주소/행정구역) — `docs/integrations/kor-travel-geo.md`.

ADR-025: 사용자 대면 geocoding은 `kor-travel-geo`의 v2 REST API를 직접 HTTP 호출한다.
in-process import / DB 직접 접근을 사용자 경로에서 쓰지 않는다. 좌표는 항상 `(lon, lat)`.

응답 최상위는 kor-travel-map과 달리 `{status, candidates[], ...}` 형태(envelope `data` 없음).
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


class KorTravelGeoError(Exception):
    """kor-travel-geo 호출 실패의 베이스."""


class KorTravelGeoUnavailable(KorTravelGeoError):
    """타임아웃 / 연결 실패 / 5xx (재시도 소진)."""


class KorTravelGeoBadRequest(KorTravelGeoError):
    """4xx 요청 오류."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code
        super().__init__(message)


class KorTravelGeoClient:
    """kor-travel-geo v2 REST 전송 전용 client (httpx.AsyncClient 1개)."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_key: str | None = None,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.2,
    ) -> None:
        self._http = http
        self._api_key = (api_key or "").strip()
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """transient(타임아웃/연결/5xx) 시 지수 백오프 재시도 후 최상위 dict 반환."""
        last: KorTravelGeoUnavailable | None = None
        body = {k: v for k, v in payload.items() if v is not None}
        for attempt in range(self._max_attempts):
            try:
                resp = await self._http.post(path, params=self._auth_params(), json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KorTravelGeoUnavailable(f"kor-travel-geo 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                    last = KorTravelGeoUnavailable(f"kor-travel-geo {resp.status_code} ({path})")
                else:
                    return self._unwrap(resp)
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
        logger.warning("kor_travel_geo.unavailable", extra={"path": path})
        raise last or KorTravelGeoUnavailable(f"kor-travel-geo 요청 실패({path})")

    @staticmethod
    def _unwrap(resp: httpx.Response) -> dict[str, Any]:
        sc = resp.status_code
        if sc >= status.HTTP_400_BAD_REQUEST:
            raise KorTravelGeoBadRequest(f"kor-travel-geo {sc}", code=_error_code(resp))
        body = resp.json()
        if not isinstance(body, dict):
            raise KorTravelGeoError(f"예상치 못한 응답 셰입({resp.request.url.path})")
        return body

    def _auth_params(self) -> dict[str, str]:
        if not self._api_key:
            raise KorTravelGeoUnavailable(
                "kor-travel-geo v2 공개 API key가 설정되지 않았습니다."
            )
        return {"key": self._api_key}

    # ── v2 endpoint (docs/integrations/kor-travel-geo.md §3) ───────────────────

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


def create_kor_travel_geo_client(app_settings: Settings) -> KorTravelGeoClient:
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kor_travel_geo_base_url,
        timeout=app_settings.pinvi_kor_travel_geo_timeout_seconds,
    )
    return KorTravelGeoClient(
        http,
        api_key=app_settings.pinvi_vworld_api_key,
        max_attempts=app_settings.pinvi_kor_travel_geo_max_attempts,
    )


@asynccontextmanager
async def kor_travel_geo_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = create_kor_travel_geo_client(settings)
    app.state.kor_travel_geo_client = client
    logger.info(
        "kor_travel_geo.client_ready", extra={"base_url": settings.pinvi_kor_travel_geo_base_url}
    )
    try:
        yield
    finally:
        await client.aclose()
        app.state.kor_travel_geo_client = None


def get_kor_travel_geo_client(request: Request) -> KorTravelGeoClient:
    client = getattr(request.app.state, "kor_travel_geo_client", None)
    if not isinstance(client, KorTravelGeoClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "GEOCODING_SERVICE_UNAVAILABLE",
                "message": "geocoding 서비스가 일시적으로 사용 불가합니다.",
            },
        )
    return client


KorTravelGeoClientDep = Annotated[KorTravelGeoClient, Depends(get_kor_travel_geo_client)]
