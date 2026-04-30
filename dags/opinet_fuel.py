from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

REGION_DAG_ID = "opinet_region_code_quarterly"
AVG_PRICE_DAG_ID = "opinet_avg_price_daily"
LOWEST_STATION_DAG_ID = "opinet_lowest_station_daily"
REGION_DATASET_KEY = "fuel_region_code"
AVG_PRICE_DATASET_KEY = "fuel_avg_price"
LOWEST_STATION_DATASET_KEY = "fuel_lowest_station"


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

_REGION_RUNTIME_CONFIG = get_etl_dataset_config(REGION_DATASET_KEY)
_AVG_PRICE_RUNTIME_CONFIG = get_etl_dataset_config(AVG_PRICE_DATASET_KEY)
_LOWEST_STATION_RUNTIME_CONFIG = get_etl_dataset_config(LOWEST_STATION_DATASET_KEY)


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
    dag_id=REGION_DAG_ID,
    description="OpiNet areaCode.do 지역코드를 수집하고 Juso 법정동 기준 시도/시군구와 매핑한다.",
    schedule=_REGION_RUNTIME_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _REGION_RUNTIME_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_REGION_RUNTIME_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "fuel", "opinet", "region-code"],
)
def opinet_region_code_quarterly() -> None:
    @task(task_id="load_opinet_region_codes")
    def load_region_codes() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key=REGION_DATASET_KEY,
            logical_datetime=_current_airflow_datetime(),
            load=_load_region_codes,
        )

    load_region_codes()


@dag(
    dag_id=AVG_PRICE_DAG_ID,
    description="OpiNet avgAllPrice.do 전국 일별 평균 유가를 수집한다.",
    schedule=_AVG_PRICE_RUNTIME_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _AVG_PRICE_RUNTIME_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_AVG_PRICE_RUNTIME_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "fuel", "opinet", "average-price"],
)
def opinet_avg_price_daily() -> None:
    @task(task_id="load_opinet_avg_prices")
    def load_avg_prices() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key=AVG_PRICE_DATASET_KEY,
            logical_datetime=_current_airflow_datetime(),
            load=_load_avg_prices,
        )

    load_avg_prices()


@dag(
    dag_id=LOWEST_STATION_DAG_ID,
    description=(
        "OpiNet lowTop10.do 최저가 주유소 후보를 매핑된 전국 시군구 전체 기준으로 수집한다."
    ),
    schedule=_LOWEST_STATION_RUNTIME_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _LOWEST_STATION_RUNTIME_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_LOWEST_STATION_RUNTIME_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "fuel", "opinet", "lowest-station"],
)
def opinet_lowest_station_daily() -> None:
    @task(task_id="load_opinet_lowest_stations_for_all_sigungu")
    def load_lowest_stations() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key=LOWEST_STATION_DATASET_KEY,
            logical_datetime=_current_airflow_datetime(),
            load=_load_lowest_stations_for_all_sigungu,
        )

    load_lowest_stations()


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
                result = load(load_session)
                load_session.commit()

            payload = _json_ready(asdict(result))
            with session_factory() as log_session:
                resolved_run_log = log_session.get(EtlRunLog, run_log_id)
                if resolved_run_log is None:
                    raise RuntimeError(f"ETL run log not found: {run_log_id}")
                mark_etl_run_success(
                    resolved_run_log,
                    message=f"OpiNet ETL 성공: {dataset_key}",
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
                    message=f"OpiNet ETL 실패: {dataset_key}",
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


def _load_region_codes(session: Any) -> Any:
    from app.etl.opinet.client import OpiNetApiClient
    from app.etl.opinet.loader import load_opinet_region_codes

    return load_opinet_region_codes(session, OpiNetApiClient())


def _load_avg_prices(session: Any) -> Any:
    from app.etl.opinet.client import OpiNetApiClient
    from app.etl.opinet.loader import load_opinet_avg_prices

    return load_opinet_avg_prices(session, OpiNetApiClient())


def _load_lowest_stations_for_all_sigungu(session: Any) -> Any:
    from app.etl.opinet.client import OpiNetApiClient
    from app.etl.opinet.loader import (
        list_opinet_sigungu_region_codes_for_periodic_collection,
        load_opinet_lowest_stations,
    )

    provider_region_codes = list_opinet_sigungu_region_codes_for_periodic_collection(session)
    if not provider_region_codes:
        raise RuntimeError(
            "OpiNet 최저가 주유소 수집 대상 시군구가 없습니다. "
            "fuel_region_code ETL을 먼저 성공시켜야 합니다."
        )
    return load_opinet_lowest_stations(
        session,
        OpiNetApiClient(),
        provider_region_codes=provider_region_codes,
    )


opinet_region_code_quarterly()
opinet_avg_price_daily()
opinet_lowest_station_daily()
