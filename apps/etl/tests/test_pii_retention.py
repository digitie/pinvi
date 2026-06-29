"""PII retention dry-run asset helper 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

from pinvi.etl.assets.pinvi_pii_retention import (
    pii_retention_cutoffs,
    pii_retention_summary_from_row,
)


def test_pii_retention_summary_metadata_is_bounded_and_dry_run() -> None:
    now = datetime(2026, 6, 28, 0, 30, tzinfo=UTC)
    cutoffs = pii_retention_cutoffs(now=now)
    summary = pii_retention_summary_from_row(
        {
            "deleted_user_pii_candidates": 2,
            "deleted_user_oauth_identity_candidates": 1,
            "excluded_privileged_deleted_users": 1,
            "expired_signup_verifications": 3,
            "expired_password_reset_tokens": 1,
            "old_revoked_sessions": 2,
            "old_expired_sessions": 1,
            "expired_oauth_login_states": 1,
            "expired_mobile_oauth_exchanges": 1,
            "location_access_logs_over_retention": 4,
            "admin_audit_pii_over_retention": 2,
        },
        cutoffs=cutoffs,
    )

    assert cutoffs.user_pii_cutoff == datetime(2026, 5, 29, 0, 30, tzinfo=UTC)
    assert cutoffs.session_cutoff == datetime(2026, 5, 29, 0, 30, tzinfo=UTC)
    assert cutoffs.location_cutoff == datetime(2025, 12, 28, 0, 30, tzinfo=UTC)
    assert summary.total_candidates == 18
    assert summary.result()["dry_run"] is True
    assert summary.result()["total_candidates"] == 18

    metadata = summary.metadata()
    assert metadata["excluded_privileged_deleted_users"] == 1
    assert metadata["user_pii_grace_days"] == 30
    assert metadata["location_retention_months"] == 6
    assert "email" not in str(metadata)
    assert "token_hash" not in str(metadata)
    assert "user_id" not in str(metadata)
