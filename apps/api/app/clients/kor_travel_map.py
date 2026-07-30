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
import json
import logging
import math
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status

from app.core.config import Settings, settings
from app.db import session as db_session
from app.middleware.api_call_logging import api_call_event_hooks

logger = logging.getLogger(__name__)

_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"  # noqa: S105 - 헤더 이름(비밀 아님)
_PUBLIC_API_KEY_HEADER = "X-Kor-Travel-Map-Api-Key"
_POSTGRES_BIGINT_MAX = 9_223_372_036_854_775_807
_WEATHER_BATCH_MAX_TARGETS = 366
_WEATHER_BATCH_MAX_FEATURES_PER_TARGET = 200
_WEATHER_BATCH_MAX_FEATURE_ID_LENGTH = 256
_WEATHER_BATCH_MAX_PAIRS = 2_000
_WEATHER_BATCH_MAX_PLANNING_WORK = 2_500
_WEATHER_BATCH_UNIQUE_FEATURE_WEIGHT = 5


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
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code


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


@dataclass(frozen=True)
class WeatherBatchMetric:
    """weather batch의 고정 metric projection."""

    forecast_style: str
    metric_key: str
    metric_name: str | None
    timeline_bucket: str | None
    value_number: float | None
    value_text: str | None
    unit: str | None
    severity: str | None
    issued_at: datetime | None
    valid_at: datetime | None
    valid_from: datetime | None
    valid_until: datetime | None
    observed_at: datetime | None
    effective_at: datetime | None
    provider: str | None
    weather_domain: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "forecast_style": self.forecast_style,
            "metric_key": self.metric_key,
            "metric_name": self.metric_name,
            "timeline_bucket": self.timeline_bucket,
            "value_number": self.value_number,
            "value_text": self.value_text,
            "unit": self.unit,
            "severity": self.severity,
            "issued_at": self.issued_at,
            "valid_at": self.valid_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "observed_at": self.observed_at,
            "effective_at": self.effective_at,
            "provider": self.provider,
            "weather_domain": self.weather_domain,
        }


@dataclass(frozen=True)
class WeatherBatchCard:
    """한 target 안에서 여러 feature가 공유할 수 있는 weather card."""

    card_key: str
    source_styles: tuple[str, ...]
    current: tuple[WeatherBatchMetric, ...]
    timeline: tuple[WeatherBatchMetric, ...]
    latest_at: datetime | None
    is_stale: bool


@dataclass(frozen=True)
class FoundWeatherBatchItem:
    feature_id: str
    card: WeatherBatchCard
    state: Literal["found"] = "found"


@dataclass(frozen=True)
class NoDataWeatherBatchItem:
    feature_id: str
    state: Literal["no_data"] = "no_data"


@dataclass(frozen=True)
class RetiredWeatherBatchItem:
    feature_id: str
    state: Literal["retired"] = "retired"


WeatherBatchItem = FoundWeatherBatchItem | NoDataWeatherBatchItem | RetiredWeatherBatchItem


_WEATHER_METRIC_FIELDS = {
    "forecast_style",
    "metric_key",
    "metric_name",
    "timeline_bucket",
    "value_number",
    "value_text",
    "unit",
    "severity",
    "issued_at",
    "valid_at",
    "valid_from",
    "valid_until",
    "observed_at",
    "effective_at",
    "provider",
    "weather_domain",
}
_WEATHER_METRIC_OPTIONAL_STRINGS = {
    "metric_name",
    "timeline_bucket",
    "value_text",
    "unit",
    "severity",
    "provider",
    "weather_domain",
}
_WEATHER_METRIC_DATETIMES = {
    "issued_at",
    "valid_at",
    "valid_from",
    "valid_until",
    "observed_at",
    "effective_at",
}


def _decode_aware_datetime(raw: object, *, field: str) -> datetime:
    if not isinstance(raw, str):
        raise KorTravelMapContractError(f"weather batch {field}가 문자열이 아닙니다.")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KorTravelMapContractError(
            f"weather batch {field}가 ISO 8601 datetime이 아닙니다."
        ) from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise KorTravelMapContractError(f"weather batch {field}에 UTC offset이 없습니다.")
    return value


