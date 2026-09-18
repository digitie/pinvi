"""`normalize_asof_query` 순수 함수 테스트 — HTTP `?asof=` naive/aware 처리.

기존에는 `test_features_api.py`의 구 kor-travel-map weather 경로를 통해서만
간접 검증됐다(T-362~T-364 flag-off 경로 삭제, T-365). 이 함수는 여러 라우터가
공유하는 HTTP 경계 로직(`features.py` weather + `admin/features.py`
weather-values)이라 순수 함수로 직접 고정한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.api.v1.features import normalize_asof_query


def test_none_passes_through() -> None:
    assert normalize_asof_query(None) is None


def test_naive_value_is_interpreted_as_kst() -> None:
    """offset 없는 값은 KST로 해석한다 — UTC로 읽으면 9시간 어긋난 시점이 조용히 돌아온다."""
    result = normalize_asof_query(datetime(2026, 7, 1, 23, 59, 59))

    assert result is not None
    assert result.utcoffset() == timedelta(hours=9)
    assert result.isoformat() == "2026-07-01T23:59:59+09:00"


def test_aware_value_with_offset_keeps_caller_offset() -> None:
    """명시된 offset은 덮어쓰지 않는다."""
    value = datetime(2026, 7, 1, 23, 59, 59, tzinfo=timezone(timedelta(hours=9)))

    result = normalize_asof_query(value)

    assert result == value


def test_aware_utc_value_keeps_utc_offset() -> None:
    """`Z`(UTC)도 그대로 UTC로 나간다 — KST로 강제 변환하지 않는다."""
    value = datetime(2026, 7, 1, 23, 59, 59, tzinfo=UTC)

    result = normalize_asof_query(value)

    assert result is not None
    assert result.utcoffset() == timedelta(0)
