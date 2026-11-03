"""Feature detail-card 투영 + 옵트인 외부 enrichment (ADR-056, T-304).

kor_travel_map 원본 dto(불투명 detail/urls/address dict)를 kind별 detail-card로 서버에서 투영하고,
옵트인 `?providers=kakao,naver`이면 Kakao/Naver Local(표시 전용)로 라이브 enrichment한다. enrichment는
name+coord fuzzy match-confidence 가드로 오귀속을 막고, provider당 실패는 degrade로 처리한다.
"""

from __future__ import annotations

import math
import re
from typing import Any, Protocol

from app.schemas.feature import (
    Coord,
    EventDetailCard,
    ExternalEnrichment,
    ExternalRefProvider,
    FeatureDetailCard,
    GenericDetailCard,
    NoticeDetailCard,
    PlaceDetailCard,
    PriceDetailCard,
    PriceItem,
)
from app.services.category_labels import EMPTY_CATEGORY_LABELS, CategoryLabels
from app.services.place_search import kakao_document_to_result, naver_item_to_result

# name 유사도/거리 임계 — 둘 다 만족해야 confident match(오귀속 방지, ADR-056).
_NAME_SIM_THRESHOLD = 0.6
_MATCH_DISTANCE_M = 300.0
# 포함 관계를 1.0으로 볼 최소 길이 비율(짧은 이름/긴 이름). '중앙시장' ⊂ '중앙시장주차장'(0.57)처럼
# 짧은 generic 이름이 다른 장소에 삼켜지는 오귀속을 막고, '광안리' vs '광안리점' 같은 지점 접미사만 통과.
_CONTAINMENT_MIN_RATIO = 0.7


class _LatLon(Protocol):
    """lon/lat를 가진 좌표의 구조적 타입(Coord/PlaceCoord 공통)."""

    lon: float
    lat: float


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _pick(source: Any, *keys: str) -> str | None:
    if not isinstance(source, dict):
        return None
    for key in keys:
        value = _clean(source.get(key))
        if value:
            return value
    return None


def address_line(address: Any) -> str | None:
    """kor_travel_map 구조화 주소 dict → 한 줄 표시 문자열(방어적 키 추출).

    Map 주소는 `{road, legal, admin, sido_name, sigungu_name, zipcode, *_code ...}`다. 도로명이 없는
    feature(국가유산 등)는 `legal`(법정동 주소)을, 그것도 없으면 `시도 시군구 읍면동`을 만든다.
    예전에는 dict의 첫 문자열 값(`admin` = "김삿갓면")으로 떨어져 상세 카드 주소가 읍면 이름뿐이었다
    (2026-11-02 prod e2e).
    """
    if not isinstance(address, dict):
        return None
    picked = _pick(address, "road", "full", "legal", "jibun", "name")
    if picked:
        return picked
    admin = _clean(address.get("admin"))
    parts: list[str] = []
    for region in (_clean(address.get("sido_name")), _clean(address.get("sigungu_name"))):
        # 일부 provider(KHOA 해수욕장 등)는 `admin`에 이미 "부산광역시 해운대구" 같은 전체 이름을 둔다.
        if region and not (admin and region in admin):
            parts.append(region)
    if admin:
        parts.append(admin)
    composed = " ".join(parts)
    if composed:
        return composed
    for key, value in address.items():
        # 코드·우편번호 값은 사람이 읽는 주소가 아니다.
        if key.endswith(("_code", "_no")) or key == "zipcode":
            continue
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return None


def _phone(detail: Any) -> str | None:
    """Map place detail의 전화 — `phones[]`(정본) → `facility_info.tel` → 예전 평면 키."""
    if not isinstance(detail, dict):
        return None
    phones = detail.get("phones")
    if isinstance(phones, list):
        for phone in phones:
            cleaned = _clean(phone)
            if cleaned:
                return cleaned
    facility = detail.get("facility_info")
    return _pick(facility, "tel", "phone") or _pick(detail, "phone", "tel", "telephone")


def _http_url(value: str | None) -> str | None:
    if value and value.lower().startswith(("http://", "https://")):
        return value
    return None


def _first_http(source: Any, *keys: str) -> str | None:
    if not isinstance(source, dict):
        return None
    for key in keys:
        url = _http_url(_clean(source.get(key)))
        if url:
            return url
    return None


def _homepage(urls: Any, detail: Any) -> str | None:
    """`urls`(정본) → place detail `facility_info.url`(반려동반여행 등 출처가 주는 홈페이지).

    http(s)가 아닌 값은 키마다 건너뛴다 — 앞 키의 잘못된 값이 뒤 키의 정상 URL을 가리지 않게.
    """
    facility = detail.get("facility_info") if isinstance(detail, dict) else None
    return _first_http(urls, "homepage", "website", "url", "home") or _first_http(
        facility, "url", "homepage"
    )


def _coord(dto: dict[str, Any]) -> Coord | None:
    lon, lat = dto.get("lon"), dto.get("lat")
    if lon is None or lat is None:
        return None
    try:
        return Coord(lon=float(lon), lat=float(lat))
    except (TypeError, ValueError):
        return None


