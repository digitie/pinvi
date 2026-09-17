"""`kor-travel-weather` 공개 REST client (transport-only) — ADR-068.

`kor-travel-weather`의 `/v1/weather/*` 공개 read를 호출하는 httpx 기반 client다. **인증
헤더가 없다** — 해당 서비스의 공개 read는 API key/ServiceToken을 요구하지 않는다
(`docs/integrations/kor-travel-weather.md` §2.1).

- transport 역할만 한다(kor_travel_map.py와 동일 원칙). 응답은 envelope(`{data, meta}`)에서
  `data`만 풀어 반환한다. Pinvi schema(`FeatureWeatherCard` 등)로의 매핑은 라우터/서비스
  계층 책임이다(P3/P4/P5, T-362~364).
- 4개 엔드포인트만 구현한다 — 설계 문서 §2.1이 정한 Pinvi 소비 표면 전체다:
  `resolve`(좌표→location 1회 해석) / `markers`(다지점 현재값+특보) / `latest`(단일 지점
  현재값) / `forecast`(단일 지점 예보 구간). `nearby`/`get_location`/`list_locations`/
  admin 표면은 Pinvi가 쓰지 않으므로 만들지 않는다.
- 이 client는 **아직 어떤 라우터에도 배선되지 않는다**(T-360/P1). 기존
  `GET /features/{id}/weather` 등은 계속 `kor_travel_map.py`를 쓴다.

계약: `docs/integrations/kor-travel-weather.md`, 원본
`kor-travel-weather` `packages/kor-travel-weather-api/openapi.json`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.core.config import Settings, settings
from app.db import session as db_session
from app.middleware.api_call_logging import api_call_event_hooks

logger = logging.getLogger(__name__)

_LAT_MIN, _LAT_MAX = 33.0, 43.0
_LON_MIN, _LON_MAX = 124.0, 132.0
_RADIUS_KM_MAX = 500.0
_MARKERS_MAX_LOCATION_IDS = 500  # 서버 422 상한(OpenAPI 스키마 밖, `docs/weather-api.md`)
_LATEST_MAX_LIMIT = 1000
_FORECAST_MAX_LIMIT = 5000


class KorTravelWeatherError(Exception):
    """`kor-travel-weather` 호출 일반 오류."""


class KorTravelWeatherContractError(KorTravelWeatherError):
    """성공 HTTP 응답이 합의한 JSON/데이터 계약을 위반함."""


class KorTravelWeatherUnavailable(KorTravelWeatherError):
    """timeout / 연결 실패 / 5xx — 재시도 후에도 실패(503 매핑 대상)."""


class KorTravelWeatherBadRequest(KorTravelWeatherError):
    """4xx — RFC7807 `problem+json` (`Problem` 스키마)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(message)


class KorTravelWeatherNotFound(KorTravelWeatherBadRequest):
    """404 — location이 없거나 비활성(disabled는 404로 숨겨진다, `docs/weather-api.md`)."""


# ── DTO (dataclass, 명시 field allow-list로 strict decode — kor_travel_map.py와 동일 관례) ──


@dataclass(frozen=True)
class MeasurementPointOut:
    provider: str
    station_name: str
    latitude: float
    longitude: float
    distance_km: float
    station_id: str | None = None
    address: str | None = None
    network: str | None = None


@dataclass(frozen=True)
class LocationOut:
    location_id: str
    name: str
    latitude: float
    longitude: float
    enabled: bool
    nx: int | None = None
    ny: int | None = None
    region_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CoordinateRequestOut:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class WeatherValueOut:
    """개별 weather 사실(`WeatherValueOut`). `target_at`=대상 시각, `known_at`=수신 시각."""

    value_id: str
    location_id: str
    provider: str
    dataset_key: str
    weather_domain: str
    forecast_style: str
    metric_key: str
    target_at: datetime
    normalization_version: str
    collected_at: datetime
    source_record_key: str
    timeline_bucket: str | None = None
    metric_name: str | None = None
    source_metric_key: str | None = None
    source_metric_name: str | None = None
    value_number: float | None = None
    value_text: str | None = None
    unit: str | None = None
    severity: str | None = None
    issued_at: datetime | None = None
    valid_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    observed_at: datetime | None = None
    known_at: datetime | None = None


