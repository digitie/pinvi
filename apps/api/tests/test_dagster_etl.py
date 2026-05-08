from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.etl_config import get_etl_dataset_config
from app.dagster_etl.definitions import (
    DAGSTER_JOBS,
    build_dagster_job,
    build_dagster_schedule,
    build_run_config,
)
from app.dagster_etl.loaders import load_opinet_region_codes as load_opinet_region_codes_dataset
from app.dagster_etl.registry import ALL_ETL_SPECS
from app.dagster_etl.runtime import (
    DagsterEtlRun,
    EtlJobSpec,
    TripMateEtlSkip,
    default_identity,
    execute_etl_spec,
    execution_from_config,
    json_ready,
    juso_monthly_identity,
    parse_logical_datetime,
    schedule_requires_any_env,
    source_year_month_override_from_config,
)
from app.etl.opinet.client import OpiNetApiError
from app.etl.vworld.legal_dong_code_loader import download_latest_legal_dong_code_csv
from app.models.etl import AdminNotification, EtlRunLog, TelegramSystemNotificationOutbox
from app.models.fuel import FuelServingOpiNetRegionCode
from app.services.etl_runtime import create_etl_run_log, mark_etl_run_success

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True)
class _FakeResult:
    row_count: int
    collected_on: date
    artifact_path: Path


def test_dagster_jobs_cover_every_tripmate_etl_spec() -> None:
    assert len(DAGSTER_JOBS) == len(ALL_ETL_SPECS)
    assert [job.name for job in DAGSTER_JOBS] == [spec.job_name for spec in ALL_ETL_SPECS]
    assert len({job.name for job in DAGSTER_JOBS}) == len(DAGSTER_JOBS)
    assert len({spec.op_name for spec in ALL_ETL_SPECS}) == len(ALL_ETL_SPECS)

    for spec, job in zip(ALL_ETL_SPECS, DAGSTER_JOBS, strict=True):
        runtime_config = get_etl_dataset_config(spec.dataset_key)
        node = job.graph.node_named(spec.op_name)
        op_definition: Any = node.definition
        assert node.name == spec.op_name
        assert job.description == spec.description
        assert job.tags["tripmate/dataset_key"] == spec.dataset_key
        assert op_definition.retry_policy is not None
        assert op_definition.retry_policy.max_retries == runtime_config.retry_max_attempts


def test_dagster_schedules_match_dataset_config_and_kst_timezone(monkeypatch: Any) -> None:
    monkeypatch.delenv("TRIPMATE_KHOA_API_KEY", raising=False)
    monkeypatch.delenv("TRIPMATE_DATA_GO_SERVICE_KEY", raising=False)

    schedules = {
        schedule.name: schedule
        for spec, job in zip(ALL_ETL_SPECS, DAGSTER_JOBS, strict=True)
        if (schedule := build_dagster_schedule(spec, job)) is not None
    }

    disabled_without_keys = {
        "khoa_beach_observation_hourly_schedule",
        "khoa_beach_index_forecast_twice_daily_schedule",
        "khoa_mudflat_index_forecast_twice_daily_schedule",
        "khoa_sea_split_index_forecast_twice_daily_schedule",
    }
    assert disabled_without_keys.isdisjoint(schedules)

    for spec in ALL_ETL_SPECS:
        if spec.schedule_enabled is not None and not spec.schedule_enabled():
            continue
        runtime_config = get_etl_dataset_config(spec.dataset_key)
        if runtime_config.schedule == "manual":
            continue
        schedule = schedules[f"{spec.job_name}_schedule"]
        assert schedule.cron_schedule == runtime_config.schedule
        assert schedule.execution_timezone == "Asia/Seoul"
        assert schedule.job_name == spec.job_name


def test_key_gated_dagster_schedules_become_active_when_key_exists(monkeypatch: Any) -> None:
    monkeypatch.setenv("TRIPMATE_DATA_GO_SERVICE_KEY", "test-key")

    schedule_names = {
        schedule.name
        for spec, job in zip(ALL_ETL_SPECS, DAGSTER_JOBS, strict=True)
        if (schedule := build_dagster_schedule(spec, job)) is not None
    }

    assert "khoa_beach_index_forecast_twice_daily_schedule" in schedule_names
    assert "khoa_mudflat_index_forecast_twice_daily_schedule" in schedule_names
    assert "khoa_sea_split_index_forecast_twice_daily_schedule" in schedule_names
    assert "khoa_beach_observation_hourly_schedule" not in schedule_names


