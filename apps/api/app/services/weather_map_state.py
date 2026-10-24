"""Map weather 상태 표면(`/v1/service/weather/*`) 해석·평탄화 (PinVi ADR-077, Map ADR-114 W7).

Map은 위치 하나의 관측·예보·세 구간 요약을 **묶음**으로 준다 — 부분(`current`·`forecasts.<style>`·
`daily_summaries`)마다 `status`(`ok`·`not_loaded`·`unavailable`·`no_data`)와 신선도가 따로 있고, 예보는 provider별
묶음(`target_at[]` + `metrics{metric: 값[]}`)이다. PinVi의 weather 규칙(`weather_metrics.py` — provider 우선순위
dedupe·안전 KMA metric key 정규화·`WeatherMetric` 투영)은 kor-travel-weather의 **평탄 행**을 전제로 하므로, 여기서
Map 응답을 같은 모양의 행(`MapWeatherValue`, `WeatherFact` 구조 타입)으로 편다. 공개 응답 셰입은 바뀌지 않는다.

평탄화 규칙(직접 경로와 같은 화면을 내기 위한 것 — 근거는 `docs/integrations/kor-travel-weather.md` §9):

- 관측: 한 값 = 한 행. `forecast_style`은 Map 값(`observed`·`nowcast`) 그대로, `valid_at = target_at`,
  `observed`면 `observed_at = target_at`.
- 예보: 묶음의 `target_at[i]`와 metric마다 한 행, `null` 자리는 버린다(Map 배열의 정렬용 null이다 — 직접 경로에는
  값 없는 행이 없다). `issued_at = published_at`. Map 예보에는 **단위가 없다**.
- `external` 예보 묶음은 `forecast_style="short"`로 편다 — weather는 외부 provider(OpenWeatherMap 등)·KHOA 예보를
  `short` 사실로 저장하고 직접 경로가 그 값을 그대로 줬다(Map은 export 묶음 이름 `external`로만 나눈다).
- 단위·이름: `python-kma-api` 행은 weather `providers/kma.py`의 `KMA_METRIC_UNITS`·`KMA_METRIC_NAMES`(같은
  provider의 고정 표)로 채운다 — 직접 경로가 주던 값과 같다. 그 밖 provider의 예보는 단위를 모른다: 단위가 provider마다
  다른 `WIND_SPEED`(km/h·m/s 혼재)는 **버린다**(잘못된 풍속을 보이는 것보다 빠지는 편이 안전하다 — 정규화 원칙과 같다).
- 세 구간 요약은 호출자가 고른 날짜(지난 여행 일자)에만 행으로 편다(`daily_values`). `vs_previous_day`는 모델이 Map
  값을 그대로 보존한다(partial이면 Map이 null로 준다 — PinVi가 다시 계산하지 않는다).
- 특보는 Map에 없다(Map ADR-114 W7 범위 밖). 호출자가 kor-travel-weather `markers()`의 `alerts`로 합친다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from datetime import date as _Date
from typing import Any, Final, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    model_validator,
)

from app.clients.kor_travel_map import KorTravelMapContractError, KorTravelMapError
from app.clients.kor_travel_map_weather import (
    MAX_BATCH_IDS,
    KorTravelMapWeatherClient,
    WeatherSection,
)
from app.clients.kor_travel_weather import (
    KorTravelWeatherClient,
    KorTravelWeatherError,
    WeatherValueOut,
)
from app.core.time import KST
from app.services.weather_metrics import provider_rank

logger = logging.getLogger(__name__)

SectionStatus = Literal["ok", "not_loaded", "unavailable", "no_data"]
#: 그 부분을 읽지 못했다(빈 데이터가 아니다) — 호출자는 "모른다"로 강등한다.
FAILED_SECTION_STATUSES: Final[frozenset[str]] = frozenset({"not_loaded", "unavailable"})

ScalarValue = StrictFloat | StrictInt | StrictStr | None

_KMA_PROVIDER: Final = "python-kma-api"
# kor-travel-weather `src/kortravelweather/providers/kma.py` `KMA_METRIC_UNITS`·`KMA_METRIC_NAMES`(같은 provider의
# 고정 표 — weather가 KMA 사실에 붙이는 단위·이름). Map 상태 값에는 이 둘이 없어 여기서 같은 값을 채운다.
KMA_METRIC_UNITS: Final[dict[str, str]] = {
    "T1H": "deg_c",
    "TMP": "deg_c",
    "TMN": "deg_c",
    "TMX": "deg_c",
    "T3H": "deg_c",
    "REH": "%",
    "WSD": "m/s",
    "WSDM": "m/s",
    "VEC": "deg",
    "RN1": "mm",
    "PCP": "mm",
    "SNO": "cm",
    "PTY": "code",
    "SKY": "code",
    "POP": "%",
    "WAV": "m",
    "UUU": "m/s",
    "VVV": "m/s",
    "LGT": "code",
}
KMA_METRIC_NAMES: Final[dict[str, str]] = {
    "T1H": "현재 기온",
    "TMP": "기온",
    "TMN": "일 최저기온",
    "TMX": "일 최고기온",
    "T3H": "3시간 기온",
    "REH": "상대습도",
    "WSD": "풍속",
    "WSDM": "평균 풍속",
    "VEC": "풍향",
    "RN1": "1시간 강수량",
    "PCP": "강수량",
    "SNO": "적설",
    "PTY": "강수형태",
    "SKY": "하늘상태",
    "POP": "강수확률",
    "WAV": "파고",
    "UUU": "동서바람성분",
    "VVV": "남북바람성분",
    "LGT": "낙뢰",
}
#: 단위가 provider마다 다른데(km/h·m/s) Map 예보에 단위가 없어 정규화할 수 없는 key.
_UNIT_AMBIGUOUS_FORECAST_KEYS: Final[frozenset[str]] = frozenset({"WIND_SPEED"})

#: Map `dto.weather_state.daily_slot_bounds`(KST): 아침 [05,11)·점심 [11,17)·저녁 [17,23).
DAILY_SLOT_HOURS: Final[dict[str, tuple[int, int]]] = {
    "morning": (5, 11),
    "noon": (11, 17),
    "evening": (17, 23),
}
_DAILY_SLOT_LABELS: Final[dict[str, str]] = {"morning": "아침", "noon": "점심", "evening": "저녁"}


# ── Map 응답 모델(소비하는 필드만, 추가 필드는 무시 — Map의 additive 변경에 깨지지 않는다) ──────────────


class _MapModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class MapWeatherFreshness(_MapModel):
    dataset: str
    stale: bool
    loaded_at: AwareDatetime
    source_collected_at: AwareDatetime | None
    checked_at: AwareDatetime | None


class MapWeatherSource(_MapModel):
    feature_id: str
    location_id: str
    distance_m: StrictFloat | StrictInt | None


class MapWeatherCoord(_MapModel):
    lon: StrictFloat | StrictInt
    lat: StrictFloat | StrictInt


class MapWeatherObservation(_MapModel):
    provider: str
    metric_key: str
    value: ScalarValue
    unit: str | None = None
    target_at: AwareDatetime
    known_at: AwareDatetime
    forecast_style: Literal["observed", "nowcast"]


class MapWeatherLocation(_MapModel):
    feature_id: str
    location_id: str
    name: str
    coord: MapWeatherCoord | None
    distance_m: StrictFloat | StrictInt | None = None
    observations: list[MapWeatherObservation] | None = None


class MapWeatherForecastGroup(_MapModel):
    provider: str
    known_at: AwareDatetime
    published_at: AwareDatetime
    target_at: list[AwareDatetime]
    metrics: dict[str, list[ScalarValue]]

    @model_validator(mode="after")
    def _aligned(self) -> MapWeatherForecastGroup:
        for key, values in self.metrics.items():
            if len(values) != len(self.target_at):
                raise ValueError(f"metric {key} 길이가 target_at과 다르다")
        return self


class MapWeatherSlotDelta(_MapModel):
    previous_date: date
    temp_min_delta: StrictFloat | StrictInt | None
    temp_max_delta: StrictFloat | StrictInt | None
    temp_avg_delta: StrictFloat | StrictInt | None
    humidity_avg_delta: StrictFloat | StrictInt | None


class MapWeatherDailySlot(_MapModel):
    date: _Date
    slot: Literal["morning", "noon", "evening"]
    temp_min: StrictFloat | StrictInt | None = None
    temp_max: StrictFloat | StrictInt | None = None
    temp_avg: StrictFloat | StrictInt | None = None
    humidity_avg: StrictFloat | StrictInt | None = None
    precip_sum_mm: StrictFloat | StrictInt | None = None
    sample_count: StrictInt
    source_providers: list[str]
    partial: bool
    vs_previous_day: MapWeatherSlotDelta | None = None


class MapWeatherCurrentSection(_MapModel):
    status: SectionStatus
    source: MapWeatherSource | None
    freshness: MapWeatherFreshness | None
    observations: list[MapWeatherObservation]


class MapWeatherForecastSection(_MapModel):
    status: SectionStatus
    source: MapWeatherSource | None
    freshness: MapWeatherFreshness | None
    groups: list[MapWeatherForecastGroup]


class MapWeatherForecastSections(_MapModel):
    ultra_short: MapWeatherForecastSection | None = None
    short: MapWeatherForecastSection | None = None
    mid: MapWeatherForecastSection | None = None
    external: MapWeatherForecastSection | None = None

    def by_style(self) -> list[tuple[str, MapWeatherForecastSection]]:
        out: list[tuple[str, MapWeatherForecastSection]] = []
        for style in ("ultra_short", "short", "mid", "external"):
            section = getattr(self, style)
            if section is not None:
                out.append((style, section))
        return out


class MapWeatherDailySection(_MapModel):
    status: SectionStatus
    source: MapWeatherSource | None
    freshness: MapWeatherFreshness | None
    slots: list[MapWeatherDailySlot]


class MapWeatherBundle(_MapModel):
    location: MapWeatherLocation
    current: MapWeatherCurrentSection | None
    forecasts: MapWeatherForecastSections = Field(default_factory=MapWeatherForecastSections)
    daily_summaries: MapWeatherDailySection | None

    def section_location_ids(self) -> list[str]:
        """값이 온 위치 id(대표 위치 먼저, 순서 보존 dedupe) — `/nearest`는 부분마다 다른 위치를 고른다."""
        ids = [self.location.location_id]
        sections: list[Any] = [self.current, self.daily_summaries]
        sections += [section for _style, section in self.forecasts.by_style()]
        for section in sections:
            if section is not None and section.source is not None:
                ids.append(section.source.location_id)
        return list(dict.fromkeys(ids))

    def any_section_failed(self) -> bool:
        """요청한 부분 중 하나라도 읽지 못했는지(`not_loaded`·`unavailable`)."""
        sections: list[Any] = [self.current, self.daily_summaries]
        sections += [section for _style, section in self.forecasts.by_style()]
        return any(s is not None and s.status in FAILED_SECTION_STATUSES for s in sections)


class MapWeatherBatchMissing(_MapModel):
    feature_id: str | None
    location_id: str | None


class MapWeatherBatch(_MapModel):
    items: list[MapWeatherBundle]
    missing: list[MapWeatherBatchMissing]


class MapWeatherLocationList(_MapModel):
    items: list[MapWeatherLocation]
    truncated: bool
    freshness: MapWeatherFreshness
    current_freshness: MapWeatherFreshness | None = None


class MapWeatherContractError(KorTravelMapContractError):
    """Map weather 응답이 PinVi 해석 모델과 맞지 않음(필드 누락·타입·배열 길이)."""


def _parse[ModelT: BaseModel](model: type[ModelT], data: dict[str, Any]) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise MapWeatherContractError(
            f"Map weather 응답 해석 실패({model.__name__}): {exc}"
        ) from exc


def parse_bundle(data: dict[str, Any]) -> MapWeatherBundle:
    return _parse(MapWeatherBundle, data)


def parse_batch(data: dict[str, Any]) -> MapWeatherBatch:
    return _parse(MapWeatherBatch, data)


def parse_location_list(data: dict[str, Any]) -> MapWeatherLocationList:
    return _parse(MapWeatherLocationList, data)


# ── 평탄 행 ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MapWeatherValue:
    """Map 상태 값 한 칸을 kor-travel-weather `WeatherValueOut`과 같은 축의 행으로 편 것(`WeatherFact`).

    Map에 없는 필드(`weather_domain`·`timeline_bucket`·`valid_from` 등)는 `None`이다 — 지어내지 않는다.
    `collected_at`은 Map 값에 없어 `known_at`으로 둔다(동률 판정의 대체 시각으로만 쓰인다).
    """

    location_id: str
    provider: str
    forecast_style: str
    metric_key: str
    target_at: datetime
    known_at: datetime | None
    collected_at: datetime
    value_number: float | None = None
    value_text: str | None = None
    unit: str | None = None
    metric_name: str | None = None
    weather_domain: str | None = None
    timeline_bucket: str | None = None
    severity: str | None = None
    issued_at: datetime | None = None
    valid_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    observed_at: datetime | None = None


def _split_scalar(value: ScalarValue) -> tuple[float | None, str | None]:
    if isinstance(value, str):
        return None, value
    if value is None:
        return None, None
    return float(value), None


def _kma_unit_name(provider: str, metric_key: str) -> tuple[str | None, str | None]:
    if provider != _KMA_PROVIDER:
        return None, None
    return KMA_METRIC_UNITS.get(metric_key), KMA_METRIC_NAMES.get(metric_key)


def observation_values(
    location_id: str, observations: Iterable[MapWeatherObservation]
) -> list[MapWeatherValue]:
    out: list[MapWeatherValue] = []
    for obs in observations:
        number, text = _split_scalar(obs.value)
        if number is None and text is None:
            continue
        kma_unit, kma_name = _kma_unit_name(obs.provider, obs.metric_key)
        out.append(
            MapWeatherValue(
                location_id=location_id,
                provider=obs.provider,
                forecast_style=obs.forecast_style,
                metric_key=obs.metric_key,
                target_at=obs.target_at,
                known_at=obs.known_at,
                collected_at=obs.known_at,
                value_number=number,
                value_text=text,
                unit=obs.unit or kma_unit,
                metric_name=kma_name,
                valid_at=obs.target_at,
                observed_at=obs.target_at if obs.forecast_style == "observed" else None,
            )
        )
    return out


def forecast_values(
    location_id: str, style: str, groups: Iterable[MapWeatherForecastGroup]
) -> list[MapWeatherValue]:
    """예보 묶음을 행으로 편다(`target_at[i]`와 metric, null 자리는 버린다)."""
    forecast_style = "short" if style == "external" else style
    out: list[MapWeatherValue] = []
    for group in groups:
        for metric_key, values in group.metrics.items():
            kma_unit, kma_name = _kma_unit_name(group.provider, metric_key)
            if kma_unit is None and metric_key in _UNIT_AMBIGUOUS_FORECAST_KEYS:
                continue
            for target_at, raw in zip(group.target_at, values, strict=True):
                number, text = _split_scalar(raw)
                if number is None and text is None:
                    continue
                out.append(
                    MapWeatherValue(
                        location_id=location_id,
                        provider=group.provider,
                        forecast_style=forecast_style,
                        metric_key=metric_key,
                        target_at=target_at,
                        known_at=group.known_at,
                        collected_at=group.known_at,
                        value_number=number,
                        value_text=text,
                        unit=kma_unit,
                        metric_name=kma_name,
                        issued_at=group.published_at,
                        valid_at=target_at,
                    )
                )
    return out


def slot_bounds(day: date, slot: str) -> tuple[datetime, datetime]:
    start_hour, end_hour = DAILY_SLOT_HOURS[slot]
    start = datetime.combine(day, time(start_hour), tzinfo=KST)
    return start, start + timedelta(hours=end_hour - start_hour)


_DAILY_METRICS: Final[tuple[tuple[str, str, str, str], ...]] = (
    # (slot 필드, PinVi metric_key, 이름 꼬리, 단위)
    ("temp_min", "TMN", "최저기온", "deg_c"),
    ("temp_max", "TMX", "최고기온", "deg_c"),
    ("humidity_avg", "REH", "평균 습도", "%"),
    ("precip_sum_mm", "PCP", "강수량", "mm"),
)


def daily_values(
    location_id: str,
    section: MapWeatherDailySection,
    *,
    dates: Iterable[date],
) -> list[MapWeatherValue]:
    """세 구간 요약을 `dates`에 든 날짜만 관측 행으로 편다(지난 여행 일자 — 직접 경로의 과거 timeline 대신).

    표본이 없는 구간(`sample_count=0`)·provider가 없는 구간은 건너뛴다. `forecast_style="observed"`,
    `timeline_bucket`은 구간 이름, `valid_from`·`valid_until`은 KST 구간 경계다.
    """
    wanted = set(dates)
    collected = (
        section.freshness.source_collected_at or section.freshness.loaded_at
        if section.freshness is not None
        else None
    )
    out: list[MapWeatherValue] = []
    for slot in section.slots:
        if slot.date not in wanted or slot.sample_count == 0 or not slot.source_providers:
            continue
        provider = min(slot.source_providers, key=provider_rank)
        start, end = slot_bounds(slot.date, slot.slot)
        label = _DAILY_SLOT_LABELS[slot.slot]
        for field_name, metric_key, name_tail, unit in _DAILY_METRICS:
            raw = getattr(slot, field_name)
            if raw is None:
                continue
            out.append(
                MapWeatherValue(
                    location_id=location_id,
                    provider=provider,
                    forecast_style="observed",
                    metric_key=metric_key,
                    target_at=start,
                    known_at=collected,
                    collected_at=collected or end,
                    value_number=float(raw),
                    unit=unit,
                    metric_name=f"{label} {name_tail}",
                    timeline_bucket=slot.slot,
                    valid_at=start,
                    valid_from=start,
                    valid_until=end,
                    observed_at=start,
                )
            )
    return out


def _section_location(bundle: MapWeatherBundle, source: MapWeatherSource | None) -> str:
    return source.location_id if source is not None else bundle.location.location_id


def bundle_values(
    bundle: MapWeatherBundle, *, daily_dates: Sequence[date] = ()
) -> list[MapWeatherValue]:
    """묶음의 `ok` 부분을 행으로 편다(`not_loaded`·`unavailable`·`no_data` 부분은 행이 없다)."""
    out: list[MapWeatherValue] = []
    if bundle.current is not None and bundle.current.status == "ok":
        out += observation_values(
            _section_location(bundle, bundle.current.source), bundle.current.observations
        )
    for style, section in bundle.forecasts.by_style():
        if section.status == "ok":
            out += forecast_values(_section_location(bundle, section.source), style, section.groups)
    daily = bundle.daily_summaries
    if daily_dates and daily is not None and daily.status == "ok":
        out += daily_values(_section_location(bundle, daily.source), daily, dates=daily_dates)
    return out


# ── 배치 조회 ──────────────────────────────────────────────────────────────────────────


#: 배치 청크를 동시에 몇 개까지 보낼지(청크 하나 = 위치 50곳).
_BATCH_CONCURRENCY: Final = 4
#: kor-travel-weather `/markers` 한 번의 location_id 상한(client가 강제하는 서버 상한).
_ALERT_MARKERS_CHUNK: Final = 500


def chunked(items: Sequence[str], size: int) -> list[list[str]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


@dataclass(slots=True)
class MapBatchResult:
    """위치 id(weather `location_id`)별 묶음과, 읽지 못한 위치 id.

    `failed`: 그 위치가 든 청크 호출이 실패했거나(Map 장애·계약 위반) 묶음의 요청 부분 중 하나가
    `not_loaded`·`unavailable`이었다 — "값 없음"이 아니라 "모른다"다. Map `missing`(지금 세대에 없는 위치)은
    실패가 아니다(그 위치의 값이 없다는 확정).
    """

    bundles: dict[str, MapWeatherBundle] = field(default_factory=dict)
    failed: set[str] = field(default_factory=set)
    missing: set[str] = field(default_factory=set)


async def fetch_location_bundles(
    client: KorTravelMapWeatherClient,
    location_ids: Sequence[str],
    *,
    sections: Sequence[WeatherSection],
    forecast_from: datetime | None = None,
    forecast_to: datetime | None = None,
) -> MapBatchResult:
    """`POST /v1/service/weather/locations/batch`를 50곳씩 나눠 부른다. 청크 실패는 그 청크만 `failed`다."""
    ids = list(dict.fromkeys(location_ids))
    result = MapBatchResult()
    if not ids:
        return result
    semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)

    async def one(chunk: list[str]) -> None:
        async with semaphore:
            try:
                batch = parse_batch(
                    await client.batch(
                        location_ids=chunk,
                        sections=sections,
                        forecast_from=forecast_from if "forecasts" in sections else None,
                        forecast_to=forecast_to if "forecasts" in sections else None,
                    )
                )
            except KorTravelMapError as exc:
                logger.warning(
                    "weather_map.batch_failed: %s",
                    exc,
                    extra={"location_count": len(chunk), "error": type(exc).__name__},
                )
                result.failed.update(chunk)
                return
        for bundle in batch.items:
            location_id = bundle.location.location_id
            result.bundles[location_id] = bundle
            if bundle.any_section_failed():
                result.failed.add(location_id)
        for missing in batch.missing:
            if missing.location_id is not None:
                result.missing.add(missing.location_id)

    await asyncio.gather(*(one(chunk) for chunk in chunked(ids, MAX_BATCH_IDS)))
    return result


async def fetch_alerts(
    weather_client: KorTravelWeatherClient | None, location_ids: Sequence[str]
) -> dict[str, list[WeatherValueOut]]:
    """특보는 Map에 없다 — kor-travel-weather `/markers`의 `alerts`만 읽는다(위치 id별).

    weather client가 없거나 실패하면 빈 결과다(특보는 카드의 보조 정보 — 관측·예보를 막지 않는다).
    """
    ids = list(dict.fromkeys(location_ids))
    out: dict[str, list[WeatherValueOut]] = {}
    if weather_client is None or not ids:
        return out
    try:
        for chunk in chunked(ids, _ALERT_MARKERS_CHUNK):
            for marker in await weather_client.markers(chunk):
                if marker.alerts:
                    out.setdefault(marker.location_id, []).extend(marker.alerts)
    except KorTravelWeatherError as exc:
        logger.warning("weather_map.alerts_failed: %s — 특보 없이 진행", exc)
    return out
