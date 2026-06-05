"""Dagster schedule 정의."""

from __future__ import annotations

from dagster import ScheduleDefinition, define_asset_job

kasi_special_days_job = define_asset_job(
    "kasi_special_days_job",
    selection=["tripmate_kasi_special_days"],
)

schedules = [
    ScheduleDefinition(
        job=kasi_special_days_job,
        cron_schedule="30 3 * * *",
        execution_timezone="Asia/Seoul",
    ),
]
