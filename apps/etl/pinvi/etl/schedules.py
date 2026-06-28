"""Dagster schedule 정의."""

from __future__ import annotations

from dagster import ScheduleDefinition, define_asset_job

kasi_special_days_job = define_asset_job(
    "kasi_special_days_job",
    selection=["pinvi_kasi_special_days"],
)

pinvi_email_outbox_job = define_asset_job(
    "pinvi_email_outbox_job",
    selection=["pinvi_email_outbox"],
)

schedules = [
    ScheduleDefinition(
        job=kasi_special_days_job,
        cron_schedule="30 3 * * *",
        execution_timezone="Asia/Seoul",
    ),
    ScheduleDefinition(
        name="pinvi_email_outbox_schedule",
        job=pinvi_email_outbox_job,
        cron_schedule="*/15 * * * *",
        execution_timezone="Asia/Seoul",
    ),
]
