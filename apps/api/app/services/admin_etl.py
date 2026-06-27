"""Admin ETL summary service.

Pinvi owns only `app` schema ETL jobs. 지도 feature/provider ETL 상태는
kor-travel-map `/v1/ops/*` HTTP 계약을 통해 읽는다.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError

from app.clients.kor_travel_map import KorTravelMapError
from app.clients.kor_travel_map_admin import KorTravelMapAdminClient
from app.core.config import settings
from app.schemas.admin import (
    AdminDagsterJobSummary,
    AdminDagsterRepositorySummary,
    AdminDagsterRunSummary,
    AdminDagsterScheduleSummary,
    AdminDagsterSensorSummary,
    AdminEtlDefinitionAsset,
    AdminEtlDefinitionJob,
    AdminEtlDefinitionSchedule,
    AdminEtlDefinitionSensor,
    AdminEtlSummary,
    AdminKorTravelMapEtlSummary,
    AdminPinviEtlSummary,
    AdminProviderDatasetSummary,
    AdminProviderImportJobRecord,
)

PINVI_DAGSTER_PROBE_TIMEOUT_SECONDS = 2.0

PINVI_ETL_ASSETS = [
    AdminEtlDefinitionAsset(
        key="pinvi_kasi_special_days",
        group_name="pinvi_kasi",
        description="KASI 특일·공휴일 기준 데이터를 Pinvi app schema로 적재합니다.",
    )
]

PINVI_ETL_JOBS = [
    AdminEtlDefinitionJob(
        name="kasi_special_days_job",
        trigger="schedule",
        description="매일 KST 03:30 KASI 특일 데이터를 갱신합니다.",
        asset_keys=["pinvi_kasi_special_days"],
    ),
    AdminEtlDefinitionJob(
        name="kasi_poi_rise_set_job",
        trigger="on_demand",
        description="POI별 일출·일몰 보강을 1회 실행합니다.",
        asset_keys=[],
    ),
]

PINVI_ETL_SCHEDULES = [
    AdminEtlDefinitionSchedule(
        name="kasi_special_days_schedule",
        job_name="kasi_special_days_job",
        cron_schedule="30 3 * * *",
        execution_timezone="Asia/Seoul",
    )
]

PINVI_ETL_SENSORS: list[AdminEtlDefinitionSensor] = []


async def build_admin_etl_summary(
    admin_client: KorTravelMapAdminClient,
) -> AdminEtlSummary:
    """Pinvi Dagster registry + kor_travel_map ops snapshot."""
    return AdminEtlSummary(
        generated_at=datetime.now(UTC),
        pinvi=await build_pinvi_etl_summary(),
        kor_travel_map=await build_kor_travel_map_etl_summary(admin_client),
    )


async def build_pinvi_etl_summary() -> AdminPinviEtlSummary:
    status, message, latency_ms = await _probe_pinvi_dagster()
    return AdminPinviEtlSummary(
        status=status,
        message=message,
        latency_ms=latency_ms,
        assets=PINVI_ETL_ASSETS,
        jobs=PINVI_ETL_JOBS,
        schedules=PINVI_ETL_SCHEDULES,
        sensors=PINVI_ETL_SENSORS,
    )


async def build_kor_travel_map_etl_summary(
    admin_client: KorTravelMapAdminClient,
) -> AdminKorTravelMapEtlSummary:
    errors: list[str] = []
    dagster: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    providers: list[AdminProviderDatasetSummary] = []
    recent_import_jobs: list[AdminProviderImportJobRecord] = []

    try:
        dagster = await admin_client.get_ops_dagster_summary(page_size=10)
    except KorTravelMapError as exc:
        errors.append(_safe_error_message(exc))
    try:
        metrics = await admin_client.get_ops_metrics()
    except KorTravelMapError as exc:
        errors.append(_safe_error_message(exc))
    try:
        provider_data = await admin_client.list_ops_providers()
        raw_items = provider_data.get("items", [])
        if isinstance(raw_items, list):
            providers = [AdminProviderDatasetSummary.model_validate(item) for item in raw_items]
    except (KorTravelMapError, ValidationError) as exc:
        errors.append(_safe_error_message(exc))
    try:
        import_payload = await admin_client.list_ops_import_jobs(page_size=10)
        raw_jobs = import_payload.get("data", {}).get("items", [])
        if isinstance(raw_jobs, list):
            recent_import_jobs = [
                AdminProviderImportJobRecord.model_validate(item) for item in raw_jobs
            ]
    except (KorTravelMapError, ValidationError) as exc:
        errors.append(_safe_error_message(exc))

    return _build_kor_travel_map_summary(
        dagster=dagster,
        metrics=metrics,
        providers=providers,
        recent_import_jobs=recent_import_jobs,
        errors=errors,
    )


def _build_kor_travel_map_summary(
    *,
    dagster: dict[str, Any],
    metrics: dict[str, Any],
    providers: list[AdminProviderDatasetSummary],
    recent_import_jobs: list[AdminProviderImportJobRecord],
    errors: list[str],
) -> AdminKorTravelMapEtlSummary:
    dagster_status = _as_str(dagster.get("status")) or ("unavailable" if errors else "unknown")
    status = "ok"
    if errors:
        status = "degraded" if dagster or metrics or providers or recent_import_jobs else "down"
    if dagster_status in {"unavailable", "error"}:
        status = "degraded" if status == "ok" else status

    provider_failure_count = sum(1 for item in providers if item.consecutive_failures > 0)
    return AdminKorTravelMapEtlSummary(
        status=status,
        dagster_status=dagster_status,
        checked_at=_as_datetime(dagster.get("checked_at"))
        or _as_datetime(metrics.get("checked_at")),
        repository_count=_as_int(dagster.get("repository_count")),
        job_count=_as_int(dagster.get("job_count")),
        asset_count=_as_int(dagster.get("asset_count")),
        schedule_count=_as_int(dagster.get("schedule_count")),
        sensor_count=_as_int(dagster.get("sensor_count")),
        run_counts=_int_dict(dagster.get("run_counts")),
        repositories=_repositories(dagster.get("repositories")),
        recent_runs=_runs(dagster.get("recent_runs")),
        features_total=_optional_int(metrics.get("features_total")),
        source_records_total=_optional_int(metrics.get("source_records_total")),
        import_jobs_by_status=_int_dict(metrics.get("import_jobs_by_status")),
        dedup_queue_by_status=_int_dict(metrics.get("dedup_queue_by_status")),
        provider_dataset_count=len(providers),
        provider_failure_count=provider_failure_count,
        recent_import_jobs=recent_import_jobs,
        errors=errors,
    )


async def _probe_pinvi_dagster() -> tuple[str, str, int | None]:
    base_url = settings.pinvi_dagster_base_url.strip()
    if not base_url:
        return "unknown", "Dagster URL 미설정", None
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=PINVI_DAGSTER_PROBE_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{base_url.rstrip('/')}/")
    except httpx.HTTPError:
        return "down", "Dagster 연결 실패", _elapsed_ms(start)
    ok = 200 <= response.status_code < 400
    return (
        "ok" if ok else "degraded",
        "Dagster 응답 정상" if ok else f"Dagster HTTP {response.status_code}",
        _elapsed_ms(start),
    )


def _repositories(value: Any) -> list[AdminDagsterRepositorySummary]:
    if not isinstance(value, list):
        return []
    repositories: list[AdminDagsterRepositorySummary] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        repositories.append(
            AdminDagsterRepositorySummary(
                name=_as_str(item.get("name")) or "unknown",
                location_name=_as_str(item.get("location_name")),
                jobs=[
                    AdminDagsterJobSummary(
                        name=_as_str(job.get("name")) or "unknown",
                        is_job=bool(job.get("is_job", True)),
                    )
                    for job in item.get("jobs", [])
                    if isinstance(job, dict)
                ],
                schedules=[
                    AdminDagsterScheduleSummary(
                        name=_as_str(schedule.get("name")) or "unknown",
                        cron_schedule=_as_str(schedule.get("cron_schedule")),
                        execution_timezone=_as_str(schedule.get("execution_timezone")),
                        status=_as_str(schedule.get("status")),
                    )
                    for schedule in item.get("schedules", [])
                    if isinstance(schedule, dict)
                ],
                sensors=[
                    AdminDagsterSensorSummary(
                        name=_as_str(sensor.get("name")) or "unknown",
                        status=_as_str(sensor.get("status")),
                    )
                    for sensor in item.get("sensors", [])
                    if isinstance(sensor, dict)
                ],
                asset_count=_as_int(item.get("asset_count")),
                asset_groups=[
                    group for group in item.get("asset_groups", []) if isinstance(group, str)
                ],
            )
        )
    return repositories


def _runs(value: Any) -> list[AdminDagsterRunSummary]:
    if not isinstance(value, list):
        return []
    runs: list[AdminDagsterRunSummary] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        run_id = _as_str(item.get("run_id"))
        status = _as_str(item.get("status"))
        if not run_id or not status:
            continue
        runs.append(
            AdminDagsterRunSummary(
                run_id=run_id,
                status=status,
                job_name=_as_str(item.get("job_name")),
                start_time=_optional_float(item.get("start_time")),
                end_time=_optional_float(item.get("end_time")),
                update_time=_optional_float(item.get("update_time")),
                tags={k: v for k, v in item.get("tags", {}).items()}
                if isinstance(item.get("tags"), dict)
                else {},
            )
        )
    return runs


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        result[key] = _as_int(raw)
    return result


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed_ms(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


def _safe_error_message(exc: Exception) -> str:
    name = exc.__class__.__name__
    return name if not str(exc) else f"{name}: {str(exc)[:120]}"
