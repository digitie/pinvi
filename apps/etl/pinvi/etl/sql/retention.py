"""Retention SQL statements for ETL smoke tests and Dagster assets."""

from __future__ import annotations

from sqlalchemy import text

PII_RETENTION_SUMMARY_SQL = text(
    """
    WITH deleted_users AS (
      SELECT user_id, roles
      FROM app.users
      WHERE status IN ('pending_delete', 'deleted')
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
      )::int AS expired_mobile_oauth_exchanges
    """
)

LOCATION_LOG_ARCHIVE_SUMMARY_SQL = text(
    """
    WITH candidates AS (
      SELECT log_id, occurred_at, content_hash
      FROM app.location_access_log
      WHERE occurred_at <= :archive_cutoff
    ),
    archive_tail AS (
      SELECT log_id, content_hash
      FROM candidates
      ORDER BY log_id DESC
      LIMIT 1
    ),
    active_head AS (
      SELECT log_id, prev_hash
      FROM app.location_access_log
      WHERE occurred_at > :archive_cutoff
      ORDER BY log_id ASC
      LIMIT 1
    ),
    pending_outbox AS (
      SELECT occurred_at
      FROM app.location_audit_outbox
      WHERE processed_at IS NULL
    )
    SELECT
      (SELECT count(*) FROM candidates)::int AS total_candidates,
      (SELECT min(occurred_at) FROM candidates) AS oldest_candidate_at,
      (SELECT max(occurred_at) FROM candidates) AS newest_candidate_at,
      (SELECT log_id FROM archive_tail) AS archive_tail_log_id,
      (SELECT content_hash FROM archive_tail) AS archive_tail_content_hash,
      (SELECT log_id FROM active_head) AS active_head_log_id,
      (SELECT prev_hash FROM active_head) AS active_head_prev_hash,
      (
        SELECT count(*)
        FROM app.location_access_log
        WHERE occurred_at > :archive_cutoff
      )::int AS active_rows_after_cutoff,
      (SELECT count(*) FROM pending_outbox)::int AS pending_outbox_total,
      (
        SELECT count(*)
        FROM pending_outbox
        WHERE occurred_at <= :archive_cutoff
      )::int AS pending_outbox_before_cutoff,
      (SELECT min(occurred_at) FROM pending_outbox) AS oldest_pending_outbox_at
    """
)

LOCATION_LOG_ARCHIVE_PURPOSE_SQL = text(
    """
    SELECT purpose, count(*)::int AS total
    FROM app.location_access_log
    WHERE occurred_at <= :archive_cutoff
    GROUP BY purpose
    ORDER BY total DESC, purpose ASC
    LIMIT :purpose_limit
    """
)
