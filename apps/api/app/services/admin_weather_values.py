"""Admin weather-values — `kor-travel-weather` 소스 조립 (T-364/P5, ADR-068).

`GET /admin/features/{id}/weather-values`의 새 경로. T-362(`weather_card.py`)와 같은
`resolve_and_collect_deduped_values` pipeline을 공유하되, 투영 대상이 공개
`WeatherMetric`이 아니라 provenance를 보존하는 `AdminFeatureWeatherMetric`이다.

**신규 제약(ADR-068 결정 2, 문서화됨)**: `AdminFeatureWeatherMetric`의
`provider_dataset_id`(int)·`dataset_display_name`(str)은 `kor-travel-map`의 정수
dataset registry에서 왔고 `kor-travel-weather`에는 대응물이 없다 — 두 필드는 항상
`None`이다(값을 지어내지 않는다). `dataset_key`는 `WeatherValueOut`에도 있어 그대로
채운다. `known_at`도 `WeatherValueOut.known_at`(nullable)을 그대로 옮긴다.

**`asof` 지원(ADR-068 결정 2 두 번째 예외 재검토)**: 구 `kor_travel_map_admin` 경로는
`asof` query 자체를 선언하지 않아 항상 422였다(Map Admin 계약이 현재값만 주므로).
`kor-travel-weather` 기반 transport는 T-362와 동일하게 시점 조회가 가능하므로, flag on
에서는 T-362와 같은 축소 규칙(`weather_card._asof_window` — 보존 2일, 어제 이전은
`no_data`)을 그대로 적용해 **허용한다**. flag off(구 경로)는 기존 422를 유지한다 — Map
Admin transport 자체가 여전히 그 파라미터를 모르기 때문이다.

T-362(단건 사용자 경로)와 마찬가지로 이 endpoint는 POI 문맥이 없는 bare `feature_id`
하나만 받으므로 좌표를 알 방법이 `kor_travel_map_admin.get_feature_detail`뿐이다 —
T-363이 도입한 "feature batch와 완전 분리" 원칙은 POI가 있는 trip view에만 성립하고
여기에는 적용되지 않는다(fallback할 Pinvi 소유 snapshot이 없다).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_weather import KorTravelWeatherClient, WeatherValueOut
from app.schemas.admin import AdminFeatureWeatherMetric, AdminFeatureWeatherValuesResponse
from app.services.weather_card import resolve_and_collect_deduped_values
from app.services.weather_metrics import to_weather_metric


def _to_admin_weather_metric(value: WeatherValueOut) -> AdminFeatureWeatherMetric:
    base = to_weather_metric(value)
    return AdminFeatureWeatherMetric(
        **base.model_dump(),
        provider_dataset_id=None,
        dataset_key=value.dataset_key,
        dataset_display_name=None,
        known_at=value.known_at,
    )


async def build_admin_feature_weather_values(
    db: AsyncSession,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    asof: datetime | None,
    weather_client: KorTravelWeatherClient,
) -> AdminFeatureWeatherValuesResponse:
    """`feature_id`의 좌표로 `kor-travel-weather` 사실을 모아 admin weather-values로 투영."""
    deduped, latest_known = await resolve_and_collect_deduped_values(
        db, feature_id=feature_id, lat=lat, lon=lon, asof=asof, weather_client=weather_client
    )
    if not deduped:
        return AdminFeatureWeatherValuesResponse(feature_id=feature_id, asof=asof)

    items = [_to_admin_weather_metric(value) for value in deduped]
    source_styles = sorted({item.forecast_style for item in items})

    return AdminFeatureWeatherValuesResponse(
        feature_id=feature_id,
        asof=asof,
        latest_at=latest_known,
        is_stale=False,
        source_styles=source_styles,
        items=items,
    )
