import uuid
from datetime import UTC, date, datetime

import pytest

from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.services.telegram_itinerary import itinerary_text, split_message


def test_plain_summary_uses_kst_and_day_overrides() -> None:
    trip = Trip(trip_id=uuid.uuid4(), title="부산 <여행>", start_date=date(2026, 11, 5))
    days = [
        TripDay(day_index=1, date=None, note="메모 " * 300),
        TripDay(day_index=2, date=date(2026, 11, 9)),
    ]
    poi = TripDayPoi(
        day_index=1,
        feature_snapshot={"name": "A & B"},
        planned_arrival_at=datetime(2026, 11, 5, 0, 30, tzinfo=UTC),
        user_note="짧은 메모",
    )
    message = itinerary_text(trip, days, [poi])
    assert "A & B · 도착 09:30 / 출발 미정" in message
    assert "1일차 · 2026-11-05" in message
    assert "2일차 · 2026-11-09" in message
    assert "…" in message and "짧은 메모" in message
    assert "<여행>" in message


@pytest.mark.parametrize("value", ["가" * 12000, "😀" * 6000, "a\n😀한" * 4000])
def test_chunks_preserve_exact_text_and_telegram_limit(value: str) -> None:
    chunks = split_message(value)
    assert "".join(chunks) == value
    assert all(len(chunk.encode("utf-16-le")) // 2 <= 3500 for chunk in chunks)
