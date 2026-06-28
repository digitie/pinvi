"""Email outbox asset helper 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

from pinvi.etl.assets.pinvi_email_outbox import email_outbox_summary_from_rows


def test_email_outbox_summary_metadata_is_bounded_and_pii_free() -> None:
    summary = email_outbox_summary_from_rows(
        {
            "total": 10,
            "pending_total": 4,
            "pending_due": 2,
            "pending_backoff": 2,
            "stuck_pending": 1,
            "failed": 1,
            "bounced": 1,
            "complained": 1,
            "retry_exhausted": 2,
            "oldest_pending_scheduled_at": datetime(2026, 6, 28, 0, 0, tzinfo=UTC),
        },
        [
            {
                "template": "verify_email",
                "total": 8,
                "pending": 2,
                "sent": 3,
                "delivered": 1,
                "failed": 1,
                "bounced": 1,
                "complained": 0,
            },
            {
                "template": "trip_invite",
                "total": 2,
                "pending": 0,
                "sent": 1,
                "delivered": 0,
                "failed": 0,
                "bounced": 0,
                "complained": 1,
            },
        ],
        stuck_threshold_minutes=15,
        max_attempts=5,
        template_window_hours=24,
    )

    assert summary.result() == {
        "total": 10,
        "pending_due": 2,
        "pending_backoff": 2,
        "stuck_pending": 1,
        "failed": 1,
        "bounced": 1,
        "complained": 1,
        "retry_exhausted": 2,
    }
    assert summary.template_stats[0].failure_count == 2
    assert summary.template_stats[0].failure_rate == 0.25
    assert summary.template_stats[1].failure_rate == 0.5

    metadata = summary.metadata()
    assert metadata["template_failure_rates"] == {
        "verify_email": 0.25,
        "trip_invite": 0.5,
    }
    assert "to_email" not in str(metadata)
    assert "payload" not in str(metadata)