def test_schedule_run_config_passes_logical_datetime_to_op() -> None:
    spec = ALL_ETL_SPECS[0]
    logical_datetime = datetime(2026, 5, 8, 4, 30, tzinfo=KST)

    run_config = build_run_config(spec, logical_datetime)

    assert run_config == {
        "ops": {
            spec.op_name: {
                "config": {
                    "logical_datetime": "2026-05-08T04:30:00+09:00",
                    "run_type": "scheduled",
                }
            }
        }
    }


def test_parse_logical_datetime_keeps_kst_policy() -> None:
    assert parse_logical_datetime("2026-05-08").isoformat() == "2026-05-08T00:00:00+09:00"
    assert (
        parse_logical_datetime("2026-05-07T19:30:00+00:00").isoformat()
        == "2026-05-08T04:30:00+09:00"
    )
    assert (
        parse_logical_datetime(datetime(2026, 5, 8, 4, 30)).isoformat()
        == "2026-05-08T04:30:00+09:00"
    )


def test_source_year_month_config_validation() -> None:
    assert source_year_month_override_from_config({}) is None
    assert source_year_month_override_from_config({"source_year_month": "202603"}) == "202603"

    with pytest.raises(ValueError, match="YYYYMM"):
        source_year_month_override_from_config({"source_year_month": "2026-03"})
    with pytest.raises(ValueError, match="between 01 and 12"):
        source_year_month_override_from_config({"source_year_month": "202613"})


def test_juso_identity_uses_manual_month_and_skips_existing_success(db_session: Session) -> None:
    runtime_config = get_etl_dataset_config("juso_road_address_korean")
    run_log = create_etl_run_log(
        db_session,
        dataset_key="juso_road_address_korean",
        run_key="202603",
        run_type="manual",
        trigger_date=date(2026, 5, 8),
        config=runtime_config,
    )
    mark_etl_run_success(run_log, message="ok")
    db_session.flush()

    execution = execution_from_config(
        {
            "logical_datetime": "2026-05-08T04:30:00+09:00",
            "source_year_month": "202603",
        }
    )
    identity = juso_monthly_identity(db_session, "juso_road_address_korean", execution)

    assert identity.run_key == "202603"
    assert identity.run_type == "manual"
    assert identity.should_skip is True
    assert "이미 성공" in (identity.skip_message or "")


def test_default_identity_uses_timestamp_run_key(db_session: Session) -> None:
    execution = execution_from_config(
        {"logical_datetime": "2026-05-08T04:30:00+09:00", "run_type": "scheduled"}
    )

    identity = default_identity(db_session, "public_campground", execution)

    assert identity.run_key == "20260508T043000"
    assert identity.run_type == "scheduled"
    assert identity.trigger_date == date(2026, 5, 8)


def test_json_ready_handles_dataclasses_paths_dates_and_nested_values(tmp_path: Path) -> None:
    payload = json_ready(
        {
            "result": _FakeResult(2, date(2026, 5, 8), tmp_path / "x.csv"),
            "items": {date(2026, 5, 8), "ok"},
        }
    )

    assert payload["result"] == {
        "row_count": 2,
        "collected_on": "2026-05-08",
        "artifact_path": str(tmp_path / "x.csv"),
    }
    items = payload["items"]
    assert isinstance(items, list)
    assert sorted(str(item) for item in items) == ["2026-05-08", "ok"]


def test_execute_etl_spec_success_writes_success_log(
    monkeypatch: Any,
    postgres_test_database_url: str,
    db_session: Session,
) -> None:
    _ = db_session
    monkeypatch.setenv("TRIPMATE_DATABASE_URL", postgres_test_database_url)

    def loader(_session: Session, run: DagsterEtlRun) -> _FakeResult:
        assert run.run_key == "20260508T043000"
        return _FakeResult(3, run.trigger_date, Path("/tmp/fake.csv"))

    spec = _fake_spec(loader)
    result = execute_etl_spec(
        spec,
        execution_from_config(
            {"logical_datetime": "2026-05-08T04:30:00+09:00", "run_type": "manual"}
        ),
        retry_exhausted=True,
    )

    assert result["row_count"] == 3
    assert _scalar_count(postgres_test_database_url, EtlRunLog, "success") == 1
    assert _scalar_count(postgres_test_database_url, AdminNotification) == 0


