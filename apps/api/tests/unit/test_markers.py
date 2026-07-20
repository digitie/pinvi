"""`app.core.markers` 단위 테스트 — 일자 기본색 + display 색 해석(ADR-055)."""

from __future__ import annotations

import pytest

from app.core.markers import (
    default_day_marker_color,
    is_marker_color_key,
    resolve_day_marker_color,
    resolve_display_marker_color,
)


@pytest.mark.parametrize(
    ("day_index", "expected"),
    [(1, "P-01"), (2, "P-02"), (16, "P-16"), (17, "P-01"), (32, "P-16"), (33, "P-01")],
)
def test_default_day_marker_color_cycles_16(day_index: int, expected: str) -> None:
    assert default_day_marker_color(day_index) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("P-01", True),
        ("P-16", True),
        ("P-00", False),
        ("P-17", False),
        ("P-1", False),
        ("red", False),
        (None, False),
        ("", False),
    ],
)
def test_is_marker_color_key(value: str | None, expected: bool) -> None:
    assert is_marker_color_key(value) is expected


def test_resolve_day_marker_color_prefers_valid_override() -> None:
    assert resolve_day_marker_color(3, "P-10") == "P-10"


def test_resolve_day_marker_color_falls_back_on_missing_or_invalid() -> None:
    assert resolve_day_marker_color(3, None) == "P-03"
    assert resolve_day_marker_color(3, "P-99") == "P-03"  # 무효 override → 기본색


def test_resolve_display_marker_color_precedence() -> None:
    # custom(POI) > 일자 override > 일자 기본색.
    assert resolve_display_marker_color(2, "P-10", "P-05") == "P-05"  # POI custom 최우선
    assert resolve_display_marker_color(2, "P-10", None) == "P-10"  # 일자 override
    assert resolve_display_marker_color(2, None, None) == "P-02"  # 일자 기본색(day 2)
    assert resolve_display_marker_color(2, None, "bad") == "P-02"  # 무효 custom 무시
