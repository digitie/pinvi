"""kor-travel-map weather 상태 표면 client — `/v1/service/weather/*` (Map ADR-114 W7, PinVi ADR-077).

`KorTravelMapTransportClient`와 같은 관례다 — 감싼 `KorTravelMapClient`의 httpx client·service token·API 호출
로깅·엄격한 JSON 해석(`_send`·`_decode_envelope`)을 공유하고 새 연결을 만들지 않는다. 오류 의미:

- 재시도 0회. 503 ``WEATHER_STATE_NOT_LOADED``는 결정적이고 Valkey 장애는 수백 ms 안에 풀리지 않는다. weather는
  화면의 보조 정보라 호출자가 부분별로 강등한다.
- 5xx·timeout·연결 실패는 problem ``code``를 실은 ``KorTravelMapWeatherUnavailable``, 401/403은
  ``code="UPSTREAM_AUTH"``, weather 라우터가 없는 옛 Map의 라우트 404는 ``code="UPSTREAM_REJECTED"``.
- 404 ``NOT_FOUND``(위치 없음 — `/nearest`는 반경 안에 위치가 없을 때)는 ``KorTravelMapFeatureNotFound``,
  409는 cursor 세대 만료(``KorTravelMapWeatherCursorExpired``), 그 밖 4xx는 ``KorTravelMapBadRequest``.
- service 표면이라 public API key로 fallback하지 않는다. token이 없으면 Map을 부르지 않는다(경고는 프로세스당 한 번).
- 호출마다 짧은 timeout(read·connect, 설정)을 쓰고, **회로차단**을 둔다 — timeout·연결 실패·5xx(``NOT_LOADED`` 제외 —
  Map은 살아 있고 결정적이다)가 연속 ``_CIRCUIT_FAILURE_THRESHOLD``번이면 ``_CIRCUIT_OPEN_SECONDS`` 동안 부르지 않고 즉시
  ``KorTravelMapWeatherUnavailable(code="CIRCUIT_OPEN")``이다. 그 뒤 시험 호출 하나만 보낸다(half-open). 회로는 감싼
  ``KorTravelMapClient`` 인스턴스(lifespan당 하나 = worker 프로세스당 하나)마다 하나이고, 이 래퍼는 요청마다 만들어도
  같은 회로를 본다. 직접 경로 `kor_travel_weather._CircuitBreaker`와 같은 상태 기계다.

응답은 envelope의 ``data`` dict다(transport-only). 해석·투영은 `services/weather_map_state.py`.

**경로는 이 모듈의 문자열 리터럴로만 둔다** — 계약 게이트(`test_kor_travel_map_weather_contract.py`)가 이 소스의
v1 경로 리터럴을 읽어 vendored OpenAPI와 대조한다(`/status`는 운영 진단용이라 PinVi가 부르지 않는다).
"""

from __future__ import annotations

import logging
import time
import weakref
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Final, Literal

import httpx
from fastapi import status

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapClient,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    KorTravelMapUnavailable,
    _error_code,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

WeatherSection = Literal["current", "forecasts", "daily_summaries"]
WeatherForecastStyle = Literal["ultra_short", "short", "mid", "external"]

#: Map `POST /locations/batch`의 `feature_ids`·`location_ids` 합 상한(`MAX_BATCH`).
MAX_BATCH_IDS: Final = 50
#: Map `/nearest`·`/locations` 근처 검색 `radius_m` 상한(100 km).
MAX_RADIUS_M: Final = 100_000.0
#: Map `/locations` `limit` 상한.
MAX_LIST_LIMIT: Final = 500

_LOCATIONS_PATH: Final = "/v1/service/weather/locations"
_LOCATION_PATH: Final = "/v1/service/weather/locations/{feature_id}"
_BATCH_PATH: Final = "/v1/service/weather/locations/batch"
_NEAREST_PATH: Final = "/v1/service/weather/nearest"

#: Map weather location_id 계약(`WeatherBatchRequest.location_ids` 항목: 1~120자, `|`·제어 문자 없음).
LOCATION_ID_MAX_LENGTH: Final = 120

_CIRCUIT_FAILURE_THRESHOLD: Final = 3
_CIRCUIT_OPEN_SECONDS: Final = 30.0
#: 503이어도 Map은 살아 있다 — 회로 실패로 세지 않는다(적재 전은 결정적이다).
_ALIVE_UNAVAILABLE_CODES: Final[frozenset[str]] = frozenset({"WEATHER_STATE_NOT_LOADED"})


