"""외부/내부 검색 결과 → `PlaceSearchResult` 순수 매핑 — `docs/integrations/kakao-naver-local.md`.

HTTP 없이 단위 테스트 가능한 순수 변환만 둔다(HTML strip, Naver 좌표 스케일 /1e7, external_id
정규화). provider 파생 콘텐츠는 여기서 표시 필드로만 매핑하고 저장하지 않는다(ADR-054 §7).
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.schemas.search import PlaceCoord, PlaceSearchResult

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def strip_html(value: str) -> str:
    """Naver `title`의 `<b>` 등 태그 제거 + HTML 엔티티 언이스케이프."""
    return html.unescape(_TAG_RE.sub("", value)).strip()


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coord(lon: Any, lat: Any) -> PlaceCoord | None:
    lon_f, lat_f = _float(lon), _float(lat)
    if lon_f is None or lat_f is None:
        return None
    return PlaceCoord(lon=lon_f, lat=lat_f)


def normalize_link(link: str) -> str:
    """Naver Local의 안정적 장소 id 부재를 보완 — link를 정규화해 external_id로 쓴다(§7 dedup 키)."""
    parts = urlsplit(link.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    return urlunsplit((scheme, netloc, parts.path.rstrip("/"), parts.query, ""))


def kakao_document_to_result(doc: dict[str, Any]) -> PlaceSearchResult | None:
    """Kakao keyword document → PlaceSearchResult. 좌표 파싱 실패 항목도 리스트엔 남긴다."""
    name = _clean(doc.get("place_name"))
    if name is None:
        return None
    external_id = _clean(doc.get("id"))
    place_url = _clean(doc.get("place_url"))
    return PlaceSearchResult(
        source="kakao",
        name=name,
        coord=_coord(doc.get("x"), doc.get("y")),
        external_id=external_id,
        address=_clean(doc.get("address_name")),
        road_address=_clean(doc.get("road_address_name")),
        category=_clean(doc.get("category_name")) or _clean(doc.get("category_group_name")),
        provider_url=place_url,
        phone=_clean(doc.get("phone")),
    )


def naver_item_to_result(item: dict[str, Any]) -> PlaceSearchResult | None:
    """Naver Local item → PlaceSearchResult. title HTML strip + mapx/mapy /1e7 + link→external_id."""
    raw_title = _clean(item.get("title"))
    if raw_title is None:
        return None
    name = strip_html(raw_title)
    if not name:
        return None
    # mapx/mapy는 WGS84 x 10^7 정수. /1e7 후 (lon, lat).
    mx, my = _float(item.get("mapx")), _float(item.get("mapy"))
    coord = PlaceCoord(lon=mx / 1e7, lat=my / 1e7) if mx is not None and my is not None else None
    link = _clean(item.get("link"))
    external_id = normalize_link(link) if link else None
    return PlaceSearchResult(
        source="naver",
        name=name,
        coord=coord,
        external_id=external_id,
        address=_clean(item.get("address")),
        road_address=_clean(item.get("roadAddress")),
        category=_clean(item.get("category")),
        provider_url=link,
        phone=_clean(item.get("telephone")),
    )


def feature_item_to_result(item: dict[str, Any]) -> PlaceSearchResult | None:
    """kor-travel-map feature item → PlaceSearchResult(source=feature)."""
    name = _clean(item.get("name")) or _clean(item.get("title"))
    feature_id = _clean(item.get("feature_id"))
    if name is None and feature_id is None:
        return None
    return PlaceSearchResult(
        source="feature",
        name=name or (feature_id or ""),
        coord=_coord(item.get("lon"), item.get("lat")),
        feature_id=feature_id,
        address=_clean(item.get("address")),
        category=_clean(item.get("category")),
        marker_color=_clean(item.get("marker_color")),
        marker_icon=_clean(item.get("marker_icon")),
    )


def address_candidate_to_result(cand: dict[str, Any]) -> PlaceSearchResult | None:
    """kor-travel-geo address candidate → PlaceSearchResult(source=address)."""
    name = (
        _clean(cand.get("road_address")) or _clean(cand.get("address")) or _clean(cand.get("name"))
    )
    if name is None:
        return None
    return PlaceSearchResult(
        source="address",
        name=name,
        coord=_coord(cand.get("lon"), cand.get("lat")),
        address=_clean(cand.get("address")),
        road_address=_clean(cand.get("road_address")),
    )


def my_poi_to_result(poi: dict[str, Any]) -> PlaceSearchResult:
    """Pinvi 내 POI dict → PlaceSearchResult(source=my_poi)."""
    return PlaceSearchResult(
        source="my_poi",
        name=_clean(poi.get("name")) or _clean(poi.get("user_note")) or "(이름 없음)",
        coord=_coord(poi.get("lon"), poi.get("lat")),
        feature_id=_clean(poi.get("feature_id")),
        poi_id=_clean(poi.get("poi_id")),
        trip_id=_clean(poi.get("trip_id")),
        trip_title=_clean(poi.get("trip_title")),
    )
