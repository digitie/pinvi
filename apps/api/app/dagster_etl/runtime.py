from __future__ import annotations

import os
from uuid import UUID

from krtour_map.dagster import (
    DEFAULT_DAGSTER_DOWNLOAD_DIR,
    DEFAULT_DAGSTER_LOG_DIR,
    KST,
    DagsterEtlExecution,
    DagsterEtlRun,
    EtlIdentityResolver,
    EtlJobSpec,
    EtlLoader,
    EtlRunIdentity,
    JsonValue,
    ScheduleEnabled,
    default_identity,
    execution_from_config,
    json_ready,
    parse_logical_datetime,
    resolve_download_dir,
    resolve_log_dir,
    schedule_is_enabled_by_default,
    schedule_requires_any_env,
    source_year_month_override_from_config,
)
from krtour_map.dagster import (
    EtlSkip as TripMateEtlSkip,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.etl_config import get_etl_dataset_config
from app.models.etl import EtlRunLog
from app.services.etl_runtime import (
    create_etl_run_log,
    has_successful_run,
    mark_etl_run_failed,
    mark_etl_run_skipped,
    mark_etl_run_success,
    should_skip_juso_monthly_update,
)

__all__ = [
    "DEFAULT_DAGSTER_DOWNLOAD_DIR",
    "DEFAULT_DAGSTER_LOG_DIR",
    "KST",
    "DagsterEtlExecution",
    "DagsterEtlRun",
    "EtlIdentityResolver",
    "EtlJobSpec",
    "EtlLoader",
    "EtlRunIdentity",
    "JsonValue",
    "ScheduleEnabled",
    "TripMateEtlSkip",
    "default_identity",
    "execute_etl_spec",
    "execution_from_config",
    "json_ready",
    "juso_monthly_identity",
    "parse_logical_datetime",
    "resolve_download_dir",
    "resolve_log_dir",
    "schedule_is_enabled_by_default",
    "schedule_requires_any_env",
    "source_year_month_override_from_config",
]


def juso_monthly_identity(
    session: Session,
    dataset_key: str,
    execution: DagsterEtlExecution,
) -> EtlRunIdentity:
    logical_date = execution.logical_datetime_kst.date()
    source_year_month_override = source_year_month_override_from_config(execution.op_config)
    if source_year_month_override is None:
        should_skip, run_key, reason = should_skip_juso_monthly_update(
            session,
            logical_date=logical_date,
            dataset_key=dataset_key,
        )
        return EtlRunIdentity(
            run_key=run_key,
            run_type=execution.run_type,
            trigger_date=logical_date,
            should_skip=should_skip,
            skip_message=reason,
            skip_extra={
                "run_key": run_key,
                "reason": reason,
                "source_year_month_override": None,
            },
        )

    should_skip = has_successful_run(
        session,
        dataset_key=dataset_key,
        run_key=source_year_month_override,
    )
    reason = (
        f"{source_year_month_override} Juso 월간 갱신은 이미 성공했다."
        if should_skip
        else f"{source_year_month_override} Juso 월간 주소 데이터 수동 적재"
    )
    return EtlRunIdentity(
        run_key=source_year_month_override,
        run_type="manual",
        trigger_date=logical_date,
        should_skip=should_skip,
        skip_message=reason,
        skip_extra={
            "run_key": source_year_month_override,
            "reason": reason,
            "source_year_month_override": source_year_month_override,
        },
    )


def execute_etl_spec(
    spec: EtlJobSpec,
    execution: DagsterEtlExecution,
    *,
    retry_exhausted: bool,
) -> dict[str, JsonValue]:
    database_url = os.environ["TRIPMATE_DATABASE_URL"]
    runtime_config = get_etl_dataset_config(spec.dataset_key)
    engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    try:
        with session_factory() as log_session:
            resolver = spec.identity_resolver or default_identity
            identity = resolver(log_session, spec.dataset_key, execution)
            run_log = create_etl_run_log(
                log_session,
                dataset_key=spec.dataset_key,
                run_key=identity.run_key,
                run_type=identity.run_type,
                trigger_date=identity.trigger_date,
                config=runtime_config,
            )
            run_log_id = run_log.id
            if identity.should_skip:
                payload = identity.skip_extra or {"reason": identity.skip_message or "skipped"}
                mark_etl_run_skipped(
                    run_log,
                    message=identity.skip_message or "ETL skipped.",
                    extra=payload,
                )
                log_session.commit()
                return {"status": "skipped", **payload}
            log_session.commit()

        run_context = DagsterEtlRun(
            dataset_key=spec.dataset_key,
            run_key=identity.run_key,
            run_type=identity.run_type,
            trigger_date=identity.trigger_date,
            logical_datetime=execution.logical_datetime_kst,
            op_config=execution.op_config,
        )

        try:
            with session_factory() as load_session:
                result = spec.loader(load_session, run_context)
                load_session.commit()

            payload = json_ready(result)
            with session_factory() as log_session:
                run_log = _get_run_log(log_session, run_log_id)
                mark_etl_run_success(
                    run_log,
                    message=spec.success_message.format(dataset_key=spec.dataset_key),
                    extra=payload,
                )
                log_session.commit()
            return payload
        except TripMateEtlSkip as exc:
            payload = {"skip_reason": type(exc).__name__, "message": str(exc)}
            with session_factory() as log_session:
                run_log = _get_run_log(log_session, run_log_id)
                mark_etl_run_skipped(run_log, message=str(exc), extra=payload)
                log_session.commit()
            return {"status": "skipped", **payload}
        except Exception as exc:
            with session_factory() as log_session:
                run_log = _get_run_log(log_session, run_log_id)
                mark_etl_run_failed(
                    log_session,
                    run_log,
                    error=exc,
                    message=spec.failure_message.format(dataset_key=spec.dataset_key),
                    exhausted=retry_exhausted,
                    config=runtime_config,
                )
                log_session.commit()
            raise
    finally:
        engine.dispose()


def _get_run_log(session: Session, run_log_id: UUID) -> EtlRunLog:
    run_log = session.get(EtlRunLog, run_log_id)
    if run_log is None:
        raise RuntimeError(f"ETL run log not found: {run_log_id}")
    return run_log
