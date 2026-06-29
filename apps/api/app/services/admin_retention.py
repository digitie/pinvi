"""Admin retention execution service (T-276)."""

from __future__ import annotations

import json
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.admin import (
    AdminAuditRetentionSummary,
    AdminLocationLogArchiveSummary,
    AdminPiiRetentionSummary,
    AdminRetentionRun,
    AdminRetentionSummary,
)
from app.services.admin_etl import (
    build_audit_retention_summary,
    build_location_log_archive_summary,
    build_pii_retention_summary,
)

RetentionScope = Literal["all", "pii", "location"]


class RetentionExecutionError(Exception):
    code = "RETENTION_EXECUTION_ERROR"


class RetentionKillSwitchDisabledError(RetentionExecutionError):
    code = "RETENTION_KILL_SWITCH_DISABLED"


class RetentionConfirmPhraseError(RetentionExecutionError):
    code = "RETENTION_CONFIRM_PHRASE_INVALID"


class RetentionPrecheckError(RetentionExecutionError):
    code = "RETENTION_PRECHECK_FAILED"


async def build_retention_summary(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    page_size: int = 10,
) -> AdminRetentionSummary:
    current = now or datetime.now(UTC)
    settings = get_settings()
    pii = await build_pii_retention_summary(db, now=current)
    audit = await build_audit_retention_summary(db, now=current)
    location = await build_location_log_archive_summary(db, now=current)
    return AdminRetentionSummary(
        generated_at=current,
        execute_enabled=settings.pinvi_retention_execute_enabled,
        confirm_phrase=settings.pinvi_retention_execute_confirm_phrase,
        pii_retention=pii,
        audit_retention=audit,
        location_log_archive=location,
        latest_runs=await list_retention_runs(db, page_size=page_size),
    )


async def list_retention_runs(
    db: AsyncSession,
    *,
    page_size: int = 20,
) -> list[AdminRetentionRun]:
    rows = (
        await db.execute(
            text(
                """
                SELECT run_id, mode, scope, status, candidate_snapshot, result,
                       kill_switch_enabled, access_reason, actor_user_id, error_message,
                       started_at, completed_at, created_at, updated_at
                FROM app.retention_runs
                ORDER BY created_at DESC
                LIMIT :page_size
                """
            ),
            {"page_size": page_size},
        )
    ).mappings()
    return [_run_from_row(row) for row in rows]


async def create_retention_dry_run(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    scope: RetentionScope,
    access_reason: str,
    now: datetime | None = None,
) -> AdminRetentionRun:
    current = now or datetime.now(UTC)
    pii, audit, location = await _collect_candidates(db, scope=scope, now=current)
    snapshot = _candidate_snapshot(pii, audit, location, scope=scope)
    row = (
        (
            await db.execute(
                _INSERT_RUN_SQL,
                {
                    "mode": "dry_run",
                    "scope": scope,
                    "status": "dry_run",
                    "candidate_snapshot": _json(snapshot),
                    "result": _json({"dry_run": True}),
                    "kill_switch_enabled": False,
                    "confirm_phrase": None,
                    "access_reason": access_reason,
                    "actor_user_id": actor_user_id,
                    "started_at": None,
                    "completed_at": current,
                    "error_message": None,
                },
            )
        )
        .mappings()
        .one()
    )
    return _run_from_row(row)


