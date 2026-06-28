"""Dagster code location 진입점."""

from __future__ import annotations

from dagster import Definitions, EnvVar

from pinvi.etl.assets import pinvi_email_outbox, pinvi_kasi_special_days
from pinvi.etl.jobs import kasi_poi_rise_set_job
from pinvi.etl.resources import KasiResource, PinviDatabaseResource
from pinvi.etl.schedules import schedules

defs = Definitions(
    assets=[pinvi_email_outbox, pinvi_kasi_special_days],
    jobs=[kasi_poi_rise_set_job],
    schedules=schedules,
    sensors=[],
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
