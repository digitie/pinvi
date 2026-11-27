"""여행 장소(POI)의 영업 정보 — 영업시간·휴무일·전화·웹사이트 (`trip_poi_place_details`).

흐름:
- 장소 정보 패널이 처음 열릴 때(`get_or_fetch_place_details`) 저장된 행이 없으면 출처에서 한 번 받아
  저장한다. 출처를 조회했는데 줄 값이 없으면 `empty`로 저장해 다시 묻지 않는다. 출처 장애는 저장하지
  않는다(다음 열람 때 다시 시도) — 화면은 조용히 아무것도 보이지 않는다.
- "다시 읽어오기"(`refresh_place_details`)는 같은 장소 `REFRESH_INTERVAL` 안 재요청을 거부하고, 받은
  값으로 행을 통째로 덮어쓴다. 출처 장애면 기존 값을 그대로 둔다.
- 장소를 지우면(`services.poi.soft_delete_poi`) 행도 지운다. 영구 삭제는 FK CASCADE다.

출처: kor-travel-map feature 상세(공공데이터)만 저장한다. Map place detail의 `business_hours`(Google
Places 호환 `FeatureOpeningHours` — `weekday_text`/`periods`/`special_days`), Map 최상위 `visitor_info`
(ADR-126)의 `usage_hours`/`rest_days` 원문, 옛 출처 원문 영업시간 문자열(`facility_info.operating_time` 등),
`phones[]`, `urls.homepage`를 읽는다(우선순위: 구조화 → `visitor_info` → 옛 평면 키). 저장된 행은 캐시라
`visitor_info`가 새로 생겨도 "다시 읽어오기" 전까지는 예전 값을 보인다. Kakao/Naver Local은
응답 저장이 금지(ADR-054, 상세 카드의 라이브 표시로만 쓴다)이고, Google Places Details는 콘텐츠 캐시
금지와 비 Google 지도 위 표시 금지 약관 때문에 쓰지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapClient, KorTravelMapError
from app.core.time import KST
from app.models.poi import TripDayPoi
from app.models.poi_place_detail import TripPoiPlaceDetail
from app.services.feature_detail import _clean, _homepage, _phone, _pick
from app.services.opening_hours import DISPLAY_ORDER as _DISPLAY_ORDER
from app.services.opening_hours import WEEKDAYS as _WEEKDAYS
from app.services.opening_hours import hours_from_structured as _hours_from_structured
from app.services.source_introduction import guide_text, visitor_info_of, visitor_info_source

MAP_SOURCE = "kor_travel_map"
REFRESH_INTERVAL = timedelta(seconds=60)

# 출처 원문 영업시간 문자열 키(MCST `operating_time`, TourAPI `usetime` 등).
_HOURS_TEXT_KEYS = (
    "operating_time",
    "opening_hours",
    "business_hours",
    "usetime",
    "use_time",
    "oper_time",
    "open_time",
)
# 출처 원문 휴무일 문자열 키(박물관·미술관 표준데이터 `rstde_info`, TourAPI `restdate` 등).
_CLOSED_TEXT_KEYS = (
    "rstde_info",
    "restdate",
    "rest_date",
    "closed_days",
    "closed_day",
    "holiday_info",
)


class PlaceDetailsUnavailable(Exception):
    """출처(kor-travel-map) 장애 — 저장하지 않고 다음에 다시 시도한다."""


class PlaceDetailsRefreshTooSoon(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("잠시 뒤 다시 시도해 주세요.")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class ExtractedPlaceDetails:
    opening_hours: list[str] = field(default_factory=list)
    closed_days: str | None = None
    phone: str | None = None
    website: str | None = None
    # 필드 이름 → 실제 출처(기본은 `kor_travel_map`). Map `visitor_info`에서 온 값은 그 원천
    # (`tourapi`·`krheritage`·`datagokr_museum`·`krforest_recreation_forest`)을 적어 화면이 정확한 출처를 보인다.
    origins: dict[str, str] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not (self.opening_hours or self.closed_days or self.phone or self.website)

    def sources(self) -> dict[str, str]:
        present = {
            "opening_hours": bool(self.opening_hours),
            "closed_days": self.closed_days is not None,
            "phone": self.phone is not None,
            "website": self.website is not None,
        }
        return {name: self.origins.get(name, MAP_SOURCE) for name, ok in present.items() if ok}


def _upcoming_closed_dates(hours: dict[str, Any], today: date) -> list[str]:
    out: list[str] = []
    for special in hours.get("special_days") or []:
        if not isinstance(special, dict) or not special.get("is_closed"):
            continue
        raw = special.get("date")
        try:
            day = date.fromisoformat(raw) if isinstance(raw, str) else None
        except ValueError:
            day = None
        if day is not None and day >= today:
            out.append(f"{day.month}월 {day.day}일")
    return out[:5]


def extract_place_details(dto: dict[str, Any], *, today: date) -> ExtractedPlaceDetails:
    """Map feature dto → 저장할 영업 정보. 값이 없으면 빈 필드다(추측하지 않는다)."""
    detail = dto.get("detail")
    detail = detail if isinstance(detail, dict) else {}
    facility = detail.get("facility_info")

    hours_lines: list[str] = []
    closed_weekdays: set[int] | None = None
    closed_dates: list[str] = []
    for key in ("business_hours", "opening_hours"):
        structured = detail.get(key)
        if isinstance(structured, dict):
            hours_lines, closed_weekdays = _hours_from_structured(structured)
            closed_dates = _upcoming_closed_dates(structured, today)
            if hours_lines:
                break
    structured_used = bool(hours_lines)
    # Map `visitor_info`(ADR-126)의 이용시간·휴무 원문 — 구조화 영업시간이 없을 때 옛 평면 키보다 먼저 쓴다.
    # 아는 원천(`source`)일 때만 읽고, 그 값을 쓴 필드는 실제 원천을 출처로 남긴다.
    info = visitor_info_of(dto)
    visitor_source = visitor_info_source(info)
    visitor = info if info is not None and visitor_source is not None else {}
    origins: dict[str, str] = {}
    if not hours_lines:
        visitor_hours = guide_text(visitor.get("usage_hours"))
        text = (
            visitor_hours or _pick(facility, *_HOURS_TEXT_KEYS) or _pick(detail, *_HOURS_TEXT_KEYS)
        )
        if text:
            hours_lines = [text]
        if visitor_hours and visitor_source:
            origins["opening_hours"] = visitor_source

    closed_parts: list[str] = []
    # 구조화 영업시간을 썼으면 휴무도 그 구조화 값(쉬는 요일·특별 휴무)을 원문 문장보다 앞세운다.
    visitor_rest = None if structured_used else guide_text(visitor.get("rest_days"))
    closed_text = (
        visitor_rest or _pick(facility, *_CLOSED_TEXT_KEYS) or _pick(detail, *_CLOSED_TEXT_KEYS)
    )
    if visitor_rest and visitor_source:
        origins["closed_days"] = visitor_source
    if closed_text:
        closed_parts.append(closed_text)
    elif closed_weekdays:
        names = [_WEEKDAYS[day] for day in _DISPLAY_ORDER if day in closed_weekdays]
        closed_parts.append(f"매주 {', '.join(names)}")
    elif closed_weekdays == set() and hours_lines:
        closed_parts.append("연중무휴")
    if closed_dates:
        closed_parts.append(f"{', '.join(closed_dates)} 휴무")

    return ExtractedPlaceDetails(
        opening_hours=hours_lines,
        closed_days=" · ".join(closed_parts) or None,
        phone=_phone(detail) or _clean(dto.get("phone")),
        website=_homepage(dto.get("urls"), detail),
        origins=origins,
    )


async def _fetch(
    poi: TripDayPoi, map_client: KorTravelMapClient | None, *, now: datetime
) -> ExtractedPlaceDetails:
    if not poi.feature_id:
        # 지도 feature가 없는 직접 추가 장소 — 저장 가능한 공식 출처가 없다.
        return ExtractedPlaceDetails()
    if map_client is None:
        raise PlaceDetailsUnavailable("kor-travel-map client가 없습니다.")
    try:
        dto = await map_client.get_feature(poi.feature_id)
    except KorTravelMapError as exc:
        raise PlaceDetailsUnavailable(str(exc)) from exc
    if dto is None:
        return ExtractedPlaceDetails()
    return extract_place_details(dto, today=now.astimezone(KST).date())


def _values(extracted: ExtractedPlaceDetails, now: datetime) -> dict[str, Any]:
    return {
        "status": "empty" if extracted.empty else "ready",
        "opening_hours": extracted.opening_hours,
        "closed_days": extracted.closed_days,
        "phone": extracted.phone,
        "website": extracted.website,
        "sources": extracted.sources(),
        "fetched_at": now,
    }


async def get_or_fetch_place_details(
    db: AsyncSession,
    *,
    poi: TripDayPoi,
    map_client: KorTravelMapClient | None,
    now: datetime | None = None,
) -> TripPoiPlaceDetail:
    """저장된 영업 정보, 없으면 한 번 받아 저장한 것. 출처 장애면 `PlaceDetailsUnavailable`."""
    row = await db.get(TripPoiPlaceDetail, poi.attachment_id)
    if row is not None:
        return row
    moment = now or datetime.now(UTC)
    extracted = await _fetch(poi, map_client, now=moment)
    # 같은 장소를 동시에 처음 열어도 한 행만 남는다(먼저 쓴 값이 이긴다).
    await db.execute(
        pg_insert(TripPoiPlaceDetail)
        .values(poi_id=poi.attachment_id, **_values(extracted, moment))
        .on_conflict_do_nothing(index_elements=[TripPoiPlaceDetail.poi_id])
    )
    await db.commit()
    row = await db.get(TripPoiPlaceDetail, poi.attachment_id, populate_existing=True)
    assert row is not None
    return row


async def refresh_place_details(
    db: AsyncSession,
    *,
    poi: TripDayPoi,
    map_client: KorTravelMapClient | None,
    now: datetime | None = None,
) -> TripPoiPlaceDetail:
    """출처에서 다시 받아 저장값을 덮어쓴다. 너무 잦으면 `PlaceDetailsRefreshTooSoon`."""
    moment = now or datetime.now(UTC)
    row = await db.get(TripPoiPlaceDetail, poi.attachment_id)
    if row is not None:
        elapsed = moment - row.fetched_at
        if elapsed < REFRESH_INTERVAL:
            raise PlaceDetailsRefreshTooSoon(
                max(1, int((REFRESH_INTERVAL - elapsed).total_seconds() + 0.999))
            )
    extracted = await _fetch(poi, map_client, now=moment)
    values = _values(extracted, moment)
    await db.execute(
        pg_insert(TripPoiPlaceDetail)
        .values(poi_id=poi.attachment_id, **values)
        .on_conflict_do_update(
            index_elements=[TripPoiPlaceDetail.poi_id],
            set_={**values, "updated_at": moment},
        )
    )
    await db.commit()
    refreshed = await db.get(TripPoiPlaceDetail, poi.attachment_id, populate_existing=True)
    assert refreshed is not None
    return refreshed
