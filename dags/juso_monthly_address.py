from __future__ import annotations

import os
import re
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

DAG_ID = "juso_monthly_address_dataset"
DATASET_KEY = "juso_road_address_korean"
DEFAULT_DOWNLOAD_DIR = "/tmp/tripmate-airflow/juso-address"


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

_RUNTIME_CONFIG = get_etl_dataset_config(DATASET_KEY)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


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


def _current_dag_conf() -> dict[str, Any]:
    try:
        from airflow.sdk import get_current_context
    except Exception:
        try:
            from airflow.operators.python import get_current_context
        except Exception:
            return {}

    try:
        context = get_current_context()
    except Exception:
        return {}

    dag_run = context.get("dag_run")
    conf = getattr(dag_run, "conf", None)
    if isinstance(conf, dict):
        return conf
    return {}


def _source_year_month_override_from_conf(conf: dict[str, Any]) -> str | None:
    value = conf.get("source_year_month")
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{6}", value):
        raise ValueError("source_year_month conf must be a YYYYMM string.")
    month = int(value[4:6])
    if month < 1 or month > 12:
        raise ValueError("source_year_month conf month must be between 01 and 12.")
    return value


@dag(
    dag_id=DAG_ID,
    description="Juso 도로명주소 한글 전체분과 관련 지번 TXT를 월 1회 갱신한다.",
    schedule=_RUNTIME_CONFIG.schedule,
    start_date=datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _RUNTIME_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_RUNTIME_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "address", "juso"],
)
def juso_monthly_address_dataset() -> None:
    @task(task_id="download_and_load_juso_monthly_address")
    def download_and_load() -> dict[str, Any]:
        database_url = os.environ["TRIPMATE_DATABASE_URL"]
        download_dir = Path(os.environ.get("TRIPMATE_AIRFLOW_DOWNLOAD_DIR", DEFAULT_DOWNLOAD_DIR))
        logical_date = _current_airflow_datetime().astimezone(ZoneInfo("Asia/Seoul")).date()
        source_year_month_override = _source_year_month_override_from_conf(_current_dag_conf())

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.etl.juso.pipeline import download_and_load_juso_address_dataset
        from app.models.etl import EtlRunLog
        from app.services.etl_runtime import (
            create_etl_run_log,
            has_successful_run,
            mark_etl_run_failed,
            mark_etl_run_skipped,
            mark_etl_run_success,
            should_skip_juso_monthly_update,
        )

        engine = create_engine(database_url, pool_pre_ping=True)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        try:
            with session_factory() as log_session:
                if source_year_month_override is None:
                    should_skip, run_key, reason = should_skip_juso_monthly_update(
                        log_session,
                        logical_date=logical_date,
                        dataset_key=DATASET_KEY,
                    )
                    run_type = "scheduled"
                else:
                    run_key = source_year_month_override
                    should_skip = has_successful_run(
                        log_session,
                        dataset_key=DATASET_KEY,
                        run_key=run_key,
                    )
                    reason = (
                        f"{run_key} Juso 월간 갱신은 이미 성공했다."
                        if should_skip
                        else f"{run_key} Juso 월간 주소 데이터 수동 적재"
                    )
                    run_type = "manual"
                run_log = create_etl_run_log(
                    log_session,
                    dataset_key=DATASET_KEY,
                    run_key=run_key,
                    run_type=run_type,
                    trigger_date=logical_date,
                    config=_RUNTIME_CONFIG,
                )
                run_log_id = run_log.id
                if should_skip:
                    payload = {
                        "run_key": run_key,
                        "reason": reason,
                        "source_year_month_override": source_year_month_override,
                    }
                    mark_etl_run_skipped(run_log, message=reason, extra=payload)
                    log_session.commit()
                    return payload
                log_session.commit()

            try:
                with session_factory() as load_session:
                    result = download_and_load_juso_address_dataset(
                        load_session,
                        download_dir,
                        source_year_month=run_key,
                    )
                    load_session.commit()

                payload = _json_ready(asdict(result))
                payload["download_dir"] = str(download_dir)
                payload["source_year_month_override"] = source_year_month_override
                with session_factory() as log_session:
                    run_log = log_session.get(EtlRunLog, run_log_id)
                    if run_log is None:
                        raise RuntimeError(f"ETL run log not found: {run_log_id}")
                    mark_etl_run_success(
                        run_log,
                        message="Juso 월간 주소 데이터 갱신 성공",
                        extra=payload,
                    )
                    log_session.commit()
                return payload
            except Exception as exc:
                retry_exhausted = _is_airflow_retry_exhausted()
                with session_factory() as log_session:
                    run_log = log_session.get(EtlRunLog, run_log_id)
                    if run_log is None:
                        raise RuntimeError(f"ETL run log not found: {run_log_id}") from exc
                    mark_etl_run_failed(
                        log_session,
                        run_log,
                        error=exc,
                        message="Juso 월간 주소 데이터 갱신 실패",
                        exhausted=retry_exhausted,
                        config=_RUNTIME_CONFIG,
                    )
                    log_session.commit()
                raise
        finally:
            engine.dispose()

    download_and_load()


juso_monthly_address_dataset()
