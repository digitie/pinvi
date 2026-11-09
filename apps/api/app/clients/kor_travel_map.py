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
import copy
import json
import logging
import math
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.clients._resilience import BULKHEAD_REJECTIONS, TransportCircuit
from app.core.config import Settings, settings
from app.db import session as db_session
from app.middleware.api_call_logging import ApiCallLoggingClient, api_call_event_hooks
from app.middleware.resilience_runtime import outbound_resilience_lifespan

logger = logging.getLogger(__name__)

_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"  # noqa: S105 - 헤더 이름(비밀 아님)
_PUBLIC_API_KEY_HEADER = "X-Kor-Travel-Map-Api-Key"
_POSTGRES_BIGINT_MAX = 9_223_372_036_854_775_807

#: pooled 연결을 Map(uvicorn 기본 ``--timeout-keep-alive`` 5초)이 닫기 **전에** 버린다. httpx 기본값도
#: 5초라 서버가 닫는 순간과 재사용이 겹치면 응답 없는 끊김(``RemoteProtocolError``)이 난다(#702).
KEEPALIVE_EXPIRY_SECONDS: float = 3.0

#: 회로 범위. 한 표면의 실패가 다른 표면을 끊지 않는다(#702 — 전국 viewport timeout이 검색·상세·trip
#: batch까지 120초 503으로 만들었다). weather 표면은 자체 회로(``kor_travel_map_weather``)만 쓴다.
#: ``festivals``: 공개 월별 축제 목록 — 첫 조회 월의 느린 응답이 검색·상세를 끊지 않게(#714).
CircuitScope = Literal["features", "viewport", "transport", "festivals"]
#: 동시 호출 상한(bulkhead) 범위(#621). 회로 범위와 같고, 자체 회로를 가진 weather 표면만 더한다.
#: 한 표면이 느려져 자리를 다 써도 다른 표면은 자기 자리로 Map에 닿는다.
BulkheadScope = Literal["features", "viewport", "transport", "festivals", "weather"]

#: 공개 월별 축제 목록의 read 예산(초). Map이 처음 조회하는 월은 기본 5초를 넘었다(#714 운영 2026-11-08:
#: 1·2월 5.9~6.2초 뒤 ReadTimeout, 직후 같은 월은 0.02~0.33초). 연결 예산은 기본값 그대로다.
FESTIVALS_MONTHLY_READ_TIMEOUT_SECONDS: float = 15.0
#: 성공한 월별 목록을 이 시간(초) 동안 재사용한다 — 공개 화면의 같은 질의가 Map을 다시 깨우지 않게.
FESTIVALS_MONTHLY_CACHE_TTL_SECONDS: float = 300.0
_FESTIVALS_MONTHLY_CACHE_MAX = 128
#: 축제 월별 목록이 동시에 쓰는 Map 호출 자리 상한 — 자기 bulkhead만 쓰고, 넘치면 바로 503(대기열 없음).
#: 연·월 없이 부르면 Map이 이번 달을 고르므로 월이 바뀐 직후 최대 TTL만큼 지난달 목록이 나올 수 있다(허용).
FESTIVALS_MAX_CONCURRENT_REQUESTS = 4

#: 백오프로 다시 보내는 오류 — 연결 자체가 맺어지지 않아 요청이 Map 처리에 닿지 않았다. ``ReadTimeout``·
#: ``ReadError``는 Map이 요청을 받아 처리 중이었거나 처리 도중 끊겼다는 뜻이라 다시 보내면 같은 무거운 질의를
#: 겹쳐 쌓을 뿐이다(#702 운영 기록: 같은 전국 bbox가 5초 timeout x3).
_RETRYABLE_TRANSPORT_ERRORS: tuple[type[httpx.TransportError], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
)
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD"})


def _path_segment(value: str) -> str | None:
    """외부 id를 Map URL 경로 한 세그먼트로만 넣는다. 라우터가 %3F·%2F를 디코드해 넘기므로
    그대로 붙이면 query·경로를 덧붙일 수 있다. 점 세그먼트는 존재할 수 없는 id라 None."""
    if value in ("", ".", ".."):
        return None
    return quote(value, safe="")


class KorTravelMapError(Exception):
    """kor-travel-map 호출 일반 오류."""


class KorTravelMapContractError(KorTravelMapError):
    """성공 HTTP 응답이 합의한 JSON/데이터 계약을 위반함."""