@dataclass(frozen=True)
class ResolvedWeatherOut:
    requested: CoordinateRequestOut
    location: LocationOut
    distance_km: float
    measurement_point: MeasurementPointOut | None = None
    source_locations: tuple[LocationOut, ...] = ()
    latest: tuple[WeatherValueOut, ...] = ()
    forecast: tuple[WeatherValueOut, ...] = ()
    alerts: tuple[WeatherValueOut, ...] = ()


@dataclass(frozen=True)
class NearbyOut:
    location_id: str
    name: str
    latitude: float
    longitude: float
    enabled: bool
    distance_km: float
    nx: int | None = None
    ny: int | None = None
    region_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    measurement_point: MeasurementPointOut | None = None
    latest: tuple[WeatherValueOut, ...] = ()
    forecast: tuple[WeatherValueOut, ...] = ()
    alerts: tuple[WeatherValueOut, ...] = ()


@dataclass(frozen=True)
class WeatherMarkerOut:
    location_id: str
    measurement_point: MeasurementPointOut | None = None
    latest: tuple[WeatherValueOut, ...] = ()
    alerts: tuple[WeatherValueOut, ...] = ()


# ── strict decode ────────────────────────────────────────────────────────────

_MEASUREMENT_POINT_REQUIRED = {"provider", "station_name", "latitude", "longitude", "distance_km"}
_MEASUREMENT_POINT_OPTIONAL = {"station_id", "address", "network"}
_MEASUREMENT_POINT_FIELDS = _MEASUREMENT_POINT_REQUIRED | _MEASUREMENT_POINT_OPTIONAL

_LOCATION_REQUIRED = {"location_id", "name", "latitude", "longitude", "enabled"}
_LOCATION_OPTIONAL = {"nx", "ny", "region_code", "metadata"}
_LOCATION_FIELDS = _LOCATION_REQUIRED | _LOCATION_OPTIONAL

_WEATHER_VALUE_REQUIRED = {
    "value_id",
    "location_id",
    "provider",
    "dataset_key",
    "weather_domain",
    "forecast_style",
    "metric_key",
    "target_at",
    "normalization_version",
    "collected_at",
    "source_record_key",
}
_WEATHER_VALUE_OPTIONAL = {
    "timeline_bucket",
    "metric_name",
    "source_metric_key",
    "source_metric_name",
    "value_number",
    "value_text",
    "unit",
    "severity",
    "issued_at",
    "valid_at",
    "valid_from",
    "valid_until",
    "observed_at",
    "known_at",
}
_WEATHER_VALUE_FIELDS = _WEATHER_VALUE_REQUIRED | _WEATHER_VALUE_OPTIONAL
_WEATHER_VALUE_DATETIMES = {
    "target_at",
    "collected_at",
    "issued_at",
    "valid_at",
    "valid_from",
    "valid_until",
    "observed_at",
    "known_at",
}


