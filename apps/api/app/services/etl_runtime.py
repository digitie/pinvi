from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, cast

from sqlalchemy import exists, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, object_session

from app.core.etl_config import EtlDatasetRuntimeConfig, get_etl_dataset_config
from app.core.redaction import redact_sensitive_text
from app.models.etl import AdminNotification, EtlRunLog, TelegramSystemNotificationOutbox
from app.models.mixins import kst_now
from app.models.trip import Trip

ETL_STATUS_STARTED = "started"
ETL_STATUS_SUCCESS = "success"
ETL_STATUS_SKIPPED = "skipped"
ETL_STATUS_FAILED = "failed"


def has_trip_on_date(session: Session, target_date: date) -> bool:
    statement = select(
        exists()
        .where(Trip.start_date.is_not(None))
        .where(Trip.end_date.is_not(None))
        .where(Trip.start_date <= target_date)
        .where(Trip.end_date >= target_date)
    )
    return bool(session.scalar(statement))


def has_successful_run(
    session: Session,
    *,
    dataset_key: str,
    run_key: str,
) -> bool:
    statement = select(
        exists()
        .where(EtlRunLog.dataset_key == dataset_key)
        .where(EtlRunLog.run_key == run_key)
        .where(EtlRunLog.status == ETL_STATUS_SUCCESS)
    )
    return bool(session.scalar(statement))


def create_etl_run_log(
    session: Session,
    *,
    dataset_key: str,
    run_key: str | None,
    run_type: str,
    trigger_date: date | None,
    status: str = ETL_STATUS_STARTED,
    message: str | None = None,
    extra: dict[str, Any] | None = None,
    config: EtlDatasetRuntimeConfig | None = None,
) -> EtlRunLog:
    runtime_config = config or get_etl_dataset_config(dataset_key)
    _close_previous_started_runs(session, dataset_key=dataset_key, run_key=run_key)
    run_log = EtlRunLog(
        dataset_key=dataset_key,
        run_key=run_key,
        run_type=run_type,
        status=status,
        trigger_date=trigger_date,
        attempt_count=0,
        max_attempts=runtime_config.retry_max_attempts,
        retry_interval_seconds=runtime_config.retry_interval_seconds,
        message=message,
        extra=extra or {},
    )
    session.add(run_log)
    session.flush()
    return run_log


def _close_previous_started_runs(
    session: Session,
    *,
    dataset_key: str,
    run_key: str | None,
) -> None:
    statement = (
        update(EtlRunLog)
        .where(EtlRunLog.dataset_key == dataset_key)
        .where(EtlRunLog.status == ETL_STATUS_STARTED)
        .values(
            status=ETL_STATUS_SKIPPED,
            finished_at=kst_now(),
            message="후속 ETL 실행으로 미완료 started 로그를 종료 처리했다.",
        )
    )
    if run_key is None:
        statement = statement.where(EtlRunLog.run_key.is_(None))
    else:
        statement = statement.where(EtlRunLog.run_key == run_key)
    session.execute(statement)


def mark_etl_run_success(
    run_log: EtlRunLog,
    *,
    message: str,
    extra: dict[str, Any] | None = None,
) -> None:
    run_log.status = ETL_STATUS_SUCCESS
    run_log.finished_at = kst_now()
    run_log.message = message
    if extra is not None:
        run_log.extra = {**run_log.extra, **extra}
    _resolve_previous_failure_notifications(run_log)


def mark_etl_run_skipped(
    run_log: EtlRunLog,
    *,
    message: str,
    extra: dict[str, Any] | None = None,
) -> None:
    run_log.status = ETL_STATUS_SKIPPED
    run_log.finished_at = kst_now()
    run_log.message = message
    if extra is not None:
        run_log.extra = {**run_log.extra, **extra}
    _resolve_previous_failure_notifications(run_log)


