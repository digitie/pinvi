"""`app.services.place_search` 순수 매핑 단위 테스트(ADR-054)."""

from __future__ import annotations

from app.services.category_labels import build_category_labels
from app.services.place_search import (
    address_candidate_to_result,
    feature_item_to_result,
    kakao_document_to_result,
    my_poi_to_result,
    naver_item_to_result,
    normalize_link,
    region_biased_items,
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


def _item(fid: str, lon: float, lat: float) -> dict[str, object]:
    return {"feature_id": fid, "name": fid, "lon": lon, "lat": lat}


_ANDONG_BBOX = (128.2, 36.3, 129.1, 37.4)


def test_region_bias_moves_in_region_items_forward_keeping_the_rest() -> None:
    """2026-11-02: "하회마을" 전국 검색은 서울 식당이 먼저였다 — 여행 지역 안의 결과를 앞으로(순서만)."""
    items = [
        _item("seoul-1", 126.97, 37.54),
        _item("seoul-2", 126.92, 37.55),
        _item("andong-1", 128.53, 36.55),
        "junk",
        _item("no-coord", float("nan"), 0.0),
    ]
    ordered = region_biased_items(items, bbox=_ANDONG_BBOX, limit=8)
    assert [item["feature_id"] for item in ordered] == [
        "andong-1",
        "seoul-1",
        "seoul-2",
        "no-coord",
    ]


def test_region_bias_caps_in_region_share_so_out_of_region_exact_match_survives() -> None:
    """지역 안의 비슷한 이름이 목록을 다 차지하면 지역 밖의 정확한 장소가 사라진다(#615 리뷰) — 절반까지만."""
    fuzzy_in_region = [_item(f"near-{i}", 128.5, 36.6) for i in range(10)]
    items = [_item("exact-far", 129.04, 35.11), *fuzzy_in_region]
    ordered = region_biased_items(items, bbox=_ANDONG_BBOX, limit=8)
    ids = [item["feature_id"] for item in ordered]
    assert len(ids) == 8
    assert ids[:4] == ["near-0", "near-1", "near-2", "near-3"]
    assert ids[4] == "exact-far"


def test_region_bias_without_bbox_is_plain_truncation() -> None:
    items = [_item(str(i), 127.0, 37.0) for i in range(12)]
    assert [item["feature_id"] for item in region_biased_items(items, bbox=None, limit=5)] == [
        "0",
        "1",
        "2",
        "3",
        "4",
    ]


def test_region_bias_pulls_in_region_item_from_beyond_limit() -> None:
    """후보를 넉넉히 받는 이유 — 지역 안 장소가 전국 순위 limit 밖(20위)에 있어도 앞으로 당긴다."""
    items = [_item(f"far-{i}", 126.9, 37.5) for i in range(20)]
    items.append(_item("andong", 128.53, 36.55))
    ordered = region_biased_items(items, bbox=_ANDONG_BBOX, limit=8)
    assert ordered[0]["feature_id"] == "andong"
    assert len(ordered) == 8


def test_region_bias_is_off_when_limit_is_one() -> None:
    items = [_item("exact-far", 129.04, 35.11), _item("near", 128.5, 36.6)]
    ordered = region_biased_items(items, bbox=_ANDONG_BBOX, limit=1)
    assert [item["feature_id"] for item in ordered] == ["exact-far"]
