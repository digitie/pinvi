"""Dagster definitions 로드 sanity 테스트."""

from __future__ import annotations


def test_definitions_load() -> None:
    from pinvi.etl.definitions import defs

    assert defs is not None
    asset_keys = {node.key.to_user_string() for node in defs.resolve_asset_graph().asset_nodes}
    assert "pinvi_kasi_special_days" in asset_keys
    assert "pinvi_email_outbox" in asset_keys
    assert "pinvi_pii_retention" in asset_keys
    assert "pinvi_location_log_archive" in asset_keys
    assert "pinvi_telegram_system_outbox" in asset_keys
    assert "pinvi_weather_retention_horizon_guard" in asset_keys
    assert defs.get_job_def("kasi_poi_rise_set_job") is not None
    assert defs.get_job_def("pinvi_email_outbox_job") is not None
    assert defs.get_job_def("pinvi_pii_retention_job") is not None
    assert defs.get_job_def("pinvi_location_log_archive_job") is not None
    assert defs.get_job_def("pinvi_telegram_system_outbox_job") is not None
    assert defs.get_job_def("pinvi_weather_retention_horizon_job") is not None
    assert defs.get_schedule_def("pinvi_email_outbox_schedule") is not None
    assert defs.get_schedule_def("pinvi_pii_retention_schedule") is not None
    assert defs.get_schedule_def("pinvi_location_log_archive_schedule") is not None
    assert defs.get_schedule_def("pinvi_telegram_system_outbox_schedule") is not None
    assert defs.get_schedule_def("pinvi_weather_retention_horizon_schedule") is not None
    # ADR-050: app-owned job 실패 통지 sensor가 등록돼 있어야 한다 (T-291).
    assert defs.get_sensor_def("pinvi_run_failure_sensor") is not None


def test_every_job_carries_the_pinvi_max_runtime_tag() -> None:
    """공유 Dagster plane에서는 instance의 `max_runtime_seconds`가 테넌트 공통이다.

    PinVi의 상한(3600초)은 job tag로만 살아남는다 — 태그 없는 job은 공유
    instance의 더 긴 상한을 조용히 물려받는다(`pinvi/etl/run_tags.py`).

    **알려진 예외는 `__ASSET_JOB` 하나다** — asset UI Materialize/backfill용 암묵 job이라
    tag를 실을 수 없고 instance 기본값을 받는다(문서화된 한계). 예외는 이름으로 건너뛰지
    않고 집합으로 단언한다: tag 없는 job이 새로 생기면(암묵 job이든 PinVi job이든) 떨어진다.
    """
    from pinvi.etl.definitions import defs
    from pinvi.etl.run_tags import PINVI_JOB_TAGS

    repository = defs.get_repository_def()
    jobs = repository.get_all_jobs()
    untagged = {
        job.name
        for job in jobs
        if any(job.tags.get(key) != value for key, value in PINVI_JOB_TAGS.items())
    }
    assert untagged == {"__ASSET_JOB"}, (
        f"PinVi max_runtime tag가 없는 job: {sorted(untagged)} — 기대는 암묵 `__ASSET_JOB` 하나"
    )
    tagged = [job for job in jobs if job.name not in untagged]
    assert tagged, "tag를 실은 PinVi job이 없다"


def test_instigator_default_status_is_the_production_state() -> None:
    """schedule/sensor의 켜짐 상태는 코드가 정본이다(공유 Dagster plane D4).

    DB에서 손으로 켠 상태는 새 `dagster_shared` instance로 옮겨지지 않는다 —
    코드의 `default_status`만 따라간다. 그래서 운영 상태와 코드 선언이 같아야 한다.

    2026-09-29 n150 운영 webserver(`repositoryOrError` 읽기 전용 조회)에서 본 상태:
    sensor `pinvi_run_failure_sensor`만 RUNNING, schedule 7개는 전부 STOPPED —
    코드 선언과 같다(DB에만 있는 override 없음). 이 기대값을 바꾸는 것은 운영
    상태를 바꾸는 결정이므로, 바꿀 때는 이 테스트와 운영을 함께 맞춘다.
    """
    from dagster import DefaultScheduleStatus, DefaultSensorStatus

    from pinvi.etl.definitions import defs

    repository = defs.get_repository_def()
    running_schedules = {
        schedule.name
        for schedule in repository.schedule_defs
        if schedule.default_status == DefaultScheduleStatus.RUNNING
    }
    running_sensors = {
        sensor.name
        for sensor in repository.sensor_defs
        if sensor.default_status == DefaultSensorStatus.RUNNING
    }
    assert running_schedules == set()
    assert running_sensors == {"pinvi_run_failure_sensor"}


def test_every_scheduled_job_resolves_op_config_from_an_empty_run_config() -> None:
    """스케줄은 run config 없이 launch한다 — 그때도 모든 op가 dict config를 받아야 한다.

    config schema가 없는 asset은 run config가 비면 `context.op_config`가 None이라
    `.get()`에서 죽는다. 2026-09-30 prod에서 PinVi schedule job 4개가 이렇게 반복 실패했다
    (kasi_special_days·trip_day_rise_sets·email_outbox·telegram_system_outbox).
    """
    from dagster import validate_run_config

    from pinvi.etl.definitions import defs

    repository = defs.get_repository_def()
    schedules = list(repository.schedule_defs)
    assert schedules, "schedule이 하나도 없다"
    offenders: list[str] = []
    for schedule in schedules:
        job = repository.get_job(schedule.job_name)
        resolved = validate_run_config(job, {})
        for node_name in job.graph.node_dict:
            op_config = resolved.get("ops", {}).get(node_name, {}).get("config")
            if not isinstance(op_config, dict):
                offenders.append(f"{schedule.job_name}:{node_name}={op_config!r}")
    assert offenders == [], f"빈 run config에서 op config가 dict가 아니다: {offenders}"
