"""`app.services.place_search` 순수 매핑 단위 테스트(ADR-054)."""

from __future__ import annotations

from app.services.category_labels import build_category_labels
from app.services.place_search import (
    address_candidate_to_result,
    feature_item_to_result,
    kakao_document_to_result,
    merge_region_biased_items,
    my_poi_to_result,
    naver_item_to_result,
    normalize_link,
    strip_html,
)


def test_strip_html_removes_tags_and_unescapes() -> None:
    assert strip_html("<b>스타벅스</b> 강남R점") == "스타벅스 강남R점"
    assert strip_html("김밥 &amp; 라면") == "김밥 & 라면"


def test_normalize_link_lowercases_host_and_trims() -> None:
    a = normalize_link("HTTP://Place.Map.NAVER.com/1234/")
    b = normalize_link("http://place.map.naver.com/1234")
    assert a == b == "http://place.map.naver.com/1234"


def test_kakao_document_mapping() -> None:
    result = kakao_document_to_result(
        {
            "id": "26338954",
            "place_name": "스타벅스 강남대로점",
            "address_name": "서울 강남구 역삼동 814",
            "road_address_name": "서울 강남구 강남대로 390",
            "x": "127.028",
            "y": "37.497",
            "category_name": "음식점 > 카페",
            "phone": "1522-3232",
            "place_url": "http://place.map.kakao.com/26338954",
        }
    )
    assert result is not None
    assert result.source == "kakao"
    assert result.name == "스타벅스 강남대로점"
    assert result.external_id == "26338954"
    assert result.coord is not None
    assert round(result.coord.lon, 3) == 127.028
    assert round(result.coord.lat, 3) == 37.497
    assert result.road_address == "서울 강남구 강남대로 390"
    assert result.provider_url == "http://place.map.kakao.com/26338954"
    assert result.phone == "1522-3232"


def test_kakao_document_missing_name_dropped() -> None:
    assert kakao_document_to_result({"id": "1", "x": "127", "y": "37"}) is None


def test_naver_item_mapping_strips_title_and_scales_coord() -> None:
    result = naver_item_to_result(
        {
            "title": "<b>경복궁</b>",
            "address": "서울특별시 종로구 세종로",
            "roadAddress": "서울특별시 종로구 사직로 161",
            "mapx": "1269768000",
            "mapy": "375796000",
            "category": "관광명소",
            "telephone": "",
            "link": "https://map.naver.com/p/1234/",
        }
    )
    assert result is not None
    assert result.source == "naver"
    assert result.name == "경복궁"  # <b> 제거
    assert result.coord is not None
    # mapx/mapy는 WGS84 x 10^7 → /1e7.
    assert round(result.coord.lon, 4) == 126.9768
    assert round(result.coord.lat, 4) == 37.5796
    assert result.external_id == "https://map.naver.com/p/1234"  # link 정규화
    assert result.phone is None  # 빈 문자열 → None


def test_naver_item_bad_coord_kept_without_coord() -> None:
    result = naver_item_to_result({"title": "이름만", "mapx": "x", "mapy": "y"})
    assert result is not None
    assert result.coord is None


def test_feature_item_mapping() -> None:
    result = feature_item_to_result(
        {
            "feature_id": "place:abc",
            "name": "광안리 해수욕장",
            "lon": 129.118,
            "lat": 35.153,
            "marker_color": "P-07",
            "marker_icon": "swimming",
            "category": "해수욕장",
        }
    )
    assert result is not None
    assert result.source == "feature"
    assert result.feature_id == "place:abc"
    assert result.marker_color == "P-07"
    assert result.coord is not None


def _geo_v2_candidate(**over: object) -> dict[str, object]:
    """kor-travel-geo v2 `/v2/search` 후보 실응답 형태(2026-11-02 prod 발췌)."""
    base: dict[str, object] = {
        "confidence": 0.5,
        "match_kind": "road",
        "address": {
            "full": "경상북도 안동시 도산서원길 154",
            "legal_dong_code": "4717042021",
            "admin_dong_code": "4717042000",
            "road_name": "도산서원길",
        },
        "point": {"lon": 128.840297, "lat": 36.728037},
        "region": {
            "sig_cd": "47170",
            "sido": "경상북도",
            "sigungu": "안동시",
            "legal_dong": "토계리",
        },
        "source": "local",
        "metadata": {"score": 0.5},
    }
    base.update(over)
    return base


