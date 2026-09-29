"""Dagster schedule 정의."""

from __future__ import annotations

from dagster import ScheduleDefinition, define_asset_job

from pinvi.etl.run_tags import PINVI_JOB_TAGS

kasi_special_days_job = define_asset_job(
    "kasi_special_days_job",
    selection=["pinvi_kasi_special_days"],
    tags=PINVI_JOB_TAGS,
)

pinvi_email_outbox_job = define_asset_job(
    "pinvi_email_outbox_job",
    selection=["pinvi_email_outbox"],
    tags=PINVI_JOB_TAGS,
)

pinvi_pii_retention_job = define_asset_job(
    "pinvi_pii_retention_job",
    selection=["pinvi_pii_retention"],
    tags=PINVI_JOB_TAGS,
)

pinvi_location_log_archive_job = define_asset_job(
    "pinvi_location_log_archive_job",
    selection=["pinvi_location_log_archive"],
    tags=PINVI_JOB_TAGS,
)

pinvi_telegram_system_outbox_job = define_asset_job(
    "pinvi_telegram_system_outbox_job",
    selection=["pinvi_telegram_system_outbox"],
    tags=PINVI_JOB_TAGS,
)

pinvi_trip_day_rise_sets_job = define_asset_job(
    "pinvi_trip_day_rise_sets_job",
    selection=["pinvi_trip_day_rise_sets"],
    tags=PINVI_JOB_TAGS,
)

pinvi_weather_retention_horizon_job = define_asset_job(
    "pinvi_weather_retention_horizon_job",
    selection=["pinvi_weather_retention_horizon_guard"],
    tags=PINVI_JOB_TAGS,
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
    ScheduleDefinition(
        name="pinvi_pii_retention_schedule",
        job=pinvi_pii_retention_job,
        cron_schedule="15 4 * * *",
        execution_timezone="Asia/Seoul",
    ),
    ScheduleDefinition(
        name="pinvi_location_log_archive_schedule",
        job=pinvi_location_log_archive_job,
        cron_schedule="30 4 * * *",
        execution_timezone="Asia/Seoul",
    ),
    ScheduleDefinition(
        name="pinvi_telegram_system_outbox_schedule",
        job=pinvi_telegram_system_outbox_job,
        cron_schedule="*/15 * * * *",
        execution_timezone="Asia/Seoul",
    ),
    # 사용자가 일정 중 POI를 추가/이동하면 pending_fetch 일자 rise/set이 생기므로 자주 채운다.
    ScheduleDefinition(
        name="pinvi_trip_day_rise_sets_schedule",
        job=pinvi_trip_day_rise_sets_job,
        cron_schedule="*/20 * * * *",
        execution_timezone="Asia/Seoul",
    ),
    ScheduleDefinition(
        name="pinvi_weather_retention_horizon_schedule",
        job=pinvi_weather_retention_horizon_job,
        cron_schedule="0 5 * * *",
        execution_timezone="Asia/Seoul",
    ),
]
