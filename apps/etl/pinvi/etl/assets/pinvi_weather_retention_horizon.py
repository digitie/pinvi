"""`kor-travel-weather` 보존 지평 가드(T-367, ADR-068 게이트 G-3).

`kor-travel-weather`의 실효 보존이 **15일 미만**이면 실패하는 점검이다. 그 서비스가
공개하는 설정값(`KOR_TRAVEL_WEATHER_RETENTION_DAYS`)을 신뢰하는 대신, 실제로 아직
살아 있는 가장 오래된 관측/예보 행의 `known_at`(수신 시각)을 조회해 **실효** 보존을
직접 측정한다 — 외부 설정 회귀로 과거 여행 날씨가 조용히 사라지는 것을 막는 유일한
장치다(`docs/integrations/kor-travel-weather.md` §4.2 대가 2, §6-I).

측정 방법: `GET /v1/weather/locations/{id}/forecast`는 `from`을 생략하면 **가장
오래된 행부터 연다**(§2, 그 문서 132행 — Pinvi의 일반 조회 경로는 이 동작을 피하려고
`from`을 항상 넘기지만, 이 가드는 정확히 그 동작을 이용해 살아남은 가장 오래된 행을
찾는다). 그 행의 `known_at`(없으면 `collected_at`)과 지금 사이의 간격이 실효 보존
일수다.

이 asset은 DB에 쓰지 않고 `kor-travel-weather`의 이미 정규화된 공개 응답 필드
2개(`known_at`/`collected_at`)만 읽으므로 provider raw → DTO 변환(금지룰 3)에
해당하지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from dagster import Backoff, RetryPolicy, asset

from pinvi.etl.resources import KorTravelWeatherResource

DEFAULT_MIN_RETENTION_DAYS = 15
DEFAULT_REFERENCE_LAT = 37.5665  # 서울시청 — 항상 데이터가 쌓이는 안정적 기준점
DEFAULT_REFERENCE_LON = 126.9780
DEFAULT_SAMPLE_LIMIT = 50


class WeatherRetentionGuardError(Exception):
    """`kor-travel-weather` 실효 보존이 임계치 미만일 때 발생한다."""


@dataclass(frozen=True, slots=True)
class RetentionHorizonResult:
    location_id: str
    oldest_known_at: datetime | None
    effective_retention_days: float
    min_retention_days: int
    passed: bool

    def metadata(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "oldest_known_at": (
                self.oldest_known_at.isoformat() if self.oldest_known_at is not None else None
            ),
            "effective_retention_days": round(self.effective_retention_days, 2),
            "min_retention_days": self.min_retention_days,
            "passed": self.passed,
        }


def _parse_datetime(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    value = datetime.fromisoformat(raw)
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def compute_oldest_known_at(values: Sequence[Mapping[str, Any]]) -> datetime | None:
    """`known_at`(없으면 `collected_at`)의 최솟값을 반환합니다. 빈 입력은 `None`."""

    candidates: list[datetime] = []
    for value in values:
        known_at = _parse_datetime(value.get("known_at"))
        if known_at is None:
            known_at = _parse_datetime(value.get("collected_at"))
        if known_at is not None:
            candidates.append(known_at)
    return min(candidates) if candidates else None


def evaluate_retention_horizon(
    *,
    location_id: str,
    oldest_known_at: datetime | None,
    now: datetime,
    min_retention_days: int = DEFAULT_MIN_RETENTION_DAYS,
) -> RetentionHorizonResult:
    """`oldest_known_at`과 `now`의 간격으로 실효 보존 일수를 계산합니다."""

    if oldest_known_at is None:
        return RetentionHorizonResult(
            location_id=location_id,
            oldest_known_at=None,
            effective_retention_days=0.0,
            min_retention_days=min_retention_days,
            passed=False,
        )
    effective_days = (now - oldest_known_at) / timedelta(days=1)
    return RetentionHorizonResult(
        location_id=location_id,
        oldest_known_at=oldest_known_at,
        effective_retention_days=effective_days,
        min_retention_days=min_retention_days,
        passed=effective_days >= min_retention_days,
    )


def _unwrap_data(resp: httpx.Response, *, what: str) -> Any:
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, Mapping) or "data" not in body:
        raise WeatherRetentionGuardError(f"kor-travel-weather {what} 응답에 data가 없습니다.")
    return body["data"]


async def resolve_reference_location(client: httpx.AsyncClient, *, lat: float, lon: float) -> str:
    """좌표 → 대표 anchor `location_id`. `/v1/weather/resolve` 1회 discovery 호출."""

    resp = await client.get("/v1/weather/resolve", params={"lat": lat, "lon": lon})
    data = _unwrap_data(resp, what="/v1/weather/resolve")
    location = data.get("location") if isinstance(data, Mapping) else None
    location_id = location.get("location_id") if isinstance(location, Mapping) else None
    if not isinstance(location_id, str) or not location_id:
        raise WeatherRetentionGuardError(
            "kor-travel-weather resolve 응답에 location_id가 없습니다."
        )
    return location_id


async def fetch_oldest_surviving_values(
    client: httpx.AsyncClient,
    location_id: str,
    *,
    now: datetime,
    limit: int = DEFAULT_SAMPLE_LIMIT,
) -> list[Mapping[str, Any]]:
    """`from` 없이 호출해 살아남은 가장 오래된 행부터 `limit`개를 가져옵니다."""

    resp = await client.get(
        f"/v1/weather/locations/{location_id}/forecast",
        params={"to": now.isoformat(), "history": "true", "limit": limit},
    )
    data = _unwrap_data(resp, what="/v1/weather/locations/{id}/forecast")
    if not isinstance(data, list):
        raise WeatherRetentionGuardError("kor-travel-weather forecast 응답이 list가 아닙니다.")
    return [item for item in data if isinstance(item, Mapping)]


@asset(
    group_name="pinvi_weather_retention",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description=("kor-travel-weather 실효 보존이 15일 미만이면 실패하는 가드(T-367, ADR-068 G-3)"),
)
async def pinvi_weather_retention_horizon_guard(  # type: ignore[no-untyped-def]
    context,
    kor_travel_weather: KorTravelWeatherResource,
) -> dict[str, Any]:
    reference_lat = float(context.op_config.get("reference_lat", DEFAULT_REFERENCE_LAT))
    reference_lon = float(context.op_config.get("reference_lon", DEFAULT_REFERENCE_LON))
    min_retention_days = int(
        context.op_config.get("min_retention_days", DEFAULT_MIN_RETENTION_DAYS)
    )
    sample_limit = int(context.op_config.get("sample_limit", DEFAULT_SAMPLE_LIMIT))

    now = datetime.now(UTC)
    client = kor_travel_weather.create_client()
    try:
        location_id = await resolve_reference_location(client, lat=reference_lat, lon=reference_lon)
        values = await fetch_oldest_surviving_values(
            client, location_id, now=now, limit=sample_limit
        )
    finally:
        await client.aclose()

    oldest_known_at = compute_oldest_known_at(values)
    result = evaluate_retention_horizon(
        location_id=location_id,
        oldest_known_at=oldest_known_at,
        now=now,
        min_retention_days=min_retention_days,
    )
    context.add_output_metadata(result.metadata())
    if not result.passed:
        raise WeatherRetentionGuardError(
            f"kor-travel-weather 실효 보존 {result.effective_retention_days:.1f}일 < "
            f"임계 {min_retention_days}일 (location_id={location_id}, "
            f"oldest_known_at={result.oldest_known_at})"
        )
    return result.metadata()