def _decode_weather_metric(raw: object) -> WeatherBatchMetric:
    if (
        not isinstance(raw, Mapping)
        or not {"forecast_style", "metric_key"} <= set(raw)
        or not set(raw) <= _WEATHER_METRIC_FIELDS
    ):
        raise KorTravelMapContractError("weather batch metric 필드 집합이 올바르지 않습니다.")
    if not all(isinstance(raw[field], str) for field in ("forecast_style", "metric_key")):
        raise KorTravelMapContractError("weather batch metric 필수 문자열이 올바르지 않습니다.")
    if not all(
        raw.get(field) is None or isinstance(raw[field], str)
        for field in _WEATHER_METRIC_OPTIONAL_STRINGS
    ):
        raise KorTravelMapContractError("weather batch metric 선택 문자열이 올바르지 않습니다.")
    value_number = raw.get("value_number")
    decoded_value_number: float | None = None
    if value_number is not None:
        if isinstance(value_number, bool) or not isinstance(value_number, (int, float)):
            raise KorTravelMapContractError(
                "weather batch metric value_number가 유한수가 아닙니다."
            )
        try:
            decoded_value_number = float(value_number)
        except OverflowError as exc:
            raise KorTravelMapContractError(
                "weather batch metric value_number가 유한수가 아닙니다."
            ) from exc
        if not math.isfinite(decoded_value_number):
            raise KorTravelMapContractError(
                "weather batch metric value_number가 유한수가 아닙니다."
            )
    datetimes = {
        field: (
            None
            if raw.get(field) is None
            else _decode_aware_datetime(raw[field], field=f"metric.{field}")
        )
        for field in _WEATHER_METRIC_DATETIMES
    }
    return WeatherBatchMetric(
        forecast_style=raw["forecast_style"],
        metric_key=raw["metric_key"],
        metric_name=raw.get("metric_name"),
        timeline_bucket=raw.get("timeline_bucket"),
        value_number=decoded_value_number,
        value_text=raw.get("value_text"),
        unit=raw.get("unit"),
        severity=raw.get("severity"),
        issued_at=datetimes["issued_at"],
        valid_at=datetimes["valid_at"],
        valid_from=datetimes["valid_from"],
        valid_until=datetimes["valid_until"],
        observed_at=datetimes["observed_at"],
        effective_at=datetimes["effective_at"],
        provider=raw.get("provider"),
        weather_domain=raw.get("weather_domain"),
    )


def _decode_weather_batch_card(raw: object) -> WeatherBatchCard:
    if not isinstance(raw, Mapping):
        raise KorTravelMapContractError("weather batch card가 객체가 아닙니다.")
    required = {
        "card_key",
        "source_styles",
        "current",
        "timeline",
        "is_stale",
    }
    if not required <= set(raw) or not set(raw) <= required | {"latest_at"}:
        raise KorTravelMapContractError("weather batch card 셰입이 올바르지 않습니다.")
    card_key = raw["card_key"]
    source_styles = raw["source_styles"]
    current = raw["current"]
    timeline = raw["timeline"]
    if not isinstance(card_key, str):
        raise KorTravelMapContractError("weather batch card_key가 문자열이 아닙니다.")
    if not isinstance(source_styles, list) or not all(
        isinstance(style, str) for style in source_styles
    ):
        raise KorTravelMapContractError("weather batch source_styles가 문자열 배열이 아닙니다.")
    if not isinstance(current, list) or not isinstance(timeline, list):
        raise KorTravelMapContractError("weather batch metric 목록이 배열이 아닙니다.")
    if not isinstance(raw["is_stale"], bool):
        raise KorTravelMapContractError("weather batch is_stale이 boolean이 아닙니다.")
    latest_at = (
        None
        if raw.get("latest_at") is None
        else _decode_aware_datetime(raw["latest_at"], field="latest_at")
    )
    return WeatherBatchCard(
        card_key=card_key,
        source_styles=tuple(source_styles),
        current=tuple(_decode_weather_metric(metric) for metric in current),
        timeline=tuple(_decode_weather_metric(metric) for metric in timeline),
        latest_at=latest_at,
        is_stale=raw["is_stale"],
    )


