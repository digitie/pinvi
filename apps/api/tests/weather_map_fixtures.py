"""Map `/v1/service/weather/*` 응답 fixture (ADR-077, Map ADR-114 W7).

모든 fixture는 vendored `contract/kor-travel-map-openapi-service.json`의 응답 schema에 맞는다 —
`tests/unit/test_kor_travel_map_weather_contract.py`가 `all_fixtures()` 전부를 매번 대조한다(낡은 대역이 계약
파손을 가리지 않게). 단위·통합 테스트는 아래 빌더로 같은 모양을 만든다 — 빌더가 낸 대표 본문이 곧 대조 대상이다.

예보 `target_at`은 Map이 지난 시각을 떼고 주므로(W5) 호출 시각 기준 미래로 만든다(`hours_from_now`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.core.time import KST

LOC_KMA = "kma-grid-60-127"
LOC_AIR = "airkorea-station-abc"
LOC_EXT = "openweathermap-seoul"
FID_KMA = "f_x_weather_0123456789abcdef"
FID_AIR = "f_x_weather_fedcba9876543210"
FID_EXT = "f_x_weather_00aa11bb22cc33dd"
FEATURE_IDS = {LOC_KMA: FID_KMA, LOC_AIR: FID_AIR, LOC_EXT: FID_EXT}


def iso(value: datetime) -> str:
    return value.isoformat()


def hours_from_now(hours: float) -> str:
    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    return iso(base + timedelta(hours=hours))


def freshness(dataset: str, *, stale: bool = False) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "generation": "g-20261024T0900",
        "source_collected_at": "2026-10-24T09:00:00+09:00",
        "source_status": "ok",
        "loaded_at": "2026-10-24T09:05:00+09:00",
        "checked_at": None,
        "age_seconds": 600,
        "max_age_seconds": 10800,
        "stale": stale,
        "item_count": 3,
    }


def location_freshness() -> dict[str, Any]:
    out = freshness("weather.locations")
    # roster의 source_status는 null이다(Map ADR-114 W4).
    out["source_status"] = None
    out["source_collected_at"] = None
    return out


def meta() -> dict[str, Any]:
    return {"duration_ms": 3, "request_id": "req-1"}


def location(
    location_id: str = LOC_KMA,
    *,
    name: str = "서울 중구",
    lon: float | None = 126.978,
    lat: float | None = 37.5665,
    distance_m: float | None = None,
    observations: list[dict[str, Any]] | None = None,
    include_observations: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "feature_id": FEATURE_IDS.get(location_id, "f_x_weather_" + location_id.replace(".", "_")),
        "kind": "weather",
        "category": "99000000",
        "marker_icon": "weather",
        "marker_color": "P-01",
        "location_id": location_id,
        "name": name,
        "coord": None if lon is None or lat is None else {"lon": lon, "lat": lat},
        "address": {"bjd_code": "1114010300", "sido_name": "서울특별시", "sigungu_name": "중구"},
        "distance_m": distance_m,
    }
    if include_observations or observations is not None:
        out["observations"] = observations
    return out


def observation(
    metric_key: str,
    value: float | str | None,
    *,
    provider: str = "python-kma-api",
    unit: str | None = None,
    forecast_style: str = "observed",
    target_at: str | None = None,
) -> dict[str, Any]:
    at = target_at or hours_from_now(-1)
    return {
        "provider": provider,
        "metric_key": metric_key,
        "value": value,
        "unit": unit,
        "target_at": at,
        "known_at": at,
        "forecast_style": forecast_style,
    }


def source(location_id: str, *, distance_m: float | None = None) -> dict[str, Any]:
    return {
        "feature_id": FEATURE_IDS.get(location_id, "f_x_weather_" + location_id),
        "location_id": location_id,
        "distance_m": distance_m,
    }


def current_section(
    status: str = "ok",
    *,
    location_id: str = LOC_KMA,
    observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ok = status == "ok"
    return {
        "status": status,
        "source": source(location_id) if ok else None,
        "freshness": freshness("weather.current") if status != "not_loaded" else None,
        "observations": (observations if observations is not None else []) if ok else [],
    }


def forecast_group(
    metrics: dict[str, list[float | str | None]],
    *,
    provider: str = "python-kma-api",
    target_at: list[str] | None = None,
) -> dict[str, Any]:
    times = target_at or [hours_from_now(h) for h in range(1, 1 + len(next(iter(metrics.values()))))]
    return {
        "provider": provider,
        "known_at": hours_from_now(-2),
        "published_at": hours_from_now(-2),
        "target_at": times,
        "metrics": metrics,
    }


def forecast_section(
    style: str,
    status: str = "ok",
    *,
    location_id: str = LOC_KMA,
    groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ok = status == "ok"
    return {
        "status": status,
        "source": source(location_id) if ok else None,
        "freshness": freshness(f"weather.forecast_{style}") if status != "not_loaded" else None,
        "groups": (groups or []) if ok else [],
    }


def slot_delta(previous: date) -> dict[str, Any]:
    return {
        "previous_date": previous.isoformat(),
        "temp_min_delta": -1.5,
        "temp_max_delta": 0.5,
        "temp_avg_delta": -0.5,
        "humidity_avg_delta": 3.0,
    }


def daily_slot(
    day: date,
    slot: str = "morning",
    *,
    temp_min: float | None = 8.0,
    temp_max: float | None = 14.0,
    sample_count: int = 6,
    partial: bool = False,
    vs_previous_day: dict[str, Any] | None = None,
    source_providers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "slot": slot,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "temp_avg": 11.0,
        "humidity_avg": 60.0,
        "precip_sum_mm": 0.0,
        "precip_occurred": False,
        "sky_code": 1,
        "wind_speed_avg": 2.1,
        "sample_count": sample_count,
        "source_providers": (
            source_providers if source_providers is not None else ["python-kma-api"]
        ),
        "partial": partial,
        "vs_previous_day": vs_previous_day,
    }


def daily_section(
    status: str = "ok",
    *,
    location_id: str = LOC_KMA,
    slots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ok = status == "ok"
    return {
        "status": status,
        "source": source(location_id) if ok else None,
        "freshness": freshness("weather.daily_summaries") if status != "not_loaded" else None,
        "slots": (slots or []) if ok else [],
    }


def bundle(
    location_id: str = LOC_KMA,
    *,
    current: dict[str, Any] | None = None,
    forecasts: dict[str, dict[str, Any]] | None = None,
    daily: dict[str, Any] | None = None,
    distance_m: float | None = None,
) -> dict[str, Any]:
    """`WeatherBundleData`. 생략한 부분은 요청하지 않은 부분(`null`·키 없음)이다."""
    return {
        "location": location(location_id, distance_m=distance_m),
        "location_freshness": location_freshness(),
        "current": current,
        "forecasts": forecasts or {},
        "daily_summaries": daily,
    }


def kma_bundle(location_id: str = LOC_KMA) -> dict[str, Any]:
    """KMA 격자 위치 하나의 정상 묶음(관측·초단기·단기·요약)."""
    today = datetime.now(KST).date()
    return bundle(
        location_id,
        current=current_section(
            location_id=location_id,
            observations=[
                observation("T1H", 12.5, unit="deg_c"),
                observation("REH", 55, unit="%"),
            ],
        ),
        forecasts={
            "ultra_short": forecast_section(
                "ultra_short",
                location_id=location_id,
                groups=[forecast_group({"T1H": [13.0, 14.0], "RN1": [0.0, None]})],
            ),
            "short": forecast_section(
                "short",
                location_id=location_id,
                groups=[forecast_group({"TMP": [15.0, None, 16.0], "POP": [20, 30, None]})],
            ),
        },
        daily=daily_section(
            location_id=location_id,
            slots=[
                daily_slot(today - timedelta(days=2), "morning"),
                daily_slot(
                    today - timedelta(days=1),
                    "morning",
                    vs_previous_day=slot_delta(today - timedelta(days=2)),
                ),
                daily_slot(today, "morning", partial=True, vs_previous_day=None),
            ],
        ),
    )


def bundle_body(data: dict[str, Any]) -> dict[str, Any]:
    return {"data": data, "meta": meta()}


def batch_body(
    items: list[dict[str, Any]], missing: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {"data": {"items": items, "missing": missing or []}, "meta": meta()}


def missing(location_id: str) -> dict[str, Any]:
    return {"feature_id": None, "location_id": location_id}


def list_body(
    items: list[dict[str, Any]], *, truncated: bool = False, with_current: bool = True
) -> dict[str, Any]:
    return {
        "data": {
            "items": items,
            "truncated": truncated,
            "freshness": location_freshness(),
            "current_freshness": freshness("weather.current") if with_current else None,
        },
        "meta": {**meta(), "page": {"page_size": 100, "next_cursor": None}},
    }


def problem_body(status: int, code: str) -> dict[str, Any]:
    return {
        "type": "about:blank",
        "title": "error",
        "status": status,
        "detail": code,
        "code": code,
        "request_id": "req-1",
    }


def nearest_split_bundle() -> dict[str, Any]:
    """가장 가까운 위치(대기질 측정소)에 예보가 없고 KMA 격자가 예보를 준 `/nearest` 묶음."""
    data = bundle(
        LOC_AIR,
        distance_m=270.0,
        current=current_section(
            location_id=LOC_AIR,
            observations=[observation("PM10", 31, provider="python-airkorea-api", unit="ug/m3")],
        ),
        forecasts={
            "ultra_short": forecast_section("ultra_short", "not_loaded"),
            "short": forecast_section(
                "short",
                location_id=LOC_KMA,
                groups=[forecast_group({"TMP": [15.0]})],
            ),
            "mid": forecast_section("mid", "no_data"),
            "external": forecast_section(
                "external",
                location_id=LOC_EXT,
                groups=[
                    forecast_group(
                        {"TEMP": [14.0], "WIND_SPEED": [10.0]}, provider="openweathermap"
                    )
                ],
            ),
        },
        daily=daily_section("unavailable"),
    )
    data["forecasts"]["short"]["source"]["distance_m"] = 1200.0
    data["forecasts"]["external"]["source"]["distance_m"] = 3400.0
    return data


def all_fixtures() -> dict[str, Any]:
    """대조 대상 대표 본문 — 이름은 `RESPONSE_SCHEMAS` 키와 같다."""
    return {
        "bundle_kma": bundle_body(kma_bundle()),
        "bundle_nearest_split": bundle_body(nearest_split_bundle()),
        "bundle_current_only": bundle_body(bundle(current=current_section("no_data"))),
        "batch": batch_body([kma_bundle()], [missing("gone-location")]),
        "list_with_current": list_body(
            [
                location(observations=[observation("T1H", 12.5, unit="deg_c")]),
                location(LOC_AIR, include_observations=True),
                location(LOC_EXT, lon=None, lat=None),
            ]
        ),
        "list_without_current": list_body([location()], with_current=False),
        "problem_not_loaded": problem_body(503, "WEATHER_STATE_NOT_LOADED"),
    }


RESPONSE_SCHEMAS: dict[str, str] = {
    "bundle_kma": "WeatherBundleResponse",
    "bundle_nearest_split": "WeatherBundleResponse",
    "bundle_current_only": "WeatherBundleResponse",
    "batch": "WeatherBatchResponse",
    "list_with_current": "WeatherLocationListResponse",
    "list_without_current": "WeatherLocationListResponse",
    "problem_not_loaded": "ProblemDetail",
}
