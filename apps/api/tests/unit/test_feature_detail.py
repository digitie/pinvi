"""`app.services.feature_detail` 단위 테스트 — kind별 투영 + match-confidence(ADR-056)."""

from __future__ import annotations

from typing import Any

from app.schemas.feature import (
    Coord,
    EventDetailCard,
    GenericDetailCard,
    NoticeDetailCard,
    PlaceDetailCard,
    PriceDetailCard,
)
from app.services.feature_detail import (
    address_line,
    best_match_enrichment,
    build_detail_card,
    is_confident_match,
)


def _place_dto(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "feature_id": "place:1",
        "kind": "place",
        "name": "스타벅스 광안리",
        "category": "카페",
        "lon": 129.12,
        "lat": 35.15,
        "address": {"road": "부산 광안로 1", "jibun": "광안동 100"},
        "marker_color": "P-07",
        "marker_icon": "cafe",
        "urls": {"homepage": "https://sb.example"},
        "detail": {"phone": "051-000-0000", "business_hours": "09:00-22:00"},
        "status": "active",
        "updated_at": "2026-06-10T12:00:00+09:00",
    }
    base.update(over)
    return base


def test_build_place_card_projects_general_fields() -> None:
    card = build_detail_card(_place_dto())
    assert isinstance(card, PlaceDetailCard)
    assert card.kind == "place"
    assert card.name == "스타벅스 광안리"
    assert card.address_line == "부산 광안로 1"  # road 우선
    assert card.phone == "051-000-0000"
    assert card.business_hours == "09:00-22:00"
    assert card.homepage_url == "https://sb.example"
    assert card.coord is not None


def test_build_event_card() -> None:
    card = build_detail_card(
        {
            "feature_id": "event:1",
            "kind": "event",
            "name": "불꽃축제",
            "lon": 129.1,
            "lat": 35.1,
            "detail": {"start_date": "2026-10-01", "end_date": "2026-10-03", "venue": "광안리"},
        }
    )
    assert isinstance(card, EventDetailCard)
    assert card.start_date == "2026-10-01"
    assert card.end_date == "2026-10-03"
    assert card.venue == "광안리"


def test_build_notice_card() -> None:
    card = build_detail_card(
        {
            "feature_id": "notice:1",
            "kind": "notice",
            "name": "바다갈라짐 특보",
            "detail": {"content": "오후 2시 통제"},
        }
    )
    assert isinstance(card, NoticeDetailCard)
    assert card.body == "오후 2시 통제"


def test_build_price_card_projects_items() -> None:
    card = build_detail_card(
        {
            "feature_id": "price:1",
            "kind": "price",
            "name": "OO주유소",
            "detail": {"unit": "원/L", "items": [{"name": "휘발유", "price": "1650"}]},
        }
    )
    assert isinstance(card, PriceDetailCard)
    assert card.unit == "원/L"
    assert len(card.items) == 1
    assert card.items[0].name == "휘발유"
    assert card.items[0].price == "1650"


def test_weather_kind_falls_back_to_generic() -> None:
    card = build_detail_card({"feature_id": "w:1", "kind": "weather", "name": "관측소"})
    assert isinstance(card, GenericDetailCard)
    assert card.kind == "weather"


def test_unknown_kind_falls_back_to_area_generic() -> None:
    card = build_detail_card({"feature_id": "x:1", "kind": "mystery", "name": "미상"})
    assert isinstance(card, GenericDetailCard)
    assert card.kind == "area"


def test_address_line_prefers_road_then_full() -> None:
    assert address_line({"jibun": "지번", "road": "도로명"}) == "도로명"
    assert address_line({"jibun": "지번", "full": "전체"}) == "전체"
    assert address_line({"etc": "기타값"}) == "기타값"
    assert address_line(None) is None


def test_is_confident_match_name_and_distance() -> None:
    feature = Coord(lon=129.12, lat=35.15)
    near = Coord(lon=129.1201, lat=35.1501)  # ~수십 m
    far = Coord(lon=129.20, lat=35.20)  # 수 km
    assert is_confident_match("스타벅스 광안리", feature, "스타벅스 광안리점", near) is True
    assert is_confident_match("스타벅스 광안리", feature, "전혀 다른 이름", near) is False
    assert is_confident_match("스타벅스 광안리", feature, "스타벅스 광안리", far) is False


def test_short_generic_name_not_swallowed_by_longer_place() -> None:
    """리뷰 P2: 짧은 generic 이름('중앙시장')이 근처 다른 장소('중앙시장주차장')로 오귀속되지 않는다."""
    feature = Coord(lon=129.12, lat=35.15)
    near = Coord(lon=129.1215, lat=35.1512)  # ~150 m(거리 게이트는 통과)
    assert is_confident_match("중앙시장", feature, "중앙시장주차장", near) is False


def test_no_match_without_coord_anchor() -> None:
    """리뷰 P3: 좌표 앵커가 없으면 이름이 같아도 매칭하지 않는다(다른 지역 동명 장소 오귀속 차단)."""
    other = Coord(lon=126.98, lat=37.57)  # 서울
    assert is_confident_match("중앙식당", None, "중앙식당", other) is False
    assert is_confident_match("중앙식당", other, "중앙식당", None) is False


def test_best_match_enrichment_matched_and_unmatched() -> None:
    docs = [
        {
            "id": "k1",
            "place_name": "스타벅스 광안리점",
            "address_name": "부산 수영구",
            "x": "129.1201",
            "y": "35.1501",
            "phone": "051-111-2222",
            "place_url": "http://place.map.kakao.com/k1",
        }
    ]
    matched = best_match_enrichment(
        "kakao",
        feature_name="스타벅스 광안리",
        feature_coord=Coord(lon=129.12, lat=35.15),
        documents=docs,
    )
    assert matched.matched is True
    assert matched.phone == "051-111-2222"
    assert matched.provider_url == "http://place.map.kakao.com/k1"

    # 이름이 전혀 다르면 confident match 없음 → matched=False(오귀속 방지).
    no_match = best_match_enrichment(
        "kakao",
        feature_name="완전히 다른 장소",
        feature_coord=Coord(lon=129.12, lat=35.15),
        documents=docs,
    )
    assert no_match.matched is False
    assert no_match.phone is None