def valid_location_id(value: str) -> bool:
    """Map이 배치에서 받는 weather location_id인지(아니면 청크 전체가 422다)."""
    return (
        0 < len(value) <= LOCATION_ID_MAX_LENGTH
        and "|" not in value
        and not any(ord(ch) < 0x20 for ch in value)
    )


class KorTravelMapWeatherUnavailable(KorTravelMapError):
    """weather 상태 표면을 지금 읽을 수 없음.

    ``code``는 Map problem ``code``(``WEATHER_STATE_NOT_LOADED``·``WEATHER_STATE_UNAVAILABLE`` 등), 401/403이면
    ``UPSTREAM_AUTH``, timeout·연결 실패면 ``None``이다.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class KorTravelMapWeatherCursorExpired(KorTravelMapError):
    """409 ``WEATHER_STATE_GENERATION_EXPIRED`` — cursor의 세대가 사라졌다. 처음부터 다시."""


class _CircuitBreaker:
    """연속 실패 회로차단 — closed → open(``open_seconds``) → half-open(시험 1회).

    **세대(generation)**: 상태가 바뀔 때마다(열림·닫힘) 세대가 오른다. ``acquire``가 호출 시작 시점의 세대를 주고,
    결과는 그 세대가 지금과 같을 때만 센다 — 회로가 열리기 전에 출발한 호출의 늦은 실패가 열린 시간을 늘리지 않고,
    늦은 성공이 half-open 시험보다 먼저 회로를 닫지 않는다. 시험 호출 자신의 결과는 언제나 센다.
    """

    def __init__(
        self, *, failure_threshold: int, open_seconds: float, clock: Callable[[], float]
    ) -> None:
        self._failure_threshold = max(1, failure_threshold)
        self._open_seconds = open_seconds
        self._clock = clock
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._trial_in_flight = False
        self._generation = 0

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None

    def acquire(self) -> tuple[bool, int]:
        """호출 허가. 열려 있으면 ``KorTravelMapWeatherUnavailable``.

        반환값은 ``(half-open 시험 호출 여부, 호출 시작 세대)``.
        """
        if self._opened_at is None:
            return False, self._generation
        if self._clock() - self._opened_at < self._open_seconds or self._trial_in_flight:
            raise KorTravelMapWeatherUnavailable(
                "kor-travel-map weather 회로 열림 — 호출하지 않음", code="CIRCUIT_OPEN"
            )
        self._trial_in_flight = True
        return True, self._generation

    def _stale(self, *, trial: bool, generation: int) -> bool:
        return not trial and generation != self._generation

    def record_success(self, *, trial: bool, generation: int) -> None:
        if self._stale(trial=trial, generation=generation):
            return
        if self._opened_at is not None:
            logger.info("kor_travel_map.weather_circuit_closed")
            self._generation += 1
        self._consecutive_failures = 0
        self._opened_at = None
        self._trial_in_flight = False

    def record_failure(self, *, trial: bool, generation: int) -> None:
        if self._stale(trial=trial, generation=generation):
            return
        self._consecutive_failures += 1
        if trial or self._consecutive_failures >= self._failure_threshold:
            if self._opened_at is None:
                logger.warning(
                    "kor_travel_map.weather_circuit_open",
                    extra={"consecutive_failures": self._consecutive_failures},
                )
            self._opened_at = self._clock()
            self._generation += 1
        if trial:
            self._trial_in_flight = False

    def release(self, *, trial: bool) -> None:
        if trial:
            self._trial_in_flight = False


_CIRCUITS: weakref.WeakKeyDictionary[KorTravelMapClient, _CircuitBreaker] = (
    weakref.WeakKeyDictionary()
)
_no_token_logged = False


def _circuit_for(map_client: KorTravelMapClient, clock: Callable[[], float]) -> _CircuitBreaker:
    circuit = _CIRCUITS.get(map_client)
    if circuit is None:
        circuit = _CircuitBreaker(
            failure_threshold=_CIRCUIT_FAILURE_THRESHOLD,
            open_seconds=_CIRCUIT_OPEN_SECONDS,
            clock=clock,
        )
        _CIRCUITS[map_client] = circuit
    return circuit


def _aware(value: datetime, *, field_name: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name}는 aware datetime이어야 합니다.")
    return value.isoformat()


def _bundle_params(
    *,
    sections: Sequence[WeatherSection] | None,
    forecast_styles: Sequence[WeatherForecastStyle] | None,
    from_: datetime | None,
    to: datetime | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if sections is not None:
        params["sections"] = list(sections)
    if forecast_styles is not None:
        params["forecast_styles"] = list(forecast_styles)
    if from_ is not None:
        params["from"] = _aware(from_, field_name="from_")
    if to is not None:
        params["to"] = _aware(to, field_name="to")
    return params


class KorTravelMapWeatherClient:
    """Map `/v1/service/weather/*` 읽기. 감싼 `KorTravelMapClient`의 연결을 공유한다."""

    def __init__(
        self,
        map_client: KorTravelMapClient,
        *,
        timeout_seconds: float = 3.0,
        connect_timeout_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._map = map_client
        self._timeout = httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds)
        self._circuit = _circuit_for(map_client, clock)

    def _data(self, resp: httpx.Response) -> tuple[dict[str, Any], dict[str, Any]]:
        sc = resp.status_code
        path = resp.request.url.path
        if sc >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise KorTravelMapWeatherUnavailable(
                f"kor-travel-map weather {sc} ({path})", code=_error_code(resp)
            )
        if sc in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            # 운영 Map은 service token을 강제한다 — 토큰 미주입(Manager compose)이 가장 흔한 원인.
            logger.warning("kor_travel_map.weather_auth_rejected", extra={"status": sc})
            raise KorTravelMapWeatherUnavailable(
                f"kor-travel-map weather {sc} ({path})", code="UPSTREAM_AUTH"
            )
        if sc == status.HTTP_404_NOT_FOUND:
            code = _error_code(resp)
            if code == "NOT_FOUND":
                raise KorTravelMapFeatureNotFound("weather 위치를 찾을 수 없습니다.", code=code)
            # weather 라우터가 없는 옛 Map의 라우트 404는 "위치 없음"이 아니라 표면 부재다.
            raise KorTravelMapWeatherUnavailable(
                f"kor-travel-map weather 404 ({path})", code="UPSTREAM_REJECTED"
            )
        if sc == status.HTTP_409_CONFLICT:
            raise KorTravelMapWeatherCursorExpired(f"kor-travel-map weather 409 ({path})")
        if sc >= status.HTTP_400_BAD_REQUEST:
            raise KorTravelMapBadRequest(f"kor-travel-map weather {sc}", code=_error_code(resp))
        return self._map._decode_envelope(resp)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        global _no_token_logged
        if not self._map.has_service_token:
            # 운영 Map은 service token 없이는 401이다 — 요청마다 거절당하러 가지 않는다.
            if not _no_token_logged:
                _no_token_logged = True
                logger.warning(
                    "kor_travel_map.weather_no_service_token — Map weather를 부르지 않음"
                )
            raise KorTravelMapWeatherUnavailable(
                "kor-travel-map service token 미설정", code="UPSTREAM_AUTH"
            )
        trial, generation = self._circuit.acquire()
        try:
            resp = await self._map._send(
                method,
                path,
                params=params,
                json=json,
                retry=False,
                request_timeout=self._timeout,
                log_failure=False,
            )
        except KorTravelMapUnavailable as exc:
            self._circuit.record_failure(trial=trial, generation=generation)
            raise KorTravelMapWeatherUnavailable(str(exc)) from exc
        except httpx.HTTPError as exc:
            # DecodingError·TooManyRedirects 등은 TransportError가 아니라 `_send`가 잡지 않는다.
            self._circuit.record_failure(trial=trial, generation=generation)
            raise KorTravelMapWeatherUnavailable(
                f"kor-travel-map 응답 오류({path}): {exc!r}"
            ) from exc
        except BaseException:
            self._circuit.release(trial=trial)
            raise
        if resp.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR and (
            _error_code(resp) not in _ALIVE_UNAVAILABLE_CODES
        ):
            self._circuit.record_failure(trial=trial, generation=generation)
        else:
            self._circuit.record_success(trial=trial, generation=generation)
        return self._data(resp)

    async def list_locations(
        self,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        near: tuple[float, float, float] | None = None,
        include_current: bool = False,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """위치 목록·근처·영역. data = ``{items, truncated, freshness, current_freshness}`` + ``next_cursor``.

        ``bbox = (min_lon, min_lat, max_lon, max_lat)``, ``near = (lon, lat, radius_m)``. Map은 둘을 함께 받지
        않고 cursor는 조건 없는 순회에만 받는다(422) — 그 조합을 여기서 먼저 막는다.
        """
        if bbox is not None and near is not None:
            raise ValueError("bbox와 near는 함께 쓸 수 없습니다.")
        if cursor is not None and (bbox is not None or near is not None):
            raise ValueError("cursor는 조건 없는 목록 순회에만 씁니다.")
        if limit is not None and not 1 <= limit <= MAX_LIST_LIMIT:
            raise ValueError(f"limit은 1..{MAX_LIST_LIMIT} 범위여야 합니다: {limit}")
        params: dict[str, Any] = {}
        if bbox is not None:
            params.update(
                {"min_lon": bbox[0], "min_lat": bbox[1], "max_lon": bbox[2], "max_lat": bbox[3]}
            )
        if near is not None:
            if not 0 < near[2] <= MAX_RADIUS_M:
                raise ValueError(f"radius_m은 0 초과 {MAX_RADIUS_M} 이하여야 합니다: {near[2]}")
            params.update({"lon": near[0], "lat": near[1], "radius_m": near[2]})
        if include_current:
            params["include_current"] = "true"
        if limit is not None:
            params["limit"] = limit
        if cursor is not None:
            params["cursor"] = cursor
        data, meta = await self._request("GET", _LOCATIONS_PATH, params=params)
        return self._map._thread_page(data, meta)

    async def location(
        self,
        feature_id: str,
        *,
        sections: Sequence[WeatherSection] | None = None,
        forecast_styles: Sequence[WeatherForecastStyle] | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
    ) -> dict[str, Any]:
        """위치 하나의 묶음. data = ``{location, location_freshness, current, forecasts, daily_summaries}``."""
        data, _meta = await self._request(
            "GET",
            _LOCATION_PATH.format(feature_id=feature_id),
            params=_bundle_params(
                sections=sections, forecast_styles=forecast_styles, from_=from_, to=to
            ),
        )
        return data

    async def nearest(
        self,
        *,
        lon: float,
        lat: float,
        radius_m: float | None = None,
        sections: Sequence[WeatherSection] | None = None,
        forecast_styles: Sequence[WeatherForecastStyle] | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
    ) -> dict[str, Any]:
        """좌표 근처 위치들에서 **부분마다** 데이터가 있는 가장 가까운 위치의 묶음.

        반경 안에 위치가 없으면 ``KorTravelMapFeatureNotFound``(404 ``NOT_FOUND``)다.
        """
        params = _bundle_params(
            sections=sections, forecast_styles=forecast_styles, from_=from_, to=to
        )
        params.update({"lon": lon, "lat": lat})
        if radius_m is not None:
            if not 0 < radius_m <= MAX_RADIUS_M:
                raise ValueError(f"radius_m은 0 초과 {MAX_RADIUS_M} 이하여야 합니다: {radius_m}")
            params["radius_m"] = radius_m
        data, _meta = await self._request("GET", _NEAREST_PATH, params=params)
        return data

    async def batch(
        self,
        *,
        feature_ids: Sequence[str] = (),
        location_ids: Sequence[str] = (),
        sections: Sequence[WeatherSection] | None = None,
        forecast_styles: Sequence[WeatherForecastStyle] | None = None,
        forecast_from: datetime | None = None,
        forecast_to: datetime | None = None,
    ) -> dict[str, Any]:
        """여러 위치(합 ≤ 50)의 묶음. data = ``{items, missing}``. 청크는 호출자 몫이다."""
        total = len(feature_ids) + len(location_ids)
        if not 1 <= total <= MAX_BATCH_IDS:
            raise ValueError(
                f"feature_ids·location_ids 합은 1..{MAX_BATCH_IDS}개여야 합니다: {total}"
            )
        if len(set(feature_ids)) != len(feature_ids) or len(set(location_ids)) != len(location_ids):
            raise ValueError("같은 id가 두 번 있습니다(Map은 422로 거절한다).")
        body: dict[str, Any] = {}
        if feature_ids:
            body["feature_ids"] = list(feature_ids)
        if location_ids:
            body["location_ids"] = list(location_ids)
        if sections is not None:
            body["sections"] = list(sections)
        if forecast_styles is not None:
            body["forecast_styles"] = list(forecast_styles)
        if forecast_from is not None:
            body["forecast_from"] = _aware(forecast_from, field_name="forecast_from")
        if forecast_to is not None:
            body["forecast_to"] = _aware(forecast_to, field_name="forecast_to")
        data, _meta = await self._request("POST", _BATCH_PATH, json=body)
        return data


def create_map_weather_client(map_client: KorTravelMapClient) -> KorTravelMapWeatherClient:
    """설정의 weather 전용 timeout으로 래퍼를 만든다(라우터·trip view가 요청마다 부른다)."""
    return KorTravelMapWeatherClient(
        map_client,
        timeout_seconds=settings.pinvi_kor_travel_map_weather_timeout_seconds,
        connect_timeout_seconds=settings.pinvi_kor_travel_map_weather_connect_timeout_seconds,
    )
