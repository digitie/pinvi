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
없고 보존이 7일이다(ADR-073, 2026-10-13). 이 단건 경로는 `asof`가 어제(KST) 이전이면
보존 지평과 무관하게 `no_data`다 — 7일보다 오래된 날짜는 이미 drop됐고, 7일 이내의
과거 날짜도 이 경로가 함께 부르는 `latest()`(현재값)를 과거 날짜 카드에 섞을 수 없어
지원하지 않는다. 지난 여행 일자의 날씨는 trip view(`trip_weather_batch.py`)가 보존
지평 안에서 보여준다. 그 외(오늘~예보 가능 범위)는
그 날짜(KST) 하루 구간의 `forecast()`로 좁혀 조회한다. `asof` 없음(기본, 가장 흔한
경로)은 `latest()` + 가까운 며칠 `forecast()`를 합쳐 "관측+예보"를 모두 담는다 —
기존 kor-travel-map 카드의 "관측 + 예보 + 특보" 계약을 유지하기 위함이다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapError
from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient
from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    KorTravelWeatherError,
    WeatherValueOut,
)
from app.schemas.feature import FeatureWeatherCard
from app.services.weather_location_resolver import (
    WeatherLocationFound,
    resolve_weather_location,
    resolve_weather_location_via_map,
)
from app.services.weather_map_state import (
    bundle_values,
    fetch_alerts,
    fetch_location_bundles,
)
from app.services.weather_metrics import (
    WeatherFact,
    dedupe_by_provider_priority,
    to_weather_metric,
)

logger = logging.getLogger(__name__)
_SEOUL = ZoneInfo("Asia/Seoul")


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
        # 과거 날짜는 no_data다(장애로 추측하지 않는다, 설계 §3.1-(1), §4.2). 대상 서비스
        # 보존은 7일(ADR-073)이라 그보다 오래된 날짜는 이미 drop됐고, 7일 이내라도 이
        # 경로는 `latest()`(현재값)를 함께 합치므로 과거 날짜 카드로 쓸 수 없다.
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
    except KorTravelWeatherError as exc:
        # 한 location 실패로 전체를 죽이지 않는다 — 다른 location_id가 있으면 그걸로
        # 채운다. 전부 실패하면 결과가 비어 카드도 비게 된다(장애를 추측해 지어내지
        # 않는다). 빈 카드가 장애 때문인지는 이 로그로 가린다.
        logger.warning(
            "weather_card.location_fetch_failed: %s", exc, extra={"location_id": location_id}
        )
        return []
    return [*latest, *forecast]


async def resolve_and_collect_deduped_values(
    db: AsyncSession,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    asof: datetime | None,
    weather_client: KorTravelWeatherClient,
) -> tuple[list[WeatherValueOut], datetime | None]:
    """`feature_id`의 좌표로 location을 해석하고 사실을 모아 dedupe한다 — 단건(T-362)과
    Admin(T-364) weather 카드 조립이 공유하는 pipeline. asof 축소·location 해석 실패
    (관측소 없음, 피호출자 `Unavailable`)·사실 0건은 전부 빈 리스트로 뭉뚱그린다(호출자가 각자의 "빈 카드" 셰입으로 투영).

    반환: `(deduped_values, latest_known_at)`. 빈 값이면 `latest_known_at`도 `None`.
    """
    now = datetime.now(UTC)
    window = _asof_window(asof, now=now)
    if window.no_data:
        # 과거 조회는 location 해석(3.1 MB `/resolve`, DB 캐시 upsert)조차 필요 없다 —
        # 대상 서비스 보존(2일) 밖이면 어차피 no_data이므로 여기서 먼저 걸러낸다.
        return [], None

    try:
        resolution = await resolve_weather_location(
            db, feature_id=feature_id, lat=lat, lon=lon, client=weather_client
        )
    except KorTravelWeatherError as exc:
        # 피호출자 장애(타임아웃·연결 실패·5xx·회로 열림)와 그 밖의 resolve 오류는 빈 카드로
        # 투영한다 — 500 금지(ADR-074 결정 4(b), `kor-travel-weather.md` §8.3 "대응"; trip view와
        # 같은 예외 계열). 응답 스키마에는 "장애"와 "데이터 없음"을 가르는 필드가 없으므로 운영
        # 구분은 이 로그로 한다(단건·Admin weather-values 공통).
        logger.warning(
            "weather_card.resolve_failed: %s — 빈 카드(장애, no_data 아님)",
            exc,
            extra={"feature_id": feature_id},
        )
        return [], None
    if not isinstance(resolution, WeatherLocationFound):
        return [], None

    per_location = await asyncio.gather(
        *(
            _fetch_location_values(weather_client, location_id, window=window)
            for location_id in resolution.source_location_ids
        )
    )
    all_values = [value for values in per_location for value in values]
    if not all_values:
        return [], None

    deduped = dedupe_by_provider_priority(all_values)
    latest_known = max((value.known_at or value.collected_at for value in deduped), default=None)
    return deduped, latest_known


