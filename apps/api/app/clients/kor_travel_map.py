"""kor-travel-map OpenAPI HTTP client (transport-only).

`kor-travel-map`의 운영 HTTP API(`kor-travel-map-api`, 포트 12701,
`openapi.user.json`)를 호출하는 httpx 기반 client다. ADR-026/027(DEC-01=B) 기준이며
in-process import(`from kor_travel_map.map import ...`)를 쓰지 않는다.

- transport 역할만 한다(ADR-005). provider 변환/feature 정규화 같은 도메인 wrapper를
  만들지 않는다. 응답은 kor_travel_map envelope(`{data, meta}`)에서 `data`만 풀어 dict로 돌려준다.
- 응답 셰입을 Pinvi schema로 매핑하는 책임은 라우터/뷰 계층(T-173/T-124)이다.
- 에러는 도메인 예외로 올리고, HTTP status 변환(503 FEATURE_SERVICE_UNAVAILABLE 등)은
  라우터(T-178)가 한다.

계약: `docs/integrations/kor-travel-map-rest-api.md`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"  # noqa: S105 - 헤더 이름(비밀 아님)


class KorTravelMapError(Exception):
    """kor-travel-map 호출 일반 오류."""


class KorTravelMapUnavailable(KorTravelMapError):
    """timeout / 연결 실패 / 5xx — 재시도 후에도 실패(503 매핑 대상)."""


class KorTravelMapFeatureNotFound(KorTravelMapError):
    """404 FEATURE_NOT_FOUND."""


class KorTravelMapBadRequest(KorTravelMapError):
    """4xx 잘못된 요청 (422 INVALID_BBOX / TOO_MANY_IDS 등)."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class KorTravelMapConflict(KorTravelMapError):
    """409 invalid state/conflict — lock busy가 아닌 운영 상태 충돌."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class KorTravelMapRateLimited(KorTravelMapError):
    """429 RATE_LIMITED / 409 LOCK_BUSY — Retry-After 존중."""

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class KorTravelMapClient:
    """kor-travel-map user-facing OpenAPI(`openapi.user.json`) HTTP client."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        service_token: str = "",
        public_api_key: str = "",
        max_attempts: int = 3,
        batch_chunk_size: int = 200,
        backoff_base_seconds: float = 0.2,
    ) -> None:
        self._http = http
        self._service_token = service_token.strip()
        self._public_api_key = public_api_key.strip()
        self._max_attempts = max(1, max_attempts)
        self._batch_chunk_size = max(1, batch_chunk_size)
        self._backoff_base_seconds = backoff_base_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── 내부 ────────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        if self._service_token:
            return {_SERVICE_TOKEN_HEADER: self._service_token}
        return {}

    def _params(self, path: str, params: Mapping[str, Any] | None) -> dict[str, Any] | None:
        merged = dict(params or {})
        if (
            self._public_api_key
            and not self._service_token
            and path.startswith("/v1/")
            and "key" not in merged
        ):
            merged["key"] = self._public_api_key
        return merged or None

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
    ) -> httpx.Response:
        """transient(타임아웃/연결/5xx) 시 지수 백오프 재시도."""
        last: KorTravelMapUnavailable | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = await self._http.request(
                    method,
                    path,
                    params=self._params(path, params),
                    json=json,
                    headers=self._headers(),
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KorTravelMapUnavailable(f"kor-travel-map 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= 500:
                    last = KorTravelMapUnavailable(f"kor-travel-map {resp.status_code} ({path})")
                else:
                    return resp
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
        logger.warning("kor_travel_map.unavailable", extra={"path": path})
        raise last or KorTravelMapUnavailable(f"kor-travel-map 요청 실패({path})")

    @staticmethod
    def _retry_after(resp: httpx.Response) -> int | None:
        raw = resp.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _payload(self, resp: httpx.Response) -> tuple[dict[str, Any], dict[str, Any]]:
        """성공 응답에서 `(data, meta)` 추출. 오류 status는 도메인 예외로 변환.

        kor_travel_map 0e45bd7 envelope = `{data: <payload>, meta: <Meta>}` (ADR-048).
        에러는 RFC7807 problem+json — 머신 코드는 top-level 확장 `code`.
        """
        sc = resp.status_code
        if sc == status.HTTP_404_NOT_FOUND:
            raise KorTravelMapFeatureNotFound("feature 를 찾을 수 없습니다.")
        if sc in (status.HTTP_429_TOO_MANY_REQUESTS, status.HTTP_409_CONFLICT):
            raise KorTravelMapRateLimited(
                f"kor-travel-map {sc}", retry_after_seconds=self._retry_after(resp)
            )
        if sc >= status.HTTP_400_BAD_REQUEST:
            raise KorTravelMapBadRequest(f"kor-travel-map {sc}", code=_error_code(resp))
        payload = resp.json()
        data = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(data, dict):
            raise KorTravelMapError(f"예상치 못한 응답 셰입({resp.request.url.path})")
        meta = payload.get("meta") if isinstance(payload, Mapping) else None
        return data, meta if isinstance(meta, dict) else {}

    def _data(self, resp: httpx.Response) -> dict[str, Any]:
        """성공 응답에서 `data`(dict)만 추출 — 단건/배치 등 page 없는 표면용."""
        return self._payload(resp)[0]

    @staticmethod
    def _thread_page(data: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
        """`meta.page`(next_cursor/total)를 data로 re-projection (구 `data.next_cursor` 폐기)."""
        page = meta.get("page")
        if isinstance(page, Mapping):
            data["next_cursor"] = page.get("next_cursor")
            if "total" in page:
                data["total"] = page.get("total")
        return data

    # ── 사용자 표면 (openapi.user.json) ─────────────────────────────────────

    async def features_in_bounds(
        self,
        *,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        kinds: Sequence[str] | None = None,
        category: str | None = None,
        zoom: int | None = None,
        cluster_unit: str | None = None,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        """viewport feature + 서버 클러스터. data = {clusters, items}.

        `max_items`(≤2000, 기본 1000 — 구 `limit` 폐기, ADR-048). granularity는
        `meta.cluster.cluster_unit`로 오므로 data에 re-projection(구 `data.cluster_unit` 폐기).
        """
        params: dict[str, Any] = {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
        }
        if kinds:
            params["kind"] = list(kinds)
        if category is not None:
            params["category"] = category
        if zoom is not None:
            params["zoom"] = zoom
        if cluster_unit is not None:
            params["cluster_unit"] = cluster_unit
        if max_items is not None:
            params["max_items"] = max_items
        data, meta = self._payload(await self._send("GET", "/v1/features/in-bounds", params=params))
        cluster = meta.get("cluster")
        if isinstance(cluster, Mapping) and "cluster_unit" in cluster:
            data["cluster_unit"] = cluster.get("cluster_unit")
        return data

    async def get_feature(self, feature_id: str) -> dict[str, Any] | None:
        """단건 상세. 404 → None."""
        resp = await self._send("GET", f"/v1/features/{feature_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            return None
        return self._data(resp)

    async def get_features(self, feature_ids: Sequence[str]) -> dict[str, Any]:
        """배치 조회 — cap 초과 시 청크 분할. data = {found: {id: detail}, missing: [id]}.

        id-keyed map 키는 ADR-048에서 `items`→`found`로 확정(list `items[]`와 타입 분리).
        inactive feature(reject/tombstone/deactivate)는 `missing`이 아니라 `found`에
        status와 함께 옴(kor_travel_map D-12) — 호출자(snapshot fallback)가 "철회/폐업" 분기.
        """
        unique = list(dict.fromkeys(feature_ids))
        found: dict[str, Any] = {}
        missing: list[str] = []
        for start in range(0, len(unique), self._batch_chunk_size):
            chunk = unique[start : start + self._batch_chunk_size]
            data = self._data(
                await self._send("POST", "/v1/features/batch", json={"feature_ids": chunk})
            )
            chunk_found = data.get("found")
            if isinstance(chunk_found, dict):
                found.update(chunk_found)
            chunk_missing = data.get("missing")
            if isinstance(chunk_missing, list):
                missing.extend(str(x) for x in chunk_missing)
        return {"found": found, "missing": missing}

    async def features_nearby(
        self,
        *,
        lon: float,
        lat: float,
        radius_m: float,
        kinds: Sequence[str] | None = None,
        category: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        """반경 조회. data = {origin, items:[+distance_m]} + threaded next_cursor/total.

        pagination은 `meta.page`(구 `data.next_cursor` 폐기) — client가 data로 re-projection.
        """
        params: dict[str, Any] = {"lon": lon, "lat": lat, "radius_m": radius_m}
        if kinds:
            params["kind"] = list(kinds)
        if category is not None:
            params["category"] = category
        if page_size is not None:
            params["page_size"] = page_size
        if cursor is not None:
            params["cursor"] = cursor
        if sort is not None:
            params["sort"] = sort
        data, meta = self._payload(await self._send("GET", "/v1/features/nearby", params=params))
        return self._thread_page(data, meta)

    async def search_features(
        self,
        *,
        q: str | None = None,
        min_lon: float | None = None,
        min_lat: float | None = None,
        max_lon: float | None = None,
        max_lat: float | None = None,
        kinds: Sequence[str] | None = None,
        category: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        include_total: bool = False,
    ) -> dict[str, Any]:
        """텍스트 검색(feature만). data = {items} + threaded next_cursor/total.

        bbox는 ADR-048 clean cut으로 분리 float 4개(min_lon/min_lat/max_lon/max_lat).
        pagination은 `meta.page`(구 `data.next_cursor`/`total_count` 폐기). `total`은
        `include_total=true` opt-in일 때만 채워짐(기본 null).
        """
        params: dict[str, Any] = {}
        if q is not None:
            params["q"] = q
        if min_lon is not None:
            params["min_lon"] = min_lon
        if min_lat is not None:
            params["min_lat"] = min_lat
        if max_lon is not None:
            params["max_lon"] = max_lon
        if max_lat is not None:
            params["max_lat"] = max_lat
        if kinds:
            params["kind"] = list(kinds)
        if category is not None:
            params["category"] = category
        if page_size is not None:
            params["page_size"] = page_size
        if cursor is not None:
            params["cursor"] = cursor
        if include_total:
            params["include_total"] = True
        data, meta = self._payload(await self._send("GET", "/v1/features/search", params=params))
        return self._thread_page(data, meta)

    async def feature_weather(
        self, feature_id: str, *, asof: datetime | None = None
    ) -> dict[str, Any]:
        """날씨 카드. data = {feature_id, asof, is_stale, source_styles, metrics}."""
        params: dict[str, Any] = {}
        if asof is not None:
            params["asof"] = asof.isoformat()
        return self._data(
            await self._send("GET", f"/v1/features/{feature_id}/weather", params=params)
        )

    async def categories(
        self, *, include_counts: bool = False, active_only: bool = False
    ) -> dict[str, Any]:
        """카테고리 카탈로그. data = {count, include_counts, items}."""
        params = {"include_counts": include_counts, "active_only": active_only}
        return self._data(await self._send("GET", "/v1/categories", params=params))

    async def public_beaches(
        self,
        *,
        sido_code: str | None = None,
        sigungu_code: str | None = None,
        q: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        include_quality: bool = False,
        include_forecast: bool = False,
    ) -> dict[str, Any]:
        """공개 해수욕장 목록. data = {items} + threaded next_cursor/total."""
        params: dict[str, Any] = {
            "include_quality": include_quality,
            "include_forecast": include_forecast,
        }
        if sido_code is not None:
            params["sido_code"] = sido_code
        if sigungu_code is not None:
            params["sigungu_code"] = sigungu_code
        if q is not None:
            params["q"] = q
        if page_size is not None:
            params["page_size"] = page_size
        if cursor is not None:
            params["cursor"] = cursor
        data, meta = self._payload(await self._send("GET", "/v1/public/beaches", params=params))
        return self._thread_page(data, meta)

    async def public_beach_markers(
        self,
        *,
        min_lon: float | None = None,
        min_lat: float | None = None,
        max_lon: float | None = None,
        max_lat: float | None = None,
        sido_code: str | None = None,
        sigungu_code: str | None = None,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        """공개 해수욕장 지도 marker layer. data = {layer_key, display_name, items}."""
        params: dict[str, Any] = {}
        for key, value in (
            ("min_lon", min_lon),
            ("min_lat", min_lat),
            ("max_lon", max_lon),
            ("max_lat", max_lat),
            ("sido_code", sido_code),
            ("sigungu_code", sigungu_code),
            ("max_items", max_items),
        ):
            if value is not None:
                params[key] = value
        return self._data(await self._send("GET", "/v1/public/beaches/map-markers", params=params))

    async def get_public_beach(
        self,
        feature_id: str,
        *,
        include_quality: bool = False,
        include_forecast: bool = False,
    ) -> dict[str, Any] | None:
        """공개 해수욕장 상세. 404 → None."""
        resp = await self._send(
            "GET",
            f"/v1/public/beaches/{feature_id}",
            params={"include_quality": include_quality, "include_forecast": include_forecast},
        )
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            return None
        return self._data(resp)

    async def public_festivals_monthly(
        self,
        *,
        year: int | None = None,
        month: int | None = None,
        sido_code: str | None = None,
        sigungu_code: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        include_months: bool = True,
    ) -> dict[str, Any]:
        """공개 월별 축제 목록. data = {months, items} + threaded next_cursor/total."""
        params: dict[str, Any] = {"include_months": include_months}
        for key, value in (
            ("year", year),
            ("month", month),
            ("sido_code", sido_code),
            ("sigungu_code", sigungu_code),
            ("page_size", page_size),
            ("cursor", cursor),
        ):
            if value is not None:
                params[key] = value
        data, meta = self._payload(
            await self._send("GET", "/v1/public/festivals/monthly", params=params)
        )
        return self._thread_page(data, meta)

    async def public_festival_markers(
        self,
        *,
        year: int | None = None,
        month: int | None = None,
        min_lon: float | None = None,
        min_lat: float | None = None,
        max_lon: float | None = None,
        max_lat: float | None = None,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        """공개 축제 지도 marker layer. data = {layer_key, display_name, items}."""
        params: dict[str, Any] = {}
        for key, value in (
            ("year", year),
            ("month", month),
            ("min_lon", min_lon),
            ("min_lat", min_lat),
            ("max_lon", max_lon),
            ("max_lat", max_lat),
            ("max_items", max_items),
        ):
            if value is not None:
                params[key] = value
        return self._data(
            await self._send("GET", "/v1/public/festivals/map-markers", params=params)
        )

    async def get_public_festival(self, feature_id: str) -> dict[str, Any] | None:
        """공개 축제 상세. 404 → None."""
        resp = await self._send("GET", f"/v1/public/festivals/{feature_id}")
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            return None
        return self._data(resp)

    async def healthz(self) -> dict[str, Any]:
        """liveness. envelope 없이 raw 객체일 수 있어 그대로 반환."""
        resp = await self._send("GET", "/health")
        body = resp.json()
        return body if isinstance(body, dict) else {"status": "unknown"}


def _error_code(resp: httpx.Response) -> str | None:
    """RFC7807 problem+json의 top-level 확장 `code`를 읽는다(구 `error.code`는 fallback)."""
    try:
        payload = resp.json()
    except ValueError:
        return None
    if isinstance(payload, Mapping):
        code = payload.get("code")  # problem+json top-level 확장(kor_travel_map 0e45bd7)
        if isinstance(code, str):
            return code
        error = payload.get("error")  # 구 envelope fallback
        if isinstance(error, Mapping):
            legacy = error.get("code")
            if isinstance(legacy, str):
                return legacy
    return None


def create_kor_travel_map_client(app_settings: Settings) -> KorTravelMapClient:
    """설정 기반 client 생성 (httpx.AsyncClient 1개)."""
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kor_travel_map_api_base_url,
        timeout=app_settings.pinvi_kor_travel_map_timeout_seconds,
    )
    return KorTravelMapClient(
        http,
        service_token=app_settings.pinvi_kor_travel_map_service_token,
        public_api_key=(
            app_settings.pinvi_kor_travel_map_public_api_key or app_settings.pinvi_vworld_api_key
        ),
        max_attempts=app_settings.pinvi_kor_travel_map_max_attempts,
        batch_chunk_size=app_settings.pinvi_kor_travel_map_batch_chunk_size,
    )


@asynccontextmanager
async def kor_travel_map_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — httpx client 1개 생성 후 `app.state`에 보관."""
    client = create_kor_travel_map_client(settings)
    app.state.kor_travel_map_client = client
    logger.info(
        "kor_travel_map.client_ready",
        extra={"base_url": settings.pinvi_kor_travel_map_api_base_url},
    )
    try:
        yield
    finally:
        await client.aclose()
        app.state.kor_travel_map_client = None


def get_kor_travel_map_client(request: Request) -> KorTravelMapClient:
    """FastAPI 의존성 — `app.state`의 client. 미주입 시 503."""
    client = getattr(request.app.state, "kor_travel_map_client", None)
    if not isinstance(client, KorTravelMapClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": "지도 feature 서비스가 일시적으로 사용 불가합니다.",
            },
        )
    return client


KorTravelMapHttpClientDep = Annotated[KorTravelMapClient, Depends(get_kor_travel_map_client)]


def get_optional_kor_travel_map_client(request: Request) -> KorTravelMapClient | None:
    """FastAPI 의존성 — client 또는 None. 미주입 시 503이 아니라 None 반환.

    feature가 보조 정보인 경로(trip 상세 view 등)에서 쓴다 — client 부재 시 POI
    `feature_snapshot`으로 degrade한다. 사용자 대면 feature read 라우터는
    `get_kor_travel_map_client`(503)를 쓴다.
    """
    client = getattr(request.app.state, "kor_travel_map_client", None)
    return client if isinstance(client, KorTravelMapClient) else None


OptionalKorTravelMapHttpClientDep = Annotated[
    KorTravelMapClient | None, Depends(get_optional_kor_travel_map_client)
]
