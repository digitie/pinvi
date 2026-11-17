"""추천 여행 주변 정보 — 기간 중 축제·행사와 주변 큐레이션 장소.

데이터는 kor-travel-map 공개 표면에서 읽는다(PinVi DB에 복사하지 않는다).

- 축제: `GET /v1/public/festivals/monthly` — plan POI 주소의 시도 코드(최대 2개)로 거르고,
  기간 창과 겹치는 행사만 남긴다. 시도를 알 수 없거나 3개 이상이면 전국에서 고른다.
  POI 좌표가 있으면 그 bbox(약 30km 여유)를 함께 보내 바쁜 달에도 근처 축제가 첫 페이지 밖으로
  밀리지 않게 하고, `next_cursor`를 최대 3페이지까지 따라간다. bbox query를 모르는 옛 Map은
  그 query를 조용히 버리므로 응답 좌표로 한 번 더 거른다(배포 순서와 무관하게 결과가 같은 범위다).
- 큐레이션: `GET /v1/curations` — plan POI 좌표 bbox(약 5km 여유) 안의 공개 큐레이션
  Feature. plan에 이미 있는 Feature는 뺀다.

두 구역 모두 POI 좌표가 있으면 가장 가까운 plan 장소까지의 거리 순으로 정렬한다.
Map 장애·예산 초과는 그 구역만 `unavailable`로 표시하고 나머지는 그대로 돌려준다.
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapClient, KorTravelMapError
from app.models.curated_plan import CuratedPlanPoi
from app.schemas.notice import (
    NoticePlanCuratedPick,
    NoticePlanEventPick,
    NoticePlanHighlightsResponse,
    NoticePlanHighlightTheme,
)
from app.schemas.public import PublicFestivalView
from app.services.admin_pois import extract_feature_coord
from app.services.notice_plan import get_published_plan, list_plan_pois

logger = logging.getLogger(__name__)

_SEOUL = ZoneInfo("Asia/Seoul")

UPCOMING_WINDOW_DAYS = 30
MAX_EVENT_MONTHS = 2
MAX_EVENT_SIDO = 2
FESTIVAL_PAGE_SIZE = 50
# (월, 시도) 조회 하나가 따라가는 최대 페이지 수 — bbox로 좁힌 근처 축제는 보통 1페이지다.
MAX_FESTIVAL_PAGES = 3
# 축제 bbox 여유 — plan 장소에서 차로 갈 만한 거리(약 30km).
EVENT_BBOX_PAD_DEGREES = 0.3
EVENT_LIMIT = 10
CURATED_PAGE_SIZE = 60
CURATED_LIMIT = 8
MAX_THEMES_PER_PICK = 3
BBOX_PAD_DEGREES = 0.05
SUMMARY_MAX_CHARS = 160
# 한 요청이 Map에 쓰는 총 시간. 넘으면 해당 구역만 unavailable로 돌려준다.
HIGHLIGHTS_BUDGET_SECONDS = 8.0

Section = Literal["curated", "events"]


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _CurationFeature(_Lenient):
    feature_id: str
    name: str
    kind: str
    category: str
    lon: float | None = None
    lat: float | None = None
    address: dict[str, Any] = {}


class _CurationMembership(_Lenient):
    theme_name: str
    title: str
    edition_key: str
    item_summary: str | None = None
    source_url: str | None = None
    status: str


class _CurationGroup(_Lenient):
    feature: _CurationFeature
    curations: list[_CurationMembership]


@dataclass(frozen=True)
class EventWindow:
    start: date
    end: date
    basis: Literal["plan", "upcoming"]


def seoul_today() -> date:
    return datetime.now(_SEOUL).date()


def plan_event_window(starts_on: date | None, ends_on: date | None, today: date) -> EventWindow:
    """plan 기간이 아직 끝나지 않았으면 plan 기간, 아니면 오늘부터 30일."""
    if starts_on is not None and ends_on is not None and ends_on >= today:
        return EventWindow(starts_on, ends_on, "plan")
    return EventWindow(today, today + timedelta(days=UPCOMING_WINDOW_DAYS), "upcoming")


def window_months(window: EventWindow, today: date) -> list[tuple[int, int]]:
    """조회할 (년, 월) — 이미 지난 날은 빼고 최대 2개월."""
    cursor = max(window.start, today).replace(day=1)
    months: list[tuple[int, int]] = []
    while cursor <= window.end and len(months) < MAX_EVENT_MONTHS:
        months.append((cursor.year, cursor.month))
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return months


def _digits(value: object, length: int) -> str | None:
    if isinstance(value, str) and len(value) >= length and value[:length].isdigit():
        return value[:length]
    return None


def snapshot_sido_code(snapshot: Mapping[str, Any]) -> str | None:
    """POI snapshot(top-level 또는 Map `address`)의 시도 코드 — 시군구·법정동 코드 앞자리도 쓴다."""
    address = snapshot.get("address")
    sources: list[Mapping[str, Any]] = [snapshot]
    if isinstance(address, Mapping):
        sources.insert(0, cast(Mapping[str, Any], address))
    for source in sources:
        for key in ("sido_code", "sigungu_code", "bjd_code", "legal_dong_code"):
            code = _digits(source.get(key), 2)
            if code is not None:
                return code
    return None


def _address_label(address: Mapping[str, Any]) -> str | None:
    for key in ("road", "road_address", "legal", "jibun_address", "admin"):
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _clip(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = " ".join(text.split())
    if not normalized:
        return None
    if len(normalized) <= SUMMARY_MAX_CHARS:
        return normalized
    return normalized[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_distance_m(
    lon: float | None, lat: float | None, anchors: Sequence[tuple[float, float]]
) -> float | None:
    if lon is None or lat is None or not anchors:
        return None
    return round(min(haversine_m(lon, lat, a_lon, a_lat) for a_lon, a_lat in anchors), 1)


def _distance_key(distance: float | None) -> float:
    return distance if distance is not None else math.inf


def _event_overlaps(event: PublicFestivalView, start: date, end: date) -> bool:
    if event.event_status == "ended":
        return False
    first = event.event_start_date
    last = event.event_end_date or first
    if first is None or last is None:
        # 날짜가 없으면 Map이 진행/예정으로 판정한 것만 믿는다.
        return event.event_status in ("ongoing", "scheduled")
    return first <= end and last >= start


def select_events(
    raw_items: Sequence[object],
    *,
    window: EventWindow,
    today: date,
    anchors: Sequence[tuple[float, float]],
) -> list[NoticePlanEventPick]:
    start = max(window.start, today)
    seen: set[str] = set()
    picks: list[NoticePlanEventPick] = []
    for raw in raw_items:
        try:
            event = PublicFestivalView.model_validate(raw)
        except ValidationError:
            logger.warning("notice_plan_highlights.festival_item_invalid")
            continue
        if event.feature_id in seen or not _event_overlaps(event, start, window.end):
            continue
        seen.add(event.feature_id)
        address = event.road_address or event.jibun_address or _address_label(event.address)
        picks.append(
            NoticePlanEventPick(
                feature_id=event.feature_id,
                name=event.festival_name,
                start_date=event.event_start_date,
                end_date=event.event_end_date,
                status=event.event_status,
                venue_name=event.venue_name,
                address=address,
                summary=_clip(event.festival_content),
                homepage_url=event.homepage_url,
                lon=event.lon,
                lat=event.lat,
                marker_color=event.marker_color,
                marker_icon=event.marker_icon,
                distance_m=nearest_distance_m(event.lon, event.lat, anchors),
            )
        )
    picks.sort(
        key=lambda p: (
            _distance_key(p.distance_m),
            p.start_date or date.max,
            p.name,
        )
    )
    return picks[:EVENT_LIMIT]


def select_curated(
    raw_items: Sequence[object],
    *,
    exclude_feature_ids: set[str],
    anchors: Sequence[tuple[float, float]],
) -> list[NoticePlanCuratedPick]:
    picks: list[NoticePlanCuratedPick] = []
    seen: set[str] = set()
    for raw in raw_items:
        try:
            group = _CurationGroup.model_validate(raw)
        except ValidationError:
            logger.warning("notice_plan_highlights.curation_item_invalid")
            continue
        feature = group.feature
        if feature.feature_id in exclude_feature_ids or feature.feature_id in seen:
            continue
        themes: list[NoticePlanHighlightTheme] = []
        for membership in group.curations:
            if membership.status != "included":
                continue
            themes.append(
                NoticePlanHighlightTheme(
                    theme_name=membership.theme_name,
                    collection_title=membership.title,
                    edition_key=membership.edition_key,
                    summary=_clip(membership.item_summary),
                    source_url=membership.source_url,
                )
            )
        if not themes:
            continue
        seen.add(feature.feature_id)
        picks.append(
            NoticePlanCuratedPick(
                feature_id=feature.feature_id,
                name=feature.name,
                kind=feature.kind,
                category=feature.category,
                lon=feature.lon,
                lat=feature.lat,
                address=_address_label(feature.address),
                distance_m=nearest_distance_m(feature.lon, feature.lat, anchors),
                themes=themes[:MAX_THEMES_PER_PICK],
            )
        )
    picks.sort(key=lambda p: (_distance_key(p.distance_m), -len(p.themes), p.name))
    return picks[:CURATED_LIMIT]


Bbox = tuple[float, float, float, float]


def _bbox(anchors: Sequence[tuple[float, float]], pad: float = BBOX_PAD_DEGREES) -> Bbox:
    lons = [lon for lon, _ in anchors]
    lats = [lat for _, lat in anchors]
    return (
        max(-180.0, min(lons) - pad),
        max(-90.0, min(lats) - pad),
        min(180.0, max(lons) + pad),
        min(90.0, max(lats) + pad),
    )


def _inside(raw: object, bbox: Bbox) -> bool:
    """Map 축제 item 좌표가 bbox 안인지 — 좌표 없는 item은 bbox 조회에서 빠진다(Map과 같다)."""
    if not isinstance(raw, Mapping):
        return False
    lon, lat = raw.get("lon"), raw.get("lat")
    if not isinstance(lon, int | float) or not isinstance(lat, int | float):
        return False
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _plan_anchors(pois: Sequence[CuratedPlanPoi]) -> list[tuple[float, float]]:
    anchors: list[tuple[float, float]] = []
    for poi in pois:
        snapshot = poi.feature_snapshot if isinstance(poi.feature_snapshot, dict) else {}
        lon, lat = extract_feature_coord(snapshot)
        if lon is not None and lat is not None:
            anchors.append((lon, lat))
    return anchors


def _plan_sido_codes(pois: Sequence[CuratedPlanPoi]) -> list[str]:
    codes: list[str] = []
    for poi in pois:
        snapshot = poi.feature_snapshot if isinstance(poi.feature_snapshot, dict) else {}
        code = snapshot_sido_code(snapshot)
        if code is not None and code not in codes:
            codes.append(code)
    return codes


async def _fetch_festival_items(
    client: KorTravelMapClient,
    *,
    months: Sequence[tuple[int, int]],
    sido_codes: Sequence[str | None],
    bbox: Bbox | None,
) -> list[object]:
    # 축제 조회는 client의 축제 자리(4)를 다른 사용자와 나눠 쓴다 — 순차로 보내 자리를 하나만 쓴다.
    items: list[object] = []
    min_lon, min_lat, max_lon, max_lat = bbox if bbox is not None else (None, None, None, None)
    for year, month in months:
        for sido_code in sido_codes:
            cursor: str | None = None
            for _ in range(MAX_FESTIVAL_PAGES):
                page = await client.public_festivals_monthly(
                    year=year,
                    month=month,
                    sido_code=sido_code,
                    page_size=FESTIVAL_PAGE_SIZE,
                    cursor=cursor,
                    include_months=False,
                    min_lon=min_lon,
                    min_lat=min_lat,
                    max_lon=max_lon,
                    max_lat=max_lat,
                )
                raw = page.get("items")
                if isinstance(raw, list):
                    items.extend(item for item in raw if bbox is None or _inside(item, bbox))
                next_cursor = page.get("next_cursor")
                if not isinstance(next_cursor, str) or not next_cursor:
                    break
                cursor = next_cursor
    return items


async def _guard[T](
    section: Section, coro: Coroutine[Any, Any, T], unavailable: list[Section]
) -> T | None:
    """구역 하나의 실패를 그 구역에 가둔다 — 다른 구역 결과는 그대로 쓴다."""
    try:
        return await coro
    except (KorTravelMapError, TimeoutError) as exc:
        logger.warning(
            "notice_plan_highlights.section_unavailable section=%s error=%s",
            section,
            type(exc).__name__,
        )
        unavailable.append(section)
        return None


async def build_plan_highlights(
    db: AsyncSession,
    *,
    notice_plan_id: uuid.UUID,
    client: KorTravelMapClient | None,
    today: date | None = None,
) -> NoticePlanHighlightsResponse:
    """추천 여행 1건의 주변 축제·큐레이션. plan이 없거나 비공개면 NoticePlanNotFoundError."""
    plan = await get_published_plan(db, notice_plan_id=notice_plan_id)
    pois = await list_plan_pois(db, notice_plan_id=notice_plan_id)
    current = today or seoul_today()
    window = plan_event_window(plan.starts_on, plan.ends_on, current)
    months = window_months(window, current)
    anchors = _plan_anchors(pois)
    sido_codes = _plan_sido_codes(pois)
    scoped = 1 <= len(sido_codes) <= MAX_EVENT_SIDO
    region_scope: Literal["sido", "nationwide"] = "sido" if scoped else "nationwide"
    exclude = {poi.feature_id for poi in pois if poi.feature_id}

    unavailable: list[Section] = []
    curated: list[NoticePlanCuratedPick] = []
    events: list[NoticePlanEventPick] = []
    if client is None:
        unavailable = ["curated", "events"]
    else:

        async def curated_section() -> list[NoticePlanCuratedPick]:
            if not anchors:
                return []
            min_lon, min_lat, max_lon, max_lat = _bbox(anchors)
            async with asyncio.timeout(HIGHLIGHTS_BUDGET_SECONDS):
                page = await client.public_curation_groups(
                    min_lon=min_lon,
                    min_lat=min_lat,
                    max_lon=max_lon,
                    max_lat=max_lat,
                    page_size=CURATED_PAGE_SIZE,
                )
            raw = page.get("items")
            return select_curated(
                raw if isinstance(raw, list) else [],
                exclude_feature_ids=exclude,
                anchors=anchors,
            )

        async def events_section() -> list[NoticePlanEventPick]:
            if not months:
                return []
            async with asyncio.timeout(HIGHLIGHTS_BUDGET_SECONDS):
                raw = await _fetch_festival_items(
                    client,
                    months=months,
                    sido_codes=list(sido_codes) if scoped else [None],
                    bbox=_bbox(anchors, EVENT_BBOX_PAD_DEGREES) if anchors else None,
                )
            return select_events(raw, window=window, today=current, anchors=anchors)

        curated_result, events_result = await asyncio.gather(
            _guard("curated", curated_section(), unavailable),
            _guard("events", events_section(), unavailable),
        )
        curated = curated_result or []
        events = events_result or []

    return NoticePlanHighlightsResponse(
        notice_plan_id=plan.curated_plan_id,
        window_start=window.start,
        window_end=window.end,
        window_basis=window.basis,
        region_scope=region_scope,
        curated=curated,
        events=events,
        unavailable=sorted(set(unavailable)),
    )
