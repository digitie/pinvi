"""통합검색의 POI 좌표 추출 회귀 (T-VN-H29).

kor-travel-map curated import로 들어온 POI의 `feature_snapshot`은 좌표를 **top-level
`lon`/`lat`**에 담는다(Map `CuratedFeatureDetailFeatureSnapshotView`는 `extra="forbid"`이고
`coord` property가 아예 없다 — T-VN-H07D에서 typed view로 고정). 과거 `_snapshot_coord`는
중첩 `coord`만 봐서 이 경로가 **구조적으로 항상 None**이었고, 같은 payload를
`services/admin_pois.py`/`services/kasi.py`는 정상 해석하던 비대칭이 있었다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.api.v1.search import _snapshot_coord

pytestmark = pytest.mark.unit


def _map_curated_feature_snapshot(*, lon: float, lat: float) -> dict[str, Any]:
    """Map `CuratedFeatureDetailFeatureSnapshotView`가 실제로 내보내는 key 집합."""
    return {
        "feature_id": "place::datagokr::bookstore::1",
        "name": "책방",
        "category": "bookstore",
        "kind": "place",
        "lon": lon,
        "lat": lat,
        "sido_code": "11",
        "sigungu_code": "11140",
        "legal_dong_code": None,
        "address": {"road": "서울특별시 중구 세종대로"},
        "detail": {},
    }


def test_map_curated_import_snapshot_yields_coordinates() -> None:
    """회귀 핵심: map-import POI가 통합검색에서 좌표 null이 되지 않는다."""
    lon, lat = _snapshot_coord(_map_curated_feature_snapshot(lon=126.977, lat=37.566))
    assert (lon, lat) == (126.977, 37.566)


def test_nested_coord_snapshot_still_supported() -> None:
    """기존에 동작하던 중첩 `coord` 형태도 계속 지원한다(회귀 방지)."""
    assert _snapshot_coord({"coord": {"lon": 129.1, "lat": 35.15}}) == (129.1, 35.15)
    assert _snapshot_coord({"coord": {"longitude": 129.1, "latitude": 35.15}}) == (
        129.1,
        35.15,
    )


def test_map_snapshot_with_null_coordinates_stays_none() -> None:
    """Map view는 `lon`/`lat`을 **required-but-nullable**로 선언한다 — null payload도 정상 입력이다.

    (vendored 계약: `anyOf: [number, null]` 이면서 `required`에 포함)
    """
    snapshot = _map_curated_feature_snapshot(lon=0.0, lat=0.0)
    snapshot["lon"] = None
    snapshot["lat"] = None
    assert _snapshot_coord(snapshot) == (None, None)


def test_zero_coordinates_are_preserved() -> None:
    """0.0은 falsy지만 유효한 좌표다 — None으로 뭉개지 않는다."""
    assert _snapshot_coord(_map_curated_feature_snapshot(lon=0.0, lat=0.0)) == (0.0, 0.0)


@pytest.mark.parametrize(
    "snapshot",
    [
        {},
        {"name": "좌표 없음"},
        {"coord": {}},
        {"lon": 126.977},  # lat 없음 — 부분 좌표는 좌표가 아니다
        {"lat": 37.566},
    ],
)
def test_missing_or_partial_coordinates_stay_none(snapshot: dict[str, Any]) -> None:
    assert _snapshot_coord(snapshot) == (None, None)


def test_my_poi_result_exposes_coordinates_for_map_imported_snapshot() -> None:
    """라우트가 실제로 만드는 결과 dict까지 좌표가 실린다(사용자 가시 회귀 지점).

    헬퍼만 검증하면 `_snapshot_coord` → 결과 dict → `PlaceSearchResult.coord` 배선이 비어도
    통과한다. 버그가 드러났던 표면이 바로 그 배선이므로 여기까지 고정한다.
    """
    from app.services.place_search import my_poi_to_result

    lon, lat = _snapshot_coord(_map_curated_feature_snapshot(lon=126.977, lat=37.566))
    result = my_poi_to_result(
        {
            "poi_id": "00000000-0000-0000-0000-000000000001",
            "trip_id": "00000000-0000-0000-0000-000000000002",
            "trip_title": "여행",
            "feature_id": "place::datagokr::bookstore::1",
            "name": "책방",
            "lon": lon,
            "lat": lat,
        }
    )

    assert result is not None
    assert result.coord is not None
    assert (result.coord.lon, result.coord.lat) == (126.977, 37.566)
