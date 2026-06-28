"""Telegram system outbox asset helper 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

from pinvi.etl.assets.pinvi_telegram_system_outbox import telegram_outbox_summary_from_rows


def test_telegram_outbox_summary_metadata_is_bounded_and_secret_free() -> None:
    summary = telegram_outbox_summary_from_rows(
        {
            "total": 8,
            "pending_total": 4,
            "pending_due": 2,
            "pending_backoff": 2,
            "stuck_pending": 1,
            "sent": 2,
            "skipped": 1,
            "failed": 1,
            "retry_exhausted": 2,
            "oldest_pending_scheduled_at": datetime(2026, 6, 28, 0, 0, tzinfo=UTC),
        },
        [
            {
                "category": "trip_created",
                "total": 5,
                "pending": 2,
                "sent": 1,
                "skipped": 1,
                "failed": 1,
                "retry_exhausted": 2,
            },
            {
                "category": "companion_invited",
                "total": 3,
                "pending": 2,
                "sent": 1,
                "skipped": 0,
                "failed": 0,
                "retry_exhausted": 0,
            },
        ],
        stuck_threshold_minutes=15,
        max_attempts=5,
        category_window_hours=24,
    )

    assert summary.result() == {
        "total": 8,
        "pending_due": 2,
        "pending_backoff": 2,
        "stuck_pending": 1,
        "sent": 2,
        "skipped": 1,
        "failed": 1,
        "retry_exhausted": 2,
    }
    assert summary.category_stats[0].retry_exhausted_rate == 0.4
    assert summary.category_stats[1].retry_exhausted_rate == 0.0

    metadata = summary.metadata()
    assert metadata["category_retry_exhausted_rates"] == {
        "trip_created": 0.4,
        "companion_invited": 0.0,
    }
    assert metadata["category_retry_exhausted"] == {
        "trip_created": 2,
        "companion_invited": 0,
    }
    assert "payload" not in str(metadata)
    assert "text" not in str(metadata)
    assert "user_id" not in str(metadata)
    assert "chat_id" not in str(metadata)
    assert "token" not in str(metadata)