class KorTravelMapUnavailable(KorTravelMapError):
    """timeout / 연결 실패 / 5xx — 재시도 후에도 실패(503 매핑 대상)."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        retry_after_seconds: int | None = None,
        status_code: int = status.HTTP_503_SERVICE_UNAVAILABLE,
        error_class: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code
        #: 마지막 실패의 종류(``ReadTimeout``·``ConnectError``·``HTTP503`` …) — 로그·진단용, 비밀 없음.
        self.error_class = error_class


class KorTravelMapFeatureNotFound(KorTravelMapError):
    """404 FEATURE_NOT_FOUND."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class KorTravelMapBadRequest(KorTravelMapError):
    """4xx 잘못된 요청 (422 INVALID_BBOX / TOO_MANY_IDS 등)."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class KorTravelMapConflict(KorTravelMapError):
    """409 invalid state/conflict — lock busy가 아닌 운영 상태 충돌."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details
        self.retry_after_seconds = retry_after_seconds


class KorTravelMapPreconditionFailed(KorTravelMapError):
    """412 stale resource revision — 최신 snapshot 재조회 후 재시도 대상."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class KorTravelMapRateLimited(KorTravelMapError):
    """429 RATE_LIMITED / 409 LOCK_BUSY — Retry-After 존중."""

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class FeatureTripCard:
    """kor-travel-map service batch의 고정 ``trip_card`` projection."""

    feature_id: str
    kind: str
    name: str
    category: str
    lon: float | None
    lat: float | None
    address: dict[str, Any]
    marker_icon: str | None
    marker_color: str | None

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "kind": self.kind,
            "name": self.name,
            "category": self.category,
            "coord": (
                {"lon": self.lon, "lat": self.lat}
                if self.lon is not None and self.lat is not None
                else None
            ),
            "address": dict(self.address),
            "marker_icon": self.marker_icon,
            "marker_color": self.marker_color,
        }


@dataclass(frozen=True)
class FoundFeatureBatchItem:
    feature_id: str
    row_revision: int
    trip_card: FeatureTripCard
    state: Literal["found"] = "found"


@dataclass(frozen=True)
class RetiredFeatureBatchItem:
    feature_id: str
    row_revision: int
    state: Literal["retired"] = "retired"


@dataclass(frozen=True)
class SuppressedFeatureBatchItem:
    feature_id: str
    row_revision: int
    state: Literal["suppressed"] = "suppressed"


@dataclass(frozen=True)
class MissingFeatureBatchItem:
    feature_id: str
    state: Literal["missing"] = "missing"


@dataclass(frozen=True)
class UnchangedFeatureBatchItem:
    feature_id: str
    row_revision: int
    state: Literal["unchanged"] = "unchanged"


FeatureBatchItem = (
    FoundFeatureBatchItem
    | RetiredFeatureBatchItem
    | SuppressedFeatureBatchItem
    | MissingFeatureBatchItem
    | UnchangedFeatureBatchItem
)


_TRIP_CARD_FIELDS = frozenset(
    {
        "feature_id",
        "kind",
        "name",
        "category",
        "lon",
        "lat",
        "address",
        "marker_icon",
        "marker_color",
    }
)
# batch item의 **알려진** 키 어휘. 상태별로 있으면 안 되는 키(missing의 row_revision, found가 아닌
# 항목의 trip_card)는 여전히 거부한다 — 그건 더해진 필드가 아니라 의미가 어긋난 응답이다.
_BATCH_ITEM_FIELDS = frozenset({"state", "feature_id", "row_revision", "trip_card"})
_BATCH_DATA_FIELDS = frozenset({"items"})


# 같은 (위치, 키 집합)은 프로세스당 한 번만 warning으로 남긴다 — 더해진 키가 실은 **개명**이라
# 선택 필드가 조용히 비는 경우를 운영 로그에서 알아차릴 수 있게(debug는 prod에서 보이지 않는다).
_WARNED_ADDITIVE: set[tuple[str, frozenset[str]]] = set()


def _note_additive_fields(raw: Mapping[str, Any], known: frozenset[str], *, what: str) -> None:
    """내부 소비자는 정확한 셰입을 핀하지 않는다 — 모르는(더해진) 키는 무시하고 로그로만 남긴다.

    2026-11-02 prod e2e: Map이 batch item에 `feature_uuid`를 더하자 정확-집합 검사가 batch 전체를
    거부해 모든 trip POI가 `unverified`가 됐다. 필수 키와 타입·상태별 의미 검사는 그대로 둔다. 더해진
    키는 decode 결과에 실리지 않으므로(알려진 필드만 복사) snapshot으로 흘러들지 않는다.
    """
    extra = frozenset(set(raw) - known)
    if not extra:
        return
    key = (what, extra)
    if key in _WARNED_ADDITIVE:
        logger.debug("kor_travel_map.%s additive fields ignored: %s", what, sorted(extra))
        return
    _WARNED_ADDITIVE.add(key)
    logger.warning("kor_travel_map.%s additive fields ignored: %s", what, sorted(extra))


def _decode_feature_trip_card(raw: object, feature_id: str) -> FeatureTripCard:
    if not isinstance(raw, Mapping):
        raise KorTravelMapContractError("feature batch found item의 trip_card가 객체가 아닙니다.")
    if not _TRIP_CARD_FIELDS <= set(raw):
        raise KorTravelMapContractError("feature batch trip_card 필드 집합이 올바르지 않습니다.")
    _note_additive_fields(raw, _TRIP_CARD_FIELDS, what="trip_card")
    if raw["feature_id"] != feature_id:
        raise KorTravelMapContractError("feature batch item과 trip_card feature_id가 다릅니다.")
    if not all(isinstance(raw[field], str) for field in ("kind", "name", "category")):
        raise KorTravelMapContractError("feature batch trip_card 문자열 필드가 올바르지 않습니다.")
    if not isinstance(raw["address"], dict):
        raise KorTravelMapContractError("feature batch trip_card address가 객체가 아닙니다.")
    if not all(
        raw[field] is None or isinstance(raw[field], str)
        for field in ("marker_icon", "marker_color")
    ):
        raise KorTravelMapContractError("feature batch trip_card marker 필드가 올바르지 않습니다.")
    for field in ("lon", "lat"):
        value = raw[field]
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise KorTravelMapContractError(
                f"feature batch trip_card {field}이 유한한 숫자가 아닙니다."
            )
    return FeatureTripCard(
        feature_id=feature_id,
        kind=raw["kind"],
        name=raw["name"],
        category=raw["category"],
        lon=float(raw["lon"]) if raw["lon"] is not None else None,
        lat=float(raw["lat"]) if raw["lat"] is not None else None,
        address=dict(raw["address"]),
        marker_icon=raw["marker_icon"],
        marker_color=raw["marker_color"],
    )


def _decode_feature_batch_item(raw: object) -> FeatureBatchItem:
    if not isinstance(raw, Mapping):
        raise KorTravelMapContractError("feature batch item이 객체가 아닙니다.")
    state = raw.get("state")
    feature_id = raw.get("feature_id")
    if not isinstance(feature_id, str):
        raise KorTravelMapContractError("feature batch item feature_id가 문자열이 아닙니다.")
    _note_additive_fields(raw, _BATCH_ITEM_FIELDS, what="batch_item")
    # 상태별로 허용되는 **알려진** 키만 본다(더해진 키는 위에서 무시).
    known_keys = set(raw) & _BATCH_ITEM_FIELDS
    if state == "missing":
        if known_keys != {"state", "feature_id"}:
            raise KorTravelMapContractError("feature batch missing item 셰입이 올바르지 않습니다.")
        return MissingFeatureBatchItem(feature_id=feature_id)
    if state not in {"found", "retired", "suppressed", "unchanged"}:
        raise KorTravelMapContractError(f"알 수 없는 feature batch state입니다: {state!r}")
    row_revision = raw.get("row_revision")
    if (
        isinstance(row_revision, bool)
        or not isinstance(row_revision, int)
        or not 1 <= row_revision <= _POSTGRES_BIGINT_MAX
    ):
        raise KorTravelMapContractError(
            "feature batch row_revision이 PostgreSQL bigint 범위의 양의 정수가 아닙니다."
        )
    if state == "found":
        if known_keys != _BATCH_ITEM_FIELDS:
            raise KorTravelMapContractError("feature batch found item 셰입이 올바르지 않습니다.")
        return FoundFeatureBatchItem(
            feature_id=feature_id,
            row_revision=row_revision,
            trip_card=_decode_feature_trip_card(raw["trip_card"], feature_id),
        )
    if known_keys != {"state", "feature_id", "row_revision"}:
        raise KorTravelMapContractError(f"feature batch {state} item 셰입이 올바르지 않습니다.")
    if state == "retired":
        return RetiredFeatureBatchItem(feature_id=feature_id, row_revision=row_revision)
    if state == "suppressed":
        return SuppressedFeatureBatchItem(feature_id=feature_id, row_revision=row_revision)
    return UnchangedFeatureBatchItem(feature_id=feature_id, row_revision=row_revision)


def _current_task_cancelling() -> bool:
    """지금 task 자체가 취소 요청을 받았는가(shield 안쪽 취소와 구분)."""
    current = asyncio.current_task()
    return current is not None and current.cancelling() > 0


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
        max_concurrent_requests: int = 16,
        surface_concurrency: Mapping[BulkheadScope, int] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """``max_concurrent_requests``는 표면별 기본 상한, ``surface_concurrency``는 표면별 덮어쓰기다."""
        self._http = http
        self._service_token = service_token.strip()
        self._public_api_key = public_api_key.strip()
        self._max_attempts = max(1, max_attempts)
        if not 1 <= batch_chunk_size <= 200:
            raise ValueError("batch_chunk_size는 producer cap 범위(1..200)여야 합니다.")
        self._batch_chunk_size = batch_chunk_size
        self._backoff_base_seconds = backoff_base_seconds
        if max_concurrent_requests < 1:
            raise ValueError("max_concurrent_requests는 양수여야 합니다.")
        # 논리 호출(재시도·backoff 포함)마다 자기 표면의 worker 내 한 자리를 쓴다. 대기열은 만들지 않는다.
        # 표면을 하나로 묶으면 느린 viewport·weather가 상세·trip view의 자리까지 가져간다(#621).
        # 축제는 공유 조회 task 수를 `_festivals_slots`(4)가 바깥에서 묶고 task마다 `_send`가 한 번이라,
        # 안쪽 자리를 같은 값으로 두면 안쪽은 결코 거부하지 않는다(덮어쓰기 대상도 아니다).
        limits: dict[BulkheadScope, int] = {
            "features": max_concurrent_requests,
            "viewport": max_concurrent_requests,
            "transport": max_concurrent_requests,
            "festivals": FESTIVALS_MAX_CONCURRENT_REQUESTS,
            "weather": max_concurrent_requests,
        }
        for scope, limit in (surface_concurrency or {}).items():
            if scope not in limits or scope == "festivals":
                raise ValueError(f"덮어쓸 수 없는 bulkhead 범위: {scope}")
            if limit < 1:
                raise ValueError("surface_concurrency는 양수여야 합니다.")
            limits[scope] = limit
        self._bulkhead_limits = limits
        self._bulkheads: dict[BulkheadScope, asyncio.Semaphore] = {
            scope: asyncio.Semaphore(limit) for scope, limit in limits.items()
        }
        self._circuits: dict[CircuitScope, TransportCircuit] = {
            "features": TransportCircuit(clock=clock),
            "viewport": TransportCircuit(clock=clock),
            "transport": TransportCircuit(clock=clock),
            "festivals": TransportCircuit(clock=clock),
        }
        self._clock = clock
        self._festivals_monthly_cache: dict[
            tuple[tuple[str, Any], ...], tuple[float, dict[str, Any]]
        ] = {}
        self._festivals_monthly_inflight: dict[
            tuple[tuple[str, Any], ...], asyncio.Task[dict[str, Any]]
        ] = {}
        self._festivals_slots = asyncio.Semaphore(FESTIVALS_MAX_CONCURRENT_REQUESTS)

    async def aclose(self) -> None:
        # 분리된 축제 조회 task가 닫힌 http client를 쓰지 않게 먼저 끝낸다.
        tasks = list(self._festivals_monthly_inflight.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._http.aclose()

    @property
    def has_service_token(self) -> bool:
        """service 표면(transport 등)을 부를 자격이 있는지 — 값은 노출하지 않는다."""
        return bool(self._service_token)

    # ── 내부 ────────────────────────────────────────────────────────────────

    def _headers(self, *, allow_public_api_key: bool) -> dict[str, str]:
        if self._service_token:
            return {_SERVICE_TOKEN_HEADER: self._service_token}
        if allow_public_api_key and self._public_api_key:
            return {_PUBLIC_API_KEY_HEADER: self._public_api_key}
        return {}

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        allow_public_api_key: bool = False,
        retry: bool = True,
        request_timeout: httpx.Timeout | None = None,
        log_failure: bool = True,
        circuit: CircuitScope | None = "features",
        bulkhead: BulkheadScope | None = None,
    ) -> httpx.Response:
        """``circuit``은 이 호출이 세고 보는 회로 범위다. ``None``이면 호출자가 자기 회로를 소유한다.

        ``bulkhead``는 이 호출이 쓰는 동시 호출 자리 범위다. 생략하면 회로 범위와 같다(회로가 없으면
        ``features``). 자체 회로를 가진 호출자(weather)는 자기 범위를 명시한다.
        """
        scope: BulkheadScope = (
            bulkhead if bulkhead is not None else (circuit if circuit is not None else "features")
        )
        slots = self._bulkheads[scope]
        if slots.locked():
            BULKHEAD_REJECTIONS.labels(provider="kor_travel_map", scope=scope).inc()
            raise KorTravelMapUnavailable(
                "kor-travel-map 동시 호출 상한 — 호출하지 않음", code="BULKHEAD_FULL"
            )
        # locked 검사와 acquire 사이에는 suspension이 없어 다른 task가 자리를 가로채지 않는다.
        async with slots:
            breaker = self._circuits[circuit] if circuit is not None else None
            token = breaker.acquire() if breaker is not None else (False, 0)
            if token is None:
                raise KorTravelMapUnavailable(
                    "kor-travel-map 회로 열림 — 호출하지 않음", code="CIRCUIT_OPEN"
                )
            try:
                response = await self._send_with_retries(
                    method,
                    path,
                    params=params,
                    json=json,
                    allow_public_api_key=allow_public_api_key,
                    retry=retry,
                    request_timeout=request_timeout,
                    log_failure=log_failure,
                )
            except KorTravelMapUnavailable as exc:
                if breaker is not None:
                    if exc.code == "POOL_TIMEOUT":
                        breaker.release(token)
                    elif breaker.failure(token):
                        logger.warning(
                            "kor_travel_map.circuit_open scope=%s path=%s error=%s trial=%s",
                            circuit,
                            path,
                            exc.error_class,
                            token[0],
                        )
                raise
            except BaseException:
                if breaker is not None:
                    breaker.release(token)
                raise
            if breaker is not None:
                breaker.success(token)
            return response

    async def _send_with_retries(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        allow_public_api_key: bool = False,
        retry: bool = True,
        request_timeout: httpx.Timeout | None = None,
        log_failure: bool = True,
    ) -> httpx.Response:
        """연결 실패·5xx는 지수 백오프로 재시도하고, ``ReadTimeout``·``ReadError``는 다시 보내지 않는다(#702).

        ``retry=False``면 한 번만 보내고 5xx 응답도 그대로 돌려준다 — 호출자가 problem ``code``를 읽어
        판단한다(transport 상태 표면: 503 ``NOT_LOADED``는 결정적이고, 지도 요청은 다음 이동이 곧
        재시도다 — ADR-076 D2). 단 멱등 GET이 재사용 연결의 끊김(``RemoteProtocolError`` 등)으로 실패하면
        어느 쪽이든 새 연결로 **한 번** 더 보낸다(시도 횟수에 넣지 않는다) — Map 장애가 아니라 pooled 연결의
        수명 문제다.

        ``request_timeout``을 주면 그 호출만 client 기본 timeout 대신 쓴다(weather 상태 표면의 짧은 connect —
        ADR-077). ``log_failure=False``면 실패 경고를 호출자가 남긴다(같은 실패의 이중 로그 방지).
        """
        attempts = self._max_attempts if retry else 1
        stale_retry = method.upper() in _IDEMPOTENT_METHODS
        sent = 0
        attempt = 0
        last: KorTravelMapUnavailable | None = None
        while attempt < attempts:
            sent += 1
            try:
                resp = await self._http.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    headers=self._headers(allow_public_api_key=allow_public_api_key),
                    timeout=(
                        request_timeout if request_timeout is not None else httpx.USE_CLIENT_DEFAULT
                    ),
                )
            except httpx.PoolTimeout as exc:
                # 로컬 연결 풀 대기는 원격 장애의 증거가 아니며 재시도하지 않는다.
                raise KorTravelMapUnavailable(
                    f"kor-travel-map 연결 풀 대기 초과({path})",
                    code="POOL_TIMEOUT",
                    error_class="PoolTimeout",
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KorTravelMapUnavailable(
                    f"kor-travel-map 요청 실패({path}): {type(exc).__name__}",
                    error_class=type(exc).__name__,
                )
                if stale_retry and isinstance(exc, httpx.RemoteProtocolError):
                    # 재사용 연결이 응답 없이 끊겼다(keep-alive 경합). 한 번만, backoff 없이, 시도 횟수를
                    # 쓰지 않고 새 연결로 다시 보낸다.
                    stale_retry = False
                    continue
                if not isinstance(exc, _RETRYABLE_TRANSPORT_ERRORS):
                    break
            else:
                if resp.status_code >= 500 and retry:
                    last = KorTravelMapUnavailable(
                        f"kor-travel-map {resp.status_code} ({path})",
                        error_class=f"HTTP{resp.status_code}",
                    )
                else:
                    return resp
            attempt += 1
            if attempt < attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2 ** (attempt - 1)))
        failure = last or KorTravelMapUnavailable(f"kor-travel-map 요청 실패({path})")
        if log_failure:
            # 예외 클래스·전송 횟수만 남긴다 — query·header·본문은 키·좌표를 담을 수 있다.
            logger.warning(
                "kor_travel_map.unavailable method=%s path=%s error=%s sent=%d",
                method,
                path,
                failure.error_class,
                sent,
            )
        raise failure

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
        return self._decode_envelope(resp)

    @staticmethod
    def _decode_envelope(resp: httpx.Response) -> tuple[dict[str, Any], dict[str, Any]]:
        """성공(2xx) 응답 본문을 엄격하게 해석해 ``(data, meta)``를 돌려준다."""
        try:
            payload = json.loads(
                resp.content,
                object_pairs_hook=_object_without_duplicates,
                parse_constant=_reject_non_finite_constant,
                parse_float=_finite_json_float,
            )
        except KorTravelMapContractError:
            raise
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise KorTravelMapContractError(
                f"kor-travel-map JSON 응답을 해석할 수 없습니다({resp.request.url.path})"
            ) from exc
        data = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(data, dict):
            raise KorTravelMapContractError(f"예상치 못한 응답 셰입({resp.request.url.path})")
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
        include_geometry: bool = False,
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
        if include_geometry:
            params["include_geometry"] = True
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
        data, meta = self._payload(
            await self._send(
                "GET",
                "/v1/features/in-bounds",
                params=params,
                allow_public_api_key=True,
                circuit="viewport",
            )
        )
        cluster = meta.get("cluster")
        if isinstance(cluster, Mapping) and "cluster_unit" in cluster:
            data["cluster_unit"] = cluster.get("cluster_unit")
        return data

    async def get_feature(self, feature_id: str) -> dict[str, Any] | None:
        """단건 상세. 404 → None."""
        segment = _path_segment(feature_id)
        if segment is None:
            return None
        # 계약 경로 표(test_kor_travel_map_contract)가 f-string 자리 이름으로 경로를 대조한다.
        feature_id = segment
        resp = await self._send("GET", f"/v1/features/{feature_id}", allow_public_api_key=True)
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            return None
        return self._data(resp)

    async def get_features(
        self,
        feature_ids: Sequence[str],
        *,
        known_row_revisions: Mapping[str, int] | None = None,
    ) -> dict[str, FeatureBatchItem]:
        """5-state ``trip_card`` batch를 cap 단위로 조회하고 exhaustively 검증한다."""
        unique = list(dict.fromkeys(feature_ids))
        revisions = dict(known_row_revisions or {})
        if not set(revisions) <= set(unique) or any(
            isinstance(revision, bool)
            or not isinstance(revision, int)
            or not 1 <= revision <= _POSTGRES_BIGINT_MAX
            for revision in revisions.values()
        ):
            raise ValueError(
                "known_row_revisions는 요청 ID의 PostgreSQL bigint 범위 양의 정수여야 합니다."
            )
        decoded: dict[str, FeatureBatchItem] = {}
        for start in range(0, len(unique), self._batch_chunk_size):
            chunk = unique[start : start + self._batch_chunk_size]
            request_items = [
                {
                    "feature_id": feature_id,
                    **(
                        {"known_row_revision": revisions[feature_id]}
                        if feature_id in revisions
                        else {}
                    ),
                }
                for feature_id in chunk
            ]
            response = await self._send(
                "POST",
                "/v1/features/batch",
                json={"items": request_items, "projection": "trip_card"},
            )
            if response.status_code == status.HTTP_404_NOT_FOUND:
                raise KorTravelMapContractError("feature batch endpoint가 404를 반환했습니다.")
            data = self._data(response)
            raw_items = data.get("items")
            if not isinstance(raw_items, list):
                raise KorTravelMapContractError("feature batch data 셰입이 올바르지 않습니다.")
            _note_additive_fields(data, _BATCH_DATA_FIELDS, what="batch_data")
            chunk_items = [_decode_feature_batch_item(item) for item in raw_items]
            if [item.feature_id for item in chunk_items] != chunk:
                raise KorTravelMapContractError(
                    "feature batch 응답이 요청 ID와 순서를 정확히 보존하지 않습니다."
                )
            for item in chunk_items:
                known_revision = revisions.get(item.feature_id)
                if isinstance(item, UnchangedFeatureBatchItem):
                    if known_revision != item.row_revision:
                        raise KorTravelMapContractError(
                            "feature batch unchanged revision이 요청 validator와 다릅니다."
                        )
                elif (
                    isinstance(item, FoundFeatureBatchItem) and known_revision == item.row_revision
                ):
                    raise KorTravelMapContractError(
                        "feature batch found item이 일치하는 validator를 무시했습니다."
                    )
                decoded[item.feature_id] = item
        return decoded

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
        data, meta = self._payload(
            await self._send(
                "GET",
                "/v1/features/nearby",
                params=params,
                allow_public_api_key=True,
                circuit="viewport",
            )
        )
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
        data, meta = self._payload(
            await self._send("GET", "/v1/features/search", params=params, allow_public_api_key=True)
        )
        return self._thread_page(data, meta)

    async def categories(self, *, include_counts: bool = False) -> dict[str, Any]:
        """카테고리 카탈로그(정적 145건). data = {items, include_counts}.

        **`active_only`는 보내지 않는다.** Map `/v1/categories`가 선언하는 query는
        `include_counts` 하나뿐이다(스냅샷 기준, `routers/categories.py`: "과거의
        ``active_only`` 스위치는 비공개 분포를 공개 표면에 노출했기에 제거됐다 — T-VN-04, F-1").
        FastAPI는 선언하지 않은 query를 422가 아니라 **조용히 버리므로** 계속 보내면 필터가
        걸린 척하는 200이 돌아온다. 제거 전 실제 upstream 동작도 확인했다: 옛 `active_only`는
        item 목록이 아니라 `db_feature_count`/`db_active` **집계 기준**만 바꿨고
        (`_STATIC_CATEGORIES`는 항상 전량), 그 집계는 이제 항상 ADR-067 공개 projection이다.

        catalog 항목별 `is_active`는 응답에 그대로 온다(required bool) — "활성만" 필터가
        필요하면 **소비 계층**이 그 필드로 거른다(`api/v1/features.py`·
        `api/v1/admin/category_mappings.py`). transport는 필터를 흉내내지 않는다(ADR-005).
        """
        return self._data(
            await self._send(
                "GET",
                "/v1/categories",
                params={"include_counts": include_counts},
                allow_public_api_key=True,
            )
        )

    async def public_beaches(
        self,
        *,
        sido_code: str | None = None,
        sigungu_code: str | None = None,
        q: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """공개 해수욕장 목록. data = {items} + threaded next_cursor/total."""
        params: dict[str, Any] = {}
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
        data, meta = self._payload(
            await self._send("GET", "/v1/public/beaches", params=params, allow_public_api_key=True)
        )
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
        return self._data(
            await self._send(
                "GET",
                "/v1/public/beaches/map-markers",
                params=params,
                allow_public_api_key=True,
                circuit="viewport",
            )
        )

    async def get_public_beach(self, feature_id: str) -> dict[str, Any] | None:
        """공개 해수욕장 상세. 404 → None."""
        segment = _path_segment(feature_id)
        if segment is None:
            return None
        # 계약 경로 표(test_kor_travel_map_contract)가 f-string 자리 이름으로 경로를 대조한다.
        feature_id = segment
        resp = await self._send(
            "GET", f"/v1/public/beaches/{feature_id}", allow_public_api_key=True
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
        cache_key = tuple(sorted(params.items()))
        cached = self._festivals_monthly_cache.get(cache_key)
        if cached is not None and self._clock() - cached[0] < FESTIVALS_MONTHLY_CACHE_TTL_SECONDS:
            return copy.deepcopy(cached[1])
        # 같은 첫 조회 월에 동시에 몰린 요청은 Map에 한 번만 보낸다(single-flight). 조회는 분리된 task라
        # 한 호출자가 취소돼도(연결 끊김·종료) 다른 호출자와 캐시 채우기는 계속된다.
        task = self._festivals_monthly_inflight.get(cache_key)
        if task is None:
            # 서로 다른 첫 조회 월이 몰려도 공유 조회 task 수를 축제 자리 수로 묶는다(task는 요청과 분리돼
            # 살아남으므로 바깥에서 센다). locked 검사와 acquire 사이에는 suspension이 없다(semaphore fast path).
            if self._festivals_slots.locked():
                BULKHEAD_REJECTIONS.labels(provider="kor_travel_map", scope="festivals").inc()
                raise KorTravelMapUnavailable(
                    "kor-travel-map 축제 동시 호출 상한 — 호출하지 않음", code="BULKHEAD_FULL"
                )
            await self._festivals_slots.acquire()
            try:
                task = asyncio.create_task(
                    self._fetch_and_cache_festivals_monthly(cache_key, params)
                )
            except BaseException:
                self._festivals_slots.release()
                raise
            self._festivals_monthly_inflight[cache_key] = task
            # 정리는 done-callback에서 — 시작 전에 취소된 task는 coroutine의 finally가 돌지 않는다.
            task.add_done_callback(lambda done: self._finish_festivals_monthly(cache_key, done))
        try:
            page = await asyncio.shield(task)
        except asyncio.CancelledError:
            # 이 호출자가 취소된 것이 아니라 공유 조회가 취소됐다(client 종료) — 503으로 바꾼다.
            if task.cancelled() and not _current_task_cancelling():
                raise KorTravelMapUnavailable(
                    "kor-travel-map 축제 조회 취소됨(종료 중)", code="SHUTTING_DOWN"
                ) from None
            raise
        except KorTravelMapUnavailable as exc:
            # 기다린 호출자마다 새 예외 — 같은 예외 객체에 traceback이 쌓이지 않게.
            raise KorTravelMapUnavailable(
                str(exc),
                code=exc.code,
                details=exc.details,
                retry_after_seconds=exc.retry_after_seconds,
                status_code=exc.status_code,
                error_class=exc.error_class,
            ) from exc
        return copy.deepcopy(page)

    async def _fetch_and_cache_festivals_monthly(
        self, cache_key: tuple[tuple[str, Any], ...], params: dict[str, Any]
    ) -> dict[str, Any]:
        """single-flight 조회 본체 — 성공만 캐시한다. 반환값은 캐시 사본이다(호출자는 다시 복사한다)."""
        page = await self._fetch_public_festivals_monthly(params)
        cache = self._festivals_monthly_cache
        cache.pop(cache_key, None)
        cache[cache_key] = (self._clock(), copy.deepcopy(page))
        while len(cache) > _FESTIVALS_MONTHLY_CACHE_MAX:
            cache.pop(next(iter(cache)))
        return cache[cache_key][1]

    def _finish_festivals_monthly(
        self, cache_key: tuple[tuple[str, Any], ...], task: asyncio.Task[dict[str, Any]]
    ) -> None:
        """조회 task가 어떻게 끝나든(시작 전 취소 포함) 자리를 한 번 놓고 in-flight에서 뺀다."""
        self._festivals_slots.release()
        if self._festivals_monthly_inflight.get(cache_key) is task:
            del self._festivals_monthly_inflight[cache_key]
        if not task.cancelled():
            task.exception()

    async def _fetch_public_festivals_monthly(self, params: dict[str, Any]) -> dict[str, Any]:
        default = self._http.timeout
        data, meta = self._payload(
            await self._send(
                "GET",
                "/v1/public/festivals/monthly",
                params=params,
                allow_public_api_key=True,
                circuit="festivals",
                request_timeout=httpx.Timeout(
                    connect=default.connect,
                    read=FESTIVALS_MONTHLY_READ_TIMEOUT_SECONDS,
                    write=default.write,
                    pool=default.pool,
                ),
            )
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
            await self._send(
                "GET",
                "/v1/public/festivals/map-markers",
                params=params,
                allow_public_api_key=True,
                circuit="viewport",
            )
        )

    async def get_public_festival(self, feature_id: str) -> dict[str, Any] | None:
        """공개 축제 상세. 404 → None."""
        segment = _path_segment(feature_id)
        if segment is None:
            return None
        # 계약 경로 표(test_kor_travel_map_contract)가 f-string 자리 이름으로 경로를 대조한다.
        feature_id = segment
        resp = await self._send(
            "GET", f"/v1/public/festivals/{feature_id}", allow_public_api_key=True
        )
        if resp.status_code == status.HTTP_404_NOT_FOUND:
            return None
        return self._data(resp)

    async def healthz(self) -> dict[str, Any]:
        """liveness. envelope 없이 raw 객체일 수 있어 그대로 반환."""
        resp = await self._send("GET", "/health")
        body = resp.json()
        return body if isinstance(body, dict) else {"status": "unknown"}


def _reject_non_finite_constant(value: str) -> Any:
    raise KorTravelMapContractError(f"kor-travel-map JSON 응답에 비유한 수가 있습니다: {value}")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise KorTravelMapContractError(
            f"kor-travel-map JSON 응답에 범위를 벗어난 실수가 있습니다: {value}"
        )
    return parsed


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """JSON object의 중복 member를 마지막 값으로 조용히 덮어쓰지 않는다."""
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise KorTravelMapContractError(
                f"kor-travel-map JSON 응답에 중복 key가 있습니다: {key}"
            )
        value[key] = item
    return value


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
    http = ApiCallLoggingClient(
        base_url=app_settings.pinvi_kor_travel_map_api_base_url,
        timeout=app_settings.pinvi_kor_travel_map_timeout_seconds,
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=KEEPALIVE_EXPIRY_SECONDS,
        ),
        event_hooks=api_call_event_hooks(
            db_session.async_session_factory, provider="kor_travel_map"
        ),
    )
    return KorTravelMapClient(
        http,
        service_token=app_settings.pinvi_kor_travel_map_service_token,
        public_api_key=(
            app_settings.pinvi_kor_travel_map_public_api_key or app_settings.pinvi_vworld_api_key
        ),
        max_attempts=app_settings.pinvi_kor_travel_map_max_attempts,
        batch_chunk_size=app_settings.pinvi_kor_travel_map_batch_chunk_size,
        surface_concurrency={
            "features": app_settings.pinvi_kor_travel_map_features_max_concurrency,
            "viewport": app_settings.pinvi_kor_travel_map_viewport_max_concurrency,
            "transport": app_settings.pinvi_kor_travel_map_transport_max_concurrency,
            "weather": app_settings.pinvi_kor_travel_map_weather_max_concurrency,
        },
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
    async with outbound_resilience_lifespan():
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
