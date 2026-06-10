"""features.py krtour → TripMate 매핑 helper 단위 테스트 (DB 불필요).

krtour 평면 lon/lat·name·status·구조화 address·cluster_key·평탄 metrics 투영을 검증한다.
"""

from __future__ import annotations

from app.api.v1.features import (
    _cluster_from_krtour,
    _coord_from_krtour,
    _detail_from_krtour,
    _summary_from_krtour,
    _weather_from_krtour,
)


def test_coord_is_none_when_lon_or_lat_missing() -> None:
    assert _coord_from_krtour({"lon": None, "lat": 35.0}) is None
    assert _coord_from_krtour({"lat": 35.0}) is None
    coord = _coord_from_krtour({"lon": 129.1, "lat": 35.1})
    assert coord is not None
    assert (coord.lon, coord.lat) == (129.1, 35.1)


def test_summary_defaults_marker_and_name() -> None:
    summary = _summary_from_krtour({"feature_id": "f1", "kind": "place", "lon": 129.1, "lat": 35.1})
    assert summary.name == ""
    assert summary.marker_color == "P-13"
    assert summary.marker_icon == "marker"
    assert summary.distance_m is None


def test_summary_carries_status_and_distance() -> None:
    summary = _summary_from_krtour(
        {
            "feature_id": "f1",
            "kind": "place",
            "name": "근처",
            "lon": 129.1,
            "lat": 35.1,
            "status": "active",
            "distance_m": 42.0,
        }
    )
    assert summary.status == "active"
    assert summary.distance_m == 42.0
    assert summary.coord is not None
    assert summary.coord.lon == 129.1


def test_cluster_uses_natural_key_and_flat_coord() -> None:
    cluster = _cluster_from_krtour(
        {"cluster_key": "11680", "feature_count": 5, "lon": 127.0, "lat": 37.5}
    )
    assert cluster.cluster_key == "11680"
    assert cluster.feature_count == 5
    assert (cluster.coord.lon, cluster.coord.lat) == (127.0, 37.5)


def test_detail_maps_structured_address_and_codes() -> None:
    detail = _detail_from_krtour(
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


def test_weather_maps_flat_metrics() -> None:
    card = _weather_from_krtour(
        {
            "feature_id": "f1",
            "is_stale": True,
            "source_styles": ["nowcast"],
            "metrics": [
                {
                    "metric_key": "T1H",
                    "forecast_style": "nowcast",
                    "value_number": 23.0,
                    "unit": "℃",
                }
            ],
        },
        feature_id="f1",
    )
    assert card.is_stale is True
    assert card.source_styles == ["nowcast"]
    assert card.metrics[0].metric_key == "T1H"
    assert card.metrics[0].value_number == 23.0