async def execute_retention(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    scope: RetentionScope,
    access_reason: str,
    confirm_phrase: str,
    now: datetime | None = None,
) -> AdminRetentionRun:
    current = now or datetime.now(UTC)
    settings = get_settings()
    if not settings.pinvi_retention_execute_enabled:
        raise RetentionKillSwitchDisabledError("retention execute kill-switch is disabled")
    if confirm_phrase != settings.pinvi_retention_execute_confirm_phrase:
        raise RetentionConfirmPhraseError("retention execute confirm phrase mismatch")

    pii, audit, location = await _collect_candidates(db, scope=scope, now=current)
    _assert_location_precheck(location, scope=scope)
    snapshot = _candidate_snapshot(pii, audit, location, scope=scope)
    run = (
        (
            await db.execute(
                _INSERT_RUN_SQL,
                {
                    "mode": "execute",
                    "scope": scope,
                    "status": "executing",
                    "candidate_snapshot": _json(snapshot),
                    "result": _json({}),
                    "kill_switch_enabled": True,
                    "confirm_phrase": confirm_phrase,
                    "access_reason": access_reason,
                    "actor_user_id": actor_user_id,
                    "started_at": current,
                    "completed_at": None,
                    "error_message": None,
                },
            )
        )
        .mappings()
        .one()
    )
    run_id = run["run_id"]

    try:
        result: dict[str, Any] = {}
        if scope in ("all", "pii"):
            result["pii"] = await _execute_pii_retention(db, pii=pii, now=current)
        if scope in ("all", "location"):
            result["location"] = await _execute_location_archive(
                db, location=location, run_id=run_id
            )
        if audit:
            result["skipped_admin_audit_pii_over_retention"] = audit.admin_audit_pii_over_retention
        row = (
            (
                await db.execute(
                    _UPDATE_RUN_SQL,
                    {
                        "run_id": run_id,
                        "status": "completed",
                        "result": _json(result),
                        "completed_at": datetime.now(UTC),
                        "error_message": None,
                    },
                )
            )
            .mappings()
            .one()
        )
        return _run_from_row(row)
    except Exception as exc:
        with suppress(Exception):
            await db.execute(
                _UPDATE_RUN_SQL,
                {
                    "run_id": run_id,
                    "status": "failed",
                    "result": _json({"error": type(exc).__name__}),
                    "completed_at": datetime.now(UTC),
                    "error_message": str(exc)[:1000],
                },
            )
        if isinstance(exc, RetentionExecutionError):
            raise
        raise RetentionExecutionError(str(exc)) from exc
    finally:
        with suppress(Exception):
            await db.execute(
                text("SELECT set_config('app.retention_location_delete_allowed', 'off', true)")
            )


async def _collect_candidates(
    db: AsyncSession,
    *,
    scope: RetentionScope,
    now: datetime,
) -> tuple[
    AdminPiiRetentionSummary | None,
    AdminAuditRetentionSummary | None,
    AdminLocationLogArchiveSummary | None,
]:
    pii = await build_pii_retention_summary(db, now=now) if scope in ("all", "pii") else None
    audit = await build_audit_retention_summary(db, now=now) if scope in ("all", "pii") else None
    location = (
        await build_location_log_archive_summary(db, now=now)
        if scope in ("all", "location")
        else None
    )
    return pii, audit, location


def _candidate_snapshot(
    pii: AdminPiiRetentionSummary | None,
    audit: AdminAuditRetentionSummary | None,
    location: AdminLocationLogArchiveSummary | None,
    *,
    scope: RetentionScope,
) -> dict[str, Any]:
    return {
        "scope": scope,
        "pii_retention": None if pii is None else pii.model_dump(mode="json"),
        "audit_retention": None if audit is None else audit.model_dump(mode="json"),
        "location_log_archive": None if location is None else location.model_dump(mode="json"),
    }


def _assert_location_precheck(
    location: AdminLocationLogArchiveSummary | None,
    *,
    scope: RetentionScope,
) -> None:
    if scope not in ("all", "location") or location is None:
        return
    if location.archive_blocked_by_pending_outbox:
        raise RetentionPrecheckError("location archive blocked by pending location_audit_outbox")
    if location.bridge_anchor_matches is False:
        raise RetentionPrecheckError("location archive chain bridge anchor mismatch")


async def _execute_pii_retention(
    db: AsyncSession,
    *,
    pii: AdminPiiRetentionSummary | None,
    now: datetime,
) -> dict[str, int]:
    if pii is None:
        return {}
    row = (
        (
            await db.execute(
                _EXECUTE_PII_SQL,
                {
                    "now": now,
                    "user_pii_cutoff": pii.user_pii_cutoff,
                    "session_cutoff": pii.session_cutoff,
                },
            )
        )
        .mappings()
        .one()
    )
    return {key: _as_int(row[key]) for key in row.keys()}


