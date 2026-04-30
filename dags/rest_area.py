from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

MASTER_DAG_ID = "rest_area_master_monthly"
OIL_PRICE_DAG_ID = "rest_area_oil_price_daily"
SERVICE_DAG_ID = "rest_area_service_monthly"
MASTER_DATASET_KEY = "rest_area_master"
OIL_PRICE_DATASET_KEY = "rest_area_oil_price"
SERVICE_DATASET_KEY = "rest_area_svcs"
DEFAULT_FK_MISMATCH_LOG_DIR = "/opt/tripmate/.tmp/airflow-logs/etl/rest_area_fk_mismatch"


def _ensure_api_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    candidates = [
        Path(os.environ["TRIPMATE_API_DIR"]) if os.environ.get("TRIPMATE_API_DIR") else None,
        repo_root / "apps" / "api",
        Path("/opt/tripmate/apps/api"),
    ]
    for api_dir in candidates:
        if api_dir is None:
            continue
        api_path = str(api_dir)
        if api_dir.exists() and api_path not in sys.path:
            sys.path.insert(0, api_path)


_ensure_api_on_path()

from app.core.etl_config import get_etl_dataset_config  # noqa: E402

_MASTER_RUNTIME_CONFIG = get_etl_dataset_config(MASTER_DATASET_KEY)
_OIL_PRICE_RUNTIME_CONFIG = get_etl_dataset_config(OIL_PRICE_DATASET_KEY)
_SERVICE_RUNTIME_CONFIG = get_etl_dataset_config(SERVICE_DATASET_KEY)


def _is_airflow_retry_exhausted() -> bool:
    try:
        from airflow.sdk import get_current_context
    except Exception:
        try:
            from airflow.operators.python import get_current_context
        except Exception:
            return True

    try:
        context = get_current_context()
    except Exception:
        return True

    task_instance = context.get("ti") or context.get("task_instance")
    if task_instance is None:
        return True

    is_eligible_to_retry = getattr(task_instance, "is_eligible_to_retry", None)
    if callable(is_eligible_to_retry):
        return not bool(is_eligible_to_retry())
    return True


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _current_airflow_datetime() -> datetime:
    try:
        from airflow.sdk import get_current_context
    except Exception:
        try:
            from airflow.operators.python import get_current_context
        except Exception:
            return datetime.now(ZoneInfo("Asia/Seoul"))

    try:
        context = get_current_context()
    except Exception:
        return datetime.now(ZoneInfo("Asia/Seoul"))

    value = (
        context.get("logical_date")
        or context.get("data_interval_start")
        or context.get("run_after")
    )
    if isinstance(value, datetime):
        return value
    return datetime.now(ZoneInfo("Asia/Seoul"))


@dag(
    dag_id=MASTER_DAG_ID,
    description="한국도로공사 휴게소 기본정보를 월 1회 수집한다.",
    schedule=_MASTER_RUNTIME_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _MASTER_RUNTIME_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_MASTER_RUNTIME_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "rest-area", "expressway", "master"],
)
def rest_area_master_monthly() -> None:
    @task(task_id="load_rest_area_master")
    def load_master() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key=MASTER_DATASET_KEY,
            logical_datetime=_current_airflow_datetime(),
            load=_load_master,
        )

    load_master()


@dag(
    dag_id=OIL_PRICE_DAG_ID,
    description="한국도로공사 휴게소 주유소 가격/업체 현황을 하루 2회 수집한다.",
    schedule=_OIL_PRICE_RUNTIME_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _OIL_PRICE_RUNTIME_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_OIL_PRICE_RUNTIME_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "rest-area", "expressway", "oil-price"],
)
def rest_area_oil_price_daily() -> None:
    @task(task_id="load_rest_area_oil_prices")
    def load_oil_prices() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key=OIL_PRICE_DATASET_KEY,
            logical_datetime=_current_airflow_datetime(),
            load=lambda session, run_key, collected_at: _load_oil_prices(
                session,
                run_key,
                collected_at,
            ),
        )

    load_oil_prices()


