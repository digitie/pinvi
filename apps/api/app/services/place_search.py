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
from app.services.category_labels import EMPTY_CATEGORY_LABELS, CategoryLabels

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


def feature_item_to_result(
    item: dict[str, Any], labels: CategoryLabels = EMPTY_CATEGORY_LABELS
) -> PlaceSearchResult | None:
    """kor-travel-map feature item → PlaceSearchResult(source=feature).

    `category`는 Map 코드 그대로(마커·필터 계약), 화면에 보일 이름은 `category_label`이다.
    """
    name = _clean(item.get("name")) or _clean(item.get("title"))
    feature_id = _clean(item.get("feature_id"))
    if name is None and feature_id is None:
        return None
    category = _clean(item.get("category"))
    return PlaceSearchResult(
        source="feature",
        name=name or (feature_id or ""),
        coord=_coord(item.get("lon"), item.get("lat")),
        feature_id=feature_id,
        address=_clean(item.get("address")),
        category=category,
        category_label=labels.label(category),
        marker_color=_clean(item.get("marker_color")),
        marker_icon=_clean(item.get("marker_icon")),
    )


def region_biased_items(
    items: list[Any],
    *,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """지역 편향 정렬 — 전국 검색 결과 중 bbox 안의 장소를 앞으로(최대 `limit`의 절반), 나머지는 원래 순서.

    bbox는 **순서만** 바꾼다. 2026-11-02 소유자 결정("하회마을"에서 서울 식당 셋이 안동 마을보다 먼저
    나왔다). 지역 안 몫을 절반으로 묶는 이유: Map 이름 검색은 느슨한 trigram이라 지역 안의 비슷한
    이름(예: 서울에서 "부산역" → "부산식당"…)이 목록을 다 차지하면 지역 밖의 정확한 장소가 사라지고,
    내부 결과가 많아 Kakao/Naver 보강도 생략된다(#615 리뷰).
    """
    dicts = [item for item in items if isinstance(item, dict)]
    if bbox is None:
        return dicts[:limit]
    lng_min, lat_min, lng_max, lat_max = bbox

    def inside(item: dict[str, Any]) -> bool:
        lon, lat = _float(item.get("lon")), _float(item.get("lat"))
        return (
            lon is not None
            and lat is not None
            and lng_min <= lon <= lng_max
            and lat_min <= lat <= lat_max
        )

    # 절반(내림) — limit 1이면 편향하지 않는다(유일한 자리를 지역 안 퍼지 매칭에 내주지 않게).
    regional_cap = limit // 2
    if regional_cap == 0:
        return dicts[:limit]
    regional = [item for item in dicts if inside(item)][:regional_cap]
    picked = {id(item) for item in regional}
    rest = [item for item in dicts if id(item) not in picked]
    return [*regional, *rest][:limit]


# geo v2 `match_kind` 중 도로명 주소 후보. 나머지(parcel=지번, region 등)는 `address`에 둔다.
_ROAD_MATCH_KINDS = frozenset({"road"})


def address_candidate_to_result(cand: dict[str, Any]) -> PlaceSearchResult | None:
    """kor-travel-geo v2 `/v2/search` 후보 → PlaceSearchResult(source=address).

    v2 후보는 중첩 셰입이다: `{match_kind, address: {full, ...}, point: {lon, lat}, region, ...}`
    (`docs/integrations/kor-travel-geo.md` §3.2). 예전 매퍼는 평면 `road_address`/`lon`/`lat`를
    읽어 **모든 주소 후보를 버렸다**(2026-11-02 prod e2e — 통합 검색에 주소 결과가 한 건도 없었다).
    `address.full`이 없는 후보(국가지점번호 `sppn` 등)는 이름을 만들 수 없어 버린다.
    """
    address = cand.get("address")
    full = _clean(address.get("full")) if isinstance(address, dict) else None
    if full is None:
        return None
    point = cand.get("point")
    coord = _coord(point.get("lon"), point.get("lat")) if isinstance(point, dict) else None
    is_road = cand.get("match_kind") in _ROAD_MATCH_KINDS
    return PlaceSearchResult(
        source="address",
        name=full,
        coord=coord,
        address=None if is_road else full,
        road_address=full if is_road else None,
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