async def _execute_location_archive(
    db: AsyncSession,
    *,
    location: AdminLocationLogArchiveSummary | None,
    run_id: uuid.UUID,
) -> dict[str, int | bool | None]:
    if location is None:
        return {}
    archive_row = (
        (
            await db.execute(
                _ARCHIVE_LOCATION_SQL,
                {"run_id": run_id, "archive_cutoff": location.archive_cutoff},
            )
        )
        .mappings()
        .one()
    )
    await db.execute(text("SELECT set_config('app.retention_location_delete_allowed', 'on', true)"))
    delete_row = (
        (
            await db.execute(
                _DELETE_ARCHIVED_LOCATION_SQL,
                {"archive_cutoff": location.archive_cutoff},
            )
        )
        .mappings()
        .one()
    )
    return {
        "archived_rows": _as_int(archive_row["archived_rows"]),
        "deleted_active_rows": _as_int(delete_row["deleted_active_rows"]),
        "chain_bridge_required": location.chain_bridge_required,
        "bridge_anchor_matches": location.bridge_anchor_matches,
    }


def _run_from_row(row: Any) -> AdminRetentionRun:
    return AdminRetentionRun(
        run_id=row["run_id"],
        mode=row["mode"],
        scope=row["scope"],
        status=row["status"],
        candidate_snapshot=_dict(row["candidate_snapshot"]),
        result=_dict(row["result"]),
        kill_switch_enabled=bool(row["kill_switch_enabled"]),
        access_reason=row["access_reason"],
        actor_user_id=row["actor_user_id"],
        error_message=row["error_message"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _as_int(value: Any) -> int:
    return int(value or 0)


_INSERT_RUN_SQL = text(
    """
    INSERT INTO app.retention_runs (
      mode, scope, status, candidate_snapshot, result, kill_switch_enabled, confirm_phrase,
      access_reason, actor_user_id, started_at, completed_at, error_message
    )
    VALUES (
      :mode, :scope, :status, CAST(:candidate_snapshot AS jsonb), CAST(:result AS jsonb),
      :kill_switch_enabled, :confirm_phrase, :access_reason, :actor_user_id,
      :started_at, :completed_at, :error_message
    )
    RETURNING run_id, mode, scope, status, candidate_snapshot, result, kill_switch_enabled,
              access_reason, actor_user_id, error_message, started_at, completed_at,
              created_at, updated_at
    """
)

_UPDATE_RUN_SQL = text(
    """
    UPDATE app.retention_runs
    SET status = :status,
        result = CAST(:result AS jsonb),
        completed_at = :completed_at,
        error_message = :error_message
    WHERE run_id = :run_id
    RETURNING run_id, mode, scope, status, candidate_snapshot, result, kill_switch_enabled,
              access_reason, actor_user_id, error_message, started_at, completed_at,
              created_at, updated_at
    """
)

_EXECUTE_PII_SQL = text(
    """
    WITH deleted_users AS (
      SELECT user_id
      FROM app.users
      WHERE status IN ('pending_delete', 'deleted')
        AND deleted_at IS NOT NULL
        AND deleted_at <= :user_pii_cutoff
        AND NOT (roles && ARRAY['admin', 'operator', 'cpo']::varchar[])
    ),
    deleted_identities AS (
      DELETE FROM app.user_oauth_identities identities
      USING deleted_users deleted
      WHERE identities.user_id = deleted.user_id
      RETURNING identities.identity_id
    ),
    anonymized_users AS (
      UPDATE app.users users
      SET email = CASE
            WHEN users.email LIKE 'deleted+%@deleted.pinvi.local' THEN users.email
            ELSE 'deleted+' || users.user_id::text || '@deleted.pinvi.local'
          END,
          password_hash = NULL,
          nickname = NULL,
          avatar_url = NULL,
          avatar_kind = 'default',
          avatar_bucket = NULL,
          avatar_storage_key = NULL,
          avatar_content_type = NULL,
          avatar_byte_size = NULL,
          avatar_updated_at = NULL,
          attachment_max_upload_bytes_override = NULL,
          trip_attachment_quota_bytes_override = NULL,
          user_attachment_quota_bytes_override = NULL,
          gender = NULL,
          birth_year_month = NULL,
          residence_sigungu_code = NULL,
          email_verified_at = NULL,
          email_status = 'suppressed',
          status = 'deleted',
          is_active = false,
          access_token_version = access_token_version + 1
      FROM deleted_users deleted
      WHERE users.user_id = deleted.user_id
      RETURNING users.user_id
    ),
    deleted_signup_verifications AS (
      DELETE FROM app.user_email_verifications
      WHERE purpose = 'signup'
        AND expires_at <= :now
      RETURNING verification_id
    ),
    deleted_password_reset_verifications AS (
      DELETE FROM app.user_email_verifications
      WHERE purpose = 'password_reset'
        AND expires_at <= :now
      RETURNING verification_id
    ),
    deleted_revoked_sessions AS (
      DELETE FROM app.user_sessions
      WHERE revoked_at IS NOT NULL
        AND revoked_at <= :session_cutoff
      RETURNING session_id
    ),
    deleted_expired_sessions AS (
      DELETE FROM app.user_sessions
      WHERE revoked_at IS NULL
        AND expires_at <= :session_cutoff
      RETURNING session_id
    ),
    deleted_oauth_login_states AS (
      DELETE FROM app.oauth_login_states
      WHERE expires_at <= :now
      RETURNING state_hash
    ),
    deleted_mobile_oauth_exchanges AS (
      DELETE FROM app.oauth_mobile_exchanges
      WHERE expires_at <= :now
      RETURNING code_hash
    )
    SELECT
      (SELECT count(*) FROM anonymized_users)::int AS anonymized_users,
      (SELECT count(*) FROM deleted_identities)::int AS deleted_oauth_identities,
      (SELECT count(*) FROM deleted_signup_verifications)::int AS deleted_signup_verifications,
      (SELECT count(*) FROM deleted_password_reset_verifications)::int
        AS deleted_password_reset_verifications,
      (SELECT count(*) FROM deleted_revoked_sessions)::int AS deleted_revoked_sessions,
      (SELECT count(*) FROM deleted_expired_sessions)::int AS deleted_expired_sessions,
      (SELECT count(*) FROM deleted_oauth_login_states)::int AS deleted_oauth_login_states,
      (SELECT count(*) FROM deleted_mobile_oauth_exchanges)::int AS deleted_mobile_oauth_exchanges
    """
)

_ARCHIVE_LOCATION_SQL = text(
    """
    WITH archived AS (
      INSERT INTO app.location_access_log_archive (
        log_id, user_id, occurred_at, endpoint, purpose, lat, lng, request_id, ip_hash,
        prev_hash, content_hash, retention_run_id
      )
      SELECT log_id, user_id, occurred_at, endpoint, purpose, lat, lng, request_id, ip_hash,
             prev_hash, content_hash, :run_id
      FROM app.location_access_log
      WHERE occurred_at <= :archive_cutoff
      ON CONFLICT (log_id) DO NOTHING
      RETURNING log_id
    )
    SELECT count(*)::int AS archived_rows FROM archived
    """
)

_DELETE_ARCHIVED_LOCATION_SQL = text(
    """
    WITH deleted AS (
      DELETE FROM app.location_access_log active
      WHERE active.occurred_at <= :archive_cutoff
        AND EXISTS (
          SELECT 1
          FROM app.location_access_log_archive archive
          WHERE archive.log_id = active.log_id
        )
      RETURNING active.log_id
    )
    SELECT count(*)::int AS deleted_active_rows FROM deleted
    """
)
