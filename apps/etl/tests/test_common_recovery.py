"""공용 정책을 실제 PinVi job/instance에 적용한 장애 경계."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from dagster import DagsterInstance, DagsterRunStatus, build_schedule_context
from dagster._core.remote_origin import (
    RegisteredCodeLocationOrigin,
    RemoteJobOrigin,
    RemoteRepositoryOrigin,
)
from kortravelcommon.dagster import has_active_run

from pinvi.etl.definitions import defs
from pinvi.etl.run_tags import INFRA_RETRY_JOBS, PINVI_LOCATION_NAME, PINVI_PROJECT


@pytest.fixture(autouse=True)
def resource_env(monkeypatch):
    monkeypatch.setenv("PINVI_DATABASE_URL", "postgresql+asyncpg://unused/unused")
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "unused")
    monkeypatch.setenv("PINVI_KOR_TRAVEL_WEATHER_BASE_URL", "http://weather.invalid")


@pytest.mark.parametrize(
    "status",
    [
        DagsterRunStatus.QUEUED,
        DagsterRunStatus.STARTING,
        DagsterRunStatus.STARTED,
        DagsterRunStatus.CANCELING,
    ],
)
def test_active_run_suppresses_schedule_and_terminal_unblocks(status, tmp_path):
    job = defs.resolve_job_def("pinvi_email_outbox_job")
    schedule = defs.get_schedule_def("pinvi_email_outbox_schedule")
    with DagsterInstance.local_temp(tempdir=str(tmp_path)) as instance:
        origin = RemoteJobOrigin(
            RemoteRepositoryOrigin(
                RegisteredCodeLocationOrigin(PINVI_LOCATION_NAME), "__repository__"
            ),
            job.name,
        )
        run = instance.create_run_for_job(
            job, status=status, tags=dict(job.tags), remote_job_origin=origin
        )
        with build_schedule_context(
            instance=instance, scheduled_execution_time=datetime.now(UTC)
        ) as context:
            assert not schedule.evaluate_tick(context).run_requests
        instance.report_run_canceled(run)
        with build_schedule_context(
            instance=instance, scheduled_execution_time=datetime.now(UTC)
        ) as context:
            assert len(schedule.evaluate_tick(context).run_requests) == 1


def test_foreign_project_does_not_block_and_metadata_error_is_not_empty():
    job = defs.resolve_job_def("pinvi_email_outbox_job")
    with DagsterInstance.ephemeral() as instance:
        instance.create_run_for_job(
            job, status=DagsterRunStatus.STARTED, tags={"kortravelcommon/project": "geo"}
        )
        assert not has_active_run(
            instance, job_name=job.name, project=PINVI_PROJECT, location_name=PINVI_LOCATION_NAME
        )

    class Broken:
        def get_runs(self, **kwargs):
            raise RuntimeError("metadata offline")

    with pytest.raises(RuntimeError, match="offline"):
        has_active_run(
            Broken(), job_name=job.name, project=PINVI_PROJECT, location_name=PINVI_LOCATION_NAME
        )


def test_retry_allowlist_executor_and_notification_cover_every_named_job():
    repository = defs.get_repository_def()
    jobs = [job for job in repository.get_all_jobs() if job.name != "__ASSET_JOB"]
    assert len(jobs) == 8
    for job in jobs:
        assert job.tags["kortravelcommon/job"] == f"pinvi/{job.name}"
        assert job.tags["dagster/max_retries"] == ("1" if job.name in INFRA_RETRY_JOBS else "0")
        assert job.tags["dagster/retry_on_asset_or_op_failure"] == "false"
        # executor config is resolved by the production job definition.
        assert job.executor_def.name == "multiprocess"
    monitored = defs.get_sensor_def("pinvi_run_failure_sensor")._monitored_jobs
    assert {job.name for job in monitored} == {job.name for job in jobs}
    assert (
        len(
            [
                sensor
                for sensor in repository.sensor_defs
                if sensor.name.startswith("pinvi_infra_retry_")
            ]
        )
        == 5
    )
