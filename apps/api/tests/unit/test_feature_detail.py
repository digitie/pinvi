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
from app.services.category_labels import build_category_labels
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
    # Map 3축 cutover(`1f2bdc3a`)로 user 표면에 `status`가 없다 → 공개 계약에도 키가 없다(T-VN-42).
    assert "status" not in card.model_dump()


def test_build_card_never_leaks_upstream_status() -> None:
    """dto에 `status`가 남아 있어도 detail-card 계약으로 새어 나오면 안 된다.

    Map 3축 feature state cutover(`1f2bdc3a feat(api): complete feature state cutover`)로
    `FeatureDetailResponse`에서 `status`가 삭제됐고 **대체 필드가 없다**. T-VN-42에서 공개
    스키마의 필드까지 제거했다.

    이 테스트가 덮는 범위를 정확히 적어 둔다: 필드를 다시 선언하고 값까지 실어 보내는 조합을
    **wire 표현**에서 막는다(선언만 되돌리는 경우는 `test_feature_schemas.py`의 필드 집합 등호
    게이트가 먼저 red다). 반대로 투영만 되돌리는 경우(`"status": _clean(dto.get("status"))`)는
    여기서 잡히지 않는다 — 필드가 선언돼 있지 않으면 pydantic 기본 `extra="ignore"`가 값을
    버리므로 애초에 새어 나갈 값이 없다. upstream 오염을 계속 주입해 두는 이유는 두 조건이 함께
    되살아날 때 조용히 통과하지 않게 하기 위해서다.
    """
    for kind in ("place", "event", "notice", "price", "area"):
        card = build_detail_card(_place_dto(kind=kind, status="active"))
        assert "status" not in card.model_dump(), kind


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


# ── 2026-11-02 prod e2e: Map place detail 실응답 키(`phones[]`·`facility_info`·`legal`) ──────────


def _map_place_dto(**over: Any) -> dict[str, Any]:
    """Map `/v1/features/{id}` 실응답 형태(영월 고씨굴 주차장·안동하회마을에서 발췌)."""
    base: dict[str, Any] = {
        "feature_id": "01a163b0-b587-7d4f-a8f5-489dee7e5699",
        "kind": "place",
        "name": "고씨굴",
        "category": "06010000",
        "lon": 128.5352623,
        "lat": 37.13117779,
        "address": {
            "road": None,
            "admin": "김삿갓면",
            "legal": "강원특별자치도 영월군 김삿갓면 진별리 506-1",
            "zipcode": "26245",
            "bjd_code": "5175032521",
            "sido_name": "강원특별자치도",
            "sigungu_name": "영월군",
        },
        "detail": {
            "phones": ["033-370-2486"],
            "place_kind": "parking",
            "facility_info": {"prkcmprt": 75},
            "business_hours": None,
        },
        "urls": {"homepage": None, "sns1": None},
        "marker_icon": "parking",
        "marker_color": "P-13",
    }
    base.update(over)
    return base


def test_place_card_reads_map_phones_list() -> None:
    card = build_detail_card(_map_place_dto())
    assert isinstance(card, PlaceDetailCard)
    assert card.phone == "033-370-2486"


def test_place_card_falls_back_to_facility_info_tel_and_url() -> None:
    card = build_detail_card(
        _map_place_dto(
            detail={
                "phones": [],
                "facility_info": {
                    "tel": "054-853-0109",
                    "url": "http://www.hahoe.or.kr/coding/main.asp",
                },
            }
        )
    )
    assert isinstance(card, PlaceDetailCard)
    assert card.phone == "054-853-0109"
    assert card.homepage_url == "http://www.hahoe.or.kr/coding/main.asp"


def test_homepage_rejects_non_http_values() -> None:
    card = build_detail_card(
        _map_place_dto(
            urls={"homepage": "javascript:alert(1)"}, detail={"facility_info": {"url": "ftp://x"}}
        )
    )
    assert card.homepage_url is None


def test_address_line_uses_legal_when_road_is_missing() -> None:
    # 예전에는 dict의 첫 문자열 값(admin="김삿갓면")만 보였다.
    card = build_detail_card(_map_place_dto())
    assert card.address_line == "강원특별자치도 영월군 김삿갓면 진별리 506-1"


def test_address_line_composes_region_when_road_and_legal_are_missing() -> None:
    assert (
        address_line(
            {
                "road": None,
                "admin": "풍천면",
                "legal": None,
                "zipcode": "36760",
                "bjd_code": "4717034033",
                "sido_name": "경상북도",
                "sigungu_name": "안동시",
            }
        )
        == "경상북도 안동시 풍천면"
    )


def test_address_line_never_shows_codes() -> None:
    assert address_line({"zipcode": "36760", "bjd_code": "4717034033"}) is None


def test_detail_card_carries_category_label_not_code() -> None:
    labels = build_category_labels(
        [{"code": "06010000", "label": "교통 > 주차장", "path": ["교통", "주차장"]}]
    )
    card = build_detail_card(_map_place_dto(), labels)
    assert card.category == "06010000"
    assert card.category_label == "주차장"


def test_address_line_does_not_repeat_region_already_in_admin() -> None:
    # KHOA 해수욕장 등은 역지오코딩이 없을 때 admin에 시도·시군구 전체 이름을 둔다.
    assert (
        address_line(
            {
                "road": None,
                "legal": None,
                "admin": "부산광역시 해운대구",
                "sido_name": "부산광역시",
                "sigungu_name": "해운대구",
            }
        )
        == "부산광역시 해운대구"
    )


def test_homepage_skips_invalid_key_and_uses_next_http_url() -> None:
    card = build_detail_card(
        _map_place_dto(urls={"homepage": "javascript:alert(1)", "website": "https://ok.example"})
    )
    assert card.homepage_url == "https://ok.example"
