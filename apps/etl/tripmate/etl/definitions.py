"""Dagster code location 진입점."""

from __future__ import annotations

from dagster import Definitions, EnvVar

from tripmate.etl.assets import tripmate_kasi_special_days
from tripmate.etl.jobs import kasi_poi_rise_set_job
from tripmate.etl.resources import KasiResource, TripmateDatabaseResource
from tripmate.etl.schedules import schedules

defs = Definitions(
    assets=[tripmate_kasi_special_days],
    jobs=[kasi_poi_rise_set_job],
    schedules=schedules,
    sensors=[],
    resources={
        "db": TripmateDatabaseResource(
            dsn=EnvVar("TRIPMATE_DATABASE_URL"),
            pool_size=10,
        ),
        "kasi": KasiResource(
            service_key=EnvVar("DATA_GO_KR_SERVICE_KEY"),
        ),
    },
)