def _price_items(detail: Any) -> list[PriceItem]:
    if not isinstance(detail, dict):
        return []
    raw = detail.get("items") or detail.get("prices")
    if not isinstance(raw, list):
        return []
    items: list[PriceItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = _pick(entry, "name", "item", "label")
        if name is None:
            continue
        price = _pick(entry, "price", "amount", "value")
        items.append(PriceItem(name=name, price=price))
    return items


def build_detail_card(
    dto: dict[str, Any], labels: CategoryLabels = EMPTY_CATEGORY_LABELS
) -> FeatureDetailCard:
    """원본 feature dto → kind별 detail-card(일반 사용자 노출 필드만).

    `status`는 채우지 않는다 — Map 3축 feature state cutover(`1f2bdc3a feat(api): complete
    feature state cutover`)로 `FeatureDetailResponse`에서 사라졌고 대체 필드가 없다(state
    축은 user profile 비노출). `DetailCardBase`에도 그 필드가 없다(T-VN-42).
    """
    kind = str(dto.get("kind") or "")
    detail = dto.get("detail")
    urls = dto.get("urls")
    common: dict[str, Any] = {
        "feature_id": str(dto["feature_id"]),
        "name": dto.get("name") or dto.get("title") or "",
        "coord": _coord(dto),
        "category": _clean(dto.get("category")),
        "category_label": labels.label(_clean(dto.get("category"))),
        "address_line": address_line(dto.get("address")),
        "marker_color": dto.get("marker_color") or "P-13",
        "marker_icon": dto.get("marker_icon") or "marker",
        "homepage_url": _homepage(urls, detail),
    }

    if kind == "place":
        return PlaceDetailCard(
            **common,
            phone=_phone(detail),
            business_hours=_pick(detail, "business_hours", "hours", "open_hours", "opening_hours"),
        )
    if kind == "event":
        return EventDetailCard(
            **common,
            start_date=_pick(detail, "starts_on", "start_date", "begin_date", "period_start", "from"),
            end_date=_pick(detail, "ends_on", "end_date", "close_date", "period_end", "to"),
            venue=_pick(detail, "venue_name", "venue", "place", "location"),
        )
    if kind == "notice":
        return NoticeDetailCard(
            **common,
            body=_pick(detail, "body", "content", "message", "description"),
            start_date=_pick(detail, "start_date", "begin_date", "period_start", "from"),
            end_date=_pick(detail, "end_date", "close_date", "period_end", "to"),
        )
    if kind == "price":
        return PriceDetailCard(
            **common,
            unit=_pick(detail, "unit", "price_unit"),
            items=_price_items(detail),
        )
    # weather/route/area + 그 외 → generic fallback(공통 필드만).
    generic_kind = kind if kind in ("weather", "route", "area") else "area"
    return GenericDetailCard(**common, kind=generic_kind)


# ── 외부 enrichment (옵트인, display-only) ────────────────────────────────────

_NON_WORD_RE = re.compile(r"[^0-9A-Za-z가-힣]+")


def _normalize_name(name: str) -> str:
    return _NON_WORD_RE.sub("", name).lower()


def _bigrams(text: str) -> set[str]:
    if len(text) < 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _name_similarity(a: str, b: str) -> float:
    """이름 유사도(0..1) — 공백/기호 제거 후 포함 관계(지점 접미사 등)면 1.0, 아니면 문자 bigram Jaccard.

    한국어는 띄어쓰기가 없어 토큰 Jaccard로는 '광안리' vs '광안리점'을 못 잡는다. 외부 provider의
    상호는 보통 feature명 + 지점 접미사('점'/'지점' 등)이므로 정규화 후 포함 관계를 강한 신호로 본다.
    """
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return 0.0
    # 포함 관계는 짧은 쪽이 긴 쪽의 큰 비율(≥0.7)일 때만 1.0 — 지점 접미사('점' 등)는 통과하고
    # 짧은 generic 이름이 다른 상호에 삼켜지는 경우는 bigram으로 떨어뜨린다.
    if na in nb or nb in na:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        if len(shorter) / len(longer) >= _CONTAINMENT_MIN_RATIO:
            return 1.0
    ba, bb = _bigrams(na), _bigrams(nb)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def _haversine_m(a: _LatLon, b: _LatLon) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dphi = math.radians(b.lat - a.lat)
    dlmb = math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def is_confident_match(
    feature_name: str, feature_coord: _LatLon | None, cand_name: str, cand_coord: _LatLon | None
) -> bool:
    """name 유사도 + 좌표 근접이 모두 임계를 넘어야 confident(오귀속 방지, ADR-056).

    좌표 앵커(양쪽 좌표)가 없으면 같은 이름의 다른 지역 장소를 구분할 수 없으므로 매칭하지 않는다
    (이름만으로 전화/URL을 붙이는 오귀속 차단).
    """
    if _name_similarity(feature_name, cand_name) < _NAME_SIM_THRESHOLD:
        return False
    if feature_coord is None or cand_coord is None:
        return False
    return _haversine_m(feature_coord, cand_coord) <= _MATCH_DISTANCE_M


def _enrichment_from_result(
    provider: ExternalRefProvider, result: Any, matched: bool
) -> ExternalEnrichment:
    return ExternalEnrichment(
        provider=provider,
        matched=matched,
        name=result.name if matched else None,
        address=(result.road_address or result.address) if matched else None,
        phone=result.phone if matched else None,
        provider_url=result.provider_url if matched else None,
        external_id=result.external_id if matched else None,
    )


def best_match_enrichment(
    provider: ExternalRefProvider,
    *,
    feature_name: str,
    feature_coord: Coord | None,
    documents: list[dict[str, Any]],
) -> ExternalEnrichment:
    """provider 검색 결과 중 confident match를 골라 enrichment 1행을 만든다. 없으면 matched=False."""
    mapper = kakao_document_to_result if provider == "kakao" else naver_item_to_result
    for raw in documents:
        if not isinstance(raw, dict):
            continue
        result = mapper(raw)
        if result is None:
            continue
        if is_confident_match(feature_name, feature_coord, result.name, result.coord):
            return _enrichment_from_result(provider, result, matched=True)
    return ExternalEnrichment(provider=provider, matched=False)
