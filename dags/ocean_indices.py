from __future__ import annotations

import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

try:
    from airflow.exceptions import AirflowSkipException
except Exception:

    class AirflowSkipException(Exception):
        pass


KHOA_MUDFLAT_INDEX_DAG_ID = "khoa_mudflat_index_forecast_twice_daily"
KHOA_SEA_SPLIT_INDEX_DAG_ID = "khoa_sea_split_index_forecast_twice_daily"


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

_MUDFLAT_CONFIG = get_etl_dataset_config("khoa_mudflat_index_forecast")
_SEA_SPLIT_CONFIG = get_etl_dataset_config("khoa_sea_split_index_forecast")


def _khoa_index_schedule(schedule: str | None) -> str | None:
    if os.environ.get("TRIPMATE_KHOA_API_KEY") or os.environ.get("TRIPMATE_DATA_GO_SERVICE_KEY"):
        return schedule
    return None


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
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
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
    dag_id=KHOA_MUDFLAT_INDEX_DAG_ID,
    description="KHOA 갯벌체험지수 예측 정보를 하루 2회 수집한다.",
    schedule=_khoa_index_schedule(_MUDFLAT_CONFIG.schedule),
    start_date=datetime(2026, 4, 29, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _MUDFLAT_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_MUDFLAT_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "ocean", "khoa", "mudflat"],
)
def khoa_mudflat_index_forecast_twice_daily() -> None:
    @task(task_id="load_khoa_mudflat_index_forecasts")
    def load_index_forecasts() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="khoa_mudflat_index_forecast",
            logical_datetime=_current_airflow_datetime(),
        )

    load_index_forecasts()


@dag(
    dag_id=KHOA_SEA_SPLIT_INDEX_DAG_ID,
    description="KHOA 바다갈라짐 체험지수 예측 정보를 하루 2회 수집한다.",
    schedule=_khoa_index_schedule(_SEA_SPLIT_CONFIG.schedule),
    start_date=datetime(2026, 4, 29, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _SEA_SPLIT_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_SEA_SPLIT_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "ocean", "khoa", "sea-split"],
)
def khoa_sea_split_index_forecast_twice_daily() -> None:
    @task(task_id="load_khoa_sea_split_index_forecasts")
    def load_index_forecasts() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="khoa_sea_split_index_forecast",
            logical_datetime=_current_airflow_datetime(),
        )

    load_index_forecasts()


def _run_logged_task(*, dataset_key: str, logical_datetime: datetime) -> dict[str, Any]:
    if not os.environ.get("TRIPMATE_KHOA_API_KEY") and not os.environ.get(
        "TRIPMATE_DATA_GO_SERVICE_KEY"
    ):
        raise AirflowSkipException("KHOA/data.go.kr 인증키가 없어 해양지수 ETL을 건너뜁니다.")

    database_url = os.environ["TRIPMATE_DATABASE_URL"]

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.etl_config import get_etl_dataset_config
    from app.etl.ocean.khoa_indices import KhoaOceanIndexClient, load_khoa_ocean_index_dataset
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
                result = load_khoa_ocean_index_dataset(
                    load_session,
                    dataset_key,
                    KhoaOceanIndexClient(),
                    collected_at=logical_datetime_kst,
                    req_date=logical_datetime_kst.date(),
                )
                load_session.commit()

            payload = _json_ready(result)
            with session_factory() as log_session:
                resolved_run_log = log_session.get(EtlRunLog, run_log_id)
                if resolved_run_log is None:
                    raise RuntimeError(f"ETL run log not found: {run_log_id}")
                mark_etl_run_success(
                    resolved_run_log,
                    message=f"KHOA 해양지수 ETL 성공: {dataset_key}",
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
                    message=f"KHOA 해양지수 ETL 실패: {dataset_key}",
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
    return parsed.astimezone(ZoneInfo("Asia/Seoul"))


khoa_mudflat_index_forecast_twice_daily()
khoa_sea_split_index_forecast_twice_daily()
