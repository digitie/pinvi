"""Telegram 알림 메시지 빌더 테스트 — T-106."""

from __future__ import annotations

from datetime import date

from app.services.telegram_messages import (
    build_companion_invited_message,
    build_trip_created_message,
)


def test_trip_created_includes_title_dates_region() -> None:
    msg = build_trip_created_message(
        title="부산 2박 3일",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 3),
        region_hint="부산",
    )
    assert "부산 2박 3일" in msg
    assert "7월 1일 ~ 7월 3일" in msg
    assert "📍 부산" in msg


def test_trip_created_handles_missing_dates_and_region() -> None:
    msg = build_trip_created_message(
        title="무계획 여행", start_date=None, end_date=None, region_hint=None
    )
    assert "미정 ~ 미정" in msg
    assert "📍" not in msg


def test_companion_invited_uses_display_name_without_email() -> None:
    msg = build_companion_invited_message(trip_title="서울 주말", display_name="지훈")
    assert "지훈님" in msg
    assert "서울 주말" in msg
    assert "@" not in msg  # PII(이메일) 미포함


def test_companion_invited_falls_back_without_name() -> None:
    msg = build_companion_invited_message(trip_title="서울 주말", display_name=None)
    assert "회원님" in msg
