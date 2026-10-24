"""Trip view weather — `kor-travel-weather` location 축 batch, feature batch와 완전 독립
(T-363/P4, ADR-068, 2026-09-17 사용자 방향 전환).

**설계 원칙 — map feature 파이프라인과 완전히 분리한다.** `trip_view_builder.py`의
feature batch(POI 존재·좌표·마커 표시용, `kor_travel_map.get_features`)와 이 모듈은
서로의 중간 결과를 주고받지 않는다. 이 함수는 `resolved_features`/`resolution_states`
(feature batch가 만드는 산출물)를 **받지 않는다** — 오직 POI 자신이 들고 있는
`feature_id`와 `feature_snapshot.coord`(POI 추가 시점에 저장된, Pinvi가 소유하는
좌표)만 입력으로 쓴다. 그 결과:

- weather 조회는 그 요청에서 `kor_travel_map` feature batch가 성공했는지, 그 feature가
  `retired`/`suppressed`/`missing`인지와 **무관**하다 — feature의 관리 상태가 어떻든
  POI가 좌표를 들고 있는 한 그 물리적 지점의 날씨를 그대로 보여준다(날씨는 장소의
  행정 상태를 모른다). 이 경로가 내는 상태는 `found`/`no_data`/`unavailable` 셋뿐이다
  — weather_client 미주입(`trip_view_builder.py`) 시에도 균일하게 `unavailable`이지
  feature 상태를 반영하지 않는다(T-365에서 구 `kor_travel_map` 날짜별 batch 경로와
  그 5-state 투영을 완전히 제거했다).
- feature batch(`get_features`) 호출이 이번 요청에서 실패하거나 아예 스킵돼도 weather
  조회는 영향받지 않는다 — snapshot에 좌표가 있으면 그대로 시도한다.

설계 `docs/integrations/kor-travel-weather.md` §3.4(2026-09-17 개정). 기존
`kor_travel_map` `POST /v1/features/weather/batch`(날짜마다 1회)를 location 축
batch로 바꾼다:

1. trip의 POI 중 `feature_id`가 있고 `feature_snapshot.coord`(lon/lat)가 있는 것만
   대상으로, `resolve_weather_location`(T-361, 캐시 우선)으로 location을 해석한다.
2. 해석된 모든 feature의 `source_location_ids` 합집합 `L`을 계산한다(§3.3 — 대표
   location 하나만 쓰면 기상청 예보가 조용히 누락된다. 이 축은 feature 단위가 아니라
   `L` 전체 단위로 한 번만 계산한다).
3. `GET /markers(L)` 1회(현재값+특보, ≤500개씩 청크) + `GET /forecast(location, from=이
   trip에서 필요한 최소 날짜, to=최대 날짜+1일)` location마다 1회, 병렬 — "날짜마다
   반복"이 아니라 "location마다 1회"다(날짜 fanout 없음).
4. feature마다: **자신의 대표 `location_id`를 card_key로 삼고**, 그 대표 id를 공유하는
   모든 feature의 `source_location_ids` 합집합(번들)에서 나온 값을 합쳐 provider
   우선순위로 dedupe한다 — 같은 location에 걸린 여러 POI가 자연히 카드를 공유한다.
   day마다 별도 `weather_cards`/`weather_by_feature_id` 네임스페이스이므로(Pydantic
   파티션 불변식은 day 단위) 같은 card_key라도 날짜별로 다른 카드 내용(그 날짜로
   슬라이스한 metrics)을 가질 수 있다.
5. 예산 10초(view당, `trip_view_builder`와 공유) 안에 끝내며 타임아웃/전체 실패 시
   미결 전체를 `unavailable`로 되돌린다(부분 실패를 추측하지 않는다). 예산은 location
   해석(코드 주석 2단계)과 값 조회(4단계)가 **함께** 쓴다 — 해석 실패(`KorTravelWeatherError`)는 그
   feature만 `unavailable`이고, 예산이 해석 중에 끝나면 pending 전체가 `unavailable`이다
   (ADR-074 결정 4(b), 500 금지). location fanout은 동시성 상한(`_FORECAST_CONCURRENCY`)을
   둔다.

**부분 실패 처리**: bundle 안의 한 location만 fetch 실패해도 다른 location이 값을
줬다면 그 값으로 `found`를 만든다(추측이 아니라 실제로 가진 데이터). bundle 전체가
실패했거나(모든 location 실패) 성공한 location들의 그 날짜 값이 0행이면서 실패한
location이 하나라도 있으면 `unavailable`(모른다를 `no_data`로 지어내지 않는다).
모든 location이 성공했는데 그 날짜 값이 0행이면 그때만 `no_data`(진짜로 확인된
없음)다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapError
from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient, WeatherSection
from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    KorTravelWeatherError,
    kor_travel_weather_call_deadline,
)
from app.models.poi import TripDayPoi
from app.services.weather_location_resolver import (
    WeatherLocationFound,
    WeatherLocationResolution,
    resolve_weather_location,
    resolve_weather_location_via_map,
)
from app.services.weather_map_state import bundle_values, fetch_alerts, fetch_location_bundles
from app.services.weather_metrics import (
    WeatherFact,
    dedupe_by_provider_priority,
    to_weather_metric,
)

logger = logging.getLogger(__name__)
_SEOUL = ZoneInfo("Asia/Seoul")

# markers 1회당 최대 location_id 개수(client가 강제하는 서버 상한과 동일, 안전하게 청크).
_MARKERS_CHUNK_SIZE = 500
# location마다 forecast()를 병렬로 부르되 동시 연결 수를 제한한다(설계 §3.4 "동시성 상한").
_FORECAST_CONCURRENCY = 10
# client 호출 deadline은 view deadline보다 이만큼 앞선다(예산의 1/10 이하) — attempt timeout이
# 바깥 취소보다 먼저 나야 회로차단이 그 실패를 센다(`kor_travel_weather_call_deadline`).
_CLIENT_DEADLINE_MARGIN_SECONDS = 0.1


def _weather_target_at(value: date) -> datetime:
    """해당 한국 일자의 24시간 timeline이 시작되는 aware datetime을 만든다."""
    return datetime.combine(value, time.min, tzinfo=_SEOUL)


def _value_seoul_date(value: WeatherFact) -> date | None:
    instant = value.valid_at or value.target_at or value.observed_at or value.valid_from
    if instant is None:
        return None
    return instant.astimezone(_SEOUL).date()


def _chunked(items: Sequence[str], size: int) -> list[list[str]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _snapshot_coord(poi: TripDayPoi) -> tuple[float, float] | None:
    """POI 자신의 `feature_snapshot.coord` — feature batch 없이도 Pinvi가 이미 갖고 있다."""
    coord = poi.feature_snapshot.get("coord") if isinstance(poi.feature_snapshot, dict) else None
    if not isinstance(coord, dict):
        return None
    lat, lon = coord.get("lat"), coord.get("lon")
    if not isinstance(lat, int | float) or not isinstance(lon, int | float):
        return None
    return float(lat), float(lon)


async def build_trip_weather_via_kor_travel_weather(
    db: AsyncSession,
    *,
    pois: Sequence[TripDayPoi],
    day_effective_date: Mapping[int, date | None],
    weather_client: KorTravelWeatherClient,
    budget_seconds: float,
) -> tuple[dict[int, dict[str, dict[str, Any]]], dict[int, dict[str, dict[str, Any]]]]:
    """`kor-travel-weather` 기반 trip weather 투영 — 기존 셰입(`weather_by_day_index`,
    `weather_cards_by_day_index`)과 동일한 dict를 반환한다.

    feature batch 결과를 전혀 받지 않는다(모듈 docstring 참조) — POI 자신의
    `feature_snapshot.coord`만으로 동작한다.

    view 1회 = client 호출 deadline 범위 1개다 — 회로차단은 이 범위에서 실패를 최대 1회 센다
    (`kor_travel_weather_call_deadline`).
    """
    # 2)~4)는 view 예산 하나를 공유한다(ADR-074 결정 4(b), `kor-travel-weather.md` §8.3 "대응").
    deadline = asyncio.get_running_loop().time() + budget_seconds
    client_deadline = deadline - min(_CLIENT_DEADLINE_MARGIN_SECONDS, budget_seconds / 10)
    with kor_travel_weather_call_deadline(client_deadline):
        return await _build_trip_weather(
            db,
            pois=pois,
            day_effective_date=day_effective_date,
            weather_client=weather_client,
            deadline=deadline,
        )


_DayMaps = dict[int, dict[str, dict[str, Any]]]
_Resolve = Callable[[str, float, float], Awaitable[WeatherLocationResolution]]


@dataclass(slots=True)
class _Pending:
    weather_by_day_index: _DayMaps
    weather_cards_by_day_index: _DayMaps
    feature_days: dict[str, list[tuple[int, date]]] = field(default_factory=dict)
    coord_by_feature_id: dict[str, tuple[float, float]] = field(default_factory=dict)

    def mark(self, feature_ids: Sequence[str], state: str, *, overwrite: bool = True) -> None:
        for feature_id in feature_ids:
            for day_index, _effective_date in self.feature_days[feature_id]:
                day = self.weather_by_day_index[day_index]
                if overwrite:
                    day[feature_id] = {"state": state}
                else:
                    day.setdefault(feature_id, {"state": state})

    def result(self) -> tuple[_DayMaps, _DayMaps]:
        return self.weather_by_day_index, self.weather_cards_by_day_index


def _collect_pending(
    pois: Sequence[TripDayPoi], day_effective_date: Mapping[int, date | None]
) -> _Pending:
    """1) POI마다 좌표 유무만으로 대상 여부를 판정한다 — feature의 관리 상태(retired 등)는 이 모듈이
    알지도, 묻지도 않는다. (day_index, effective_date) 쌍으로 들고 다녀 이후 단계에서 None 재조회를 피한다.
    """
    day_indexes = sorted(day_effective_date)
    pending = _Pending(
        weather_by_day_index={di: {} for di in day_indexes},
        weather_cards_by_day_index={di: {} for di in day_indexes},
    )
    for poi in pois:
        feature_id = poi.feature_id
        effective_date = day_effective_date.get(poi.day_index)
        if feature_id is None or effective_date is None:
            continue
        coord = pending.coord_by_feature_id.get(feature_id) or _snapshot_coord(poi)
        if coord is None:
            pending.weather_by_day_index[poi.day_index][feature_id] = {"state": "unavailable"}
            continue
        pending.coord_by_feature_id[feature_id] = coord
        pending.feature_days.setdefault(feature_id, []).append((poi.day_index, effective_date))
    return pending


async def _resolve_all(
    pending: _Pending,
    resolve: _Resolve,
    *,
    deadline: float,
    errors: tuple[type[Exception], ...],
) -> dict[str, WeatherLocationFound] | None:
    """2) location 해석(캐시 우선) — feature마다 1회, **순차**(한 `AsyncSession`을 쓰므로 동시 실행 금지).

    실패는 두 층으로 투영한다: (i) resolve 호출마다 개별 try — 그 feature만 `unavailable`(`no_data` 아님 —
    관측소 없음을 지어내지 않는다)로 두고 계속 진행해 미스 1건이 적중 N건의 날씨를 빼앗지 않게 한다.
    (ii) 바깥 예산 — 피호출자가 SYN을 버리면 미스 1건이 호출당 connect 상한(≈6.6 s)까지 가므로 (i)만으로는
    예산을 못 지킨다. 예산이 끊기면 pending **전체**를 `unavailable`로 찍고 `None`을 돌려준다.
    """
    caught: tuple[type[Exception], ...] = (*errors, TimeoutError)
    resolutions: dict[str, WeatherLocationResolution] = {}
    unavailable_feature_ids: set[str] = set()
    try:
        async with asyncio.timeout_at(deadline):
            for feature_id in pending.feature_days:
                lat, lon = pending.coord_by_feature_id[feature_id]
                try:
                    resolutions[feature_id] = await resolve(feature_id, lat, lon)
                except caught as exc:
                    logger.warning(
                        "trip_weather_batch.resolve_failed: %s — 이 feature만 unavailable",
                        exc,
                        extra={"feature_id": feature_id},
                    )
                    unavailable_feature_ids.add(feature_id)
    except TimeoutError:
        # 예산이 2단계에서 끝났다 — 4단계 값 조회를 할 시간이 없으므로 이미 해석된 feature도
        # 포함해 pending **전체**를 `unavailable`로 찍는다(found 여부 무관, §8.3 "대응" (ii)).
        logger.error("trip_weather_batch.resolve_budget_exceeded — 미결 feature 전부 unavailable")
        pending.mark(list(pending.feature_days), "unavailable")
        return None

    found: dict[str, WeatherLocationFound] = {}
    for feature_id in pending.feature_days:
        resolution = resolutions.get(feature_id)
        if isinstance(resolution, WeatherLocationFound):
            found[feature_id] = resolution
            continue
        state = "unavailable" if feature_id in unavailable_feature_ids else "no_data"
        pending.mark([feature_id], state)
    return found


@dataclass(frozen=True, slots=True)
class _Bundles:
    by_card_key: dict[str, set[str]]
    location_ids: list[str]
    needed_dates: list[date]


def _bundles(pending: _Pending, found: Mapping[str, WeatherLocationFound]) -> _Bundles:
    """3) card_key(대표 location_id)별 bundle(source_location_ids 합집합)과 이 trip이 필요한 날짜."""
    by_card_key: dict[str, set[str]] = {}
    for resolution in found.values():
        by_card_key.setdefault(resolution.location_id, set()).update(resolution.source_location_ids)
    location_ids = sorted({loc for bundle in by_card_key.values() for loc in bundle})
    needed_dates = sorted(
        {
            effective_date
            for feature_id in found
            for _day_index, effective_date in pending.feature_days[feature_id]
        }
    )
    return _Bundles(by_card_key, location_ids, needed_dates)


def _project(
    pending: _Pending,
    found: Mapping[str, WeatherLocationFound],
    bundles: _Bundles,
    values_by_location: Mapping[str, Sequence[WeatherFact]],
    location_failed: Mapping[str, bool],
) -> None:
    """5) card_key별로 dedupe된 값을 day마다 그 날짜로 슬라이스해 카드/상태를 만든다."""
    deduped_by_card_key: dict[str, list[WeatherFact]] = {
        card_key: dedupe_by_provider_priority(
            [value for location_id in bundle for value in values_by_location.get(location_id, ())]
        )
        for card_key, bundle in bundles.by_card_key.items()
    }
    any_failed_by_card_key: dict[str, bool] = {
        card_key: any(location_failed.get(location_id, False) for location_id in bundle)
        for card_key, bundle in bundles.by_card_key.items()
    }

    for feature_id, resolution in found.items():
        card_key = resolution.location_id
        deduped = deduped_by_card_key[card_key]
        for day_index, effective_date in pending.feature_days[feature_id]:
            day_values = [value for value in deduped if _value_seoul_date(value) == effective_date]
            if day_values:
                day_cards = pending.weather_cards_by_day_index[day_index]
                if card_key not in day_cards:
                    metrics = [to_weather_metric(value) for value in day_values]
                    latest_known = max(
                        (value.known_at or value.collected_at for value in day_values),
                        default=None,
                    )
                    day_cards[card_key] = {
                        "asof": _weather_target_at(effective_date),
                        "latest_at": latest_known,
                        "is_stale": False,
                        "source_styles": sorted({metric.forecast_style for metric in metrics}),
                        "metrics": [metric.model_dump() for metric in metrics],
                    }
                pending.weather_by_day_index[day_index][feature_id] = {
                    "state": "found",
                    "card_key": card_key,
                }
            elif any_failed_by_card_key[card_key]:
                pending.weather_by_day_index[day_index][feature_id] = {"state": "unavailable"}
            else:
                pending.weather_by_day_index[day_index][feature_id] = {"state": "no_data"}


async def _build_trip_weather(
    db: AsyncSession,
    *,
    pois: Sequence[TripDayPoi],
    day_effective_date: Mapping[int, date | None],
    weather_client: KorTravelWeatherClient,
    deadline: float,
) -> tuple[_DayMaps, _DayMaps]:
    pending = _collect_pending(pois, day_effective_date)
    if not pending.feature_days:
        return pending.result()

    async def resolve(feature_id: str, lat: float, lon: float) -> WeatherLocationResolution:
        return await resolve_weather_location(
            db, feature_id=feature_id, lat=lat, lon=lon, client=weather_client
        )

    found = await _resolve_all(pending, resolve, deadline=deadline, errors=(KorTravelWeatherError,))
    if not found:
        return pending.result()

    bundles = _bundles(pending, found)
    range_from = _weather_target_at(bundles.needed_dates[0])
    range_to = _weather_target_at(bundles.needed_dates[-1]) + timedelta(days=1)

    # 4) markers 1회(청크) + forecast location마다 1회(병렬, 동시성 상한) — 예산 안에서.
    values_by_location: dict[str, list[WeatherFact]] = {loc: [] for loc in bundles.location_ids}
    location_failed: dict[str, bool] = dict.fromkeys(bundles.location_ids, False)
    try:
        async with asyncio.timeout_at(deadline):
            for chunk in _chunked(bundles.location_ids, _MARKERS_CHUNK_SIZE):
                markers = await weather_client.markers(chunk)
                for marker in markers:
                    values_by_location[marker.location_id].extend(marker.latest)
                    values_by_location[marker.location_id].extend(marker.alerts)

            semaphore = asyncio.Semaphore(_FORECAST_CONCURRENCY)

            async def _fetch_forecast(location_id: str) -> None:
                async with semaphore:
                    try:
                        forecast = await weather_client.forecast(
                            location_id, from_=range_from, to=range_to, limit=1000
                        )
                    except KorTravelWeatherError:
                        # 한 location 실패로 전체를 죽이지 않는다 — 아래 5)에서
                        # "부분 실패" 규칙으로 처리한다(추측하지 않는다).
                        location_failed[location_id] = True
                        return
                    values_by_location[location_id].extend(forecast)

            await asyncio.gather(*(_fetch_forecast(loc) for loc in bundles.location_ids))
    except (KorTravelWeatherError, TimeoutError) as exc:
        logger.error(
            "trip_weather_batch.failed: %s — 전체 미결 weather를 unavailable 처리",
            exc,
        )
        pending.mark(list(found), "unavailable", overwrite=False)
        return pending.result()

    _project(pending, found, bundles, values_by_location, location_failed)
    return pending.result()


async def build_trip_weather_via_kor_travel_map(
    db: AsyncSession,
    *,
    pois: Sequence[TripDayPoi],
    day_effective_date: Mapping[int, date | None],
    map_client: KorTravelMapWeatherClient,
    weather_client: KorTravelWeatherClient | None,
    budget_seconds: float,
) -> tuple[_DayMaps, _DayMaps]:
    """Map weather 상태 표면 기반 trip weather 투영(ADR-077, 플래그 on) — 셰입은 직접 경로와 같다.

    1)~3)·5)는 직접 경로와 **같은 함수**다(대상 판정·순차 해석과 예산·bundle 합집합·날짜 슬라이스와 부분
    실패 규칙). 다른 것은 2) 해석(Map `/nearest`)과 4) 값 조회다: Map `POST /locations/batch`(bundle 위치
    전체, 50곳씩 청크)로 관측(`current`)·예보(`forecasts`, 이 trip 날짜 창 — 창이 이미 지났으면 요청하지
    않는다)·지난 날짜의 세 구간 요약(`daily_summaries` — 직접 경로의 과거 timeline 대신,
    `weather_map_state.daily_values`)을 받고, 특보만 kor-travel-weather `/markers`의 `alerts`로 합친다
    (weather client가 없으면 특보 없이).

    부분별 강등: 위치의 요청 부분 중 하나가 `not_loaded`·`unavailable`이거나 그 위치의 청크 호출이 실패하면
    그 위치를 "실패"로 센다 — 직접 경로의 location fetch 실패와 같은 규칙(값이 있으면 `found`, 없으면
    `unavailable`, 전부 확인됐는데 없을 때만 `no_data`). 예산(view당)이 끝나면 미결 전체가 `unavailable`이다.
    """
    deadline = asyncio.get_running_loop().time() + budget_seconds
    client_deadline = deadline - min(_CLIENT_DEADLINE_MARGIN_SECONDS, budget_seconds / 10)
    with kor_travel_weather_call_deadline(client_deadline):
        pending = _collect_pending(pois, day_effective_date)
        if not pending.feature_days:
            return pending.result()

        async def resolve(feature_id: str, lat: float, lon: float) -> WeatherLocationResolution:
            return await resolve_weather_location_via_map(
                db, feature_id=feature_id, lat=lat, lon=lon, client=map_client
            )

        found = await _resolve_all(pending, resolve, deadline=deadline, errors=(KorTravelMapError,))
        if not found:
            return pending.result()

        bundles = _bundles(pending, found)
        now = datetime.now(UTC)
        today = now.astimezone(_SEOUL).date()
        range_from = _weather_target_at(bundles.needed_dates[0])
        range_to = _weather_target_at(bundles.needed_dates[-1]) + timedelta(days=1)
        past_dates = [d for d in bundles.needed_dates if d < today]
        sections: list[WeatherSection] = ["current"]
        if range_to > now:
            sections.append("forecasts")
        if past_dates:
            sections.append("daily_summaries")

        try:
            async with asyncio.timeout_at(deadline):
                batch, alerts = await asyncio.gather(
                    fetch_location_bundles(
                        map_client,
                        bundles.location_ids,
                        sections=sections,
                        forecast_from=max(range_from, now),
                        forecast_to=range_to,
                    ),
                    fetch_alerts(weather_client, bundles.location_ids),
                )
        except TimeoutError:
            logger.error("trip_weather_batch.map_budget_exceeded — 미결 weather를 unavailable 처리")
            pending.mark(list(found), "unavailable", overwrite=False)
            return pending.result()

        values_by_location: dict[str, list[WeatherFact]] = {}
        location_failed: dict[str, bool] = {}
        for location_id in bundles.location_ids:
            bundle = batch.bundles.get(location_id)
            values: list[WeatherFact] = []
            if bundle is not None:
                values += bundle_values(bundle, daily_dates=past_dates)
            values += alerts.get(location_id, [])
            values_by_location[location_id] = values
            # Map이 묶음도 missing도 주지 않은 위치는 확인되지 않은 것이다(실패로 센다).
            location_failed[location_id] = location_id in batch.failed or (
                bundle is None and location_id not in batch.missing
            )
        _project(pending, found, bundles, values_by_location, location_failed)
        return pending.result()