def mark_etl_run_failed(
    session: Session,
    run_log: EtlRunLog,
    *,
    error: BaseException,
    message: str,
    log_file_path: str | None = None,
    exhausted: bool = True,
    config: EtlDatasetRuntimeConfig | None = None,
) -> None:
    runtime_config = config or get_etl_dataset_config(run_log.dataset_key)
    safe_message = redact_sensitive_text(message) or message
    safe_error_message = redact_sensitive_text(str(error)) or str(error)
    run_log.status = ETL_STATUS_FAILED
    run_log.finished_at = kst_now()
    run_log.message = safe_message
    run_log.error_type = type(error).__name__
    run_log.error_message = safe_error_message
    run_log.log_file_path = log_file_path
    run_log.extra = {
        **run_log.extra,
        "retry_exhausted": exhausted,
        "runtime_config": asdict(runtime_config),
    }

    if exhausted and runtime_config.failure_admin_notification_enabled:
        session.add(
            AdminNotification(
                recipient_scope="admins",
                severity="error",
                title=f"ETL 실패: {run_log.dataset_key}",
                message=safe_message,
                source="etl",
                dataset_key=run_log.dataset_key,
                etl_run_log_id=run_log.id,
                is_read=False,
                is_resolved=False,
            )
        )

    if exhausted and runtime_config.failure_telegram_notification_enabled:
        session.add(
            TelegramSystemNotificationOutbox(
                recipient_scope="privileged_admins",
                dataset_key=run_log.dataset_key,
                etl_run_log_id=run_log.id,
                title=f"ETL 실패: {run_log.dataset_key}",
                message=safe_message,
                status="pending",
                payload={
                    "dataset_key": run_log.dataset_key,
                    "run_key": run_log.run_key,
                    "error_type": run_log.error_type,
                    "error_message": run_log.error_message,
                },
            )
        )


def _resolve_previous_failure_notifications(run_log: EtlRunLog) -> None:
    session = object_session(run_log)
    if session is None:
        return

    session.execute(
        update(AdminNotification)
        .where(AdminNotification.dataset_key == run_log.dataset_key)
        .where(AdminNotification.is_resolved.is_(False))
        .values(is_resolved=True)
    )
    session.execute(
        update(TelegramSystemNotificationOutbox)
        .where(TelegramSystemNotificationOutbox.dataset_key == run_log.dataset_key)
        .where(TelegramSystemNotificationOutbox.status == "pending")
        .values(
            status="cancelled",
            error_message=f"후속 ETL 성공으로 취소됨: {run_log.id}",
        )
    )


def reconcile_recovered_failure_notifications(session: Session) -> int:
    """Resolve stale ETL failure notifications after a later non-failed run."""
    failed_run = EtlRunLog.__table__.alias("failed_run")
    recovered_run = EtlRunLog.__table__.alias("recovered_run")
    recovered_exists = (
        select(recovered_run.c.id)
        .where(recovered_run.c.dataset_key == AdminNotification.dataset_key)
        .where(recovered_run.c.status.in_([ETL_STATUS_SUCCESS, ETL_STATUS_SKIPPED]))
        .where(recovered_run.c.finished_at.is_not(None))
        .where(recovered_run.c.finished_at > failed_run.c.finished_at)
        .where(failed_run.c.id == AdminNotification.etl_run_log_id)
        .exists()
    )
    notification_statement = (
        update(AdminNotification)
        .where(AdminNotification.is_resolved.is_(False))
        .where(recovered_exists)
        .values(is_resolved=True)
    )
    notification_result = cast(CursorResult[Any], session.execute(notification_statement))
    outbox_statement = (
        update(TelegramSystemNotificationOutbox)
        .where(TelegramSystemNotificationOutbox.status == "pending")
        .where(
            select(recovered_run.c.id)
            .where(recovered_run.c.dataset_key == TelegramSystemNotificationOutbox.dataset_key)
            .where(recovered_run.c.status.in_([ETL_STATUS_SUCCESS, ETL_STATUS_SKIPPED]))
            .where(recovered_run.c.finished_at.is_not(None))
            .where(recovered_run.c.finished_at > failed_run.c.finished_at)
            .where(failed_run.c.id == TelegramSystemNotificationOutbox.etl_run_log_id)
            .exists()
        )
        .values(status="cancelled", error_message="후속 ETL 회복 상태로 취소됨")
    )
    session.execute(outbox_statement)
    return int(notification_result.rowcount or 0)


def juso_run_key_for_date(logical_date: date) -> str:
    target_year = logical_date.year
    target_month = logical_date.month - 1
    if target_month == 0:
        target_year -= 1
        target_month = 12
    return f"{target_year:04d}{target_month:02d}"


def should_skip_juso_monthly_update(
    session: Session,
    *,
    logical_date: date,
    dataset_key: str = "juso_road_address_korean",
) -> tuple[bool, str, str]:
    run_key = juso_run_key_for_date(logical_date)
    if logical_date.day < 10:
        return True, run_key, "Juso 월간 갱신은 매월 10일 이후에만 실행한다."
    if has_successful_run(session, dataset_key=dataset_key, run_key=run_key):
        return True, run_key, f"{run_key} Juso 월간 갱신은 이미 성공했다."
    if has_trip_on_date(session, logical_date):
        return True, run_key, "실행일이 DB 여행계획 날짜에 포함되어 Juso 갱신을 건너뛴다."
    return False, run_key, "Juso 월간 갱신 실행 가능"
