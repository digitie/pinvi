"""`kor-travel-weather` `WeatherValueOut` → 정규화된 `WeatherMetric` 공용 변환 (ADR-068).

T-362(단건 feature weather, `weather_card.py`)와 T-363(trip view batch,
`trip_weather_batch.py`)가 이 모듈을 공유한다 — provider 우선순위·안전 metric key
정규화·dedupe 규칙이 두 소비자에서 갈라지면 같은 사실이 화면마다 다르게 보이는
정합성 버그가 된다.

metric key 정규화는 **안전하게 1:1 대응 가능한 것만** 한다(설계
`docs/integrations/kor-travel-weather.md` §3.1-(3)). 단위 체계가 다르거나 대응이
없는 것(`CLOUD_COVER`/`VISIBILITY`/`UV_INDEX`/`WEATHER_CODE`, AirKorea
`O3`/`NO2`/`SO2`/`CO`)은 원래 값 그대로 통과한다 — 잘못된 값을 보여주는 것보다
클라이언트가 인식 못해 카드에서 빠지는 편이 안전하다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.clients.kor_travel_weather import WeatherValueOut
from app.schemas.feature import WeatherMetric

# provider 우선순위 — 왼쪽일수록 우선. 이 목록에 없는 provider는 최하위로 취급한다.
PROVIDER_PRIORITY: tuple[str, ...] = (
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

_TEMP_KEYS = {"TEMP"}
_HUMIDITY_KEYS = {"HUMIDITY"}
_WIND_SPEED_KEYS = {"WIND_SPEED"}
_WIND_DIRECTION_KEYS = {"WIND_DIRECTION"}
_PRECIP_PROB_KEYS = {"PRECIP_PROB"}
_PRECIP_KEYS = {"PRECIP"}
_OBSERVED_STYLES = {"observed", "nowcast"}


def provider_rank(provider: str) -> int:
    try:
        return PROVIDER_PRIORITY.index(provider)
    except ValueError:
        return len(PROVIDER_PRIORITY)


def normalize_metric(value: WeatherValueOut) -> tuple[str, float | None, str | None]:
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
    return key, number, unit


def to_weather_metric(value: WeatherValueOut) -> WeatherMetric:
    is_alert = value.weather_domain == "weather_alert"
    forecast_style = "advisory" if is_alert else value.forecast_style
    if is_alert:
        metric_key, metric_number, unit = value.metric_key, value.value_number, value.unit
    else:
        metric_key, metric_number, unit = normalize_metric(value)
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


def dedupe_by_provider_priority(values: Sequence[WeatherValueOut]) -> list[WeatherValueOut]:
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
        current_rank = provider_rank(current.provider)
        new_rank = provider_rank(value.provider)
        if new_rank < current_rank:
            best[key] = value
            continue
        if new_rank == current_rank:
            current_known = current.known_at or current.collected_at
            new_known = value.known_at or value.collected_at
            if new_known > current_known:
                best[key] = value
    return list(best.values())