def _decode_weather_batch_item(
    raw: object,
    *,
    cards: Mapping[str, WeatherBatchCard],
) -> WeatherBatchItem:
    if not isinstance(raw, Mapping):
        raise KorTravelMapContractError("weather batch item이 객체가 아닙니다.")
    state = raw.get("state")
    feature_id = raw.get("feature_id")
    if not isinstance(feature_id, str) or not feature_id:
        raise KorTravelMapContractError("weather batch item feature_id가 빈 문자열입니다.")
    if state == "no_data":
        if set(raw) != {"state", "feature_id"}:
            raise KorTravelMapContractError("weather batch no_data item 셰입이 올바르지 않습니다.")
        return NoDataWeatherBatchItem(feature_id=feature_id)
    if state == "retired":
        if set(raw) != {"state", "feature_id"}:
            raise KorTravelMapContractError("weather batch retired item 셰입이 올바르지 않습니다.")
        return RetiredWeatherBatchItem(feature_id=feature_id)
    if state != "found":
        raise KorTravelMapContractError(f"알 수 없는 weather batch state입니다: {state!r}")
    if set(raw) != {"state", "feature_id", "card_key"}:
        raise KorTravelMapContractError("weather batch found item 셰입이 올바르지 않습니다.")
    card_key = raw["card_key"]
    if not isinstance(card_key, str):
        raise KorTravelMapContractError("weather batch found card_key가 문자열이 아닙니다.")
    card = cards.get(card_key)
    if card is None:
        raise KorTravelMapContractError(
            "weather batch found item이 target-local card를 참조하지 못합니다."
        )
    return FoundWeatherBatchItem(
        feature_id=feature_id,
        card=card,
    )


def _require_aware_datetime(value: datetime, *, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field}에는 UTC offset이 필요합니다.")


def _prepare_weather_batch_targets(
    targets: Mapping[datetime, Sequence[str]],
) -> list[tuple[datetime, list[str]]]:
    if len(targets) > _WEATHER_BATCH_MAX_TARGETS:
        raise ValueError(
            f"weather batch target은 최대 {_WEATHER_BATCH_MAX_TARGETS}개까지 허용됩니다."
        )

    prepared: list[tuple[datetime, list[str]]] = []
    all_feature_ids: set[str] = set()
    pair_count = 0
    for target_at, feature_ids in targets.items():
        if not isinstance(target_at, datetime):
            raise ValueError("weather batch target_at은 datetime이어야 합니다.")
        _require_aware_datetime(target_at, field="target_at")
        try:
            target_at + timedelta(days=1)
        except OverflowError as exc:
            raise ValueError("target_at은 1일 timeline을 계산할 수 있어야 합니다.") from exc
        if isinstance(feature_ids, (str, bytes)):
            raise ValueError("weather batch feature_ids는 문자열 배열이어야 합니다.")
        unique = list(dict.fromkeys(feature_ids))
        if not unique:
            raise ValueError("weather batch target의 feature_ids는 비어 있을 수 없습니다.")
        if len(unique) > _WEATHER_BATCH_MAX_FEATURES_PER_TARGET:
            raise ValueError(
                "weather batch target별 feature_id는 "
                f"최대 {_WEATHER_BATCH_MAX_FEATURES_PER_TARGET}개까지 허용됩니다."
            )
        if any(
            not isinstance(feature_id, str)
            or not feature_id
            or len(feature_id) > _WEATHER_BATCH_MAX_FEATURE_ID_LENGTH
            for feature_id in unique
        ):
            raise ValueError(
                "weather batch feature_id는 1~"
                f"{_WEATHER_BATCH_MAX_FEATURE_ID_LENGTH}자 문자열이어야 합니다."
            )
        pair_count += len(unique)
        all_feature_ids.update(unique)
        prepared.append((target_at, unique))

    planning_work = pair_count + _WEATHER_BATCH_UNIQUE_FEATURE_WEIGHT * len(all_feature_ids)
    if pair_count > _WEATHER_BATCH_MAX_PAIRS:
        raise ValueError(
            f"weather batch target-feature pair는 최대 {_WEATHER_BATCH_MAX_PAIRS}개까지 허용됩니다."
        )
    if planning_work > _WEATHER_BATCH_MAX_PLANNING_WORK:
        raise ValueError(
            f"weather batch planning work가 {_WEATHER_BATCH_MAX_PLANNING_WORK} 한도를 초과했습니다."
        )
    prepared.sort(key=lambda target: target[0])
    return prepared


