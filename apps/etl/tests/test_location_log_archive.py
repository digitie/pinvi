"""위치 접근 로그 archive dry-run asset helper 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

from pinvi.etl.assets.pinvi_location_log_archive import (
    location_log_archive_summary_from_rows,
    subtract_months,
)


def test_location_log_archive_summary_bridge_and_metadata_are_bounded() -> None:
    now = datetime(2026, 6, 28, 4, 30, tzinfo=UTC)
    archive_cutoff = subtract_months(now, 6)
    summary = location_log_archive_summary_from_rows(
        {
            "total_candidates": 2,
            "oldest_candidate_at": datetime(2025, 12, 1, 0, 0, tzinfo=UTC),
            "newest_candidate_at": datetime(2025, 12, 27, 23, 59, tzinfo=UTC),
            "archive_tail_log_id": 10,
            "archive_tail_content_hash": "a" * 64,
            "active_head_log_id": 11,
            "active_head_prev_hash": "a" * 64,
            "active_rows_after_cutoff": 3,
            "pending_outbox_total": 1,
            "pending_outbox_before_cutoff": 0,
            "oldest_pending_outbox_at": datetime(2026, 6, 27, 0, 0, tzinfo=UTC),
        },
        [{"purpose": "nearby_attractions", "total": 2}],
        generated_at=now,
        archive_cutoff=archive_cutoff,
        location_retention_months=6,
    )

    assert archive_cutoff == datetime(2025, 12, 28, 4, 30, tzinfo=UTC)
    assert summary.chain_bridge_required is True
    assert summary.bridge_anchor_matches is True
    assert summary.archive_blocked_by_pending_outbox is False
    assert summary.result() == {
        "dry_run": True,
        "total_candidates": 2,
        "chain_bridge_required": True,
        "bridge_anchor_matches": True,
        "archive_blocked_by_pending_outbox": False,
        "pending_outbox_before_cutoff": 0,
    }

    metadata = summary.metadata()
    assert metadata["location_retention_months"] == 6
    assert metadata["purpose_counts"] == {"nearby_attractions": 2}
    assert "user_id" not in str(metadata)
    assert "lat" not in str(metadata)
    assert "lng" not in str(metadata)


def test_location_log_archive_summary_blocks_archive_for_old_pending_outbox() -> None:
    now = datetime(2026, 6, 28, 4, 30, tzinfo=UTC)
    summary = location_log_archive_summary_from_rows(
        {
            "total_candidates": 1,
            "oldest_candidate_at": datetime(2025, 12, 1, 0, 0, tzinfo=UTC),
            "newest_candidate_at": datetime(2025, 12, 1, 0, 0, tzinfo=UTC),
            "archive_tail_log_id": 20,
            "archive_tail_content_hash": "b" * 64,
            "active_head_log_id": None,
            "active_head_prev_hash": None,
            "active_rows_after_cutoff": 0,
            "pending_outbox_total": 1,
            "pending_outbox_before_cutoff": 1,
            "oldest_pending_outbox_at": datetime(2025, 12, 1, 0, 0, tzinfo=UTC),
        },
        [],
        generated_at=now,
        archive_cutoff=subtract_months(now, 6),
        location_retention_months=6,
    )

    assert summary.chain_bridge_required is False
    assert summary.bridge_anchor_matches is None
    assert summary.archive_blocked_by_pending_outbox is True
    assert summary.result()["pending_outbox_before_cutoff"] == 1
