"""Admin ETL summary service.

Pinvi owns only `app` schema ETL jobs. 지도 feature/provider ETL 상태는
kor-travel-map `/v1/ops/*` HTTP 계약을 통해 읽는다.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapError
from app.clients.kor_travel_map_admin import KorTravelMapAdminClient
from app.core.config import settings
from app.schemas.admin import (
    AdminDagsterJobSummary,
    AdminDagsterRepositorySummary,
    AdminDagsterRunSummary,
    AdminDagsterScheduleSummary,
    AdminDagsterSensorSummary,
    AdminEmailOutboxSummary,
    AdminEmailOutboxTemplateSummary,
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
EMAIL_OUTBOX_STUCK_THRESHOLD_MINUTES = 15
EMAIL_OUTBOX_MAX_ATTEMPTS = 5
EMAIL_OUTBOX_TEMPLATE_WINDOW_HOURS = 24
EMAIL_OUTBOX_TEMPLATE_STATS_LIMIT = 10

PINVI_ETL_ASSETS = [
    AdminEtlDefinitionAsset(
        key="pinvi_kasi_special_days",
        group_name="pinvi_kasi",
        description="KASI 특일·공휴일 기준 데이터를 Pinvi app schema로 적재합니다.",
    ),
    AdminEtlDefinitionAsset(
        key="pinvi_email_outbox",
        group_name="pinvi_email",
        description="email_queue pending/backoff/stuck/failed 상태를 PII 없이 집계합니다.",
    ),
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
    AdminEtlDefinitionJob(
        name="pinvi_email_outbox_job",
        trigger="schedule",
        description="15분마다 email_queue 상태와 template별 실패율을 점검합니다.",
        asset_keys=["pinvi_email_outbox"],
    ),
]

PINVI_ETL_SCHEDULES = [
    AdminEtlDefinitionSchedule(
        name="kasi_special_days_schedule",
        job_name="kasi_special_days_job",
        cron_schedule="30 3 * * *",
        execution_timezone="Asia/Seoul",
    ),
    AdminEtlDefinitionSchedule(
        name="pinvi_email_outbox_schedule",
        job_name="pinvi_email_outbox_job",
        cron_schedule="*/15 * * * *",
        execution_timezone="Asia/Seoul",
    ),
]

PINVI_ETL_SENSORS: list[AdminEtlDefinitionSensor] = []


async def build_admin_etl_summary(
    admin_client: KorTravelMapAdminClient,
    db: AsyncSession,
) -> AdminEtlSummary:
    """Pinvi Dagster registry + kor_travel_map ops snapshot."""
    return AdminEtlSummary(
        generated_at=datetime.now(UTC),
        pinvi=await build_pinvi_etl_summary(db),
        kor_travel_map=await build_kor_travel_map_etl_summary(admin_client),
    )


async def build_pinvi_etl_summary(db: AsyncSession) -> AdminPinviEtlSummary:
    status, message, latency_ms = await _probe_pinvi_dagster()
    return AdminPinviEtlSummary(
        status=status,
        message=message,
        latency_ms=latency_ms,
        assets=PINVI_ETL_ASSETS,
        jobs=PINVI_ETL_JOBS,
        schedules=PINVI_ETL_SCHEDULES,
        sensors=PINVI_ETL_SENSORS,
        email_outbox=await build_email_outbox_summary(db),
    )


async def build_email_outbox_summary(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> AdminEmailOutboxSummary:
    current = now or datetime.now(UTC)
    params = {
        "now": current,
        "stuck_before": current - timedelta(minutes=EMAIL_OUTBOX_STUCK_THRESHOLD_MINUTES),
        "max_attempts": EMAIL_OUTBOX_MAX_ATTEMPTS,
        "template_window_start": current - timedelta(hours=EMAIL_OUTBOX_TEMPLATE_WINDOW_HOURS),
        "template_limit": EMAIL_OUTBOX_TEMPLATE_STATS_LIMIT,
    }
    summary = (await db.execute(_EMAIL_OUTBOX_SUMMARY_SQL, params)).mappings().one()
    templates = list((await db.execute(_EMAIL_OUTBOX_TEMPLATE_SQL, params)).mappings())
    return AdminEmailOutboxSummary(
        total=_as_int(summary["total"]),
        pending_total=_as_int(summary["pending_total"]),
        pending_due=_as_int(summary["pending_due"]),
        pending_backoff=_as_int(summary["pending_backoff"]),
        stuck_pending=_as_int(summary["stuck_pending"]),
        failed=_as_int(summary["failed"]),
        bounced=_as_int(summary["bounced"]),
        complained=_as_int(summary["complained"]),
        retry_exhausted=_as_int(summary["retry_exhausted"]),
        oldest_pending_scheduled_at=summary["oldest_pending_scheduled_at"],
        stuck_threshold_minutes=EMAIL_OUTBOX_STUCK_THRESHOLD_MINUTES,
        max_attempts=EMAIL_OUTBOX_MAX_ATTEMPTS,
        template_window_hours=EMAIL_OUTBOX_TEMPLATE_WINDOW_HOURS,
        template_stats=[_email_template_summary(row) for row in templates],
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


def _email_template_summary(item: Any) -> AdminEmailOutboxTemplateSummary:
    row = item if isinstance(item, Mapping) else {}
    template = _as_str(row.get("template"))
    failed = _as_int(row.get("failed"))
    bounced = _as_int(row.get("bounced"))
    complained = _as_int(row.get("complained"))
    failure_count = failed + bounced + complained
    total = _as_int(row.get("total"))
    return AdminEmailOutboxTemplateSummary(
        template=template or "unknown",
        total=total,
        pending=_as_int(row.get("pending")),
        sent=_as_int(row.get("sent")),
        delivered=_as_int(row.get("delivered")),
        failed=failed,
        bounced=bounced,
        complained=complained,
        failure_count=failure_count,
        failure_rate=0.0 if total == 0 else round(failure_count / total, 4),
    )


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


_EMAIL_OUTBOX_SUMMARY_SQL = text(
    """
    SELECT
      count(*)::int AS total,
      count(*) FILTER (WHERE status = 'pending')::int AS pending_total,
      count(*) FILTER (
        WHERE status = 'pending' AND scheduled_at <= :now
      )::int AS pending_due,
      count(*) FILTER (
        WHERE status = 'pending' AND scheduled_at > :now
      )::int AS pending_backoff,
      count(*) FILTER (
        WHERE status = 'pending' AND scheduled_at <= :stuck_before
      )::int AS stuck_pending,
      count(*) FILTER (WHERE status = 'failed')::int AS failed,
      count(*) FILTER (WHERE status = 'bounced')::int AS bounced,
      count(*) FILTER (WHERE status = 'complained')::int AS complained,
      count(*) FILTER (
        WHERE status = 'failed' OR (status = 'pending' AND attempts >= :max_attempts)
      )::int AS retry_exhausted,
      min(scheduled_at) FILTER (WHERE status = 'pending') AS oldest_pending_scheduled_at
    FROM app.email_queue
    """
)

_EMAIL_OUTBOX_TEMPLATE_SQL = text(
    """
    SELECT
      template,
      count(*)::int AS total,
      count(*) FILTER (WHERE status = 'pending')::int AS pending,
      count(*) FILTER (WHERE status = 'sent')::int AS sent,
      count(*) FILTER (WHERE status = 'delivered')::int AS delivered,
      count(*) FILTER (WHERE status = 'failed')::int AS failed,
      count(*) FILTER (WHERE status = 'bounced')::int AS bounced,
      count(*) FILTER (WHERE status = 'complained')::int AS complained
    FROM app.email_queue
    WHERE created_at >= :template_window_start
    GROUP BY template
    ORDER BY total DESC, template ASC
    LIMIT :template_limit
    """
)
