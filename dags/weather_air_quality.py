from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

WEATHER_SHORT_TERM_DAG_ID = "weather_short_term_sigungu_grid"
WEATHER_ALERT_DAG_ID = "weather_kma_alert"
AIR_QUALITY_STATION_DAG_ID = "air_quality_station_daily"
AIR_QUALITY_FORECAST_DAG_ID = "air_quality_forecast_daily"
AIR_QUALITY_MEASUREMENT_DAG_ID = "air_quality_sido_measurement_hourly"
KMA_TOUR_COURSE_DAG_ID = "kma_recommended_tour_course_annual"


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

_SHORT_TERM_CONFIG = get_etl_dataset_config("weather_short_term")
_ALERT_CONFIG = get_etl_dataset_config("weather_kma_alert")
_AIR_STATION_CONFIG = get_etl_dataset_config("air_quality_station")
_AIR_FORECAST_CONFIG = get_etl_dataset_config("air_quality_forecast")
_AIR_MEASUREMENT_CONFIG = get_etl_dataset_config("air_quality_sido_measurement")
_KMA_TOUR_CONFIG = get_etl_dataset_config("kma_recommended_tour_course")


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


@dag(
    dag_id=WEATHER_SHORT_TERM_DAG_ID,
    description="기상청 초단기실황을 활성화된 시군구 대표 격자 단위로 수집한다.",
    schedule=_SHORT_TERM_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _SHORT_TERM_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_SHORT_TERM_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "weather", "kma", "short-term"],
)
def weather_short_term_sigungu_grid() -> None:
    @task(task_id="load_weather_short_term")
    def load_short_term(logical_datetime_iso: str) -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="weather_short_term",
            logical_datetime=_parse_airflow_datetime(logical_datetime_iso),
            load=_load_short_term,
        )

    load_short_term("{{ ts }}")


@dag(
    dag_id=WEATHER_ALERT_DAG_ID,
    description="기상청 기상특보, 기상정보, 기상속보 목록을 텔레그램 알림용으로 수집한다.",
    schedule=_ALERT_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _ALERT_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_ALERT_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "weather", "kma", "alert"],
)
def weather_kma_alert() -> None:
    @task(task_id="load_weather_kma_alerts")
    def load_alerts(logical_datetime_iso: str) -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="weather_kma_alert",
            logical_datetime=_parse_airflow_datetime(logical_datetime_iso),
            load=_load_alerts,
        )

    load_alerts("{{ ts }}")


@dag(
    dag_id=AIR_QUALITY_STATION_DAG_ID,
    description="에어코리아 측정소 목록을 수집하고 법정동 경계와 매핑한다.",
    schedule=_AIR_STATION_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _AIR_STATION_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_AIR_STATION_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "air-quality", "airkorea", "station"],
)
def air_quality_station_daily() -> None:
    @task(task_id="load_air_quality_stations")
    def load_stations(logical_datetime_iso: str) -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="air_quality_station",
            logical_datetime=_parse_airflow_datetime(logical_datetime_iso),
            load=_load_air_quality_stations,
        )

    load_stations("{{ ts }}")


@dag(
    dag_id=AIR_QUALITY_FORECAST_DAG_ID,
    description="에어코리아 미세먼지/오존 예보통보를 수집한다.",
    schedule=_AIR_FORECAST_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _AIR_FORECAST_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_AIR_FORECAST_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "air-quality", "airkorea", "forecast"],
)
def air_quality_forecast_daily() -> None:
    @task(task_id="load_air_quality_forecasts")
    def load_forecasts(logical_datetime_iso: str) -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="air_quality_forecast",
            logical_datetime=_parse_airflow_datetime(logical_datetime_iso),
            load=_load_air_quality_forecasts,
        )

    load_forecasts("{{ ts }}")


