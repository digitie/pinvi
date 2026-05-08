from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.etl_config import get_etl_dataset_config
from app.core.json_types import JsonValue
from app.models.etl import EtlRunLog
from app.services.etl_runtime import (
    create_etl_run_log,
    has_successful_run,
    mark_etl_run_failed,
    mark_etl_run_skipped,
    mark_etl_run_success,
    should_skip_juso_monthly_update,
)

KST = ZoneInfo("Asia/Seoul")
DEFAULT_DAGSTER_DOWNLOAD_DIR = "/tmp/tripmate-dagster/downloads"
DEFAULT_DAGSTER_LOG_DIR = "/opt/tripmate/.tmp/dagster-logs"


class TripMateEtlSkip(Exception):
    """Skip an ETL run without treating provider/data absence as a failure."""


@dataclass(frozen=True)
class DagsterEtlExecution:
    logical_datetime: datetime
    run_type: str
    op_config: Mapping[str, object]

    @property
    def logical_datetime_kst(self) -> datetime:
        return self.logical_datetime.astimezone(KST)


@dataclass(frozen=True)
class DagsterEtlRun:
    dataset_key: str
    run_key: str
    run_type: str
    trigger_date: date
    logical_datetime: datetime
    op_config: Mapping[str, object]

    @property
    def collected_at(self) -> datetime:
        return self.logical_datetime.astimezone(KST)


@dataclass(frozen=True)
class EtlRunIdentity:
    run_key: str
    run_type: str
    trigger_date: date
    should_skip: bool = False
    skip_message: str | None = None
    skip_extra: dict[str, JsonValue] | None = None


EtlLoader = Callable[[Session, DagsterEtlRun], object]
EtlIdentityResolver = Callable[[Session, str, DagsterEtlExecution], EtlRunIdentity]
ScheduleEnabled = Callable[[], bool]


@dataclass(frozen=True)
class EtlJobSpec:
    job_name: str
    op_name: str
    dataset_key: str
    description: str
    tags: tuple[str, ...]
    loader: EtlLoader
    success_message: str
    failure_message: str
    identity_resolver: EtlIdentityResolver | None = None
    schedule_enabled: ScheduleEnabled | None = None


def parse_logical_datetime(value: object | None) -> datetime:
    if value is None:
        return datetime.now(KST)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.combine(date.fromisoformat(value), datetime.min.time())
    else:
        raise TypeError("logical_datetime must be an ISO datetime/date string.")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def source_year_month_override_from_config(config: Mapping[str, object]) -> str | None:
    value = config.get("source_year_month")
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{6}", value):
        raise ValueError("source_year_month config must be a YYYYMM string.")
    month = int(value[4:6])
    if month < 1 or month > 12:
        raise ValueError("source_year_month config month must be between 01 and 12.")
    return value


def execution_from_config(config: Mapping[str, object]) -> DagsterEtlExecution:
    run_type = config.get("run_type", "manual")
    if run_type not in ("manual", "scheduled"):
        raise ValueError("run_type must be 'manual' or 'scheduled'.")
    return DagsterEtlExecution(
        logical_datetime=parse_logical_datetime(config.get("logical_datetime")),
        run_type=str(run_type),
        op_config=config,
    )


def default_identity(
    _session: Session,
    _dataset_key: str,
    execution: DagsterEtlExecution,
) -> EtlRunIdentity:
    logical_datetime = execution.logical_datetime_kst
    return EtlRunIdentity(
        run_key=logical_datetime.strftime("%Y%m%dT%H%M%S"),
        run_type=execution.run_type,
        trigger_date=logical_datetime.date(),
    )


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


def json_ready(value: object) -> dict[str, JsonValue]:
    converted = _json_ready(value)
    if isinstance(converted, dict):
        return converted
    return {"value": converted}


def _json_ready(value: object) -> JsonValue:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_ready(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def resolve_download_dir(dataset_slug: str) -> Path:
    root = os.environ.get("TRIPMATE_DAGSTER_DOWNLOAD_DIR") or DEFAULT_DAGSTER_DOWNLOAD_DIR
    return Path(root) / dataset_slug


def resolve_log_dir() -> Path:
    root = os.environ.get("TRIPMATE_DAGSTER_LOG_DIR") or DEFAULT_DAGSTER_LOG_DIR
    return Path(root)


def schedule_is_enabled_by_default() -> bool:
    return True


def schedule_requires_any_env(*names: str) -> ScheduleEnabled:
    def enabled() -> bool:
        return any(bool(os.environ.get(name)) for name in names)

    return enabled


def _get_run_log(session: Session, run_log_id: UUID) -> EtlRunLog:
    run_log = session.get(EtlRunLog, run_log_id)
    if run_log is None:
        raise RuntimeError(f"ETL run log not found: {run_log_id}")
    return run_log