def test_address_candidate_maps_geo_v2_nested_road_candidate() -> None:
    """예전 매퍼는 평면 `road_address`/`lon`을 읽어 v2 후보를 전부 버렸다(통합 검색 주소 0건)."""
    result = address_candidate_to_result(_geo_v2_candidate())
    assert result is not None
    assert result.source == "address"
    assert result.name == "경상북도 안동시 도산서원길 154"
    assert result.road_address == "경상북도 안동시 도산서원길 154"
    assert result.address is None
    assert result.coord is not None
    assert (result.coord.lon, result.coord.lat) == (128.840297, 36.728037)


def test_address_candidate_parcel_match_fills_jibun_address() -> None:
    result = address_candidate_to_result(
        _geo_v2_candidate(
            match_kind="parcel",
            address={"full": "경상북도 안동시 도산면 토계리 679-2"},
        )
    )
    assert result is not None
    assert result.address == "경상북도 안동시 도산면 토계리 679-2"
    assert result.road_address is None


def test_address_candidate_without_full_address_is_dropped() -> None:
    # 국가지점번호(sppn) 후보 등은 address가 없을 수 있다 — 이름을 만들 수 없다.
    assert address_candidate_to_result(_geo_v2_candidate(match_kind="sppn", address=None)) is None
    assert address_candidate_to_result(_geo_v2_candidate(address={"full": "  "})) is None


def test_feature_result_keeps_code_and_adds_human_category_label() -> None:
    labels = build_category_labels(
        [{"code": "06010000", "label": "교통 > 주차장", "path": ["교통", "주차장"]}]
    )
    result = feature_item_to_result(
        {"feature_id": "f1", "name": "도산서원", "category": "06010000", "lon": 128.8, "lat": 36.7},
        labels,
    )
    assert result is not None
    assert result.category == "06010000"
    assert result.category_label == "주차장"


def test_feature_result_unknown_code_has_no_label() -> None:
    result = feature_item_to_result({"feature_id": "f1", "name": "x", "category": "06010000"})
    assert result is not None
    assert result.category_label is None


def test_my_poi_mapping() -> None:
    result = my_poi_to_result(
        {
            "poi_id": "11111111-1111-1111-1111-111111111111",
            "trip_id": "22222222-2222-2222-2222-222222222222",
            "trip_title": "부산 여행",
            "feature_id": "place:xyz",
            "name": "숙소",
            "lon": 129.0,
            "lat": 35.1,
        }
    )
    assert result.source == "my_poi"
    assert result.name == "숙소"
    assert result.poi_id == "11111111-1111-1111-1111-111111111111"
    assert result.trip_title == "부산 여행"
    assert result.coord is not None


def test_region_bias_puts_in_region_items_first_then_everywhere_without_duplicates() -> None:
    """2026-11-02: "하회마을" 전국 검색은 서울 식당이 먼저였다 — 여행 지역 안의 결과를 앞으로."""
    everywhere = [
        {"feature_id": "seoul-1", "name": "하회마을"},
        {"feature_id": "seoul-2", "name": "하회마을"},
        {"feature_id": "andong-1", "name": "안동하회마을"},
    ]
    regional = [{"feature_id": "andong-1", "name": "안동하회마을"}, {"feature_id": "andong-2"}]
    merged = merge_region_biased_items(regional, everywhere, limit=8)
    assert [item["feature_id"] for item in merged] == ["andong-1", "andong-2", "seoul-1", "seoul-2"]


def test_region_bias_respects_limit_and_skips_non_dicts() -> None:
    merged = merge_region_biased_items(
        [{"feature_id": "a"}, "junk", {"feature_id": "b"}],
        [{"feature_id": "c"}, {"feature_id": "d"}],
        limit=3,
    )
    assert [item["feature_id"] for item in merged] == ["a", "b", "c"]
