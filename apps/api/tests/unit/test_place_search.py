"""`app.services.place_search` 순수 매핑 단위 테스트(ADR-054)."""

from __future__ import annotations

from app.services.place_search import (
    address_candidate_to_result,
    feature_item_to_result,
    kakao_document_to_result,
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


def test_address_candidate_mapping_prefers_road_address_name() -> None:
    result = address_candidate_to_result(
        {"address": "테헤란로 지번", "road_address": "테헤란로 152", "lon": 127.0, "lat": 37.5}
    )
    assert result is not None
    assert result.source == "address"
    assert result.name == "테헤란로 152"
    assert result.coord is not None


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
