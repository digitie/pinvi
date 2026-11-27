"""지도 장소 layer에서 transport 레이어 항목(주유소·교통 돌발)을 빼는 규칙."""

from __future__ import annotations

from typing import Any

from app.schemas.feature import FeatureSummary
from app.services.transport_place_overlap import (
    is_transport_layer_feature,
    without_transport_layer_features,
)


def _summary(**overrides: Any) -> FeatureSummary:
    base: dict[str, Any] = {
        "feature_id": "f_1",
        "kind": "place",
        "name": "장소",
        "category": "01070100",
        "marker_color": "P-07",
        "marker_icon": "swimming",
    }
    base.update(overrides)
    return FeatureSummary(**base)


def test_fuel_station_places_are_transport_layer_features() -> None:
    assert is_transport_layer_feature(_summary(category="06020000", marker_icon="fuel"))
    # 원천과 무관하게 주유소 카테고리 계층 전체(하위 코드 포함)다.
    assert is_transport_layer_feature(_summary(category="06020100"))


def test_neighbouring_transport_categories_are_ordinary_places() -> None:
    # 주차장·정류장·휴게소는 transport 레이어가 지도에 그리지 않는다 — 장소로 남는다.
    for code in ("06010000", "06030100", "06040101", "06000000"):
        assert not is_transport_layer_feature(_summary(category=code))
    assert not is_transport_layer_feature(_summary(category=None))


def test_traffic_notice_needs_both_category_and_roadblock_icon() -> None:
    incident = _summary(kind="notice", category="99000000", marker_icon="roadblock")
    assert is_transport_layer_feature(incident)
    # 99000000은 산림 안전 notice 등과 같이 쓰는 placeholder — 아이콘이 다르면 남긴다.
    forest = _summary(kind="notice", category="99000000", marker_icon="danger")
    assert not is_transport_layer_feature(forest)
    # 주유소 카테고리라도 place가 아니면(가격 feature는 퇴역) 장소 규칙을 적용하지 않는다.
    assert not is_transport_layer_feature(_summary(kind="price", category="06020000"))


def test_filter_keeps_order_and_honours_explicit_fuel_category() -> None:
    beach = _summary(feature_id="beach")
    fuel = _summary(feature_id="fuel", category="06020000")
    incident = _summary(
        feature_id="inc", kind="notice", category="99000000", marker_icon="roadblock"
    )
    cafe = _summary(feature_id="cafe", category="01020000")
    items = [beach, fuel, incident, cafe]
    kept = without_transport_layer_features(items, requested_category=None)
    assert [i.feature_id for i in kept] == ["beach", "cafe"]
    # 다른 카테고리를 골라도 제외는 그대로다.
    kept = without_transport_layer_features(items, requested_category="01070100")
    assert [i.feature_id for i in kept] == ["beach", "cafe"]
    # 주유소 계층을 명시해 고르면 그 뜻대로 돌려준다.
    assert without_transport_layer_features(items, requested_category="06020000") == items