def _decode_feature_trip_card(raw: object, feature_id: str) -> FeatureTripCard:
    if not isinstance(raw, Mapping):
        raise KorTravelMapContractError("feature batch found item의 trip_card가 객체가 아닙니다.")
    required = {
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
    if set(raw) != required:
        raise KorTravelMapContractError("feature batch trip_card 필드 집합이 올바르지 않습니다.")
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
    if state == "missing":
        if set(raw) != {"state", "feature_id"}:
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
        if set(raw) != {"state", "feature_id", "row_revision", "trip_card"}:
            raise KorTravelMapContractError("feature batch found item 셰입이 올바르지 않습니다.")
        return FoundFeatureBatchItem(
            feature_id=feature_id,
            row_revision=row_revision,
            trip_card=_decode_feature_trip_card(raw["trip_card"], feature_id),
        )
    if set(raw) != {"state", "feature_id", "row_revision"}:
        raise KorTravelMapContractError(f"feature batch {state} item 셰입이 올바르지 않습니다.")
    if state == "retired":
        return RetiredFeatureBatchItem(feature_id=feature_id, row_revision=row_revision)
    if state == "suppressed":
        return SuppressedFeatureBatchItem(feature_id=feature_id, row_revision=row_revision)
    return UnchangedFeatureBatchItem(feature_id=feature_id, row_revision=row_revision)


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
        if not 1 <= batch_chunk_size <= 200:
            raise ValueError("batch_chunk_size는 producer cap 범위(1..200)여야 합니다.")
        self._batch_chunk_size = batch_chunk_size
        self._backoff_base_seconds = backoff_base_seconds

    async def aclose(self) -> None:
        await self._http.aclose()

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
    ) -> httpx.Response:
        """transient(타임아웃/연결/5xx) 시 지수 백오프 재시도."""
        last: KorTravelMapUnavailable | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = await self._http.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    headers=self._headers(allow_public_api_key=allow_public_api_key),
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
        data, meta = self._payload(
            await self._send(
                "GET",
                "/v1/features/in-bounds",
                params=params,
                allow_public_api_key=True,
            )
        )
        cluster = meta.get("cluster")
        if isinstance(cluster, Mapping) and "cluster_unit" in cluster:
            data["cluster_unit"] = cluster.get("cluster_unit")
        return data

    async def get_feature(self, feature_id: str) -> dict[str, Any] | None:
        """단건 상세. 404 → None."""
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
            if set(data) != {"items"} or not isinstance(raw_items, list):
                raise KorTravelMapContractError("feature batch data 셰입이 올바르지 않습니다.")
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

    async def get_weather_batch(
        self,
        targets: Mapping[datetime, Sequence[str]],
        *,
        known_at: datetime,
    ) -> dict[datetime, dict[str, WeatherBatchItem]]:
        """여러 target의 sparse weather snapshot을 한 요청으로 조회·검증한다."""
        _require_aware_datetime(known_at, field="known_at")
        prepared = _prepare_weather_batch_targets(targets)
        if not prepared:
            return {}

        response = await self._send(
            "POST",
            "/v1/features/weather/batch",
            json={
                "targets": [
                    {
                        "target_at": target_at.isoformat(),
                        "feature_ids": feature_ids,
                    }
                    for target_at, feature_ids in prepared
                ],
                "known_at": known_at.isoformat(),
            },
        )
        if response.status_code == status.HTTP_404_NOT_FOUND:
            raise KorTravelMapContractError("weather batch endpoint가 404를 반환했습니다.")
        data = self._data(response)
        if set(data) != {"known_at", "targets"}:
            raise KorTravelMapContractError("weather batch data 필드 집합이 올바르지 않습니다.")
        raw_targets = data["targets"]
        if not isinstance(raw_targets, list):
            raise KorTravelMapContractError("weather batch targets가 배열이 아닙니다.")
        response_known_at = _decode_aware_datetime(data["known_at"], field="known_at")
        if response_known_at != known_at:
            raise KorTravelMapContractError("weather batch 응답 known_at이 요청과 다릅니다.")
        if len(raw_targets) != len(prepared):
            raise KorTravelMapContractError("weather batch 응답 target 수가 요청과 다릅니다.")

        decoded: dict[datetime, dict[str, WeatherBatchItem]] = {}
        for (target_at, feature_ids), raw_target in zip(
            prepared,
            raw_targets,
            strict=True,
        ):
            if not isinstance(raw_target, Mapping) or set(raw_target) != {
                "target_at",
                "timeline_until",
                "items",
                "cards",
            }:
                raise KorTravelMapContractError(
                    "weather batch target data 셰입이 올바르지 않습니다."
                )
            response_target_at = _decode_aware_datetime(
                raw_target["target_at"],
                field="target.target_at",
            )
            timeline_until = _decode_aware_datetime(
                raw_target["timeline_until"],
                field="target.timeline_until",
            )
            if response_target_at != target_at:
                raise KorTravelMapContractError(
                    "weather batch 응답 target 순서나 시각이 요청과 다릅니다."
                )
            if timeline_until != target_at + timedelta(days=1):
                raise KorTravelMapContractError(
                    "weather batch target timeline 지평선이 1일이 아닙니다."
                )

            raw_cards = raw_target["cards"]
            raw_items = raw_target["items"]
            if not isinstance(raw_cards, list) or not isinstance(raw_items, list):
                raise KorTravelMapContractError(
                    "weather batch target items/cards가 배열이 아닙니다."
                )
            cards: dict[str, WeatherBatchCard] = {}
            for raw_card in raw_cards:
                card = _decode_weather_batch_card(raw_card)
                if card.card_key in cards:
                    raise KorTravelMapContractError("weather batch target card_key가 중복됐습니다.")
                cards[card.card_key] = card

            target_items = [_decode_weather_batch_item(item, cards=cards) for item in raw_items]
            if [item.feature_id for item in target_items] != feature_ids:
                raise KorTravelMapContractError(
                    "weather batch 응답이 target별 요청 ID와 순서를 정확히 보존하지 않습니다."
                )
            referenced_card_keys = {
                item.card.card_key
                for item in target_items
                if isinstance(item, FoundWeatherBatchItem)
            }
            if referenced_card_keys != set(cards):
                raise KorTravelMapContractError(
                    "weather batch target cards와 found 참조가 정확히 일치하지 않습니다."
                )
            decoded[target_at] = {item.feature_id: item for item in target_items}
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
            await self._send("GET", "/v1/features/nearby", params=params, allow_public_api_key=True)
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

    async def feature_weather(
        self, feature_id: str, *, asof: datetime | None = None
    ) -> dict[str, Any]:
        """날씨 카드. data = {feature_id, asof, is_stale, source_styles, metrics}."""
        params: dict[str, Any] = {}
        if asof is not None:
            params["asof"] = asof.isoformat()
        return self._data(
            await self._send(
                "GET",
                f"/v1/features/{feature_id}/weather",
                params=params,
                allow_public_api_key=True,
            )
        )

    async def categories(
        self, *, include_counts: bool = False, active_only: bool = False
    ) -> dict[str, Any]:
        """카테고리 카탈로그. data = {count, include_counts, items}."""
        params = {"include_counts": include_counts, "active_only": active_only}
        return self._data(
            await self._send("GET", "/v1/categories", params=params, allow_public_api_key=True)
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
            )
        )

    async def get_public_beach(self, feature_id: str) -> dict[str, Any] | None:
        """공개 해수욕장 상세. 404 → None."""
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
        data, meta = self._payload(
            await self._send(
                "GET",
                "/v1/public/festivals/monthly",
                params=params,
                allow_public_api_key=True,
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
            )
        )

    async def get_public_festival(self, feature_id: str) -> dict[str, Any] | None:
        """공개 축제 상세. 404 → None."""
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
    http = httpx.AsyncClient(
        base_url=app_settings.pinvi_kor_travel_map_api_base_url,
        timeout=app_settings.pinvi_kor_travel_map_timeout_seconds,
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
