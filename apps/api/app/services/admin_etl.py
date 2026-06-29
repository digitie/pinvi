"""Admin ETL summary service.

Pinvi owns only `app` schema ETL jobs. 지도 feature/provider ETL 상태는
kor-travel-map `/v1/ops/*` HTTP 계약을 통해 읽는다.
"""

from __future__ import annotations

import time
from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    AdminAuditRetentionSummary,
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
    AdminLocationLogArchivePurposeSummary,
    AdminLocationLogArchiveSummary,
    AdminPiiRetentionSummary,
    AdminPinviEtlSummary,
    AdminProviderDatasetSummary,
    AdminProviderImportJobRecord,
    AdminSystemStatus,
    AdminTelegramOutboxCategorySummary,
    AdminTelegramOutboxSummary,
)

PINVI_DAGSTER_PROBE_TIMEOUT_SECONDS = 2.0
PINVI_DAGSTER_RECENT_RUN_LIMIT = 5
EMAIL_OUTBOX_STUCK_THRESHOLD_MINUTES = 15
EMAIL_OUTBOX_MAX_ATTEMPTS = 5
EMAIL_OUTBOX_TEMPLATE_WINDOW_HOURS = 24
EMAIL_OUTBOX_TEMPLATE_STATS_LIMIT = 10
TELEGRAM_OUTBOX_STUCK_THRESHOLD_MINUTES = 15
TELEGRAM_OUTBOX_MAX_ATTEMPTS = 5
TELEGRAM_OUTBOX_CATEGORY_WINDOW_HOURS = 24
TELEGRAM_OUTBOX_CATEGORY_STATS_LIMIT = 10
PII_RETENTION_USER_GRACE_DAYS = 30
PII_RETENTION_SESSION_GRACE_DAYS = 30
AUDIT_RETENTION_DAYS = 90
LOCATION_LOG_ARCHIVE_RETENTION_MONTHS = 6
LOCATION_LOG_ARCHIVE_PURPOSE_STATS_LIMIT = 10

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
    AdminEtlDefinitionAsset(
        key="pinvi_telegram_system_outbox",
        group_name="pinvi_telegram",
        description="telegram_system_notification_outbox retry/backoff/stuck 상태를 payload 없이 집계합니다.",
    ),
    AdminEtlDefinitionAsset(
        key="pinvi_pii_retention",
        group_name="pinvi_retention",
        description="PIPA/LBS 보존 기간 만료 후보를 dry-run metadata로 집계합니다.",
    ),
    AdminEtlDefinitionAsset(
        key="pinvi_location_log_archive",
        group_name="pinvi_retention",
        description="location_access_log archive 후보와 hash-chain bridge 상태를 dry-run으로 집계합니다.",
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
    AdminEtlDefinitionJob(
        name="pinvi_telegram_system_outbox_job",
        trigger="schedule",
        description="15분마다 Telegram system outbox의 retry/backoff/stuck 상태를 점검합니다.",
        asset_keys=["pinvi_telegram_system_outbox"],
    ),
    AdminEtlDefinitionJob(
        name="pinvi_pii_retention_job",
        trigger="schedule",
        description="매일 KST 04:15 PII 보존 기간 만료 후보를 dry-run으로 점검합니다.",
        asset_keys=["pinvi_pii_retention"],
    ),
    AdminEtlDefinitionJob(
        name="pinvi_location_log_archive_job",
        trigger="schedule",
        description="매일 KST 04:30 위치 접근 로그 archive 후보와 chain bridge 상태를 점검합니다.",
        asset_keys=["pinvi_location_log_archive"],
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
    AdminEtlDefinitionSchedule(
        name="pinvi_telegram_system_outbox_schedule",
        job_name="pinvi_telegram_system_outbox_job",
        cron_schedule="*/15 * * * *",
        execution_timezone="Asia/Seoul",
    ),
    AdminEtlDefinitionSchedule(
        name="pinvi_pii_retention_schedule",
        job_name="pinvi_pii_retention_job",
        cron_schedule="15 4 * * *",
        execution_timezone="Asia/Seoul",
    ),
    AdminEtlDefinitionSchedule(
        name="pinvi_location_log_archive_schedule",
        job_name="pinvi_location_log_archive_job",
        cron_schedule="30 4 * * *",
        execution_timezone="Asia/Seoul",
    ),
]

PINVI_ETL_SENSORS: list[AdminEtlDefinitionSensor] = []

_PINVI_DAGSTER_LIVE_QUERY = """
query PinviDagsterLive($runLimit: Int!) {
  version
  repositoriesOrError {
    __typename
    ... on RepositoryConnection {
      nodes {
        name
        location { name }
        jobs { name isJob }
        schedules {
          name
          pipelineName
          cronSchedule
          executionTimezone
          scheduleState { status }
        }
        sensors {
          name
          sensorState { status }
        }
        assetNodes { groupName }
      }
    }
    ... on PythonError { message }
    ... on RepositoryNotFoundError { message }
  }
  runsOrError(limit: $runLimit) {
    __typename
    ... on Runs {
      results {
        runId
        status
        jobName
        startTime
        endTime
        updateTime
      }
    }
    ... on PythonError { message }
    ... on InvalidPipelineRunsFilterError { message }
  }
}
"""


@dataclass(frozen=True, slots=True)
class _PinviDagsterProbeResult:
    status: AdminSystemStatus
    message: str | None
    latency_ms: int | None
    checked_at: datetime
    dagster_version: str | None = None
    dagster_webserver_version: str | None = None
    dagster_graphql_version: str | None = None
    repositories: list[AdminDagsterRepositorySummary] = field(default_factory=list)
    recent_runs: list[AdminDagsterRunSummary] = field(default_factory=list)

    @property
    def repository_count(self) -> int:
        return len(self.repositories)

    @property
    def job_count(self) -> int:
        return sum(len(item.jobs) for item in self.repositories)

    @property
    def asset_count(self) -> int:
        return sum(item.asset_count for item in self.repositories)

    @property
    def schedule_count(self) -> int:
        return sum(len(item.schedules) for item in self.repositories)

    @property
    def sensor_count(self) -> int:
        return sum(len(item.sensors) for item in self.repositories)


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
    dagster = await _probe_pinvi_dagster()
    return AdminPinviEtlSummary(
        status=dagster.status,
        message=dagster.message,
        latency_ms=dagster.latency_ms,
        checked_at=dagster.checked_at,
        dagster_version=dagster.dagster_version,
        dagster_webserver_version=dagster.dagster_webserver_version,
        dagster_graphql_version=dagster.dagster_graphql_version,
        repository_count=dagster.repository_count,
        job_count=dagster.job_count,
        asset_count=dagster.asset_count,
        schedule_count=dagster.schedule_count,
        sensor_count=dagster.sensor_count,
        repositories=dagster.repositories,
        recent_runs=dagster.recent_runs,
        assets=PINVI_ETL_ASSETS,
        jobs=PINVI_ETL_JOBS,
        schedules=PINVI_ETL_SCHEDULES,
        sensors=PINVI_ETL_SENSORS,
        email_outbox=await build_email_outbox_summary(db),
        telegram_outbox=await build_telegram_outbox_summary(db),
        pii_retention=await build_pii_retention_summary(db),
        audit_retention=await build_audit_retention_summary(db),
        location_log_archive=await build_location_log_archive_summary(db),
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
        suppressed=_as_int(summary["suppressed"]),
        delivery_delayed=_as_int(summary["delivery_delayed"]),
        retry_exhausted=_as_int(summary["retry_exhausted"]),
        oldest_pending_scheduled_at=summary["oldest_pending_scheduled_at"],
        stuck_threshold_minutes=EMAIL_OUTBOX_STUCK_THRESHOLD_MINUTES,
        max_attempts=EMAIL_OUTBOX_MAX_ATTEMPTS,
        template_window_hours=EMAIL_OUTBOX_TEMPLATE_WINDOW_HOURS,
        template_stats=[_email_template_summary(row) for row in templates],
    )


async def build_telegram_outbox_summary(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> AdminTelegramOutboxSummary:
    current = now or datetime.now(UTC)
    params = {
        "now": current,
        "stuck_before": current - timedelta(minutes=TELEGRAM_OUTBOX_STUCK_THRESHOLD_MINUTES),
        "max_attempts": TELEGRAM_OUTBOX_MAX_ATTEMPTS,
        "category_window_start": current - timedelta(hours=TELEGRAM_OUTBOX_CATEGORY_WINDOW_HOURS),
        "category_limit": TELEGRAM_OUTBOX_CATEGORY_STATS_LIMIT,
    }
    summary = (await db.execute(_TELEGRAM_OUTBOX_SUMMARY_SQL, params)).mappings().one()
    categories = list((await db.execute(_TELEGRAM_OUTBOX_CATEGORY_SQL, params)).mappings())
    return AdminTelegramOutboxSummary(
        total=_as_int(summary["total"]),
        pending_total=_as_int(summary["pending_total"]),
        pending_due=_as_int(summary["pending_due"]),
        pending_backoff=_as_int(summary["pending_backoff"]),
        stuck_pending=_as_int(summary["stuck_pending"]),
        sent=_as_int(summary["sent"]),
        skipped=_as_int(summary["skipped"]),
        failed=_as_int(summary["failed"]),
        retry_exhausted=_as_int(summary["retry_exhausted"]),
        oldest_pending_scheduled_at=summary["oldest_pending_scheduled_at"],
        stuck_threshold_minutes=TELEGRAM_OUTBOX_STUCK_THRESHOLD_MINUTES,
        max_attempts=TELEGRAM_OUTBOX_MAX_ATTEMPTS,
        category_window_hours=TELEGRAM_OUTBOX_CATEGORY_WINDOW_HOURS,
        category_stats=[_telegram_category_summary(row) for row in categories],
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
    status: AdminSystemStatus = "ok"
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


async def _probe_pinvi_dagster() -> _PinviDagsterProbeResult:
    base_url = settings.pinvi_dagster_base_url.strip()
    checked_at = datetime.now(UTC)
    if not base_url:
        return _PinviDagsterProbeResult(
            status="unknown",
            message="Dagster URL 미설정",
            latency_ms=None,
            checked_at=checked_at,
        )
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=PINVI_DAGSTER_PROBE_TIMEOUT_SECONDS) as client:
            return await _fetch_pinvi_dagster_snapshot(
                client,
                base_url=base_url.rstrip("/"),
                start=start,
                checked_at=checked_at,
            )
    except httpx.HTTPError:
        return _PinviDagsterProbeResult(
            status="down",
            message="Dagster 연결 실패",
            latency_ms=_elapsed_ms(start),
            checked_at=checked_at,
        )


async def _fetch_pinvi_dagster_snapshot(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    start: float,
    checked_at: datetime,
) -> _PinviDagsterProbeResult:
    server_response = await client.get(f"{base_url}/server_info")
    if not 200 <= server_response.status_code < 400:
        return _PinviDagsterProbeResult(
            status="degraded",
            message=f"Dagster server_info HTTP {server_response.status_code}",
            latency_ms=_elapsed_ms(start),
            checked_at=checked_at,
        )
    server_info = _json_object(server_response)
    latency_ms = _elapsed_ms(start)
    dagster_version = _as_str(server_info.get("dagster_version"))
    dagster_webserver_version = _as_str(server_info.get("dagster_webserver_version"))
    dagster_graphql_version = _as_str(server_info.get("dagster_graphql_version"))

    try:
        graph_response = await client.post(
            f"{base_url}/graphql",
            json={
                "query": _PINVI_DAGSTER_LIVE_QUERY,
                "variables": {"runLimit": PINVI_DAGSTER_RECENT_RUN_LIMIT},
            },
        )
    except httpx.HTTPError:
        return _PinviDagsterProbeResult(
            status="degraded",
            message="Dagster live query 연결 실패",
            latency_ms=latency_ms,
            checked_at=checked_at,
            dagster_version=dagster_version,
            dagster_webserver_version=dagster_webserver_version,
            dagster_graphql_version=dagster_graphql_version,
        )
    if not 200 <= graph_response.status_code < 400:
        return _PinviDagsterProbeResult(
            status="degraded",
            message=f"Dagster live query HTTP {graph_response.status_code}",
            latency_ms=latency_ms,
            checked_at=checked_at,
            dagster_version=dagster_version,
            dagster_webserver_version=dagster_webserver_version,
            dagster_graphql_version=dagster_graphql_version,
        )

    payload = _json_object(graph_response)
    if payload.get("errors"):
        return _PinviDagsterProbeResult(
            status="degraded",
            message="Dagster live query 오류",
            latency_ms=latency_ms,
            checked_at=checked_at,
            dagster_version=dagster_version,
            dagster_webserver_version=dagster_webserver_version,
            dagster_graphql_version=dagster_graphql_version,
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        return _PinviDagsterProbeResult(
            status="degraded",
            message="Dagster live query 응답 형식 오류",
            latency_ms=latency_ms,
            checked_at=checked_at,
            dagster_version=dagster_version,
            dagster_webserver_version=dagster_webserver_version,
            dagster_graphql_version=dagster_graphql_version,
        )

    repositories_payload = data.get("repositoriesOrError")
    repositories = _pinvi_repositories_from_graphql(repositories_payload)
    if repositories_payload and not repositories:
        return _PinviDagsterProbeResult(
            status="degraded",
            message=_graphql_error_message(repositories_payload, "Dagster repository 조회 실패"),
            latency_ms=latency_ms,
            checked_at=checked_at,
            dagster_version=dagster_version,
            dagster_webserver_version=dagster_webserver_version,
            dagster_graphql_version=dagster_graphql_version,
        )

    runs_payload = data.get("runsOrError")
    recent_runs = _pinvi_runs_from_graphql(runs_payload)
    if (
        runs_payload
        and not recent_runs
        and not (
            isinstance(runs_payload, dict) and _as_str(runs_payload.get("__typename")) == "Runs"
        )
    ):
        return _PinviDagsterProbeResult(
            status="degraded",
            message=_graphql_error_message(runs_payload, "Dagster run 조회 실패"),
            latency_ms=latency_ms,
            checked_at=checked_at,
            dagster_version=dagster_version,
            dagster_webserver_version=dagster_webserver_version,
            dagster_graphql_version=dagster_graphql_version,
            repositories=repositories,
        )

    return _PinviDagsterProbeResult(
        status="ok",
        message="Dagster server_info/live snapshot 정상",
        latency_ms=latency_ms,
        checked_at=checked_at,
        dagster_version=_as_str(data.get("version")) or dagster_version,
        dagster_webserver_version=dagster_webserver_version,
        dagster_graphql_version=dagster_graphql_version,
        repositories=repositories,
        recent_runs=recent_runs,
    )


def _pinvi_repositories_from_graphql(value: Any) -> list[AdminDagsterRepositorySummary]:
    if not isinstance(value, dict) or _as_str(value.get("__typename")) != "RepositoryConnection":
        return []
    nodes = value.get("nodes")
    if not isinstance(nodes, list):
        return []
    repositories: list[AdminDagsterRepositorySummary] = []
    for item in nodes:
        if not isinstance(item, dict):
            continue
        asset_nodes = item.get("assetNodes")
        asset_nodes_list = asset_nodes if isinstance(asset_nodes, list) else []
        asset_groups: set[str] = set()
        for asset in asset_nodes_list:
            if not isinstance(asset, dict):
                continue
            group = _as_str(asset.get("groupName"))
            if group:
                asset_groups.add(group)
        location = item.get("location")
        repositories.append(
            AdminDagsterRepositorySummary(
                name=_as_str(item.get("name")) or "unknown",
                location_name=_as_str(location.get("name")) if isinstance(location, dict) else None,
                jobs=[
                    AdminDagsterJobSummary(
                        name=_as_str(job.get("name")) or "unknown",
                        is_job=bool(job.get("isJob", True)),
                    )
                    for job in item.get("jobs", [])
                    if isinstance(job, dict)
                ],
                schedules=[
                    AdminDagsterScheduleSummary(
                        name=_as_str(schedule.get("name")) or "unknown",
                        job_name=_as_str(schedule.get("pipelineName")),
                        cron_schedule=_as_str(schedule.get("cronSchedule")),
                        execution_timezone=_as_str(schedule.get("executionTimezone")),
                        status=_as_str(
                            schedule.get("scheduleState", {}).get("status")
                            if isinstance(schedule.get("scheduleState"), dict)
                            else None
                        ),
                    )
                    for schedule in item.get("schedules", [])
                    if isinstance(schedule, dict)
                ],
                sensors=[
                    AdminDagsterSensorSummary(
                        name=_as_str(sensor.get("name")) or "unknown",
                        status=_as_str(
                            sensor.get("sensorState", {}).get("status")
                            if isinstance(sensor.get("sensorState"), dict)
                            else None
                        ),
                    )
                    for sensor in item.get("sensors", [])
                    if isinstance(sensor, dict)
                ],
                asset_count=len(asset_nodes_list),
                asset_groups=sorted(asset_groups),
            )
        )
    return repositories


def _pinvi_runs_from_graphql(value: Any) -> list[AdminDagsterRunSummary]:
    if not isinstance(value, dict) or _as_str(value.get("__typename")) != "Runs":
        return []
    results = value.get("results")
    if not isinstance(results, list):
        return []
    return [
        AdminDagsterRunSummary(
            run_id=_as_str(item.get("runId")) or "unknown",
            status=_as_str(item.get("status")) or "UNKNOWN",
            job_name=_as_str(item.get("jobName")),
            start_time=_optional_float(item.get("startTime")),
            end_time=_optional_float(item.get("endTime")),
            update_time=_optional_float(item.get("updateTime")),
            tags={},
        )
        for item in results
        if isinstance(item, dict) and _as_str(item.get("runId")) and _as_str(item.get("status"))
    ]


def _graphql_error_message(value: Any, fallback: str) -> str:
    if not isinstance(value, dict):
        return fallback
    typename = _as_str(value.get("__typename"))
    message = _as_str(value.get("message"))
    if typename and message:
        return f"{fallback}: {typename}"
    return fallback


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


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
                        job_name=_as_str(schedule.get("job_name")),
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
    suppressed = _as_int(row.get("suppressed"))
    delivery_delayed = _as_int(row.get("delivery_delayed"))
    failure_count = failed + bounced + complained + suppressed
    total = _as_int(row.get("total"))
    return AdminEmailOutboxTemplateSummary(
        template=template or "unknown",
        total=total,
        pending=_as_int(row.get("pending")),
        sent=_as_int(row.get("sent")),
        delivered=_as_int(row.get("delivered")),
        delivery_delayed=delivery_delayed,
        failed=failed,
        bounced=bounced,
        complained=complained,
        suppressed=suppressed,
        failure_count=failure_count,
        failure_rate=0.0 if total == 0 else round(failure_count / total, 4),
    )


def _telegram_category_summary(item: Any) -> AdminTelegramOutboxCategorySummary:
    row = item if isinstance(item, Mapping) else {}
    category = _as_str(row.get("category"))
    retry_exhausted = _as_int(row.get("retry_exhausted"))
    total = _as_int(row.get("total"))
    return AdminTelegramOutboxCategorySummary(
        category=category or "unknown",
        total=total,
        pending=_as_int(row.get("pending")),
        sent=_as_int(row.get("sent")),
        skipped=_as_int(row.get("skipped")),
        failed=_as_int(row.get("failed")),
        retry_exhausted=retry_exhausted,
        retry_exhausted_rate=0.0 if total == 0 else round(retry_exhausted / total, 4),
    )


async def build_pii_retention_summary(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> AdminPiiRetentionSummary:
    current = now or datetime.now(UTC)
    user_pii_cutoff = current - timedelta(days=PII_RETENTION_USER_GRACE_DAYS)
    session_cutoff = current - timedelta(days=PII_RETENTION_SESSION_GRACE_DAYS)
    params = {
        "now": current,
        "user_pii_cutoff": user_pii_cutoff,
        "session_cutoff": session_cutoff,
    }
    summary = (await db.execute(_PII_RETENTION_SUMMARY_SQL, params)).mappings().one()
    counts = {
        "deleted_user_pii_candidates": _as_int(summary["deleted_user_pii_candidates"]),
        "deleted_user_oauth_identity_candidates": _as_int(
            summary["deleted_user_oauth_identity_candidates"]
        ),
        "expired_signup_verifications": _as_int(summary["expired_signup_verifications"]),
        "expired_password_reset_tokens": _as_int(summary["expired_password_reset_tokens"]),
        "old_revoked_sessions": _as_int(summary["old_revoked_sessions"]),
        "old_expired_sessions": _as_int(summary["old_expired_sessions"]),
        "expired_oauth_login_states": _as_int(summary["expired_oauth_login_states"]),
        "expired_mobile_oauth_exchanges": _as_int(summary["expired_mobile_oauth_exchanges"]),
    }
    return AdminPiiRetentionSummary(
        dry_run=True,
        generated_at=current,
        user_pii_cutoff=user_pii_cutoff,
        session_cutoff=session_cutoff,
        user_pii_grace_days=PII_RETENTION_USER_GRACE_DAYS,
        session_grace_days=PII_RETENTION_SESSION_GRACE_DAYS,
        total_candidates=sum(counts.values()),
        excluded_privileged_deleted_users=_as_int(summary["excluded_privileged_deleted_users"]),
        **counts,
    )


async def build_audit_retention_summary(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> AdminAuditRetentionSummary:
    current = now or datetime.now(UTC)
    audit_cutoff = current - timedelta(days=AUDIT_RETENTION_DAYS)
    summary = (
        (await db.execute(_AUDIT_RETENTION_SUMMARY_SQL, {"audit_cutoff": audit_cutoff}))
        .mappings()
        .one()
    )
    return AdminAuditRetentionSummary(
        dry_run=True,
        generated_at=current,
        audit_cutoff=audit_cutoff,
        audit_retention_days=AUDIT_RETENTION_DAYS,
        admin_audit_pii_over_retention=_as_int(summary["admin_audit_pii_over_retention"]),
    )


async def build_location_log_archive_summary(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> AdminLocationLogArchiveSummary:
    current = now or datetime.now(UTC)
    archive_cutoff = _subtract_months(current, LOCATION_LOG_ARCHIVE_RETENTION_MONTHS)
    params = {
        "archive_cutoff": archive_cutoff,
        "purpose_limit": LOCATION_LOG_ARCHIVE_PURPOSE_STATS_LIMIT,
    }
    summary = (await db.execute(_LOCATION_LOG_ARCHIVE_SUMMARY_SQL, params)).mappings().one()
    purpose_rows = list((await db.execute(_LOCATION_LOG_ARCHIVE_PURPOSE_SQL, params)).mappings())
    archive_tail_log_id = _optional_int(summary["archive_tail_log_id"])
    active_head_log_id = _optional_int(summary["active_head_log_id"])
    archive_tail_content_hash = _as_str(summary["archive_tail_content_hash"])
    active_head_prev_hash = _as_str(summary["active_head_prev_hash"])
    chain_bridge_required = archive_tail_log_id is not None and active_head_log_id is not None
    bridge_anchor_matches = (
        None if not chain_bridge_required else active_head_prev_hash == archive_tail_content_hash
    )
    pending_outbox_before_cutoff = _as_int(summary["pending_outbox_before_cutoff"])
    return AdminLocationLogArchiveSummary(
        dry_run=True,
        generated_at=current,
        archive_cutoff=archive_cutoff,
        location_retention_months=LOCATION_LOG_ARCHIVE_RETENTION_MONTHS,
        total_candidates=_as_int(summary["total_candidates"]),
        oldest_candidate_at=summary["oldest_candidate_at"],
        newest_candidate_at=summary["newest_candidate_at"],
        archive_tail_log_id=archive_tail_log_id,
        active_head_log_id=active_head_log_id,
        active_rows_after_cutoff=_as_int(summary["active_rows_after_cutoff"]),
        chain_bridge_required=chain_bridge_required,
        bridge_anchor_matches=bridge_anchor_matches,
        pending_outbox_total=_as_int(summary["pending_outbox_total"]),
        pending_outbox_before_cutoff=pending_outbox_before_cutoff,
        archive_blocked_by_pending_outbox=pending_outbox_before_cutoff > 0,
        oldest_pending_outbox_at=summary["oldest_pending_outbox_at"],
        purpose_stats=[_location_archive_purpose_summary(row) for row in purpose_rows],
    )


def _location_archive_purpose_summary(
    item: Any,
) -> AdminLocationLogArchivePurposeSummary:
    row = item if isinstance(item, Mapping) else {}
    purpose = _as_str(row.get("purpose"))
    return AdminLocationLogArchivePurposeSummary(
        purpose=purpose or "unknown",
        total=_as_int(row.get("total")),
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


def _subtract_months(value: datetime, months: int) -> datetime:
    month_index = value.month - months - 1
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


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
      count(*) FILTER (WHERE status = 'suppressed')::int AS suppressed,
      count(*) FILTER (WHERE status = 'delivery_delayed')::int AS delivery_delayed,
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
      count(*) FILTER (WHERE status = 'delivery_delayed')::int AS delivery_delayed,
      count(*) FILTER (WHERE status = 'failed')::int AS failed,
      count(*) FILTER (WHERE status = 'bounced')::int AS bounced,
      count(*) FILTER (WHERE status = 'complained')::int AS complained,
      count(*) FILTER (WHERE status = 'suppressed')::int AS suppressed
    FROM app.email_queue
    WHERE created_at >= :template_window_start
    GROUP BY template
    ORDER BY total DESC, template ASC
    LIMIT :template_limit
    """
)

_TELEGRAM_OUTBOX_SUMMARY_SQL = text(
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
      count(*) FILTER (WHERE status = 'sent')::int AS sent,
      count(*) FILTER (WHERE status = 'skipped')::int AS skipped,
      count(*) FILTER (WHERE status = 'failed')::int AS failed,
      count(*) FILTER (
        WHERE status = 'failed' OR (status = 'pending' AND attempts >= :max_attempts)
      )::int AS retry_exhausted,
      min(scheduled_at) FILTER (WHERE status = 'pending') AS oldest_pending_scheduled_at
    FROM app.telegram_system_notification_outbox
    """
)

_TELEGRAM_OUTBOX_CATEGORY_SQL = text(
    """
    SELECT
      category,
      count(*)::int AS total,
      count(*) FILTER (WHERE status = 'pending')::int AS pending,
      count(*) FILTER (WHERE status = 'sent')::int AS sent,
      count(*) FILTER (WHERE status = 'skipped')::int AS skipped,
      count(*) FILTER (WHERE status = 'failed')::int AS failed,
      count(*) FILTER (
        WHERE status = 'failed' OR (status = 'pending' AND attempts >= :max_attempts)
      )::int AS retry_exhausted
    FROM app.telegram_system_notification_outbox
    WHERE created_at >= :category_window_start
    GROUP BY category
    ORDER BY total DESC, category ASC
    LIMIT :category_limit
    """
)

_PII_RETENTION_SUMMARY_SQL = text(
    """
    WITH deleted_users AS (
      SELECT user_id, roles
      FROM app.users
      WHERE status IN ('pending_delete', 'deleted')
        AND deleted_at IS NOT NULL
        AND deleted_at <= :user_pii_cutoff
    ),
    eligible_deleted_users AS (
      SELECT user_id
      FROM deleted_users
      WHERE NOT (roles && ARRAY['admin', 'operator', 'cpo']::varchar[])
    )
    SELECT
      (SELECT count(*) FROM eligible_deleted_users)::int
        AS deleted_user_pii_candidates,
      (
        SELECT count(*)
        FROM app.user_oauth_identities identities
        JOIN eligible_deleted_users deleted USING (user_id)
      )::int AS deleted_user_oauth_identity_candidates,
      (
        SELECT count(*)
        FROM deleted_users
        WHERE roles && ARRAY['admin', 'operator', 'cpo']::varchar[]
      )::int AS excluded_privileged_deleted_users,
      (
        SELECT count(*)
        FROM app.user_email_verifications
        WHERE purpose = 'signup'
          AND expires_at <= :now
      )::int AS expired_signup_verifications,
      (
        SELECT count(*)
        FROM app.user_email_verifications
        WHERE purpose = 'password_reset'
          AND expires_at <= :now
      )::int AS expired_password_reset_tokens,
      (
        SELECT count(*)
        FROM app.user_sessions
        WHERE revoked_at IS NOT NULL
          AND revoked_at <= :session_cutoff
      )::int AS old_revoked_sessions,
      (
        SELECT count(*)
        FROM app.user_sessions
        WHERE revoked_at IS NULL
          AND expires_at <= :session_cutoff
      )::int AS old_expired_sessions,
      (
        SELECT count(*)
        FROM app.oauth_login_states
        WHERE expires_at <= :now
      )::int AS expired_oauth_login_states,
      (
        SELECT count(*)
        FROM app.oauth_mobile_exchanges
        WHERE expires_at <= :now
      )::int AS expired_mobile_oauth_exchanges
    """
)

_AUDIT_RETENTION_SUMMARY_SQL = text(
    """
    SELECT count(*)::int AS admin_audit_pii_over_retention
    FROM app.admin_audit_log
    WHERE occurred_at <= :audit_cutoff
      AND (target_pii_fields IS NOT NULL OR user_agent IS NOT NULL)
    """
)

_LOCATION_LOG_ARCHIVE_SUMMARY_SQL = text(
    """
    WITH candidates AS (
      SELECT log_id, occurred_at, content_hash
      FROM app.location_access_log
      WHERE occurred_at <= :archive_cutoff
    ),
    archive_tail AS (
      SELECT log_id, content_hash
      FROM candidates
      ORDER BY log_id DESC
      LIMIT 1
    ),
    active_head AS (
      SELECT log_id, prev_hash
      FROM app.location_access_log
      WHERE occurred_at > :archive_cutoff
      ORDER BY log_id ASC
      LIMIT 1
    ),
    pending_outbox AS (
      SELECT occurred_at
      FROM app.location_audit_outbox
      WHERE processed_at IS NULL
    )
    SELECT
      (SELECT count(*) FROM candidates)::int AS total_candidates,
      (SELECT min(occurred_at) FROM candidates) AS oldest_candidate_at,
      (SELECT max(occurred_at) FROM candidates) AS newest_candidate_at,
      (SELECT log_id FROM archive_tail) AS archive_tail_log_id,
      (SELECT content_hash FROM archive_tail) AS archive_tail_content_hash,
      (SELECT log_id FROM active_head) AS active_head_log_id,
      (SELECT prev_hash FROM active_head) AS active_head_prev_hash,
      (
        SELECT count(*)
        FROM app.location_access_log
        WHERE occurred_at > :archive_cutoff
      )::int AS active_rows_after_cutoff,
      (SELECT count(*) FROM pending_outbox)::int AS pending_outbox_total,
      (
        SELECT count(*)
        FROM pending_outbox
        WHERE occurred_at <= :archive_cutoff
      )::int AS pending_outbox_before_cutoff,
      (SELECT min(occurred_at) FROM pending_outbox) AS oldest_pending_outbox_at
    """
)

_LOCATION_LOG_ARCHIVE_PURPOSE_SQL = text(
    """
    SELECT purpose, count(*)::int AS total
    FROM app.location_access_log
    WHERE occurred_at <= :archive_cutoff
    GROUP BY purpose
    ORDER BY total DESC, purpose ASC
    LIMIT :purpose_limit
    """
)
