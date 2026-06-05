"""KASI 부속 데이터 helper 단위 테스트."""

from __future__ import annotations

from app.services.kasi import extract_feature_coordinates


def test_extract_feature_coordinates_from_flat_lon_lat() -> None:
    assert extract_feature_coordinates({"lon": "127.1", "lat": 37.5}) == (127.1, 37.5)


def test_extract_feature_coordinates_from_nested_location() -> None:
    snapshot = {"location": {"longitude": 126.98, "latitude": "37.56"}}

    assert extract_feature_coordinates(snapshot) == (126.98, 37.56)


def test_extract_feature_coordinates_rejects_invalid_range() -> None:
    assert extract_feature_coordinates({"lon": 200, "lat": 37.5}) is None
