from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

DAG_ID = "legal_dong_code_standard_quarterly"
DEFAULT_DOWNLOAD_DIR = "/tmp/tripmate-airflow/legal-dong-code-standard"
DATASET_KEY = "legal_dong_code_standard"


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


@dag(
    dag_id=DAG_ID,
    description="Download data.go.kr legal-dong code CSV and refresh TripMate code standard.",
    schedule=_RUNTIME_CONFIG.schedule,
    start_date=datetime(2026, 5, 15, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _RUNTIME_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_RUNTIME_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "address", "legal-dong-code", "data-go"],
)
def legal_dong_code_standard_quarterly() -> None:
    @task(task_id="download_and_load_legal_dong_code_standard")
    def download_and_load() -> dict[str, Any]:
        database_url = os.environ["TRIPMATE_DATABASE_URL"]
        download_dir = Path(os.environ.get("TRIPMATE_AIRFLOW_DOWNLOAD_DIR", DEFAULT_DOWNLOAD_DIR))

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.etl.vworld.legal_dong_code_loader import (
            DATA_GO_LEGAL_DONG_PAGE_URL,
            load_latest_legal_dong_code_from_data_go,
        )
        from app.models.etl import EtlRunLog
        from app.services.etl_runtime import (
            create_etl_run_log,
            mark_etl_run_failed,
            mark_etl_run_success,
        )

        engine = create_engine(database_url, pool_pre_ping=True)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        logical_date = _current_airflow_datetime().astimezone(ZoneInfo("Asia/Seoul")).date()

        try:
            with session_factory() as log_session:
                run_log = create_etl_run_log(
                    log_session,
                    dataset_key=DATASET_KEY,
                    run_key=logical_date.strftime("%Y%m%d"),
                    run_type="scheduled",
                    trigger_date=logical_date,
                    config=_RUNTIME_CONFIG,
                )
                run_log_id = run_log.id
                log_session.commit()

            try:
                with session_factory() as load_session:
                    result = load_latest_legal_dong_code_from_data_go(
                        load_session,
                        download_dir,
                    )
                    load_session.commit()

                payload = _json_ready(asdict(result))
                payload["page_url"] = DATA_GO_LEGAL_DONG_PAGE_URL
                payload["download_dir"] = str(download_dir)
                with session_factory() as log_session:
                    run_log = log_session.get(EtlRunLog, run_log_id)
                    if run_log is None:
                        raise RuntimeError(f"ETL run log not found: {run_log_id}")
                    mark_etl_run_success(
                        run_log,
                        message="법정동코드 기준 데이터 갱신 성공",
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
                        message="법정동코드 기준 데이터 갱신 실패",
                        exhausted=retry_exhausted,
                        config=_RUNTIME_CONFIG,
                    )
                    log_session.commit()
                raise
        finally:
            engine.dispose()

    download_and_load()


legal_dong_code_standard_quarterly()
