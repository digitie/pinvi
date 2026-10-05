"""Dagster code location 진입점."""

from __future__ import annotations

from dagster import Definitions, EnvVar, multiprocess_executor
from kortravelcommon.dagster import infrastructure_retry_sensor

from pinvi.etl.assets import (
    pinvi_email_outbox,
    pinvi_kasi_special_days,
    pinvi_location_log_archive,
    pinvi_pii_retention,
    pinvi_telegram_system_outbox,
    pinvi_trip_day_rise_sets,
    pinvi_weather_retention_horizon_guard,
)
from pinvi.etl.jobs import kasi_poi_rise_set_job
from pinvi.etl.resources import KasiResource, KorTravelWeatherResource, PinviDatabaseResource
from pinvi.etl.run_tags import INFRA_RETRY_JOBS, PINVI_LOCATION_NAME, PINVI_PROJECT, recovery_policy
from pinvi.etl.schedules import (
    kasi_special_days_job,
    pinvi_email_outbox_job,
    pinvi_location_log_archive_job,
    pinvi_pii_retention_job,
    pinvi_telegram_system_outbox_job,
    pinvi_trip_day_rise_sets_job,
    pinvi_weather_retention_horizon_job,
    schedules,
)
from pinvi.etl.sensors import pinvi_run_failure_sensor

defs = Definitions(
    assets=[
        pinvi_email_outbox,
        pinvi_kasi_special_days,
        pinvi_location_log_archive,
        pinvi_pii_retention,
        pinvi_telegram_system_outbox,
        pinvi_trip_day_rise_sets,
        pinvi_weather_retention_horizon_guard,
    ],
    # asset job을 명시 등록한다. run_failure_sensor가 있으면 schedule-only job의
    # get_job_def가 dig_for_warning→sensor.jobs(raise) 경로를 타므로, 명시 등록으로
    # 직접 해석되게 한다.
    jobs=[
        kasi_poi_rise_set_job,
        kasi_special_days_job,
        pinvi_email_outbox_job,
        pinvi_pii_retention_job,
        pinvi_location_log_archive_job,
        pinvi_telegram_system_outbox_job,
        pinvi_trip_day_rise_sets_job,
        pinvi_weather_retention_horizon_job,
    ],
    schedules=schedules,
    sensors=[pinvi_run_failure_sensor],
    executor=multiprocess_executor.configured({"max_concurrent": 1}),
    resources={
        "db": PinviDatabaseResource(
            dsn=EnvVar("PINVI_DATABASE_URL"),
            pool_size=1,
        ),
        "kasi": KasiResource(
            service_key=EnvVar("DATA_GO_KR_SERVICE_KEY"),
        ),
        "kor_travel_weather": KorTravelWeatherResource(
            base_url=EnvVar("PINVI_KOR_TRAVEL_WEATHER_BASE_URL"),
        ),
    },
)


# resolve 후 job을 주입한다. asset job의 config/selection을 그대로 보존한다.
_base_defs = defs
_retry_sensors = [
    infrastructure_retry_sensor(
        name=f"pinvi_infra_retry_{name}",
        project=PINVI_PROJECT,
        location_name=PINVI_LOCATION_NAME,
        job=_base_defs.resolve_job_def(name),
        policy=recovery_policy(name),
    ).with_updated_job(next(job for job in _base_defs.jobs if job.name == name))
    for name in sorted(INFRA_RETRY_JOBS)
]
defs = Definitions.merge(_base_defs, Definitions(sensors=_retry_sensors))

# gRPC module autodiscovery는 이름이 private여도 모든 Definitions 객체를 센다.
# 조립용 임시 정의를 모듈에 남기면 code location 자체가 로드되지 않는다.
del _base_defs