@dag(
    dag_id=SERVICE_DAG_ID,
    description="한국도로공사 휴게소 편의시설 현황을 월 1회 수집한다.",
    schedule=_SERVICE_RUNTIME_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _SERVICE_RUNTIME_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_SERVICE_RUNTIME_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "rest-area", "expressway", "service"],
)
def rest_area_service_monthly() -> None:
    @task(task_id="load_rest_area_services")
    def load_services() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key=SERVICE_DATASET_KEY,
            logical_datetime=_current_airflow_datetime(),
            load=lambda session, run_key, collected_at: _load_services(
                session,
                run_key,
                collected_at,
            ),
        )

    load_services()


def _run_logged_task(
    *,
    dataset_key: str,
    logical_datetime: datetime,
    load: Any,
) -> dict[str, Any]:
    database_url = os.environ["TRIPMATE_DATABASE_URL"]

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.etl_config import get_etl_dataset_config
    from app.models.etl import EtlRunLog
    from app.services.etl_runtime import (
        create_etl_run_log,
        mark_etl_run_failed,
        mark_etl_run_success,
    )

    runtime_config = get_etl_dataset_config(dataset_key)
    logical_datetime_kst = logical_datetime.astimezone(ZoneInfo("Asia/Seoul"))
    run_key = logical_datetime_kst.strftime("%Y%m%dT%H%M%S")
    trigger_date = logical_datetime_kst.date()
    engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    try:
        with session_factory() as log_session:
            run_log = create_etl_run_log(
                log_session,
                dataset_key=dataset_key,
                run_key=run_key,
                run_type="scheduled",
                trigger_date=trigger_date,
                config=runtime_config,
            )
            run_log_id = run_log.id
            log_session.commit()

        try:
            with session_factory() as load_session:
                result = load(load_session, run_key, logical_datetime_kst)
                load_session.commit()

            payload = _json_ready(asdict(result))
            with session_factory() as log_session:
                resolved_run_log = log_session.get(EtlRunLog, run_log_id)
                if resolved_run_log is None:
                    raise RuntimeError(f"ETL run log not found: {run_log_id}")
                mark_etl_run_success(
                    resolved_run_log,
                    message=f"한국도로공사 휴게소 ETL 성공: {dataset_key}",
                    extra=payload,
                )
                log_session.commit()
            return payload
        except Exception as exc:
            retry_exhausted = _is_airflow_retry_exhausted()
            with session_factory() as log_session:
                resolved_run_log = log_session.get(EtlRunLog, run_log_id)
                if resolved_run_log is None:
                    raise RuntimeError(f"ETL run log not found: {run_log_id}") from exc
                mark_etl_run_failed(
                    log_session,
                    resolved_run_log,
                    error=exc,
                    message=f"한국도로공사 휴게소 ETL 실패: {dataset_key}",
                    exhausted=retry_exhausted,
                    config=runtime_config,
                )
                log_session.commit()
            raise
    finally:
        engine.dispose()


def _parse_airflow_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(value), datetime.min.time())
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return parsed


def _fk_mismatch_log_dir() -> Path:
    log_root = os.environ.get("TRIPMATE_AIRFLOW_LOG_DIR")
    if log_root:
        return Path(log_root) / "etl" / "rest_area_fk_mismatch"
    return Path(DEFAULT_FK_MISMATCH_LOG_DIR)


def _load_master(session: Any, run_key: str, collected_at: datetime) -> Any:
    _ = run_key
    from app.etl.rest_area.client import ExpresswayApiClient
    from app.etl.rest_area.loader import load_rest_area_master

    return load_rest_area_master(session, ExpresswayApiClient(), collected_at=collected_at)


def _load_oil_prices(session: Any, run_key: str, collected_at: datetime) -> Any:
    from app.etl.rest_area.client import ExpresswayApiClient
    from app.etl.rest_area.loader import load_rest_area_oil_prices

    return load_rest_area_oil_prices(
        session,
        ExpresswayApiClient(),
        collected_at=collected_at,
        fk_mismatch_log_dir=_fk_mismatch_log_dir(),
        run_id=run_key,
    )


def _load_services(session: Any, run_key: str, collected_at: datetime) -> Any:
    from app.etl.rest_area.client import ExpresswayApiClient
    from app.etl.rest_area.loader import load_rest_area_services

    return load_rest_area_services(
        session,
        ExpresswayApiClient(),
        collected_at=collected_at,
        fk_mismatch_log_dir=_fk_mismatch_log_dir(),
        run_id=run_key,
    )


rest_area_master_monthly()
rest_area_oil_price_daily()
rest_area_service_monthly()
