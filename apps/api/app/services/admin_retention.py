"""Admin retention execution service (T-276)."""

from __future__ import annotations

import json
import logging
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


logger = logging.getLogger(__name__)


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
    # 영수증 행은 **파괴적 작업과 같은 트랜잭션에 두지 않는다**(T-338). 같이 두면 실패 시 라우트의
    # `rollback()`이 작업과 함께 영수증까지 지워, "무엇을 시도했고 어디서 멈췄는가"가 남지 않는다.
    # 먼저 독립적으로 커밋해 두면 이후 어떤 롤백에도 살아남는다.
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
    await db.commit()

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
        # **`BaseException`으로 넓히지 않는다.** 취소(`CancelledError`)를 잡고 나서 `await`를 하면
        # 두 가지 중 하나가 일어나는데 둘 다 좋지 않다 — 취소 스코프 안이면 그 `await`가 즉시
        # 되던져져 원래 예외를 가리고, 아니면 종료 중에 DB I/O를 기다리며 셧다운을 지연시킨다.
        # 얻는 것도 없다: 이 배포에서 `CancelledError`는 클라이언트 끊김으로도(uvicorn이
        # `disconnected` 플래그만 세운다) SIGTERM으로도(graceful timeout 미설정 → cancel 없음)
        # 발생하지 않는다. 취소 중 영수증이 남지 않는 것은 알려진 한계이며 그렇게 문서화한다.
        await record_retention_run_failure(db, run_id, exc)
        if isinstance(exc, RetentionExecutionError):
            raise
        raise RetentionExecutionError(str(exc)) from exc
    finally:
        # 트랜잭션이 살아 있을 때만 되돌린다. 실패 경로에서는 `record_retention_run_failure`가 이미
        # rollback+commit으로 트랜잭션을 끝냈으므로, 여기서 문장을 실행하면 **새 트랜잭션이 열리고
        # 아무도 닫지 않는다** — 세션이 `idle in transaction`으로 반환된다.
        # 애초에 이 GUC는 `is_local=true`라 트랜잭션이 끝나면 함께 사라진다. 이 블록은 성공 경로에서
        # 커밋 전에 창을 좁히는 방어일 뿐이다.
        if db.in_transaction():
            with suppress(Exception):
                await db.execute(
                    text("SELECT set_config('app.retention_location_delete_allowed', 'off', true)")
                )


async def record_retention_run_failure(
    db: AsyncSession, run_id: uuid.UUID, exc: BaseException
) -> None:
    """실패 사실을 영수증에 남긴다. **호출부의 트랜잭션을 끝낸다.**

    먼저 rollback하는 것이 이 함수의 핵심이고, 두 가지가 동시에 해소된다.

    1. 원인이 DB 오류면 트랜잭션이 abort 상태라 어떤 문장도 실행되지 않는다. rollback이 그것을 푼다.
    2. `completed` UPDATE가 **성공한 뒤** 실패하면 그 행에 `FOR NO KEY UPDATE` 락이 남아 있다.
       그 상태에서 별도 세션으로 같은 행을 UPDATE하면 **무기한 블록된다** — 대기 그래프에 간선이
       하나뿐이라 PostgreSQL이 deadlock으로 탐지하지 못하고, 이 프로세스에는 `lock_timeout`도
       `statement_timeout`도 설정돼 있지 않다. rollback이 락을 먼저 놓아 그 창을 없앤다.

    그 뒤 commit해야 호출부의 `rollback()`을 견딘다(T-338). 즉 이 함수는 실패 경로에서 파괴적
    작업의 폐기와 영수증 보존을 **한 세션 안에서** 끝낸다 — 두 번째 커넥션이 필요 없어진다.

    **계약**: 이 함수는 호출부의 트랜잭션을 끝내고, 그 부작용으로 **세션의 모든 ORM 인스턴스가
    만료된다**(SQLAlchemy rollback 규약). 이 라우트에서는 RBAC가 적재한 `admin: User`가 해당하는데
    호출 이후 그것을 읽는 코드가 없어 지금은 무해하다. 이 함수를 부른 뒤 ORM 속성을 읽으면 새
    SELECT가 나가거나(새 트랜잭션) 세션이 닫힌 뒤라면 예외가 난다.

    실패해도 예외를 올리지 않는다. 원래 예외를 가리는 것이 더 나쁘기 때문이다. 다만 조용히 넘기지는
    않는다 — 영수증을 못 남긴 사실 자체가 기록돼야 한다.
    """
    try:
        await db.rollback()
        outcome = await db.execute(
            _FAIL_RUN_SQL,
            {
                "run_id": run_id,
                "result": _json({"error": type(exc).__name__}),
                "completed_at": datetime.now(UTC),
                "error_message": str(exc)[:1000],
            },
        )
        await db.commit()
        if outcome.rowcount == 0:  # type: ignore[attr-defined]  # CursorResult에는 있다
            # 가드가 막았다 = 이 run은 이미 종결 상태다. 거의 확실히 커밋 ack 유실이며, 파괴 작업은
            # **실제로 수행됐다**. 조용히 넘기면 영수증과 예외가 어긋난 채로 아무도 모른다.
            logger.error(
                "retention run %s: 실패를 기록하려 했으나 이미 종결 상태다 "
                "(커밋 ack 유실 가능성 — 작업은 수행됐을 수 있다)",
                run_id,
            )
    except Exception:
        logger.exception("retention run %s 실패 영수증을 남기지 못했다", run_id)


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

#: 실패 영수증 전용. **`executing`인 run만** 바꾼다.
#:
#: 커밋이 서버에서는 성공했는데 ack가 유실되면 호출부는 예외를 보고, 그 run은 실제로 `completed`로
#: 커밋돼 있다. 가드 없이 덮으면 **파괴 작업이 실제로 수행된 run에 "아무것도 지우지 않았다"라고
#: 새기게 된다** — `failed`의 의미를 정반대로 뒤집는 기록이다.
_FAIL_RUN_SQL = text(
    """
    UPDATE app.retention_runs
    SET status = 'failed',
        result = CAST(:result AS jsonb),
        completed_at = :completed_at,
        error_message = :error_message
    WHERE run_id = :run_id AND status = 'executing'
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

#: 아카이브는 **무손실 사본**이어야 한다. 컬럼을 명시 나열하므로 원본에 컬럼이 늘면 여기도 함께
#: 늘려야 하고, 잊으면 오류 없이 조용히 빠진 채 원본이 삭제된다(T-332가 그렇게 깨졌다). 두 테이블의
#: 컬럼 집합 일치는 `tests/integration/test_retention_archive_fidelity.py`가 강제한다.
_ARCHIVE_LOCATION_SQL = text(
    """
    WITH archived AS (
      INSERT INTO app.location_access_log_archive (
        log_id, user_id, occurred_at, endpoint, purpose, coord_source, lat, lng,
        request_id, ip_hash, prev_hash, content_hash, retention_run_id
      )
      SELECT log_id, user_id, occurred_at, endpoint, purpose, coord_source, lat, lng,
             request_id, ip_hash, prev_hash, content_hash, :run_id
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
