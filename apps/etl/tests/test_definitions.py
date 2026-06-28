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
    assert defs.get_job_def("kasi_poi_rise_set_job") is not None
    assert defs.get_job_def("pinvi_email_outbox_job") is not None
    assert defs.get_job_def("pinvi_pii_retention_job") is not None
    assert defs.get_job_def("pinvi_location_log_archive_job") is not None
    assert defs.get_job_def("pinvi_telegram_system_outbox_job") is not None
    assert defs.get_schedule_def("pinvi_email_outbox_schedule") is not None
    assert defs.get_schedule_def("pinvi_pii_retention_schedule") is not None
    assert defs.get_schedule_def("pinvi_location_log_archive_schedule") is not None
    assert defs.get_schedule_def("pinvi_telegram_system_outbox_schedule") is not None
    # ADR-050: app-owned job 실패 통지 sensor가 등록돼 있어야 한다 (T-291).
    assert defs.get_sensor_def("pinvi_run_failure_sensor") is not None