@dag(
    dag_id=AIR_QUALITY_MEASUREMENT_DAG_ID,
    description="에어코리아 시도별 실시간 측정값을 시간 단위로 수집한다.",
    schedule=_AIR_MEASUREMENT_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _AIR_MEASUREMENT_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_AIR_MEASUREMENT_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "air-quality", "airkorea", "measurement"],
)
def air_quality_sido_measurement_hourly() -> None:
    @task(task_id="load_air_quality_sido_measurements")
    def load_measurements(logical_datetime_iso: str) -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="air_quality_sido_measurement",
            logical_datetime=_parse_airflow_datetime(logical_datetime_iso),
            load=_load_air_quality_measurements,
        )

    load_measurements("{{ ts }}")


@dag(
    dag_id=KMA_TOUR_COURSE_DAG_ID,
    description="기상청 추천 관광코스 CSV/ZIP 파일을 DB화한다.",
    schedule=_KMA_TOUR_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _KMA_TOUR_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_KMA_TOUR_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "tour", "kma", "course"],
)
def kma_recommended_tour_course_annual() -> None:
    @task(task_id="load_kma_recommended_tour_course")
    def load_tour_course(logical_datetime_iso: str) -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="kma_recommended_tour_course",
            logical_datetime=_parse_airflow_datetime(logical_datetime_iso),
            load=_load_kma_tour_course,
        )

    load_tour_course("{{ ts }}")


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
                result = load(load_session, logical_datetime_kst)
                load_session.commit()

            payload = _json_ready(asdict(result))
            with session_factory() as log_session:
                resolved_run_log = log_session.get(EtlRunLog, run_log_id)
                if resolved_run_log is None:
                    raise RuntimeError(f"ETL run log not found: {run_log_id}")
                mark_etl_run_success(
                    resolved_run_log,
                    message=f"날씨/대기질 ETL 성공: {dataset_key}",
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
                    message=f"날씨/대기질 ETL 실패: {dataset_key}",
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


def _load_short_term(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.client import KmaWeatherApiClient
    from app.etl.weather.loader import (
        build_sigungu_weather_grid_mappings_from_boundaries,
        load_short_term_weather_for_active_mappings,
    )
    from app.models.weather import WeatherShortTermGridMapping

    existing_count = session.query(WeatherShortTermGridMapping).filter_by(is_active=True).count()
    if existing_count == 0:
        build_sigungu_weather_grid_mappings_from_boundaries(session)
    return load_short_term_weather_for_active_mappings(
        session,
        KmaWeatherApiClient(),
        collected_at=collected_at,
    )


def _load_alerts(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.client import KmaWeatherApiClient
    from app.etl.weather.loader import load_kma_alerts

    to_date = collected_at.date()
    return load_kma_alerts(
        session,
        KmaWeatherApiClient(),
        from_date=to_date - timedelta(days=1),
        to_date=to_date,
        collected_at=collected_at,
    )


def _load_air_quality_stations(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.client import AirKoreaApiClient
    from app.etl.weather.loader import load_air_quality_stations

    return load_air_quality_stations(session, AirKoreaApiClient(), collected_at=collected_at)


def _load_air_quality_forecasts(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.client import AirKoreaApiClient
    from app.etl.weather.loader import load_air_quality_forecasts

    return load_air_quality_forecasts(session, AirKoreaApiClient(), collected_at=collected_at)


def _load_air_quality_measurements(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.client import AirKoreaApiClient
    from app.etl.weather.loader import load_air_quality_sido_measurements

    return load_air_quality_sido_measurements(
        session, AirKoreaApiClient(), collected_at=collected_at
    )


def _load_kma_tour_course(session: Any, collected_at: datetime) -> Any:
    from airflow.exceptions import AirflowSkipException

    from app.etl.tour.kma_tour_course import load_kma_tour_course_file

    source_path = os.environ.get("TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH")
    if not source_path:
        raise AirflowSkipException(
            "TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH is not configured. "
            "Upload or place the KMA tour course ZIP/CSV before running this DAG."
        )
    return load_kma_tour_course_file(session, source_path, collected_at=collected_at)


weather_short_term_sigungu_grid()
weather_kma_alert()
air_quality_station_daily()
air_quality_forecast_daily()
air_quality_sido_measurement_hourly()
kma_recommended_tour_course_annual()
