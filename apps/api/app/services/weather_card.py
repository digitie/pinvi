"""단건 feature weather 카드 — `kor-travel-weather` 소스 조립 (T-362/P3, ADR-068).

`GET /features/{id}/weather`의 새 경로. 공개 계약(`FeatureWeatherCard` 셰입)은
그대로 두고, 내부적으로 `kor-travel-weather`의 location 사실을 모아 같은 셰입으로
투영한다. 흐름:

1. `resolve_weather_location`으로 `feature_id`의 좌표를 location으로 해석(캐시 우선).
2. `WeatherLocationNoData`면 빈 카드(`metrics=[]`)를 돌려준다 — 기존 kor-travel-map
   경로도 데이터가 없으면 빈 metrics로 표현했으므로 계약이 같다.
3. `source_location_ids` 전체(대표 하나만 쓰면 기상청 예보가 조용히 누락된다 — 설계
   §3.3)에 대해 `latest()` + `forecast()`를 부르고 합친다.
4. 같은 `(metric_key, forecast_style, target_at)`에 여러 provider가 값을 줄 수 있다
   — provider 우선순위(KMA > AirKorea > 상용) + 동률 시 `known_at` 최신으로 하나만
   남긴다.
5. metric_key를 **안전하게 매핑 가능한 것만** KMA 어휘로 정규화한다(설계
   §3.1-(3) 권장안 — 서버 정규화로 클라이언트 변경 0 유지). 단위 체계가 다르거나
   1:1 대응이 없는 것(`CLOUD_COVER`/`VISIBILITY`/`UV_INDEX`/`WEATHER_CODE`,
   AirKorea `O3`/`NO2`/`SO2`/`CO`)은 **원래 값 그대로 통과**한다 — 잘못된 값을
   보여주는 것보다 클라이언트가 인식 못해 카드에서 빠지는 편이 안전하다. 이 잔여
   한계는 `docs/integrations/kor-travel-weather.md`에 정직하게 남긴다.
6. `weather_domain == "weather_alert"`인 사실은 `forecast_style="advisory"`로
   투영한다(대상 서비스에는 `advisory` forecast_style이 없다 — 특보는 별도
   `weather_alert` 도메인으로 온다).

**`asof` 축소** (설계 §3.1-(1)): 대상 서비스에는 시점 재현(snapshot) 엔드포인트가
없고 보존이 2일이다. `asof`가 어제 이전이면 `no_data`. 그 외(오늘~예보 가능 범위)는
그 날짜(KST) 하루 구간의 `forecast()`로 좁혀 조회한다. `asof` 없음(기본, 가장 흔한
경로)은 `latest()` + 가까운 며칠 `forecast()`를 합쳐 "관측+예보"를 모두 담는다 —
기존 kor-travel-map 카드의 "관측 + 예보 + 특보" 계약을 유지하기 위함이다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    KorTravelWeatherError,
    WeatherValueOut,
)
from app.schemas.feature import FeatureWeatherCard, WeatherMetric
from app.services.weather_location_resolver import (
    WeatherLocationFound,
    resolve_weather_location,
)

_SEOUL = ZoneInfo("Asia/Seoul")

# provider 우선순위 — 왼쪽일수록 우선. 동률(같은 provider가 여러 개일 순 없으므로
# 사실상 "이 목록에 없는 provider"는 최하위로 취급한다.
_PROVIDER_PRIORITY: tuple[str, ...] = (
    "python-kma-api",
    "python-airkorea-api",
    "python-khoa-api",
    "python-krforest-api",
    "python-krex-api",
    "openweathermap",
    "weatherapi",
    "open_meteo",
    "wttr_in",
)


def _provider_rank(provider: str) -> int:
    try:
        return _PROVIDER_PRIORITY.index(provider)
    except ValueError:
        return len(_PROVIDER_PRIORITY)


# ── metric key 정규화 — 안전하게 1:1 대응 가능한 것만(설계 §3.1-(3)) ──────────────

_TEMP_KEYS = {"TEMP"}
_HUMIDITY_KEYS = {"HUMIDITY"}
_WIND_SPEED_KEYS = {"WIND_SPEED"}
_WIND_DIRECTION_KEYS = {"WIND_DIRECTION"}
_PRECIP_PROB_KEYS = {"PRECIP_PROB"}
_PRECIP_KEYS = {"PRECIP"}
_OBSERVED_STYLES = {"observed", "nowcast"}


def _normalize_metric(value: WeatherValueOut) -> tuple[str, float | None, str | None]:
    """`(metric_key, value_number, unit)` — 정규화 가능하면 KMA 코드로, 아니면 원본 그대로.

    단위가 provider마다 다를 수 있어(`docs/integrations/kor-travel-weather.md` §2.3)
    `unit`을 항상 확인하고 무가정 변환하지 않는다. 풍속만 km/h -> m/s 변환이 필요할
    수 있어 명시 처리한다.
    """
    key = value.metric_key
    unit = value.unit
    number = value.value_number

    if key in _TEMP_KEYS:
        kma_key = "T1H" if value.forecast_style in _OBSERVED_STYLES else "TMP"
        return kma_key, number, unit or "deg_c"
    if key in _HUMIDITY_KEYS:
        return "REH", number, unit or "%"
    if key in _WIND_SPEED_KEYS:
        if unit == "km/h" and number is not None:
            return "WSD", number / 3.6, "m/s"
        return "WSD", number, unit or "m/s"
    if key in _WIND_DIRECTION_KEYS:
        return "VEC", number, unit or "deg"
    if key in _PRECIP_PROB_KEYS:
        return "POP", number, unit or "%"
    if key in _PRECIP_KEYS:
        kma_key = "RN1" if value.forecast_style == "ultra_short" else "PCP"
        return kma_key, number, unit
    # 매핑 불가 — CLOUD_COVER/VISIBILITY/UV_INDEX/WEATHER_CODE, AirKorea O3/NO2/SO2/CO 등.
    # 원래 값 그대로 통과한다(틀린 값보다 미인식이 안전).
    return key, number, unit


def _to_weather_metric(value: WeatherValueOut) -> WeatherMetric:
    is_alert = value.weather_domain == "weather_alert"
    forecast_style = "advisory" if is_alert else value.forecast_style
    if is_alert:
        metric_key, metric_number, unit = value.metric_key, value.value_number, value.unit
    else:
        metric_key, metric_number, unit = _normalize_metric(value)
    return WeatherMetric(
        metric_key=metric_key,
        metric_name=value.metric_name,
        forecast_style=forecast_style,
        timeline_bucket=value.timeline_bucket,
        provider=value.provider,
        weather_domain=value.weather_domain,
        valid_at=value.valid_at or value.target_at,
        valid_from=value.valid_from,
        valid_until=value.valid_until,
        effective_at=None,  # kor-travel-weather에는 대응 필드가 없다.
        issued_at=value.issued_at,
        observed_at=value.observed_at,
        value_number=metric_number,
        value_text=value.value_text,
        unit=unit,
        severity=value.severity,
    )


def _dedupe_by_provider_priority(values: Sequence[WeatherValueOut]) -> list[WeatherValueOut]:
    """같은 `(metric_key, forecast_style, target_at)`는 provider 우선순위로 하나만 남긴다.

    동률이면 `known_at`이 더 최신인 쪽. `known_at`이 없으면(nullable) `collected_at`으로
    대신한다.
    """
    best: dict[tuple[str, str, datetime], WeatherValueOut] = {}
    for value in values:
        key = (value.metric_key, value.forecast_style, value.target_at)
        current = best.get(key)
        if current is None:
            best[key] = value
            continue
        current_rank = _provider_rank(current.provider)
        new_rank = _provider_rank(value.provider)
        if new_rank < current_rank:
            best[key] = value
            continue
        if new_rank == current_rank:
            current_known = current.known_at or current.collected_at
            new_known = value.known_at or value.collected_at
            if new_known > current_known:
                best[key] = value
    return list(best.values())


@dataclass(frozen=True, slots=True)
class _AsofWindow:
    no_data: bool
    from_: datetime | None
    to: datetime | None


def _asof_window(asof: datetime | None, *, now: datetime) -> _AsofWindow:
    if asof is None:
        return _AsofWindow(no_data=False, from_=now, to=now + timedelta(days=3))
    target_date = asof.astimezone(_SEOUL).date()
    today = now.astimezone(_SEOUL).date()
    if target_date < today:
        # 대상 서비스 보존 2일 — 어제 이전은 이미 drop됐을 수 있다. 장애로 추측하지
        # 않고 no_data로 둔다(설계 §3.1-(1), §4.2).
        return _AsofWindow(no_data=True, from_=None, to=None)
    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=_SEOUL)
    return _AsofWindow(no_data=False, from_=day_start, to=day_start + timedelta(days=1))


async def _fetch_location_values(
    client: KorTravelWeatherClient, location_id: str, *, window: _AsofWindow
) -> list[WeatherValueOut]:
    try:
        latest, forecast = await asyncio.gather(
            client.latest(location_id, limit=200),
            client.forecast(location_id, from_=window.from_, to=window.to, limit=1000),
        )
    except KorTravelWeatherError:
        # 한 location 실패로 전체를 죽이지 않는다 — 다른 location_id가 있으면 그걸로
        # 채운다. 전부 실패하면 결과가 비어 카드도 비게 된다(장애를 추측해 지어내지
        # 않는다).
        return []
    return [*latest, *forecast]


async def build_feature_weather_card(
    db: AsyncSession,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    asof: datetime | None,
    weather_client: KorTravelWeatherClient,
) -> FeatureWeatherCard:
    """`feature_id`의 좌표로 `kor-travel-weather` 사실을 모아 `FeatureWeatherCard`를 만든다."""
    now = datetime.now(UTC)
    window = _asof_window(asof, now=now)
    if window.no_data:
        # 과거 조회는 location 해석(3.1 MB `/resolve`, DB 캐시 upsert)조차 필요 없다 —
        # 대상 서비스 보존(2일) 밖이면 어차피 no_data이므로 여기서 먼저 걸러낸다.
        return FeatureWeatherCard(feature_id=feature_id, asof=asof)

    resolution = await resolve_weather_location(
        db, feature_id=feature_id, lat=lat, lon=lon, client=weather_client
    )
    if not isinstance(resolution, WeatherLocationFound):
        return FeatureWeatherCard(feature_id=feature_id, asof=asof)

    per_location = await asyncio.gather(
        *(
            _fetch_location_values(weather_client, location_id, window=window)
            for location_id in resolution.source_location_ids
        )
    )
    all_values = [value for values in per_location for value in values]
    if not all_values:
        return FeatureWeatherCard(feature_id=feature_id, asof=asof)

    deduped = _dedupe_by_provider_priority(all_values)
    metrics = [_to_weather_metric(value) for value in deduped]
    source_styles = sorted({metric.forecast_style for metric in metrics})
    latest_known = max((value.known_at or value.collected_at for value in deduped), default=None)

    return FeatureWeatherCard(
        feature_id=feature_id,
        asof=asof,
        latest_at=latest_known,
        is_stale=False,
        source_styles=source_styles,
        metrics=metrics,
    )
