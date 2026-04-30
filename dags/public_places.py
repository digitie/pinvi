from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

ARBORETUM_DAG_ID = "public_arboretum_basic_annual"
TOURIST_INFO_CENTER_DAG_ID = "public_tourist_information_center_annual"
RECREATION_FOREST_DAG_ID = "public_recreation_forest_semiannual"
MUSEUM_ART_DAG_ID = "public_museum_art_gallery_annual"
CAMPGROUND_DAG_ID = "public_campground_daily"


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

_ARBORETUM_CONFIG = get_etl_dataset_config("public_arboretum_basic")
_TOURIST_INFO_CENTER_CONFIG = get_etl_dataset_config("public_tourist_information_center")
_RECREATION_FOREST_CONFIG = get_etl_dataset_config("public_recreation_forest")
_MUSEUM_ART_CONFIG = get_etl_dataset_config("public_museum_art_gallery")
_CAMPGROUND_CONFIG = get_etl_dataset_config("public_campground")


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
    dag_id=ARBORETUM_DAG_ID,
    description="한국수목원정원관리원 수목원 기본관람정보를 저빈도 확인 수집한다.",
    schedule=_ARBORETUM_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _ARBORETUM_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_ARBORETUM_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "place", "data-go-kr", "arboretum"],
)
def public_arboretum_basic_annual() -> None:
    @task(task_id="load_public_arboretum_basic")
    def load_dataset() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="public_arboretum_basic",
            logical_datetime=_current_airflow_datetime(),
        )

    load_dataset()


@dag(
    dag_id=TOURIST_INFO_CENTER_DAG_ID,
    description="전국관광안내소표준데이터를 연간 수집해 표준 장소 DB에 반영한다.",
    schedule=_TOURIST_INFO_CENTER_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _TOURIST_INFO_CENTER_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_TOURIST_INFO_CENTER_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "place", "data-go-kr", "tourist-information"],
)
def public_tourist_information_center_annual() -> None:
    @task(task_id="load_public_tourist_information_center")
    def load_dataset() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="public_tourist_information_center",
            logical_datetime=_current_airflow_datetime(),
        )

    load_dataset()


@dag(
    dag_id=RECREATION_FOREST_DAG_ID,
    description="전국휴양림표준데이터를 반기 수집해 표준 장소 DB에 반영한다.",
    schedule=_RECREATION_FOREST_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _RECREATION_FOREST_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_RECREATION_FOREST_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "place", "data-go-kr", "forest"],
)
def public_recreation_forest_semiannual() -> None:
    @task(task_id="load_public_recreation_forest")
    def load_dataset() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="public_recreation_forest",
            logical_datetime=_current_airflow_datetime(),
        )

    load_dataset()


@dag(
    dag_id=MUSEUM_ART_DAG_ID,
    description="전국박물관미술관정보표준데이터를 연간 수집해 표준 장소 DB에 반영한다.",
    schedule=_MUSEUM_ART_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _MUSEUM_ART_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_MUSEUM_ART_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "place", "data-go-kr", "museum", "art"],
)
def public_museum_art_gallery_annual() -> None:
    @task(task_id="load_public_museum_art_gallery")
    def load_dataset() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="public_museum_art_gallery",
            logical_datetime=_current_airflow_datetime(),
        )

    load_dataset()


@dag(
    dag_id=CAMPGROUND_DAG_ID,
    description="전국야영(캠핑)장표준데이터를 매일 수집해 표준 장소 DB에 반영한다.",
    schedule=_CAMPGROUND_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _CAMPGROUND_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_CAMPGROUND_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "place", "data-go-kr", "campground"],
)
def public_campground_daily() -> None:
    @task(task_id="load_public_campground")
    def load_dataset() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="public_campground",
            logical_datetime=_current_airflow_datetime(),
        )

    load_dataset()


def _run_logged_task(*, dataset_key: str, logical_datetime: datetime) -> dict[str, Any]:
    database_url = os.environ["TRIPMATE_DATABASE_URL"]

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.etl_config import get_etl_dataset_config
    from app.etl.places.public_data_places import (
        CompositePublicPlaceClient,
        load_public_place_dataset,
    )
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
                result = load_public_place_dataset(
                    load_session,
                    dataset_key,
                    CompositePublicPlaceClient(),
                    collected_at=logical_datetime_kst,
                )
                load_session.commit()

            payload = _json_ready(asdict(result))
            with session_factory() as log_session:
                resolved_run_log = log_session.get(EtlRunLog, run_log_id)
                if resolved_run_log is None:
                    raise RuntimeError(f"ETL run log not found: {run_log_id}")
                mark_etl_run_success(
                    resolved_run_log,
                    message=f"공공 장소 ETL 성공: {dataset_key}",
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
                    message=f"공공 장소 ETL 실패: {dataset_key}",
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


public_arboretum_basic_annual()
public_tourist_information_center_annual()
public_recreation_forest_semiannual()
public_museum_art_gallery_annual()
public_campground_daily()