def _require_mapping(raw: object, *, what: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise KorTravelWeatherContractError(f"kor-travel-weather {what}이(가) object가 아닙니다.")
    return raw


def _check_fields(
    raw: Mapping[str, Any], *, required: set[str], allowed: set[str], what: str
) -> None:
    missing = required - raw.keys()
    if missing:
        raise KorTravelWeatherContractError(
            f"kor-travel-weather {what}에 필수 필드가 없습니다: {sorted(missing)}"
        )
    extra = raw.keys() - allowed
    if extra:
        raise KorTravelWeatherContractError(
            f"kor-travel-weather {what}에 알 수 없는 필드가 있습니다: {sorted(extra)}"
        )


def _decode_datetime(raw: object, *, field_name: str, what: str) -> datetime:
    if not isinstance(raw, str):
        raise KorTravelWeatherContractError(
            f"kor-travel-weather {what}.{field_name}가 문자열이 아닙니다."
        )
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KorTravelWeatherContractError(
            f"kor-travel-weather {what}.{field_name}가 ISO 8601 datetime이 아닙니다."
        ) from exc


def _decode_optional_datetime(raw: object, *, field_name: str, what: str) -> datetime | None:
    if raw is None:
        return None
    return _decode_datetime(raw, field_name=field_name, what=what)


def _decode_measurement_point(raw: object) -> MeasurementPointOut:
    obj = _require_mapping(raw, what="measurement_point")
    _check_fields(
        obj,
        required=_MEASUREMENT_POINT_REQUIRED,
        allowed=_MEASUREMENT_POINT_FIELDS,
        what="measurement_point",
    )
    return MeasurementPointOut(
        provider=obj["provider"],
        station_name=obj["station_name"],
        latitude=obj["latitude"],
        longitude=obj["longitude"],
        distance_km=obj["distance_km"],
        station_id=obj.get("station_id"),
        address=obj.get("address"),
        network=obj.get("network"),
    )


def _decode_optional_measurement_point(raw: object) -> MeasurementPointOut | None:
    return None if raw is None else _decode_measurement_point(raw)


def _decode_location(raw: object) -> LocationOut:
    obj = _require_mapping(raw, what="location")
    _check_fields(obj, required=_LOCATION_REQUIRED, allowed=_LOCATION_FIELDS, what="location")
    metadata = obj.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise KorTravelWeatherContractError(
            "kor-travel-weather location.metadata가 object가 아닙니다."
        )
    return LocationOut(
        location_id=obj["location_id"],
        name=obj["name"],
        latitude=obj["latitude"],
        longitude=obj["longitude"],
        enabled=obj["enabled"],
        nx=obj.get("nx"),
        ny=obj.get("ny"),
        region_code=obj.get("region_code"),
        metadata=dict(metadata),
    )


def _decode_coordinate_request(raw: object) -> CoordinateRequestOut:
    obj = _require_mapping(raw, what="requested")
    _check_fields(
        obj,
        required={"latitude", "longitude"},
        allowed={"latitude", "longitude"},
        what="requested",
    )
    return CoordinateRequestOut(latitude=obj["latitude"], longitude=obj["longitude"])


def _decode_weather_value(raw: object) -> WeatherValueOut:
    obj = _require_mapping(raw, what="weather_value")
    _check_fields(
        obj,
        required=_WEATHER_VALUE_REQUIRED,
        allowed=_WEATHER_VALUE_FIELDS,
        what="weather_value",
    )
    kwargs: dict[str, Any] = {
        k: obj[k] for k in _WEATHER_VALUE_REQUIRED if k not in _WEATHER_VALUE_DATETIMES
    }
    for name in _WEATHER_VALUE_DATETIMES:
        if name in _WEATHER_VALUE_REQUIRED:
            kwargs[name] = _decode_datetime(obj[name], field_name=name, what="weather_value")
        else:
            kwargs[name] = _decode_optional_datetime(
                obj.get(name), field_name=name, what="weather_value"
            )
    for name in _WEATHER_VALUE_OPTIONAL - _WEATHER_VALUE_DATETIMES:
        kwargs[name] = obj.get(name)
    return WeatherValueOut(**kwargs)


def _decode_weather_value_list(raw: object, *, what: str) -> tuple[WeatherValueOut, ...]:
    if not isinstance(raw, list):
        raise KorTravelWeatherContractError(f"kor-travel-weather {what}가 배열이 아닙니다.")
    return tuple(_decode_weather_value(item) for item in raw)


def _decode_resolved_weather(raw: object) -> ResolvedWeatherOut:
    obj = _require_mapping(raw, what="resolve 응답")
    required = {"requested", "location", "distance_km"}
    optional = {"measurement_point", "source_locations", "latest", "forecast", "alerts"}
    _check_fields(obj, required=required, allowed=required | optional, what="resolve 응답")
    source_locations = obj.get("source_locations", [])
    if not isinstance(source_locations, list):
        raise KorTravelWeatherContractError(
            "kor-travel-weather resolve.source_locations가 배열이 아닙니다."
        )
    return ResolvedWeatherOut(
        requested=_decode_coordinate_request(obj["requested"]),
        location=_decode_location(obj["location"]),
        distance_km=obj["distance_km"],
        measurement_point=_decode_optional_measurement_point(obj.get("measurement_point")),
        source_locations=tuple(_decode_location(item) for item in source_locations),
        latest=_decode_weather_value_list(obj.get("latest", []), what="resolve.latest"),
        forecast=_decode_weather_value_list(obj.get("forecast", []), what="resolve.forecast"),
        alerts=_decode_weather_value_list(obj.get("alerts", []), what="resolve.alerts"),
    )


def _decode_marker(raw: object) -> WeatherMarkerOut:
    obj = _require_mapping(raw, what="marker")
    required = {"location_id"}
    optional = {"measurement_point", "latest", "alerts"}
    _check_fields(obj, required=required, allowed=required | optional, what="marker")
    return WeatherMarkerOut(
        location_id=obj["location_id"],
        measurement_point=_decode_optional_measurement_point(obj.get("measurement_point")),
        latest=_decode_weather_value_list(obj.get("latest", []), what="marker.latest"),
        alerts=_decode_weather_value_list(obj.get("alerts", []), what="marker.alerts"),
    )


def _decode_marker_list(raw: object) -> tuple[WeatherMarkerOut, ...]:
    if not isinstance(raw, list):
        raise KorTravelWeatherContractError("kor-travel-weather markers 응답이 배열이 아닙니다.")
    return tuple(_decode_marker(item) for item in raw)


def _require_aware_datetime(value: datetime, *, field_name: str) -> None:
    """transport로 나가는 시각은 offset이 있어야 한다(`kor_travel_map.py`와 동일 정책).

    naive → aware 보정은 시간대 의미를 아는 HTTP 경계(라우터)가 한다. transport는 의미를
    추측하지 않는다.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name}에는 UTC offset이 필요합니다.")


class KorTravelWeatherClient:
    """`kor-travel-weather` 공개 REST 전송 전용 client (httpx.AsyncClient 1개, 인증 없음)."""

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

    # ── 내부 ────────────────────────────────────────────────────────────────

    async def _send(
        self, method: str, path: str, *, params: Mapping[str, Any] | None = None
    ) -> httpx.Response:
        """transient(타임아웃/연결/5xx) 시 지수 백오프 재시도."""
        last: KorTravelWeatherUnavailable | None = None
        cleaned = {k: v for k, v in (params or {}).items() if v is not None}
        for attempt in range(self._max_attempts):
            try:
                resp = await self._http.request(method, path, params=cleaned)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = KorTravelWeatherUnavailable(f"kor-travel-weather 요청 실패({path}): {exc!r}")
            else:
                if resp.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                    last = KorTravelWeatherUnavailable(
                        f"kor-travel-weather {resp.status_code} ({path})"
                    )
                else:
                    return resp
            if attempt + 1 < self._max_attempts:
                await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
        logger.warning("kor_travel_weather.unavailable", extra={"path": path})
        raise last or KorTravelWeatherUnavailable(f"kor-travel-weather 요청 실패({path})")

    @staticmethod
    def _problem_fields(resp: httpx.Response) -> tuple[str | None, str | None]:
        """RFC7807 `Problem`에서 `(code, detail)`을 읽는다. 파싱 실패 시 둘 다 `None`."""
        try:
            payload = resp.json()
        except ValueError:
            return None, None
        if not isinstance(payload, Mapping):
            return None, None
        code = payload.get("code")
        detail = payload.get("detail")
        return (
            code if isinstance(code, str) else None,
            detail if isinstance(detail, str) else None,
        )

    def _unwrap_data(self, resp: httpx.Response, *, path: str) -> Any:
        """성공 응답에서 `data`를 추출. 오류 status는 도메인 예외로 변환.

        envelope = `{data, meta}`. 오류는 RFC7807 `application/problem+json`(`Problem`).
        """
        sc = resp.status_code
        if sc == status.HTTP_404_NOT_FOUND:
            code, detail = self._problem_fields(resp)
            raise KorTravelWeatherNotFound(
                f"kor-travel-weather {sc} ({path})", status_code=sc, code=code, detail=detail
            )
        if sc >= status.HTTP_400_BAD_REQUEST:
            code, detail = self._problem_fields(resp)
            raise KorTravelWeatherBadRequest(
                f"kor-travel-weather {sc} ({path})", status_code=sc, code=code, detail=detail
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise KorTravelWeatherContractError(
                f"kor-travel-weather JSON 응답을 해석할 수 없습니다({path})"
            ) from exc
        if not isinstance(payload, Mapping) or "data" not in payload:
            raise KorTravelWeatherContractError(f"예상치 못한 응답 셰입({path})")
        return payload["data"]

    # ── 공개 표면 (설계 문서 §2.1) ────────────────────────────────────────────

    async def resolve(
        self, *, lat: float, lon: float, radius_km: float | None = None
    ) -> ResolvedWeatherOut:
        """좌표 → 최근접 anchor + 전체 source bundle. **1회용 discovery** — 3.1 MB급 응답.

        조회 경로에서 반복 호출하지 않는다. 결과(`location.location_id` +
        `source_locations`)를 호출자가 캐시한다(설계 §3.2/§3.3).
        """
        if not _LAT_MIN <= lat <= _LAT_MAX:
            raise ValueError(f"lat는 {_LAT_MIN}..{_LAT_MAX} 범위여야 합니다: {lat}")
        if not _LON_MIN <= lon <= _LON_MAX:
            raise ValueError(f"lon은 {_LON_MIN}..{_LON_MAX} 범위여야 합니다: {lon}")
        if radius_km is not None and not 0 < radius_km <= _RADIUS_KM_MAX:
            raise ValueError(f"radius_km은 0 초과 {_RADIUS_KM_MAX} 이하여야 합니다: {radius_km}")
        resp = await self._send(
            "GET", "/v1/weather/resolve", params={"lat": lat, "lon": lon, "radius_km": radius_km}
        )
        return _decode_resolved_weather(self._unwrap_data(resp, path="/v1/weather/resolve"))

    async def markers(self, location_ids: Sequence[str]) -> tuple[WeatherMarkerOut, ...]:
        """다지점 현재값 + 특보(예보 없음). 지도 marker 배치 갱신용, ~2 KB/지점."""
        ids = list(location_ids)
        if not ids:
            raise ValueError("location_ids는 최소 1개 이상이어야 합니다.")
        if len(ids) > _MARKERS_MAX_LOCATION_IDS:
            raise ValueError(
                f"location_ids는 최대 {_MARKERS_MAX_LOCATION_IDS}개까지입니다: {len(ids)}개"
            )
        resp = await self._send("GET", "/v1/weather/markers", params={"location_id": ids})
        return _decode_marker_list(self._unwrap_data(resp, path="/v1/weather/markers"))

    async def latest(
        self, location_id: str, *, limit: int | None = None
    ) -> tuple[WeatherValueOut, ...]:
        """단일 지점 현재값. 존재하지 않거나 비활성인 location_id는 404."""
        if not location_id:
            raise ValueError("location_id가 비어 있습니다.")
        if limit is not None and not 1 <= limit <= _LATEST_MAX_LIMIT:
            raise ValueError(f"limit은 1..{_LATEST_MAX_LIMIT} 범위여야 합니다: {limit}")
        path = f"/v1/weather/locations/{location_id}/latest"
        resp = await self._send("GET", path, params={"limit": limit})
        return _decode_weather_value_list(self._unwrap_data(resp, path=path), what="latest")

    async def forecast(
        self,
        location_id: str,
        *,
        from_: datetime | None = None,
        to: datetime | None = None,
        dataset_key: str | None = None,
        metric_key: str | None = None,
        history: bool = False,
        limit: int | None = None,
    ) -> tuple[WeatherValueOut, ...]:
        """단일 지점 예보/관측 구간. `from_` 생략 시 최고령 행부터 열리므로 **항상 넘긴다**."""
        if not location_id:
            raise ValueError("location_id가 비어 있습니다.")
        if from_ is not None:
            _require_aware_datetime(from_, field_name="from_")
        if to is not None:
            _require_aware_datetime(to, field_name="to")
        if limit is not None and not 1 <= limit <= _FORECAST_MAX_LIMIT:
            raise ValueError(f"limit은 1..{_FORECAST_MAX_LIMIT} 범위여야 합니다: {limit}")
        path = f"/v1/weather/locations/{location_id}/forecast"
        resp = await self._send(
            "GET",
            path,
            params={
                "from": from_.isoformat() if from_ else None,
                "to": to.isoformat() if to else None,
                "dataset_key": dataset_key,
                "metric_key": metric_key,
                "history": history if history else None,
                "limit": limit,
            },
        )
        return _decode_weather_value_list(self._unwrap_data(resp, path=path), what="forecast")


def create_kor_travel_weather_client(app_settings: Settings) -> KorTravelWeatherClient:
    """설정 기반 client 생성 (httpx.AsyncClient 1개, 인증 헤더 없음)."""
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kor_travel_weather_base_url,
        timeout=app_settings.pinvi_kor_travel_weather_timeout_seconds,
        event_hooks=api_call_event_hooks(
            db_session.async_session_factory, provider="kor_travel_weather"
        ),
    )
    return KorTravelWeatherClient(
        http, max_attempts=app_settings.pinvi_kor_travel_weather_max_attempts
    )


@asynccontextmanager
async def kor_travel_weather_client_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — httpx client 1개 생성 후 `app.state`에 보관.

    flag(`pinvi_kor_travel_weather_single_feature_enabled`)가 꺼져 있어도 항상
    생성한다 — httpx.AsyncClient 하나 생성뿐이라 비용이 없고, flag를 재배포 없이
    바꿀 수 있게 한다.
    """
    client = create_kor_travel_weather_client(settings)
    app.state.kor_travel_weather_client = client
    logger.info(
        "kor_travel_weather.client_ready",
        extra={"base_url": settings.pinvi_kor_travel_weather_base_url},
    )
    try:
        yield
    finally:
        await client.aclose()
        app.state.kor_travel_weather_client = None


def get_kor_travel_weather_client(request: Request) -> KorTravelWeatherClient:
    """FastAPI 의존성 — `app.state`의 client. 미주입 시 503."""
    client = getattr(request.app.state, "kor_travel_weather_client", None)
    if not isinstance(client, KorTravelWeatherClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WEATHER_SERVICE_UNAVAILABLE",
                "message": "날씨 서비스가 일시적으로 사용 불가합니다.",
            },
        )
    return client


KorTravelWeatherClientDep = Annotated[
    KorTravelWeatherClient, Depends(get_kor_travel_weather_client)
]


def get_optional_kor_travel_weather_client(request: Request) -> KorTravelWeatherClient | None:
    """FastAPI 의존성 — client 또는 None(503 없음).

    T-362(P3)의 단건 weather 라우터가 쓴다 — flag가 꺼져 있으면(기본값) 이 client를
    아예 쓰지 않으므로, **필수 dependency로 선언하면 flag off인 기존 경로 테스트까지
    이 dependency를 항상 resolve하게 되어**(client override가 없는 테스트는 lifespan도
    안 걸린 채 503을 맞는다) 실측으로 회귀가 났다. optional로 선언해 두면
    `app.dependency_overrides`는 그대로 쓰면서 flag off 경로는 영향받지 않는다. flag
    on인데 None이면(배선 누락) 호출부가 직접 503으로 승격한다.
    """
    client = getattr(request.app.state, "kor_travel_weather_client", None)
    return client if isinstance(client, KorTravelWeatherClient) else None


OptionalKorTravelWeatherClientDep = Annotated[
    KorTravelWeatherClient | None, Depends(get_optional_kor_travel_weather_client)
]
