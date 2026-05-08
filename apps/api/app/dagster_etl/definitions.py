from datetime import datetime
from typing import Any

import dagster as dg
from dagster import OpExecutionContext

from app.core.etl_config import get_etl_dataset_config
from app.dagster_etl.registry import ALL_ETL_SPECS
from app.dagster_etl.runtime import (
    EtlJobSpec,
    execute_etl_spec,
    execution_from_config,
)

DAGSTER_TIMEZONE = "Asia/Seoul"

OP_CONFIG_SCHEMA = {
    "logical_datetime": dg.Field(
        dg.String,
        is_required=False,
        description="ISO datetime used as the ETL logical time. Naive values are KST.",
    ),
    "run_type": dg.Field(
        dg.String,
        is_required=False,
        default_value="manual",
        description="TripMate ETL run type: manual or scheduled.",
    ),
    "source_year_month": dg.Field(
        dg.String,
        is_required=False,
        description="Juso manual backfill source month in YYYYMM format.",
    ),
}


def build_dagster_job(spec: EtlJobSpec) -> dg.JobDefinition:
    runtime_config = get_etl_dataset_config(spec.dataset_key)

    @dg.op(
        name=spec.op_name,
        description=spec.description,
        config_schema=OP_CONFIG_SCHEMA,
        retry_policy=dg.RetryPolicy(
            max_retries=runtime_config.retry_max_attempts,
            delay=float(runtime_config.retry_interval_seconds),
        ),
        tags={tag: "true" for tag in spec.tags},
    )
    def run_tripmate_etl(context: OpExecutionContext) -> dict[str, Any]:
        retry_number = int(getattr(context, "retry_number", 0))
        retry_exhausted = retry_number >= runtime_config.retry_max_attempts
        return execute_etl_spec(
            spec,
            execution_from_config(context.op_config),
            retry_exhausted=retry_exhausted,
        )

    @dg.job(
        name=spec.job_name,
        description=spec.description,
        tags={
            "tripmate/dataset_key": spec.dataset_key,
            **{f"tripmate_tag_{tag}": "true" for tag in spec.tags},
        },
    )
    def tripmate_etl_job() -> None:
        run_tripmate_etl()

    return tripmate_etl_job


def build_run_config(spec: EtlJobSpec, logical_datetime: datetime) -> dict[str, Any]:
    return {
        "ops": {
            spec.op_name: {
                "config": {
                    "logical_datetime": logical_datetime.isoformat(),
                    "run_type": "scheduled",
                }
            }
        }
    }


def build_dagster_schedule(
    spec: EtlJobSpec,
    job_def: dg.JobDefinition,
) -> dg.ScheduleDefinition | None:
    runtime_config = get_etl_dataset_config(spec.dataset_key)
    if runtime_config.schedule == "manual":
        return None
    if spec.schedule_enabled is not None and not spec.schedule_enabled():
        return None

    def run_config_fn(context: dg.ScheduleEvaluationContext) -> dict[str, Any]:
        scheduled_at = context.scheduled_execution_time or datetime.now().astimezone()
        return build_run_config(spec, scheduled_at)

    return dg.ScheduleDefinition(
        name=f"{spec.job_name}_schedule",
        job=job_def,
        cron_schedule=runtime_config.schedule,
        execution_timezone=DAGSTER_TIMEZONE,
        run_config_fn=run_config_fn,
        default_status=dg.DefaultScheduleStatus.RUNNING,
        description=spec.description,
    )


DAGSTER_JOBS = [build_dagster_job(spec) for spec in ALL_ETL_SPECS]
DAGSTER_SCHEDULES = [
    schedule
    for spec, job_def in zip(ALL_ETL_SPECS, DAGSTER_JOBS, strict=True)
    if (schedule := build_dagster_schedule(spec, job_def)) is not None
]

defs = dg.Definitions(
    jobs=DAGSTER_JOBS,
    schedules=DAGSTER_SCHEDULES,
)
