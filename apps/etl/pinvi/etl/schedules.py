"""Dagster schedule 정의.

켜짐 상태는 코드가 정본이다(공유 Dagster plane D4) — 공유 `dagster_shared` instance는 이력을
새로 시작하므로 DB에서 손으로 켠 상태는 옮겨지지 않는다. 운영에서 도는 schedule은
모두 `default_status=RUNNING`을 선언한다(`tests/test_definitions.py`가 고정).
"""

from __future__ import annotations

from dagster import DefaultScheduleStatus, define_asset_job
from kortravelcommon.dagster import coalescing_schedule

from pinvi.etl.run_tags import PINVI_LOCATION_NAME, PINVI_PROJECT, job_tags

kasi_special_days_job = define_asset_job(
    "kasi_special_days_job",
    selection=["pinvi_kasi_special_days"],
    tags=job_tags("kasi_special_days_job"),
)

pinvi_email_outbox_job = define_asset_job(
    "pinvi_email_outbox_job",
    selection=["pinvi_email_outbox"],
    tags=job_tags("pinvi_email_outbox_job"),
)

pinvi_pii_retention_job = define_asset_job(
    "pinvi_pii_retention_job",
    selection=["pinvi_pii_retention"],
    tags=job_tags("pinvi_pii_retention_job"),
)

pinvi_location_log_archive_job = define_asset_job(
    "pinvi_location_log_archive_job",
    selection=["pinvi_location_log_archive"],
    tags=job_tags("pinvi_location_log_archive_job"),
)

pinvi_telegram_system_outbox_job = define_asset_job(
    "pinvi_telegram_system_outbox_job",
    selection=["pinvi_telegram_system_outbox"],
    tags=job_tags("pinvi_telegram_system_outbox_job"),
)

pinvi_trip_day_rise_sets_job = define_asset_job(
    "pinvi_trip_day_rise_sets_job",
    selection=["pinvi_trip_day_rise_sets"],
    tags=job_tags("pinvi_trip_day_rise_sets_job"),
)

pinvi_weather_retention_horizon_job = define_asset_job(
    "pinvi_weather_retention_horizon_job",
    selection=["pinvi_weather_retention_horizon_guard"],
    tags=job_tags("pinvi_weather_retention_horizon_job"),
)

schedules = [
    coalescing_schedule(
        project=PINVI_PROJECT,
        location_name=PINVI_LOCATION_NAME,
        job=kasi_special_days_job,
        cron_schedule="30 3 * * *",
        execution_timezone="Asia/Seoul",
        default_status=DefaultScheduleStatus.RUNNING,
    ),
    coalescing_schedule(
        project=PINVI_PROJECT,
        location_name=PINVI_LOCATION_NAME,
        name="pinvi_email_outbox_schedule",
        job=pinvi_email_outbox_job,
        cron_schedule="*/15 * * * *",
        execution_timezone="Asia/Seoul",
        default_status=DefaultScheduleStatus.RUNNING,
    ),
    coalescing_schedule(
        project=PINVI_PROJECT,
        location_name=PINVI_LOCATION_NAME,
        name="pinvi_pii_retention_schedule",
        job=pinvi_pii_retention_job,
        cron_schedule="15 4 * * *",
        execution_timezone="Asia/Seoul",
        default_status=DefaultScheduleStatus.RUNNING,
    ),
    coalescing_schedule(
        project=PINVI_PROJECT,
        location_name=PINVI_LOCATION_NAME,
        name="pinvi_location_log_archive_schedule",
        job=pinvi_location_log_archive_job,
        cron_schedule="30 4 * * *",
        execution_timezone="Asia/Seoul",
        default_status=DefaultScheduleStatus.RUNNING,
    ),
    coalescing_schedule(
        project=PINVI_PROJECT,
        location_name=PINVI_LOCATION_NAME,
        name="pinvi_telegram_system_outbox_schedule",
        job=pinvi_telegram_system_outbox_job,
        cron_schedule="*/15 * * * *",
        execution_timezone="Asia/Seoul",
        default_status=DefaultScheduleStatus.RUNNING,
    ),
    # 사용자가 일정 중 POI를 추가/이동하면 pending_fetch 일자 rise/set이 생기므로 자주 채운다.
    coalescing_schedule(
        project=PINVI_PROJECT,
        location_name=PINVI_LOCATION_NAME,
        name="pinvi_trip_day_rise_sets_schedule",
        job=pinvi_trip_day_rise_sets_job,
        cron_schedule="*/20 * * * *",
        execution_timezone="Asia/Seoul",
        default_status=DefaultScheduleStatus.RUNNING,
    ),
    coalescing_schedule(
        project=PINVI_PROJECT,
        location_name=PINVI_LOCATION_NAME,
        name="pinvi_weather_retention_horizon_schedule",
        job=pinvi_weather_retention_horizon_job,
        cron_schedule="0 5 * * *",
        execution_timezone="Asia/Seoul",
        default_status=DefaultScheduleStatus.RUNNING,
    ),
]
