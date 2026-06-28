"""Dagster code location 진입점."""

from __future__ import annotations

from dagster import Definitions, EnvVar

from pinvi.etl.assets import (
    pinvi_email_outbox,
    pinvi_kasi_special_days,
    pinvi_location_log_archive,
    pinvi_pii_retention,
    pinvi_telegram_system_outbox,
)
from pinvi.etl.jobs import kasi_poi_rise_set_job
from pinvi.etl.resources import KasiResource, PinviDatabaseResource
from pinvi.etl.schedules import (
    kasi_special_days_job,
    pinvi_email_outbox_job,
    pinvi_location_log_archive_job,
    pinvi_pii_retention_job,
    pinvi_telegram_system_outbox_job,
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
    ],
    schedules=schedules,
    sensors=[pinvi_run_failure_sensor],
    resources={
        "db": PinviDatabaseResource(
            dsn=EnvVar("PINVI_DATABASE_URL"),
            pool_size=10,
        ),
        "kasi": KasiResource(
            service_key=EnvVar("DATA_GO_KR_SERVICE_KEY"),
        ),
    },
)