def test_execute_etl_spec_skip_writes_skipped_log_without_notification(
    monkeypatch: Any,
    postgres_test_database_url: str,
    db_session: Session,
) -> None:
    _ = db_session
    monkeypatch.setenv("TRIPMATE_DATABASE_URL", postgres_test_database_url)

    def loader(_session: Session, _run: DagsterEtlRun) -> object:
        raise TripMateEtlSkip("optional source file is not configured")

    result = execute_etl_spec(
        _fake_spec(loader),
        execution_from_config({"logical_datetime": "2026-05-08T04:30:00+09:00"}),
        retry_exhausted=True,
    )

    assert result["status"] == "skipped"
    assert "optional source file" in str(result["message"])
    assert _scalar_count(postgres_test_database_url, EtlRunLog, "skipped") == 1
    assert _scalar_count(postgres_test_database_url, AdminNotification) == 0


def test_opinet_region_dataset_uses_fresh_cache_on_zero_provider_response(
    monkeypatch: Any,
    db_session: Session,
) -> None:
    _add_cached_opinet_region(db_session, collected_at=datetime(2026, 5, 8, 4, 0, tzinfo=KST))
    _make_opinet_region_source_return_zero(monkeypatch)

    with pytest.raises(TripMateEtlSkip, match="using 1 cached region code rows"):
        load_opinet_region_codes_dataset(
            db_session,
            _dagster_run_for_test(logical_datetime=datetime(2026, 5, 8, 5, 0, tzinfo=KST)),
        )


def test_opinet_region_dataset_raises_when_zero_provider_response_has_stale_cache(
    monkeypatch: Any,
    db_session: Session,
) -> None:
    _add_cached_opinet_region(db_session, collected_at=datetime(2026, 1, 1, 12, 0, tzinfo=KST))
    _make_opinet_region_source_return_zero(monkeypatch)

    with pytest.raises(OpiNetApiError, match="zero sido rows"):
        load_opinet_region_codes_dataset(
            db_session,
            _dagster_run_for_test(logical_datetime=datetime(2026, 5, 8, 5, 0, tzinfo=KST)),
        )


def test_execute_etl_spec_failed_retry_does_not_notify_until_exhausted(
    monkeypatch: Any,
    postgres_test_database_url: str,
    db_session: Session,
) -> None:
    _ = db_session
    monkeypatch.setenv("TRIPMATE_DATABASE_URL", postgres_test_database_url)

    def loader(_session: Session, _run: DagsterEtlRun) -> object:
        raise RuntimeError("GET https://api.example.test?serviceKey=secret-key failed")

    with pytest.raises(RuntimeError):
        execute_etl_spec(
            _fake_spec(loader),
            execution_from_config({"logical_datetime": "2026-05-08T04:30:00+09:00"}),
            retry_exhausted=False,
        )

    assert _scalar_count(postgres_test_database_url, EtlRunLog, "failed") == 1
    assert _scalar_count(postgres_test_database_url, AdminNotification) == 0
    assert _scalar_count(postgres_test_database_url, TelegramSystemNotificationOutbox) == 0


def test_execute_etl_spec_exhausted_failure_redacts_and_notifies(
    monkeypatch: Any,
    postgres_test_database_url: str,
    db_session: Session,
) -> None:
    _ = db_session
    monkeypatch.setenv("TRIPMATE_DATABASE_URL", postgres_test_database_url)

    def loader(_session: Session, _run: DagsterEtlRun) -> object:
        raise RuntimeError("GET https://api.example.test?certkey=secret-key failed")

    with pytest.raises(RuntimeError):
        execute_etl_spec(
            _fake_spec(loader),
            execution_from_config({"logical_datetime": "2026-05-08T04:30:00+09:00"}),
            retry_exhausted=True,
        )

    run_log = _latest_run_log(postgres_test_database_url)
    assert run_log.status == "failed"
    assert run_log.extra["retry_exhausted"] is True
    assert "secret-key" not in (run_log.error_message or "")
    assert "certkey=***" in (run_log.error_message or "")
    assert _scalar_count(postgres_test_database_url, AdminNotification) == 1
    assert _scalar_count(postgres_test_database_url, TelegramSystemNotificationOutbox) == 1


