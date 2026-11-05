"""관리자 weather-values — 사용자 카드와 같은 설정의 소스에서 정본 사실을 조립한다.

ADR-077의 Map 모드이면 관측·예보를 Map 상태로, 특보만 weather 직접으로 읽는다.
직접 모드는 기존 weather 경로를 유지하며 장애 시 다른 소스로 숨은 fallback하지 않는다.
공통 collect_weather_values가 예산·해석·dedupe를 소유하고 관리자 투영은 provenance를 보존한다.

Map에 원천 dataset_key가 없으므로 null이다. 직접 weather 값은 실제 key를 보존한다.
정수 provider_dataset_id·dataset_display_name도 대응물이 없으면 null이며 known_at은 원문이다.
is_stale는 실제 선택한 사실의 지연 신호다. false만으로 최신 확인을 뜻하지 않는다.

좌표는 비공개 feature도 조회할 수 있는 admin 상세에서 얻는다. asof 축소는 사용자
단건 카드와 같고, 빈 결과는 조회 실패와 무자료를 구별하지 못하므로 UI는 판정 불가로 안내한다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient
from app.clients.kor_travel_weather import KorTravelWeatherClient
from app.core.config import settings
from app.schemas.admin import AdminFeatureWeatherMetric, AdminFeatureWeatherValuesResponse
from app.services.weather_card import collect_weather_values
from app.services.weather_metrics import WeatherFact, to_weather_metric


def _to_admin_weather_metric(value: WeatherFact) -> AdminFeatureWeatherMetric:
    base = to_weather_metric(value)
    return AdminFeatureWeatherMetric(
        **base.model_dump(),
        provider_dataset_id=None,
        dataset_key=getattr(value, "dataset_key", None),
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
    weather_client: KorTravelWeatherClient | None,
    map_weather_client: KorTravelMapWeatherClient | None = None,
    map_budget_seconds: float = 5.0,
) -> AdminFeatureWeatherValuesResponse:
    """`feature_id`의 좌표로 `kor-travel-weather` 사실을 모아 admin weather-values로 투영."""
    deduped, latest_known = await collect_weather_values(
        db,
        feature_id=feature_id,
        lat=lat,
        lon=lon,
        asof=asof,
        weather_client=weather_client,
        map_weather_client=map_weather_client,
        map_budget_seconds=map_budget_seconds,
        direct_budget_seconds=settings.pinvi_kor_travel_weather_admin_request_budget_seconds,
    )
    if not deduped:
        return AdminFeatureWeatherValuesResponse(feature_id=feature_id, asof=asof)

    items = [_to_admin_weather_metric(value) for value in deduped]
    source_styles = sorted({item.forecast_style for item in items})

    return AdminFeatureWeatherValuesResponse(
        feature_id=feature_id,
        asof=asof,
        latest_at=latest_known,
        is_stale=any(value.source_stale for value in deduped),
        source_styles=source_styles,
        items=items,
    )
