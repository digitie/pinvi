"""PII 보존 기간 만료 후보 dry-run asset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from dagster import Backoff, RetryPolicy, asset
from sqlalchemy.ext.asyncio import AsyncConnection

from pinvi.etl.resources import PinviDatabaseResource
from pinvi.etl.sql.retention import PII_RETENTION_SUMMARY_SQL as _PII_RETENTION_SUMMARY_SQL

DEFAULT_USER_PII_GRACE_DAYS = 30
DEFAULT_SESSION_GRACE_DAYS = 30


@dataclass(frozen=True, slots=True)
class PiiRetentionCutoffs:
    generated_at: datetime
    user_pii_cutoff: datetime
    session_cutoff: datetime
    user_pii_grace_days: int
    session_grace_days: int

    def metadata(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "user_pii_cutoff": self.user_pii_cutoff.isoformat(),
            "session_cutoff": self.session_cutoff.isoformat(),
            "user_pii_grace_days": self.user_pii_grace_days,
            "session_grace_days": self.session_grace_days,
        }


@dataclass(frozen=True, slots=True)
class PiiRetentionSummary:
    cutoffs: PiiRetentionCutoffs
    deleted_user_pii_candidates: int
    deleted_user_oauth_identity_candidates: int
    excluded_privileged_deleted_users: int
    expired_signup_verifications: int
    expired_password_reset_tokens: int
    old_revoked_sessions: int
    old_expired_sessions: int
    expired_oauth_login_states: int
    expired_mobile_oauth_exchanges: int

    @property
    def total_candidates(self) -> int:
        return (
            self.deleted_user_pii_candidates
            + self.deleted_user_oauth_identity_candidates
            + self.expired_signup_verifications
            + self.expired_password_reset_tokens
            + self.old_revoked_sessions
            + self.old_expired_sessions
            + self.expired_oauth_login_states
            + self.expired_mobile_oauth_exchanges
        )

    def result(self) -> dict[str, Any]:
        return {
            "dry_run": True,
            "total_candidates": self.total_candidates,
            "deleted_user_pii_candidates": self.deleted_user_pii_candidates,
            "expired_signup_verifications": self.expired_signup_verifications,
            "expired_password_reset_tokens": self.expired_password_reset_tokens,
            "old_revoked_sessions": self.old_revoked_sessions,
            "old_expired_sessions": self.old_expired_sessions,
        }

    def metadata(self) -> dict[str, Any]:
        return {
            **self.cutoffs.metadata(),
            **self.result(),
            "deleted_user_oauth_identity_candidates": (self.deleted_user_oauth_identity_candidates),
            "excluded_privileged_deleted_users": self.excluded_privileged_deleted_users,
            "expired_oauth_login_states": self.expired_oauth_login_states,
            "expired_mobile_oauth_exchanges": self.expired_mobile_oauth_exchanges,
        }


async def collect_pii_retention_summary(
    conn: AsyncConnection,
    *,
    now: datetime,
    user_pii_grace_days: int = DEFAULT_USER_PII_GRACE_DAYS,
    session_grace_days: int = DEFAULT_SESSION_GRACE_DAYS,
) -> PiiRetentionSummary:
    """파괴 작업 없이 PII 보존 기간 만료 후보만 집계합니다."""

    cutoffs = pii_retention_cutoffs(
        now=now,
        user_pii_grace_days=user_pii_grace_days,
        session_grace_days=session_grace_days,
    )
    row = (
        (
            await conn.execute(
                _PII_RETENTION_SUMMARY_SQL,
                {
                    "now": now,
                    "user_pii_cutoff": cutoffs.user_pii_cutoff,
                    "session_cutoff": cutoffs.session_cutoff,
                },
            )
        )
        .mappings()
        .one()
    )
    return pii_retention_summary_from_row(row, cutoffs=cutoffs)


def pii_retention_cutoffs(
    *,
    now: datetime,
    user_pii_grace_days: int = DEFAULT_USER_PII_GRACE_DAYS,
    session_grace_days: int = DEFAULT_SESSION_GRACE_DAYS,
) -> PiiRetentionCutoffs:
    return PiiRetentionCutoffs(
        generated_at=now,
        user_pii_cutoff=now - timedelta(days=user_pii_grace_days),
        session_cutoff=now - timedelta(days=session_grace_days),
        user_pii_grace_days=user_pii_grace_days,
        session_grace_days=session_grace_days,
    )


def pii_retention_summary_from_row(
    row: Mapping[str, Any],
    *,
    cutoffs: PiiRetentionCutoffs,
) -> PiiRetentionSummary:
    return PiiRetentionSummary(
        cutoffs=cutoffs,
        deleted_user_pii_candidates=_as_int(row["deleted_user_pii_candidates"]),
        deleted_user_oauth_identity_candidates=_as_int(
            row["deleted_user_oauth_identity_candidates"]
        ),
        excluded_privileged_deleted_users=_as_int(row["excluded_privileged_deleted_users"]),
        expired_signup_verifications=_as_int(row["expired_signup_verifications"]),
        expired_password_reset_tokens=_as_int(row["expired_password_reset_tokens"]),
        old_revoked_sessions=_as_int(row["old_revoked_sessions"]),
        old_expired_sessions=_as_int(row["old_expired_sessions"]),
        expired_oauth_login_states=_as_int(row["expired_oauth_login_states"]),
        expired_mobile_oauth_exchanges=_as_int(row["expired_mobile_oauth_exchanges"]),
    )


@asset(
    group_name="pinvi_retention",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="PIPA/LBS 보존 기간 만료 후보를 dry-run metadata로 집계",
)
async def pinvi_pii_retention(  # type: ignore[no-untyped-def]
    context,
    db: PinviDatabaseResource,
) -> dict[str, Any]:
    current = datetime.now(UTC)
    user_pii_grace_days = int(
        context.op_config.get("user_pii_grace_days", DEFAULT_USER_PII_GRACE_DAYS)
    )
    session_grace_days = int(
        context.op_config.get("session_grace_days", DEFAULT_SESSION_GRACE_DAYS)
    )
    engine = db.create_engine()
    try:
        async with engine.connect() as conn:
            summary = await collect_pii_retention_summary(
                conn,
                now=current,
                user_pii_grace_days=user_pii_grace_days,
                session_grace_days=session_grace_days,
            )
    finally:
        await engine.dispose()

    context.add_output_metadata(summary.metadata())
    return summary.result()


def _as_int(value: Any) -> int:
    return int(value or 0)