def test_dagster_job_execute_in_process_uses_tripmate_executor(
    monkeypatch: Any,
    postgres_test_database_url: str,
    db_session: Session,
) -> None:
    _ = db_session
    monkeypatch.setenv("TRIPMATE_DATABASE_URL", postgres_test_database_url)

    def loader(_session: Session, run: DagsterEtlRun) -> dict[str, Any]:
        return {"run_key": run.run_key, "collected_at": run.collected_at}

    spec = _fake_spec(loader, job_name="fake_dagster_smoke_job", op_name="load_fake_smoke")
    job = build_dagster_job(spec)

    result = job.execute_in_process(
        run_config={
            "ops": {
                spec.op_name: {
                    "config": {
                        "logical_datetime": "2026-05-08T04:30:00+09:00",
                        "run_type": "manual",
                    }
                }
            }
        }
    )

    assert result.success is True
    assert _scalar_count(postgres_test_database_url, EtlRunLog, "success") == 1


def test_schedule_requires_any_env_checks_multiple_key_names(monkeypatch: Any) -> None:
    enabled = schedule_requires_any_env("TRIPMATE_KHOA_API_KEY", "TRIPMATE_DATA_GO_SERVICE_KEY")
    monkeypatch.delenv("TRIPMATE_KHOA_API_KEY", raising=False)
    monkeypatch.delenv("TRIPMATE_DATA_GO_SERVICE_KEY", raising=False)
    assert enabled() is False

    monkeypatch.setenv("TRIPMATE_DATA_GO_SERVICE_KEY", "test-key")
    assert enabled() is True


@pytest.mark.live
def test_live_data_go_legal_dong_download_smoke(tmp_path: Path) -> None:
    if os.environ.get("TRIPMATE_LIVE_ETL_TESTS") != "1":
        pytest.skip("Set TRIPMATE_LIVE_ETL_TESTS=1 to call the live data.go.kr endpoint.")

    settings = get_settings()
    result = download_latest_legal_dong_code_csv(
        tmp_path,
        service_key=settings.data_go_service_key,
    )

    assert result.file_path.exists()
    assert result.file_path.stat().st_size > 0
    assert len(result.source_file_hash) == 64
    if settings.data_go_service_key:
        assert settings.data_go_service_key not in result.download_url
    assert result.download_url.startswith("https://")


def _dagster_run_for_test(*, logical_datetime: datetime) -> DagsterEtlRun:
    return DagsterEtlRun(
        dataset_key="fuel_region_code",
        run_key=logical_datetime.strftime("%Y%m%dT%H%M%S"),
        run_type="scheduled",
        trigger_date=logical_datetime.date(),
        logical_datetime=logical_datetime,
        op_config={},
    )


def _add_cached_opinet_region(db_session: Session, *, collected_at: datetime) -> None:
    db_session.add(
        FuelServingOpiNetRegionCode(
            provider_region_code="01",
            provider_region_name="서울",
            region_level="sido",
            parent_provider_region_code=None,
            address_code_standard_code=None,
            mapping_status="unmatched",
            mapping_source="test",
            raw_payload={"AREA_CD": "01", "AREA_NM": "서울"},
            collected_at=collected_at,
            is_active=True,
        )
    )
    db_session.flush()


def _make_opinet_region_source_return_zero(monkeypatch: Any) -> None:
    from app.etl.opinet import client as opinet_client_module
    from app.etl.opinet import loader as opinet_loader_module

    def fake_load_region_codes(*_args: Any, **_kwargs: Any) -> object:
        raise OpiNetApiError("OpiNet areaCode.do returned zero sido rows.")

    monkeypatch.setattr(opinet_client_module, "OpiNetApiClient", lambda: object())
    monkeypatch.setattr(opinet_loader_module, "load_opinet_region_codes", fake_load_region_codes)


def _fake_spec(
    loader: Any,
    *,
    job_name: str = "fake_tripmate_etl_job",
    op_name: str = "load_fake_tripmate_etl",
) -> EtlJobSpec:
    return EtlJobSpec(
        job_name=job_name,
        op_name=op_name,
        dataset_key="public_campground",
        description="Fake TripMate ETL job for tests.",
        tags=("tripmate", "test"),
        loader=loader,
        success_message="공공 장소 ETL 성공: {dataset_key}",
        failure_message="공공 장소 ETL 실패: {dataset_key}",
    )


def _scalar_count(
    database_url: str,
    model: type[Any],
    status: str | None = None,
) -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            statement = select(func.count()).select_from(model)
            if status is not None:
                statement = statement.where(EtlRunLog.status == status)
            return int(session.scalar(statement) or 0)
    finally:
        engine.dispose()


def _latest_run_log(database_url: str) -> EtlRunLog:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as session:
            run_log = session.scalar(select(EtlRunLog).order_by(EtlRunLog.id.desc()).limit(1))
            assert run_log is not None
            session.expunge(run_log)
            return run_log
    finally:
        engine.dispose()
