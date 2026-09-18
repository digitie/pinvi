"""features.py kor_travel_map → Pinvi 매핑 helper 단위 테스트 (DB 불필요).

kor_travel_map 평면 lon/lat·name·구조화 address·cluster_key·평탄 metrics 투영을 검증한다.
Map cutover로 **제거한** 필드(`status`, T-VN-42)를 여기서 고정한다. 날씨 매핑
(`_weather_from_kor_travel_map`)은 T-365에서 `kor-travel-weather`로 이관되며 삭제됐다
(ADR-068).
"""

from __future__ import annotations

from app.api.v1.features import (
    _category_from_kor_travel_map,
    _cluster_from_kor_travel_map,
    _coord_from_kor_travel_map,
    _detail_from_kor_travel_map,
    _summary_from_kor_travel_map,
)


def test_category_maps_catalog_fields() -> None:
    category = _category_from_kor_travel_map(
        {
            "code": "01070100",
            "label": "해수욕장",
            "parent_code": "010701",
            "depth": 3,
            "path": ["자연", "해안", "해수욕장"],
            "maki_icon": "swimming",
            "is_active": True,
            "sort_order": 5,
        }
    )
    assert category.code == "01070100"
    assert category.label == "해수욕장"
    assert category.parent_code == "010701"
    assert category.path == ["자연", "해안", "해수욕장"]
    assert category.maki_icon == "swimming"


def test_category_defaults_when_sparse() -> None:
    category = _category_from_kor_travel_map({"code": "99", "label": "X"})
    assert category.depth == 0
    assert category.path == []
    assert category.maki_icon == "marker"
    assert category.is_active is True


def test_coord_is_none_when_lon_or_lat_missing() -> None:
    assert _coord_from_kor_travel_map({"lon": None, "lat": 35.0}) is None
    assert _coord_from_kor_travel_map({"lat": 35.0}) is None
    coord = _coord_from_kor_travel_map({"lon": 129.1, "lat": 35.1})
    assert coord is not None
    assert (coord.lon, coord.lat) == (129.1, 35.1)


def test_summary_defaults_marker_and_name() -> None:
    summary = _summary_from_kor_travel_map(
        {"feature_id": "f1", "kind": "place", "lon": 129.1, "lat": 35.1}
    )
    assert summary.name == ""
    assert summary.marker_color == "P-13"
    assert summary.marker_icon == "marker"
    assert summary.distance_m is None


def test_summary_carries_distance() -> None:
    summary = _summary_from_kor_travel_map(
        {
            "feature_id": "f1",
            "kind": "place",
            "name": "근처",
            "lon": 129.1,
            "lat": 35.1,
            "distance_m": 42.0,
        }
    )
    assert summary.distance_m == 42.0
    assert summary.coord is not None
    assert summary.coord.lon == 129.1


def test_summary_and_detail_never_read_status_from_map_dto() -> None:
    """Map 3축 feature state cutover(`1f2bdc3a`)로 user 표면에서 `status`가 사라졌다.

    대체 필드가 없어 T-VN-42에서 공개 스키마의 필드까지 제거했다. dto에 `status`가 남아 있어도
    (구 스냅샷·mock) Pinvi 응답 키로 나타나면 안 된다. 필드 선언이 되살아나는 회귀는
    `test_feature_schemas.py`의 필드 집합 등호 게이트가 잡고, 여기서는 선언과 값이 함께 되돌아온
    조합이 조용히 통과하지 않게 upstream 오염을 계속 주입해 둔다.
    """
    dto = {
        "feature_id": "f1",
        "kind": "place",
        "name": "이름",
        "lon": 129.1,
        "lat": 35.1,
        "status": "active",
        "updated_at": "2026-06-10T12:00:00+09:00",
    }
    assert "status" not in _summary_from_kor_travel_map(dto).model_dump()
    assert "status" not in _detail_from_kor_travel_map(dto).model_dump()


def test_cluster_uses_natural_key_and_flat_coord() -> None:
    cluster = _cluster_from_kor_travel_map(
        {"cluster_key": "11680", "feature_count": 5, "lon": 127.0, "lat": 37.5}
    )
    assert cluster.cluster_key == "11680"
    assert cluster.feature_count == 5
    assert (cluster.coord.lon, cluster.coord.lat) == (127.0, 37.5)


def test_detail_maps_structured_address_and_codes() -> None:
    detail = _detail_from_kor_travel_map(
        {
            "feature_id": "f1",
            "kind": "place",
            "name": "상세",
            "lon": 129.0,
            "lat": 35.0,
            "address": {"road": "부산 광안로 1"},
            "sigungu_code": "11680",
            "urls": {"homepage": "h"},
            "detail": {"x": 1},
            "status": "active",
            "updated_at": "2026-06-10T12:00:00+09:00",
        }
    )
    assert detail.name == "상세"
    assert detail.address == {"road": "부산 광안로 1"}
    assert detail.sigungu_code == "11680"
    assert detail.urls == {"homepage": "h"}
