"""PII 보존 기간 만료 후보 dry-run asset."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from dagster import Backoff, RetryPolicy, asset
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from pinvi.etl.resources import PinviDatabaseResource

DEFAULT_USER_PII_GRACE_DAYS = 30
DEFAULT_SESSION_GRACE_DAYS = 30
DEFAULT_LOCATION_RETENTION_MONTHS = 6


@dataclass(frozen=True, slots=True)
class PiiRetentionCutoffs:
    generated_at: datetime
    user_pii_cutoff: datetime
    session_cutoff: datetime
    location_cutoff: datetime
    user_pii_grace_days: int
    session_grace_days: int
    location_retention_months: int

    def metadata(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "user_pii_cutoff": self.user_pii_cutoff.isoformat(),
            "session_cutoff": self.session_cutoff.isoformat(),
            "location_cutoff": self.location_cutoff.isoformat(),
            "user_pii_grace_days": self.user_pii_grace_days,
            "session_grace_days": self.session_grace_days,
            "location_retention_months": self.location_retention_months,
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
    location_access_logs_over_retention: int
    admin_audit_pii_over_retention: int

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
            + self.location_access_logs_over_retention
            + self.admin_audit_pii_over_retention
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
            "location_access_logs_over_retention": self.location_access_logs_over_retention,
        }

    def metadata(self) -> dict[str, Any]:
        return {
            **self.cutoffs.metadata(),
            **self.result(),
            "deleted_user_oauth_identity_candidates": (self.deleted_user_oauth_identity_candidates),
            "excluded_privileged_deleted_users": self.excluded_privileged_deleted_users,
            "expired_oauth_login_states": self.expired_oauth_login_states,
            "expired_mobile_oauth_exchanges": self.expired_mobile_oauth_exchanges,
            "admin_audit_pii_over_retention": self.admin_audit_pii_over_retention,
        }


async def collect_pii_retention_summary(
    conn: AsyncConnection,
    *,
    now: datetime,
    user_pii_grace_days: int = DEFAULT_USER_PII_GRACE_DAYS,
    session_grace_days: int = DEFAULT_SESSION_GRACE_DAYS,
    location_retention_months: int = DEFAULT_LOCATION_RETENTION_MONTHS,
) -> PiiRetentionSummary:
    """파괴 작업 없이 PII 보존 기간 만료 후보만 집계합니다."""

    cutoffs = pii_retention_cutoffs(
        now=now,
        user_pii_grace_days=user_pii_grace_days,
        session_grace_days=session_grace_days,
        location_retention_months=location_retention_months,
    )
    row = (
        (
            await conn.execute(
                _PII_RETENTION_SUMMARY_SQL,
                {
                    "now": now,
                    "user_pii_cutoff": cutoffs.user_pii_cutoff,
                    "session_cutoff": cutoffs.session_cutoff,
                    "location_cutoff": cutoffs.location_cutoff,
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
    location_retention_months: int = DEFAULT_LOCATION_RETENTION_MONTHS,
) -> PiiRetentionCutoffs:
    return PiiRetentionCutoffs(
        generated_at=now,
        user_pii_cutoff=now - timedelta(days=user_pii_grace_days),
        session_cutoff=now - timedelta(days=session_grace_days),
        location_cutoff=_subtract_months(now, location_retention_months),
        user_pii_grace_days=user_pii_grace_days,
        session_grace_days=session_grace_days,
        location_retention_months=location_retention_months,
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
        location_access_logs_over_retention=_as_int(row["location_access_logs_over_retention"]),
        admin_audit_pii_over_retention=_as_int(row["admin_audit_pii_over_retention"]),
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
    location_retention_months = int(
        context.op_config.get(
            "location_retention_months",
            DEFAULT_LOCATION_RETENTION_MONTHS,
        )
    )

    engine = db.create_engine()
    try:
        async with engine.connect() as conn:
            summary = await collect_pii_retention_summary(
                conn,
                now=current,
                user_pii_grace_days=user_pii_grace_days,
                session_grace_days=session_grace_days,
                location_retention_months=location_retention_months,
            )
    finally:
        await engine.dispose()

    context.add_output_metadata(summary.metadata())
    return summary.result()


def _subtract_months(value: datetime, months: int) -> datetime:
    month_index = value.month - months - 1
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _as_int(value: Any) -> int:
    return int(value or 0)


_PII_RETENTION_SUMMARY_SQL = text(
    """
    WITH deleted_users AS (
      SELECT user_id, roles
      FROM app.users
      WHERE status = 'deleted'
        AND deleted_at IS NOT NULL
        AND deleted_at <= :user_pii_cutoff
    ),
    eligible_deleted_users AS (
      SELECT user_id
      FROM deleted_users
      WHERE NOT (roles && ARRAY['admin', 'operator', 'cpo']::varchar[])
    )
    SELECT
      (SELECT count(*) FROM eligible_deleted_users)::int
        AS deleted_user_pii_candidates,
      (
        SELECT count(*)
        FROM app.user_oauth_identities identities
        JOIN eligible_deleted_users deleted USING (user_id)
      )::int AS deleted_user_oauth_identity_candidates,
      (
        SELECT count(*)
        FROM deleted_users
        WHERE roles && ARRAY['admin', 'operator', 'cpo']::varchar[]
      )::int AS excluded_privileged_deleted_users,
      (
        SELECT count(*)
        FROM app.user_email_verifications
        WHERE purpose = 'signup'
          AND expires_at <= :now
      )::int AS expired_signup_verifications,
      (
        SELECT count(*)
        FROM app.user_email_verifications
        WHERE purpose = 'password_reset'
          AND expires_at <= :now
      )::int AS expired_password_reset_tokens,
      (
        SELECT count(*)
        FROM app.user_sessions
        WHERE revoked_at IS NOT NULL
          AND revoked_at <= :session_cutoff
      )::int AS old_revoked_sessions,
      (
        SELECT count(*)
        FROM app.user_sessions
        WHERE revoked_at IS NULL
          AND expires_at <= :session_cutoff
      )::int AS old_expired_sessions,
      (
        SELECT count(*)
        FROM app.oauth_login_states
        WHERE expires_at <= :now
      )::int AS expired_oauth_login_states,
      (
        SELECT count(*)
        FROM app.oauth_mobile_exchanges
        WHERE expires_at <= :now
      )::int AS expired_mobile_oauth_exchanges,
      (
        SELECT count(*)
        FROM app.location_access_log
        WHERE occurred_at <= :location_cutoff
      )::int AS location_access_logs_over_retention,
      (
        SELECT count(*)
        FROM app.admin_audit_log
        WHERE occurred_at <= :location_cutoff
          AND (target_pii_fields IS NOT NULL OR user_agent IS NOT NULL)
      )::int AS admin_audit_pii_over_retention
    """
)
