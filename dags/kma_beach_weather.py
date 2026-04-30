from __future__ import annotations

import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from airflow.decorators import dag, task

KMA_BEACH_CATALOG_DAG_ID = "kma_beach_catalog_annual"
KMA_BEACH_ULTRA_SHORT_DAG_ID = "kma_beach_ultra_short_forecast_hourly"
KMA_BEACH_VILLAGE_DAG_ID = "kma_beach_village_forecast_3hourly"
KMA_BEACH_WAVE_DAG_ID = "kma_beach_wave_height_hourly"
KMA_BEACH_WATER_TEMP_DAG_ID = "kma_beach_water_temperature_hourly"
KMA_BEACH_TIDE_SUN_DAG_ID = "kma_beach_tide_sun_daily"


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

_CATALOG_CONFIG = get_etl_dataset_config("kma_beach_catalog")
_ULTRA_SHORT_CONFIG = get_etl_dataset_config("kma_beach_ultra_short_forecast")
_VILLAGE_CONFIG = get_etl_dataset_config("kma_beach_village_forecast")
_WAVE_CONFIG = get_etl_dataset_config("kma_beach_wave_height")
_WATER_TEMP_CONFIG = get_etl_dataset_config("kma_beach_water_temperature")
_TIDE_SUN_CONFIG = get_etl_dataset_config("kma_beach_tide_sun")


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
    dag_id=KMA_BEACH_CATALOG_DAG_ID,
    description="기상청 전국 해수욕장 위치 카탈로그를 장소 DB와 매핑한다.",
    schedule=_CATALOG_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _CATALOG_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_CATALOG_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "weather", "kma", "beach", "catalog"],
)
def kma_beach_catalog_annual() -> None:
    @task(task_id="load_kma_beach_catalog")
    def load_catalog() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="kma_beach_catalog",
            logical_datetime=_current_airflow_datetime(),
            load=_load_catalog,
        )

    load_catalog()


@dag(
    dag_id=KMA_BEACH_ULTRA_SHORT_DAG_ID,
    description="해수욕장별 기상청 초단기예보를 6~8월 시간 단위로 수집한다.",
    schedule=_ULTRA_SHORT_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _ULTRA_SHORT_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_ULTRA_SHORT_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "weather", "kma", "beach", "ultra-short"],
)
def kma_beach_ultra_short_forecast_hourly() -> None:
    @task(task_id="load_kma_beach_ultra_short_forecasts")
    def load_weather() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="kma_beach_ultra_short_forecast",
            logical_datetime=_current_airflow_datetime(),
            load=_load_ultra_short,
        )

    load_weather()


@dag(
    dag_id=KMA_BEACH_VILLAGE_DAG_ID,
    description="해수욕장별 기상청 단기예보를 6~8월 3시간 기준으로 수집한다.",
    schedule=_VILLAGE_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _VILLAGE_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_VILLAGE_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "weather", "kma", "beach", "village"],
)
def kma_beach_village_forecast_3hourly() -> None:
    @task(task_id="load_kma_beach_village_forecasts")
    def load_weather() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="kma_beach_village_forecast",
            logical_datetime=_current_airflow_datetime(),
            load=_load_village,
        )

    load_weather()


@dag(
    dag_id=KMA_BEACH_WAVE_DAG_ID,
    description="해수욕장별 파고 관측값을 6~8월 시간 단위로 수집한다.",
    schedule=_WAVE_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _WAVE_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_WAVE_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "weather", "kma", "beach", "wave"],
)
def kma_beach_wave_height_hourly() -> None:
    @task(task_id="load_kma_beach_wave_heights")
    def load_weather() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="kma_beach_wave_height",
            logical_datetime=_current_airflow_datetime(),
            load=_load_wave,
        )

    load_weather()


@dag(
    dag_id=KMA_BEACH_WATER_TEMP_DAG_ID,
    description="해수욕장별 수온 관측값을 6~8월 시간 단위로 수집한다.",
    schedule=_WATER_TEMP_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _WATER_TEMP_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_WATER_TEMP_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "weather", "kma", "beach", "water-temperature"],
)
def kma_beach_water_temperature_hourly() -> None:
    @task(task_id="load_kma_beach_water_temperatures")
    def load_weather() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="kma_beach_water_temperature",
            logical_datetime=_current_airflow_datetime(),
            load=_load_water_temperature,
        )

    load_weather()


