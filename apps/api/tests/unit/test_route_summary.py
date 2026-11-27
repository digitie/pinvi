"""Map ADR-128 `route` 요약 — 등산 코스를 일정에 넣을 때 쓰는 투영."""

from __future__ import annotations

from typing import Any

from app.api.v1.features import _detail_from_kor_travel_map, _summary_from_kor_travel_map
from app.clients.kor_travel_map import _decode_feature_trip_card
from app.schemas.feature import RouteSummary
from app.services.place_search import feature_item_to_result

_ROUTE: dict[str, Any] = {
    "route_type": "hiking_course",
    "length_m": 23003.7,
    "duration_minutes": 775,
    "duration_basis": "source",
    "difficulty": None,
    "shape": "network",
    "start": {"lon": 127.5296338, "lat": 35.29684841, "name": "노고단고개"},
    "end": {"lon": 127.7164709, "lat": 35.33257238, "name": "천왕봉"},
}


def _course(**overrides: Any) -> dict[str, Any]:
    return {
        "feature_id": "01a2-course",
        "kind": "route",
        "name": "노고단고개 ~ 천왕봉",
        "category": "01020103",
        # 등산 코스의 feature 좌표는 출발점이다(Map ADR-128).
        "lon": 127.5296338,
        "lat": 35.29684841,
        "marker_icon": "park",
        "marker_color": "P-06",
        "route": _ROUTE,
        **overrides,
    }


def test_route_summary_parses_map_payload() -> None:
    summary = RouteSummary.from_kor_travel_map(_ROUTE)
    assert summary is not None
    assert summary.length_m == 23003.7
    assert summary.start is not None
    assert summary.start.name == "노고단고개"


def test_route_summary_drops_contract_violations_instead_of_the_item() -> None:
    assert RouteSummary.from_kor_travel_map(None) is None
    assert RouteSummary.from_kor_travel_map("x") is None
    assert RouteSummary.from_kor_travel_map({**_ROUTE, "length_m": -5}).length_m is None  # type: ignore[union-attr]
    item = _summary_from_kor_travel_map(_course(route={"route_type": 3}))
    assert item.route is None
    assert item.name == "노고단고개 ~ 천왕봉"


def test_summary_and_detail_carry_route_and_start_coordinate() -> None:
    summary = _summary_from_kor_travel_map(_course())
    assert summary.route is not None
    assert summary.route.duration_minutes == 775
    assert summary.coord is not None
    assert summary.route.start is not None
    assert (summary.coord.lon, summary.coord.lat) == (
        summary.route.start.lon,
        summary.route.start.lat,
    )
    detail = _detail_from_kor_travel_map(
        {**_course(), "address": {}, "urls": {}, "detail": {}, "updated_at": "2026-11-27T00:00:00Z"}
    )
    assert detail.route is not None
    assert detail.route.shape == "network"


def test_search_result_carries_kind_and_route_for_features() -> None:
    result = feature_item_to_result(_course())
    assert result is not None
    assert result.kind == "route"
    assert result.route is not None
    assert result.route.end is not None
    assert result.route.end.name == "천왕봉"
    place = feature_item_to_result({**_course(), "kind": "place", "route": None})
    assert place is not None
    assert place.kind == "place"
    assert place.route is None
    unknown = feature_item_to_result({**_course(), "kind": "spaceship"})
    assert unknown is not None
    assert unknown.kind is None


def test_trip_card_route_flows_into_snapshot() -> None:
    card = _decode_feature_trip_card(
        {
            "feature_id": "01a2-course",
            "kind": "route",
            "name": "노고단고개 ~ 천왕봉",
            "category": "01020103",
            "lon": 127.5296338,
            "lat": 35.29684841,
            "address": {},
            "marker_icon": "park",
            "marker_color": "P-06",
            "route": _ROUTE,
        },
        "01a2-course",
    )
    snapshot = card.as_snapshot()
    assert snapshot["route"]["duration_minutes"] == 775
    assert snapshot["coord"] == {"lon": 127.5296338, "lat": 35.29684841}

    broken = _decode_feature_trip_card(
        {**card.as_snapshot(), "lon": 127.5, "lat": 35.3, "route": {"length_m": "far"}},
        "01a2-course",
    )
    assert "route" not in broken.as_snapshot()


def test_route_summary_drops_only_the_offending_field() -> None:
    summary = RouteSummary.from_kor_travel_map(
        {
            **_ROUTE,
            "shape": "zigzag",
            "duration_basis": "guessed",
            "duration_minutes": 12.7,
            "start": {"lon": float("nan"), "lat": 35.3},
        }
    )
    assert summary is not None
    assert summary.length_m == 23003.7
    assert summary.duration_minutes == 13
    assert summary.shape is None
    assert summary.duration_basis is None
    assert summary.start is None
    assert summary.end is not None
