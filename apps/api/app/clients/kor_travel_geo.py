"""kor-travel-geo v2 REST client (geocoding/주소/행정구역) — `docs/integrations/kor-travel-geo.md`.

ADR-025: 사용자 대면 geocoding은 `kor-travel-geo`의 v2 REST API를 직접 HTTP 호출한다.
in-process import / DB 직접 접근을 사용자 경로에서 쓰지 않는다. 좌표는 항상 `(lon, lat)`.

응답 최상위는 kor-travel-map과 달리 공통 헤더 `{status, query_id, input, ...}` 형태(envelope
`data` 없음). geocode/reverse/search는 `candidates[]`를, `/v2/regions/within-radius`는
level별 그룹 배열(`center, radius_km, sido[], sigungu[], emd[]`)을 함께 싣는다(geo ADR-060·062).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.clients._resilience import BULKHEAD_REJECTIONS, TransportCircuit
from app.core.config import Settings, settings
from app.db import session as db_session
from app.middleware.api_call_logging import ApiCallLoggingClient, api_call_event_hooks

logger = logging.getLogger(__name__)


class KorTravelGeoError(Exception):
    """kor-travel-geo 호출 실패의 베이스."""


class KorTravelGeoUnavailable(KorTravelGeoError):
    """타임아웃 / 연결 실패 / 5xx (재시도 소진)."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code
        super().__init__(message)


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
        max_concurrent_requests: int = 16,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._api_key = (api_key or "").strip()
        self._max_attempts = max(1, max_attempts)
        self._backoff_base_seconds = backoff_base_seconds
        if max_concurrent_requests < 1:
            raise ValueError("max_concurrent_requests는 양수여야 합니다.")
        self._slots = asyncio.Semaphore(max_concurrent_requests)
        self._transport_circuit = TransportCircuit(clock=clock)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _post(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        max_attempts: int | None = None,
        attempt_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if self._slots.locked():
            BULKHEAD_REJECTIONS.labels(provider="kor_travel_geo", scope="all").inc()
            raise KorTravelGeoUnavailable(
                "kor-travel-geo 동시 호출 상한 — 호출하지 않음", code="BULKHEAD_FULL"
            )
        async with self._slots:
            token = self._transport_circuit.acquire()
            if token is None:
                raise KorTravelGeoUnavailable(
                    "kor-travel-geo 회로 열림 — 호출하지 않음", code="CIRCUIT_OPEN"
                )
            try:
                result = await self._post_with_retries(
                    path,
                    payload,
                    max_attempts=max_attempts,
                    attempt_timeout_seconds=attempt_timeout_seconds,
                )
            except KorTravelGeoUnavailable as exc:
                if exc.code in {"POOL_TIMEOUT", "AUTH_NOT_CONFIGURED"}:
                    self._transport_circuit.release(token)
                else:
                    self._transport_circuit.failure(token)
                raise
            except KorTravelGeoBadRequest:
                self._transport_circuit.success(token)
                raise
            except BaseException:
                self._transport_circuit.release(token)
                raise
            self._transport_circuit.success(token)
            return result

    async def _post_with_retries(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        max_attempts: int | None = None,
        attempt_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """transient(타임아웃/연결/5xx) 시 지수 백오프 재시도 후 최상위 dict 반환.

        `max_attempts`/`attempt_timeout_seconds`는 호출 단위 덮어쓰기다(기본은 client 설정).
        """
        last: KorTravelGeoUnavailable | None = None
        body = {k: v for k, v in payload.items() if v is not None}
        attempts = self._max_attempts if max_attempts is None else max(1, max_attempts)
        request_timeout: Any = (
            httpx.USE_CLIENT_DEFAULT if attempt_timeout_seconds is None else attempt_timeout_seconds
        )
        for attempt in range(attempts):
            try:
                resp = await self._http.post(
                    path, params=self._auth_params(), json=body, timeout=request_timeout
                )
            except httpx.PoolTimeout as exc:
                raise KorTravelGeoUnavailable(
                    f"kor-travel-geo 연결 풀 대기 초과({path})", code="POOL_TIMEOUT"
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KorTravelGeoUnavailable(f"kor-travel-geo 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                    last = KorTravelGeoUnavailable(f"kor-travel-geo {resp.status_code} ({path})")
                else:
                    return self._unwrap(resp)
            if attempt + 1 < attempts:
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
                "kor-travel-geo v2 공개 API key가 설정되지 않았습니다.", code="AUTH_NOT_CONFIGURED"
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
        max_attempts: int | None = None,
        attempt_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """주소/도로명/행정구역/장소 검색(자동완성). data = {status, total, candidates[]}.

        자동완성 호출부는 `max_attempts=1`과 짧은 `attempt_timeout_seconds`를 넘긴다 — 짧은 검색어에서 geo가
        DB statement timeout(504 E0504)을 내면 그건 재시도해도 같은 결과다.
        """
        return await self._post(
            "/v2/search",
            {"query": query, "type": kind, "sig_cd": sig_cd, "page": page, "size": size},
            max_attempts=max_attempts,
            attempt_timeout_seconds=attempt_timeout_seconds,
        )

    async def regions_within_radius(
        self,
        *,
        lon: float,
        lat: float,
        radius_km: float,
        levels: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """좌표 반경 내 행정구역(level별 그룹).

        v2 계약: `radius_km`(≤500) + `levels`(sido|sigungu|emd, 비어있지 않음).
        data = {status, center, radius_km, sido[], sigungu[], emd[]} (구 candidate[] 폐지).
        """
        return await self._post(
            "/v2/regions/within-radius",
            {
                "lon": lon,
                "lat": lat,
                "radius_km": radius_km,
                "levels": list(levels) if levels else None,
            },
        )

    async def healthz(self) -> dict[str, Any]:
        # 진단 GET도 같은 provider 상한을 쓴다. 본 요청의 회로 판정은 변경하지 않는다.
        if self._slots.locked():
            BULKHEAD_REJECTIONS.labels(provider="kor_travel_geo", scope="all").inc()
            raise KorTravelGeoUnavailable(
                "kor-travel-geo 동시 호출 상한 — 호출하지 않음", code="BULKHEAD_FULL"
            )
        async with self._slots:
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
    http = ApiCallLoggingClient(
        base_url=app_settings.pinvi_kor_travel_geo_base_url,
        timeout=app_settings.pinvi_kor_travel_geo_timeout_seconds,
        event_hooks=api_call_event_hooks(
            db_session.async_session_factory, provider="kor_travel_geo"
        ),
    )
    return KorTravelGeoClient(
        http,
        api_key=(
            app_settings.pinvi_kor_travel_geo_api_key.get_secret_value()
            if app_settings.pinvi_kor_travel_geo_api_key is not None
            else ""
        ),
        max_attempts=app_settings.pinvi_kor_travel_geo_max_attempts,
        max_concurrent_requests=app_settings.pinvi_kor_travel_geo_max_concurrency,
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