@dag(
    dag_id=KMA_BEACH_TIDE_SUN_DAG_ID,
    description="해수욕장별 조석과 일출·일몰 정보를 6~8월 일 단위로 수집한다.",
    schedule=_TIDE_SUN_CONFIG.schedule,
    start_date=datetime(2026, 5, 1, tzinfo=ZoneInfo("Asia/Seoul")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "tripmate",
        "retries": _TIDE_SUN_CONFIG.retry_max_attempts,
        "retry_delay": timedelta(seconds=_TIDE_SUN_CONFIG.retry_interval_seconds),
    },
    tags=["tripmate", "weather", "kma", "beach", "tide", "sun"],
)
def kma_beach_tide_sun_daily() -> None:
    @task(task_id="load_kma_beach_tide_sun")
    def load_weather() -> dict[str, Any]:
        return _run_logged_task(
            dataset_key="kma_beach_tide_sun",
            logical_datetime=_current_airflow_datetime(),
            load=_load_tide_sun,
        )

    load_weather()


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

            payload = _json_ready(result)
            with session_factory() as log_session:
                resolved_run_log = log_session.get(EtlRunLog, run_log_id)
                if resolved_run_log is None:
                    raise RuntimeError(f"ETL run log not found: {run_log_id}")
                mark_etl_run_success(
                    resolved_run_log,
                    message=f"해수욕장 날씨 ETL 성공: {dataset_key}",
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
                    message=f"해수욕장 날씨 ETL 실패: {dataset_key}",
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


def _load_catalog(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.beach import KmaBeachWeatherClient, load_beach_catalog

    return load_beach_catalog(session, KmaBeachWeatherClient(), collected_at=collected_at)


def _load_ultra_short(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.beach import KMA_BEACH_ULTRA_SHORT_ENDPOINT

    return _load_weather_endpoint(session, collected_at, KMA_BEACH_ULTRA_SHORT_ENDPOINT)


def _load_village(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.beach import KMA_BEACH_VILLAGE_ENDPOINT

    return _load_weather_endpoint(session, collected_at, KMA_BEACH_VILLAGE_ENDPOINT)


def _load_wave(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.beach import KMA_BEACH_WAVE_ENDPOINT

    return _load_weather_endpoint(session, collected_at, KMA_BEACH_WAVE_ENDPOINT)


def _load_water_temperature(session: Any, collected_at: datetime) -> Any:
    from app.etl.weather.beach import KMA_BEACH_WATER_TEMP_ENDPOINT

    return _load_weather_endpoint(session, collected_at, KMA_BEACH_WATER_TEMP_ENDPOINT)


def _load_tide_sun(session: Any, collected_at: datetime) -> dict[str, Any]:
    from app.etl.weather.beach import KMA_BEACH_SUN_ENDPOINT, KMA_BEACH_TIDE_ENDPOINT

    tide = _load_weather_endpoint(session, collected_at, KMA_BEACH_TIDE_ENDPOINT)
    sun = _load_weather_endpoint(session, collected_at, KMA_BEACH_SUN_ENDPOINT)
    return {"tide": tide, "sun": sun}


def _load_weather_endpoint(session: Any, collected_at: datetime, endpoint: str) -> Any:
    from app.etl.weather.beach import KmaBeachWeatherClient, load_beach_weather_for_active_locations
    from app.models.weather import WeatherBeachLocation

    client = KmaBeachWeatherClient()
    existing_count = session.query(WeatherBeachLocation).filter_by(is_active=True).count()
    if existing_count == 0:
        _load_catalog(session, collected_at)
    return load_beach_weather_for_active_locations(
        session,
        client,
        endpoint=endpoint,
        collected_at=collected_at,
    )


kma_beach_catalog_annual()
kma_beach_ultra_short_forecast_hourly()
kma_beach_village_forecast_3hourly()
kma_beach_wave_height_hourly()
kma_beach_water_temperature_hourly()
kma_beach_tide_sun_daily()
