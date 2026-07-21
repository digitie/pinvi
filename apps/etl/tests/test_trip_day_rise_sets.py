"""일자 rise/set asset helper 테스트 (ADR-055 §6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pinvi.etl.assets.pinvi_trip_day_rise_sets import _parse_kasi_time, _rise_set_payload


def test_parse_kasi_time_hhmm_to_kst() -> None:
    parsed = _parse_kasi_time(date(2026, 6, 10), "0530")
    assert parsed is not None
    assert parsed.year == 2026 and parsed.month == 6 and parsed.day == 10
    assert parsed.hour == 5 and parsed.minute == 30
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 9 * 3600  # KST


def test_parse_kasi_time_rejects_invalid() -> None:
    assert _parse_kasi_time(date(2026, 6, 10), None) is None
    assert _parse_kasi_time(date(2026, 6, 10), "530") is None  # 4자리 아님
    assert _parse_kasi_time(date(2026, 6, 10), "2560") is None  # 분 60
    assert _parse_kasi_time(date(2026, 6, 10), "2400") is None  # 시 24
    assert _parse_kasi_time(date(2026, 6, 10), "abcd") is None


@dataclass(frozen=True)
class _Item:
    raw: dict[str, object]


def test_rise_set_payload_returns_raw_dict() -> None:
    assert _rise_set_payload(_Item({"sunrise": "0530"})) == {"sunrise": "0530"}
    assert _rise_set_payload(_Item({})) == {}