async def resolve_and_collect_deduped_values_via_map(
    db: AsyncSession,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    asof: datetime | None,
    map_client: KorTravelMapWeatherClient,
    weather_client: KorTravelWeatherClient | None,
) -> tuple[list[WeatherFact], datetime | None]:
    """`resolve_and_collect_deduped_values`의 Map 경로(ADR-077, 플래그 on).

    해석은 Map `/nearest`(캐시 우선), 값은 Map `POST /locations/batch`(source 위치 전체, 50곳씩)의
    관측·예보 부분, 특보만 kor-travel-weather `/markers`다. 같은 `asof` 축소·provider 우선순위 dedupe를 탄다.
    부분별 강등: 읽지 못한 부분(`not_loaded`·`unavailable`)은 행이 없을 뿐 나머지 부분으로 카드를 채운다.
    Map 자체를 못 읽으면 빈 카드다(직접 경로의 피호출자 장애와 같다 — 500 금지).
    """
    now = datetime.now(UTC)
    window = _asof_window(asof, now=now)
    if window.no_data:
        return [], None
    try:
        resolution = await resolve_weather_location_via_map(
            db, feature_id=feature_id, lat=lat, lon=lon, client=map_client
        )
    except KorTravelMapError as exc:
        logger.warning(
            "weather_card.map_resolve_failed: %s — 빈 카드(장애, no_data 아님)",
            exc,
            extra={"feature_id": feature_id},
        )
        return [], None
    if not isinstance(resolution, WeatherLocationFound):
        return [], None

    location_ids = list(resolution.source_location_ids)
    batch, alerts = await asyncio.gather(
        fetch_location_bundles(
            map_client,
            location_ids,
            sections=("current", "forecasts"),
            forecast_from=window.from_,
            forecast_to=window.to,
        ),
        fetch_alerts(weather_client, location_ids),
    )
    all_values: list[WeatherFact] = [
        value for bundle in batch.bundles.values() for value in bundle_values(bundle)
    ]
    all_values += [value for values in alerts.values() for value in values]
    if not all_values:
        return [], None
    deduped = dedupe_by_provider_priority(all_values)
    latest_known = max((value.known_at or value.collected_at for value in deduped), default=None)
    return deduped, latest_known


async def build_feature_weather_card(
    db: AsyncSession,
    *,
    feature_id: str,
    lat: float,
    lon: float,
    asof: datetime | None,
    weather_client: KorTravelWeatherClient | None,
    map_weather_client: KorTravelMapWeatherClient | None = None,
) -> FeatureWeatherCard:
    """`feature_id`의 좌표로 weather 사실을 모아 `FeatureWeatherCard`를 만든다.

    `map_weather_client`가 있으면(플래그 on) Map 경로, 없으면 kor-travel-weather 직접 경로다 — 직접 경로는
    `weather_client`가 있어야 한다(라우터가 보장한다).
    """
    deduped: Sequence[WeatherFact]
    if map_weather_client is not None:
        deduped, latest_known = await resolve_and_collect_deduped_values_via_map(
            db,
            feature_id=feature_id,
            lat=lat,
            lon=lon,
            asof=asof,
            map_client=map_weather_client,
            weather_client=weather_client,
        )
    else:
        if weather_client is None:
            raise ValueError("직접 경로에는 weather_client가 필요합니다.")
        deduped, latest_known = await resolve_and_collect_deduped_values(
            db, feature_id=feature_id, lat=lat, lon=lon, asof=asof, weather_client=weather_client
        )
    if not deduped:
        return FeatureWeatherCard(feature_id=feature_id, asof=asof)

    metrics = [to_weather_metric(value) for value in deduped]
    source_styles = sorted({metric.forecast_style for metric in metrics})

    return FeatureWeatherCard(
        feature_id=feature_id,
        asof=asof,
        latest_at=latest_known,
        is_stale=False,
        source_styles=source_styles,
        metrics=metrics,
    )
