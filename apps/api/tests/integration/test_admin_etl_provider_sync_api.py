"""Admin ETL/provider sync API 통합 테스트 (T-220)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.api.v1.admin import etl as etl_router
from app.clients.kor_travel_map import (
    KorTravelMapConflict,
    KorTravelMapFeatureNotFound,
    KorTravelMapUnavailable,
)
from app.clients.kor_travel_map_admin import (
    KorTravelMapAdminClient,
    get_kor_travel_map_admin_client,
)
from app.main import app
from app.models.audit import AdminAuditLog, LocationAuditOutbox
from app.models.email_queue import EmailQueue
from app.models.oauth_identity import OAuthLoginState, OAuthMobileExchange, UserOAuthIdentity
from app.models.session import UserSession
from app.models.telegram_outbox import TelegramNotificationOutbox
from app.models.user import User
from app.models.user_email_verification import UserEmailVerification
from app.schemas.admin import (
    AdminDagsterJobSummary,
    AdminDagsterRepositorySummary,
    AdminDagsterRunSummary,
    AdminDagsterScheduleSummary,
)
from app.services import admin_etl as admin_etl_service
from app.services.location_audit import append_location_log

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    email: str,
    roles: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash="x",
            status="active",
            roles=roles or ["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _request_audits(session_factory: Any, request_id: uuid.UUID) -> list[AdminAuditLog]:
    async with session_factory() as db:
        rows = await db.scalars(
            select(AdminAuditLog)
            .where(AdminAuditLog.request_id == request_id)
            .order_by(AdminAuditLog.log_id)
        )
        return list(rows)


async def _seed_email_queue(session_factory: Any) -> None:
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add_all(
            [
                EmailQueue(
                    to_email="due@example.com",
                    template="verify_email",
                    subject="Verify",
                    payload={},
                    status="pending",
                    attempts=0,
                    scheduled_at=now - timedelta(minutes=20),
                ),
                EmailQueue(
                    to_email="backoff@example.com",
                    template="verify_email",
                    subject="Verify retry",
                    payload={},
                    status="pending",
                    attempts=1,
                    scheduled_at=now + timedelta(minutes=5),
                ),
                EmailQueue(
                    to_email="failed@example.com",
                    template="verify_email",
                    subject="Verify failed",
                    payload={},
                    status="failed",
                    attempts=5,
                    last_error="provider down",
                    scheduled_at=now - timedelta(hours=1),
                ),
                EmailQueue(
                    to_email="invite@example.com",
                    template="trip_invite",
                    subject="Invite",
                    payload={},
                    status="bounced",
                    attempts=1,
                    bounce_type="hard",
                    scheduled_at=now - timedelta(hours=1),
                ),
            ]
        )
        await db.commit()


async def _seed_telegram_outbox(session_factory: Any) -> None:
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add_all(
            [
                TelegramNotificationOutbox(
                    category="trip_created",
                    payload={"user_id": str(uuid.uuid4()), "text": "due"},
                    status="pending",
                    attempts=0,
                    scheduled_at=now - timedelta(minutes=20),
                ),
                TelegramNotificationOutbox(
                    category="trip_created",
                    payload={"user_id": str(uuid.uuid4()), "text": "backoff"},
                    status="pending",
                    attempts=1,
                    scheduled_at=now + timedelta(minutes=5),
                ),
                TelegramNotificationOutbox(
                    category="trip_created",
                    payload={"user_id": str(uuid.uuid4()), "text": "failed"},
                    status="failed",
                    attempts=5,
                    last_error="provider down",
                    scheduled_at=now - timedelta(hours=1),
                ),
                TelegramNotificationOutbox(
                    category="trip_created",
                    payload={"user_id": str(uuid.uuid4()), "text": "skipped"},
                    status="skipped",
                    attempts=1,
                    scheduled_at=now - timedelta(hours=1),
                ),
                TelegramNotificationOutbox(
                    category="companion_invited",
                    payload={"user_id": str(uuid.uuid4()), "text": "sent"},
                    status="sent",
                    attempts=1,
                    sent_at=now - timedelta(minutes=5),
                    scheduled_at=now - timedelta(minutes=10),
                ),
            ]
        )
        await db.commit()


async def _seed_pii_retention_candidates(session_factory: Any) -> None:
    now = datetime.now(UTC)
    async with session_factory() as db:
        deleted_user = User(
            email="deleted-retention@example.com",
            password_hash="x",
            nickname="삭제대상",
            status="deleted",
            roles=["user"],
            is_active=False,
            deleted_at=now - timedelta(days=31),
        )
        privileged_deleted_user = User(
            email="privileged-deleted-retention@example.com",
            password_hash="x",
            status="deleted",
            roles=["user", "admin"],
            is_active=False,
            deleted_at=now - timedelta(days=31),
        )
        active_user = User(
            email="retention-active@example.com",
            password_hash="x",
            status="active",
            roles=["user"],
            email_verified_at=now,
        )
        db.add_all([deleted_user, privileged_deleted_user, active_user])
        await db.flush()
        await append_location_log(
            db,
            user_id=active_user.user_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("37.123456"),
            lng=Decimal("127.123456"),
            request_id=uuid.uuid4(),
            ip_hash="a" * 64,
            occurred_at=now - timedelta(days=200),
            commit=False,
        )
        await append_location_log(
            db,
            user_id=active_user.user_id,
            endpoint="/features/in-bounds",
            purpose="viewport_query",
            lat=None,
            lng=None,
            request_id=uuid.uuid4(),
            ip_hash="b" * 64,
            occurred_at=now - timedelta(days=1),
            commit=False,
        )
        db.add_all(
            [
                UserOAuthIdentity(
                    user_id=deleted_user.user_id,
                    provider="google",
                    provider_user_id="deleted-provider-subject",
                    provider_email="deleted-provider@example.com",
                    provider_email_verified=True,
                    display_name_snapshot="deleted",
                    linked_at=now - timedelta(days=45),
                ),
                UserEmailVerification(
                    user_id=active_user.user_id,
                    token_hash="expired-signup-token",
                    purpose="signup",
                    expires_at=now - timedelta(hours=2),
                ),
                UserEmailVerification(
                    user_id=active_user.user_id,
                    token_hash="expired-reset-token",
                    purpose="password_reset",
                    expires_at=now - timedelta(hours=2),
                ),
                UserSession(
                    user_id=active_user.user_id,
                    session_token_hash="old-revoked-session-token",
                    expires_at=now - timedelta(days=40),
                    revoked_at=now - timedelta(days=31),
                    user_agent="old revoked",
                    ip_address="127.0.0.1",
                ),
                UserSession(
                    user_id=active_user.user_id,
                    session_token_hash="old-expired-session-token",
                    expires_at=now - timedelta(days=31),
                    user_agent="old expired",
                    ip_address="127.0.0.1",
                ),
                OAuthLoginState(
                    state_hash="expired-oauth-state",
                    nonce_hash="nonce",
                    pkce_code_verifier_hash="pkce",
                    provider="google",
                    mode="login",
                    expires_at=now - timedelta(minutes=10),
                    created_at=now - timedelta(hours=1),
                ),
                OAuthMobileExchange(
                    code_hash="expired-mobile-oauth-exchange",
                    user_id=active_user.user_id,
                    expires_at=now - timedelta(minutes=10),
                    created_at=now - timedelta(hours=1),
                ),
                LocationAuditOutbox(
                    user_id=active_user.user_id,
                    occurred_at=now - timedelta(days=1),
                    endpoint="/features/in-bounds",
                    purpose="viewport_query",
                    lat=None,
                    lng=None,
                    request_id=uuid.uuid4(),
                    ip_hash="g" * 64,
                    processed_at=None,
                ),
                AdminAuditLog(
                    actor_user_id=active_user.user_id,
                    action="reveal_email",
                    resource_type="user",
                    resource_id=str(deleted_user.user_id),
                    before_state=None,
                    after_state=None,
                    access_reason="retention test",
                    target_pii_fields=["email"],
                    ip_hash="d" * 64,
                    user_agent="retention-test",
                    request_id=uuid.uuid4(),
                    prev_hash="e" * 64,
                    content_hash="f" * 64,
                    occurred_at=now - timedelta(days=200),
                ),
            ]
        )
        await db.commit()


def _provider_item() -> dict[str, Any]:
    return {
        "provider": "kma",
        "dataset_key": "special_days",
        "sync_scope": "dataset_wide",
        "status": "healthy",
        "last_success_at": "2026-06-12T00:00:00+09:00",
        "last_failure_at": None,
        "consecutive_failures": 0,
        "eligible_after": "2026-06-13T03:30:00+09:00",
        "detail_url": (
            "/v1/ops/datasets/detail?provider=kma&dataset_key=special_days&sync_scope=dataset_wide"
        ),
        "freshness": {
            "state": "fresh",
            "basis": "policy_stale_after",
            "sla_seconds": 86400,
            "due_at": "2026-06-13T00:00:00+09:00",
            "is_overdue": False,
            "overdue_by_seconds": 0,
        },
        "schedule": {
            "source": "dagster_graphql",
            "basis": "dagster_definition_tags",
            "status": "RUNNING",
            "schedule_names": ["kma_special_days_schedule"],
            "active_schedule_names": ["kma_special_days_schedule"],
            "next_scheduled_at": "2026-06-14T03:30:00+09:00",
        },
        "latest_execution": None,
        "active_execution": None,
        "catalog_state": "canonical",
        "orphan_reason": None,
        "mutable": True,
        "catalog": {
            "feature_kind": "weather",
            "provider_state_default_scope": "daily",
            "label": "특일",
            "is_feature_load": True,
            "is_refreshable": True,
            "scope_refresh": {
                "supported": False,
                "selector": "none",
                "effect": "dataset_wide",
                "default_sync_scope": "dataset_wide",
                "allowed_sync_scopes": [],
                "reason": "이 dataset은 전체 dataset 단위로만 갱신합니다.",
            },
            "preview": {
                "supported": True,
                "sources": ["fixture"],
                "input_kind": "none",
                "default_max_items": 20,
                "max_items_limit": 100,
                "timeout_seconds": 5.0,
                "external_call_budget": 0,
            },
        },
        "refresh_policy": None,
        "dataset_issues": {"open_count": 0, "severity_counts": {}},
        "provider_issues": {"open_count": 0, "severity_counts": {}},
    }


def _import_job() -> dict[str, Any]:
    return {
        "id": "11111111-1111-4111-8111-111111111111",
        "kind": "import_job",
        "status": "running",
        "progress": 1,
        "current_stage": "normalize",
        "error_message": None,
        "created_at": "2026-06-12T00:00:00+09:00",
        "started_at": "2026-06-12T00:01:00+09:00",
        "finished_at": None,
        "scope_type": None,
        "priority": None,
        "run_mode": None,
        "operator": None,
        "dagster_run_id": "run-1",
        "dagster_run_status": "STARTED",
        "trigger_kind": "manual",
        "operation_registry_version": "1",
        "requested_job_id": None,
        "linked_job_count": 2,
        "providers": ["kma"],
        "dataset_keys": ["special_days"],
        "provider_datasets": [
            {
                "provider": "kma",
                "dataset_key": "special_days",
                "sync_scope": None,
                "operation_member_id": "22222222-2222-4222-8222-222222222222",
                "status": "running",
            }
        ],
        "detail_url": (
            "/v1/ops/pipeline/executions/import_job/11111111-1111-4111-8111-111111111111"
        ),
        "projected_job": {
            "id": "22222222-2222-4222-8222-222222222222",
            "job_kind": "provider_import",
            "status": "running",
            "progress": 1,
            "current_stage": "normalize",
            "error_message": None,
            "created_at": "2026-06-12T00:00:00+09:00",
            "started_at": "2026-06-12T00:01:00+09:00",
            "finished_at": None,
            "dagster_run_id": "run-1",
            "dagster_run_status": "STARTED",
            "trigger_kind": "manual",
            "operation_registry_version": "1",
            "load_batch_id": None,
            "parent_job_id": None,
            "depth": 1,
            "detail_url": (
                "/v1/ops/pipeline/executions/import_job/22222222-2222-4222-8222-222222222222"
            ),
        },
        "cancellation": None,
    }


class _FakeOpsClient:
    def __init__(self, *, fail: bool = False, cancel_conflict: bool = False) -> None:
        self.fail = fail
        self.cancel_conflict = cancel_conflict
        self.dataset_calls = 0
        self.schedule_source_status = "ok"
        self.schedule_source_errors: list[str] = []
        self.import_kwargs: dict[str, Any] | None = None
        self.cancel_args: tuple[str, dict[str, Any]] | None = None

    async def get_ops_pipeline_overview(self, *, run_limit: int = 10) -> dict[str, Any]:
        if self.fail:
            raise KorTravelMapUnavailable("ops down")
        assert run_limit == 10
        return {
            "checked_at": "2026-06-12T00:00:00+09:00",
            "dagster": {
                "status": "ok",
                "dagster_url": "http://dagster.internal",
                "graphql_url": "http://dagster.internal/graphql",
                "version": "1.11.0",
                "schedule_count": 2,
                "sensor_count": 1,
                "run_counts": {"STARTED": 1, "SUCCESS": 9},
                "recent_runs": [
                    {
                        "run_id": "run-1",
                        "job_name": "kma_special_days_job",
                        "status": "STARTED",
                        "tags": {},
                        "start_time": 1781190000.0,
                        "end_time": None,
                        "update_time": 1781190010.0,
                    }
                ],
                "sensors": [{"name": "provider_refresh", "status": "RUNNING", "recent_ticks": []}],
                "errors": [],
            },
            "operations_by_status": {
                "queued": 0,
                "running": 1,
                "done": 9,
                "failed": 0,
                "cancelled": 0,
            },
            "active_operations": 1,
            "failed_operations_24h": 0,
        }

    async def list_ops_datasets(self) -> dict[str, Any]:
        if self.fail:
            raise KorTravelMapUnavailable("datasets down")
        self.dataset_calls += 1
        return {
            "items": [_provider_item()],
            "schedule_source_status": self.schedule_source_status,
            "schedule_source_errors": self.schedule_source_errors,
            "execution_coverage": "db_recorded_canonical_operations",
        }

    async def list_ops_pipeline_executions(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail:
            raise KorTravelMapUnavailable("jobs down")
        self.import_kwargs = kwargs
        canonical_url = "/v1/ops/pipeline/executions?kind=import_job"
        for name in ("status_filter", "load_batch_id", "parent_job_id"):
            value = kwargs.get(name)
            if value is not None:
                query_name = "status" if name == "status_filter" else name
                canonical_url += f"&{query_name}={value}"
        return {
            "data": {
                "items": [_import_job()],
                "canonical_url": canonical_url,
            },
            "meta": {
                "page": {
                    "page_size": kwargs.get("page_size", 50),
                    "next_cursor": "cursor-2",
                }
            },
        }

    async def get_ops_pipeline_execution(self, job_id: str) -> dict[str, Any]:
        item = _import_job()
        assert item["id"] == job_id
        item["projected_job"] = {
            **item["projected_job"],
            "id": job_id,
            "depth": 0,
            "detail_url": f"/v1/ops/pipeline/executions/import_job/{job_id}",
        }
        item["linked_job_count"] = 1
        item["provider_datasets"][0]["operation_member_id"] = job_id  # type: ignore[index]
        return {
            "execution": {
                "kind": "import_job",
                "id": job_id,
                "status": item["status"],
                "created_at": item["created_at"],
                "job_kind": "provider_import",
                "provider": "kma",
                "dataset_key": "special_days",
                "progress": item["progress"],
                "current_stage": item["current_stage"],
                "scope_type": item["scope_type"],
                "priority": item["priority"],
                "run_mode": item["run_mode"],
                "operator": item["operator"],
                "error_message": item["error_message"],
                "started_at": item["started_at"],
                "finished_at": item["finished_at"],
                "dagster_run_id": item["dagster_run_id"],
                "dagster_run_status": item["dagster_run_status"],
                "trigger_kind": item["trigger_kind"],
                "operation_registry_version": item["operation_registry_version"],
                "job_id": None,
                "request_id": None,
                "load_batch_id": None,
                "parent_job_id": None,
                "detail_url": item["detail_url"],
            },
            "root": item,
            "import_job": {
                "job_id": job_id,
                "kind": "provider_import",
                "load_batch_id": None,
                "parent_job_id": None,
                "payload": {"sync_scope": "dataset_wide"},
                "status": item["status"],
                "progress": item["progress"],
                "current_stage": item["current_stage"],
                "source_checksum": None,
                "error_message": item["error_message"],
                "dagster_run_id": item["dagster_run_id"],
                "provider": "kma",
                "dataset_key": "special_days",
                "trigger_kind": item["trigger_kind"],
                "operation_registry_version": item["operation_registry_version"],
                "dagster_run_status": item["dagster_run_status"],
                "created_at": item["created_at"],
                "started_at": item["started_at"],
                "finished_at": item["finished_at"],
                "heartbeat_at": "2026-06-12T00:02:00+09:00",
            },
            "update_request": None,
            "cancellation": None,
            "events": [],
            "events_next_cursor": None,
        }

    async def cancel_ops_pipeline_execution(
        self,
        job_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.cancel_conflict:
            raise KorTravelMapConflict(
                "unsafe cancellation",
                code="PIPELINE_CANCELLATION_UNSAFE",
            )
        self.cancel_args = (job_id, {"reason": reason})
        return {
            "cancellation_id": "22222222-2222-4222-8222-222222222222",
            "previous_cancellation_id": None,
            "root": {"kind": "import_job", "id": job_id},
            "status": "completed",
            "requested_at": "2026-06-12T00:03:00+09:00",
            "requested_by": "service:pinvi",
            "reason": reason,
            "error": None,
            "updated_at": "2026-06-12T00:04:00+09:00",
            "finished_at": "2026-06-12T00:04:00+09:00",
            "retryable": False,
            "unresolved_member_count": 0,
            "members": [
                {
                    "job_id": job_id,
                    "dagster_run_id": "run-1",
                    "operation_kind": "provider_import",
                    "requires_run_termination": True,
                    "initial_status": "running",
                    "result": "cancelled",
                    "terminal_status": "cancelled",
                    "error": None,
                    "updated_at": "2026-06-12T00:04:00+09:00",
                }
            ],
            "dagster_runs": [
                {
                    "dagster_run_id": "run-1",
                    "initial_status": "STARTED",
                    "termination_reserved_at": "2026-06-12T00:03:30+09:00",
                    "result": "cancelled",
                    "terminal_status": "CANCELED",
                    "error": None,
                    "engine_started_at": "2026-06-12T00:03:30+09:00",
                    "engine_finished_at": "2026-06-12T00:04:00+09:00",
                    "updated_at": "2026-06-12T00:04:00+09:00",
                }
            ],
            "committed_data_rolled_back": False,
            "warnings": ["이미 commit된 데이터는 rollback하지 않습니다."],
        }


class _EmptyOpsClient(_FakeOpsClient):
    async def get_ops_pipeline_overview(self, *, run_limit: int = 10) -> dict[str, Any]:
        data = await super().get_ops_pipeline_overview(run_limit=run_limit)
        data["dagster"]["run_counts"] = {}
        data["dagster"]["recent_runs"] = []
        data["operations_by_status"] = {
            "queued": 0,
            "running": 0,
            "done": 0,
            "failed": 0,
            "cancelled": 0,
        }
        data["active_operations"] = 0
        return data

    async def list_ops_datasets(self) -> dict[str, Any]:
        return {
            "items": [],
            "schedule_source_status": "ok",
            "schedule_source_errors": [],
            "execution_coverage": "db_recorded_canonical_operations",
        }

    async def list_ops_pipeline_executions(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "data": {
                "items": [],
                "canonical_url": "/v1/ops/pipeline/executions?kind=import_job",
            },
            "meta": {
                "page": {
                    "page_size": kwargs.get("page_size", 50),
                    "next_cursor": None,
                }
            },
        }


class _AuditOrderingOpsClient(_FakeOpsClient):
    def __init__(self, session_factory: Any, request_id: uuid.UUID) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.request_id = request_id
        self.started_seen_before_dispatch = False

    async def cancel_ops_pipeline_execution(
        self,
        job_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:
            started = await db.scalar(
                select(AdminAuditLog).where(
                    AdminAuditLog.request_id == self.request_id,
                    AdminAuditLog.action == "provider_import_job.cancel.started",
                )
            )
        self.started_seen_before_dispatch = started is not None
        return await super().cancel_ops_pipeline_execution(job_id, reason=reason)


class _DagsterDegradedOpsClient(_EmptyOpsClient):
    async def get_ops_pipeline_overview(self, *, run_limit: int = 10) -> dict[str, Any]:
        data = await super().get_ops_pipeline_overview(run_limit=run_limit)
        data["dagster"]["status"] = "unavailable"
        data["dagster"]["errors"] = ["Dagster GraphQL unavailable"]
        return data


class _MalformedExecutionPageClient(_FakeOpsClient):
    def __init__(self, *, wrong_url: bool = False, missing_page: bool = False) -> None:
        super().__init__()
        self.wrong_url = wrong_url
        self.missing_page = missing_page

    async def list_ops_pipeline_executions(self, **kwargs: Any) -> dict[str, Any]:
        payload = await super().list_ops_pipeline_executions(**kwargs)
        if self.wrong_url:
            payload["data"]["canonical_url"] = "/v1/ops/import-jobs"
        if self.missing_page:
            payload["meta"] = {}
        return payload


def _override(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)


async def test_admin_etl_summary_combines_pinvi_registry_and_upstream_ops(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe() -> admin_etl_service._PinviDagsterProbeResult:
        return admin_etl_service._PinviDagsterProbeResult(
            status="ok",
            message="Dagster server_info/live snapshot 정상",
            latency_ms=11,
            checked_at=datetime.now(UTC),
            dagster_version="1.13.11",
            dagster_webserver_version="1.13.11",
            dagster_graphql_version="1.13.11",
            repositories=[
                AdminDagsterRepositorySummary(
                    name="__repository__",
                    location_name="pinvi.etl.definitions",
                    jobs=[
                        AdminDagsterJobSummary(name="kasi_special_days_job"),
                        AdminDagsterJobSummary(name="pinvi_email_outbox_job"),
                    ],
                    schedules=[
                        AdminDagsterScheduleSummary(
                            name="pinvi_email_outbox_schedule",
                            job_name="pinvi_email_outbox_job",
                            cron_schedule="*/15 * * * *",
                            execution_timezone="Asia/Seoul",
                            status="RUNNING",
                        )
                    ],
                    sensors=[],
                    asset_count=5,
                    asset_groups=["pinvi_email", "pinvi_kasi"],
                )
            ],
            recent_runs=[
                AdminDagsterRunSummary(
                    run_id="pinvi-run-1",
                    status="SUCCESS",
                    job_name="pinvi_email_outbox_job",
                    start_time=1781190000.0,
                    end_time=1781190010.0,
                    update_time=1781190010.0,
                    tags={},
                )
            ],
        )

    monkeypatch.setattr(admin_etl_service, "_probe_pinvi_dagster", fake_probe)
    monkeypatch.setattr(
        etl_router, "build_admin_etl_summary", admin_etl_service.build_admin_etl_summary
    )
    admin_id = await _create_user(
        session_factory, email="admin-etl@example.com", roles=["user", "operator", "cpo"]
    )
    await _seed_email_queue(session_factory)
    await _seed_telegram_outbox(session_factory)
    await _seed_pii_retention_candidates(session_factory)
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get("/admin/etl/summary", cookies=auth_cookies(str(admin_id)))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert "localhost" not in resp.text
    data = resp.json()["data"]
    assert data["pinvi"]["status"] == "ok"
    assert data["pinvi"]["dagster_version"] == "1.13.11"
    assert data["pinvi"]["repository_count"] == 1
    assert data["pinvi"]["job_count"] == 2
    assert data["pinvi"]["asset_count"] == 5
    assert data["pinvi"]["schedule_count"] == 1
    assert data["pinvi"]["repositories"][0]["location_name"] == "pinvi.etl.definitions"
    assert data["pinvi"]["repositories"][0]["schedules"][0]["job_name"] == "pinvi_email_outbox_job"
    assert data["pinvi"]["repositories"][0]["schedules"][0]["execution_timezone"] == "Asia/Seoul"
    assert data["pinvi"]["recent_runs"][0]["job_name"] == "pinvi_email_outbox_job"
    assert data["pinvi"]["recent_runs"][0]["tags"] == {}
    assert {job["name"] for job in data["pinvi"]["jobs"]} == {
        "kasi_special_days_job",
        "kasi_poi_rise_set_job",
        "pinvi_email_outbox_job",
        "pinvi_telegram_system_outbox_job",
        "pinvi_pii_retention_job",
        "pinvi_location_log_archive_job",
    }
    assert data["pinvi"]["email_outbox"]["pending_due"] == 1
    assert data["pinvi"]["email_outbox"]["pending_backoff"] == 1
    assert data["pinvi"]["email_outbox"]["stuck_pending"] == 1
    assert data["pinvi"]["email_outbox"]["retry_exhausted"] == 1
    assert data["pinvi"]["telegram_outbox"]["pending_due"] == 1
    assert data["pinvi"]["telegram_outbox"]["pending_backoff"] == 1
    assert data["pinvi"]["telegram_outbox"]["stuck_pending"] == 1
    assert data["pinvi"]["telegram_outbox"]["sent"] == 1
    assert data["pinvi"]["telegram_outbox"]["skipped"] == 1
    assert data["pinvi"]["telegram_outbox"]["retry_exhausted"] == 1
    trip_created_stats = next(
        item
        for item in data["pinvi"]["telegram_outbox"]["category_stats"]
        if item["category"] == "trip_created"
    )
    assert trip_created_stats["total"] == 4
    assert trip_created_stats["retry_exhausted"] == 1
    assert trip_created_stats["retry_exhausted_rate"] == pytest.approx(0.25, abs=0.0001)
    assert data["pinvi"]["pii_retention"]["dry_run"] is True
    assert data["pinvi"]["pii_retention"]["deleted_user_pii_candidates"] == 1
    assert data["pinvi"]["pii_retention"]["deleted_user_oauth_identity_candidates"] == 1
    assert data["pinvi"]["pii_retention"]["excluded_privileged_deleted_users"] == 1
    assert data["pinvi"]["pii_retention"]["expired_signup_verifications"] == 1
    assert data["pinvi"]["pii_retention"]["expired_password_reset_tokens"] == 1
    assert data["pinvi"]["pii_retention"]["old_revoked_sessions"] == 1
    assert data["pinvi"]["pii_retention"]["old_expired_sessions"] == 1
    assert data["pinvi"]["pii_retention"]["expired_oauth_login_states"] == 1
    assert data["pinvi"]["pii_retention"]["expired_mobile_oauth_exchanges"] == 1
    assert data["pinvi"]["pii_retention"]["total_candidates"] == 8
    assert data["pinvi"]["audit_retention"]["policy"] == "append_only_cold_storage"
    assert data["pinvi"]["audit_retention"]["audit_retention_days"] == 90
    assert data["pinvi"]["audit_retention"]["admin_audit_pii_over_retention"] == 1
    assert data["pinvi"]["location_log_archive"]["dry_run"] is True
    assert data["pinvi"]["location_log_archive"]["total_candidates"] == 1
    assert data["pinvi"]["location_log_archive"]["active_rows_after_cutoff"] == 1
    assert data["pinvi"]["location_log_archive"]["chain_bridge_required"] is True
    assert data["pinvi"]["location_log_archive"]["bridge_anchor_matches"] is True
    assert data["pinvi"]["location_log_archive"]["pending_outbox_total"] == 1
    assert data["pinvi"]["location_log_archive"]["pending_outbox_before_cutoff"] == 0
    assert data["pinvi"]["location_log_archive"]["archive_blocked_by_pending_outbox"] is False
    assert data["pinvi"]["location_log_archive"]["purpose_stats"] == [
        {"purpose": "nearby_attractions", "total": 1}
    ]
    verify_stats = next(
        item
        for item in data["pinvi"]["email_outbox"]["template_stats"]
        if item["template"] == "verify_email"
    )
    assert verify_stats["total"] == 3
    assert verify_stats["failure_count"] == 1
    assert verify_stats["failure_rate"] == pytest.approx(1 / 3, abs=0.0001)
    assert data["kor_travel_map"]["dagster_status"] == "ok"
    assert data["kor_travel_map"]["schedule_count"] == 2
    assert data["kor_travel_map"]["repository_count"] is None
    assert data["kor_travel_map"]["job_count"] is None
    assert data["kor_travel_map"]["asset_count"] is None
    assert data["kor_travel_map"]["features_total"] is None
    assert data["kor_travel_map"]["source_records_total"] is None
    assert data["kor_travel_map"]["operations_by_status"]["running"] == 1
    assert data["kor_travel_map"]["active_operations"] == 1
    assert data["kor_travel_map"]["failed_operations_24h"] == 0
    assert data["kor_travel_map"]["provider_dataset_count"] == 1
    assert data["kor_travel_map"]["recent_import_jobs"][0]["status"] == "running"
    assert data["kor_travel_map"]["recent_import_jobs"][0]["progress"] == 1
    assert (
        data["kor_travel_map"]["recent_import_jobs"][0]["projected_job_id"]
        == "22222222-2222-4222-8222-222222222222"
    )
    location_resp = await client.get(
        "/admin/audit/location",
        cookies=auth_cookies(str(admin_id)),
    )
    assert location_resp.status_code == 200, location_resp.text
    assert location_resp.headers.get("X-Chain-Broken") != "true"
    assert len(location_resp.json()["data"]) == 2


async def test_admin_etl_summary_degrades_when_upstream_ops_is_unavailable(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe() -> admin_etl_service._PinviDagsterProbeResult:
        return admin_etl_service._PinviDagsterProbeResult(
            status="ok",
            message="Dagster server_info/live snapshot 정상",
            latency_ms=11,
            checked_at=datetime.now(UTC),
        )

    monkeypatch.setattr(admin_etl_service, "_probe_pinvi_dagster", fake_probe)
    monkeypatch.setattr(
        etl_router, "build_admin_etl_summary", admin_etl_service.build_admin_etl_summary
    )
    admin_id = await _create_user(
        session_factory, email="admin-etl-down@example.com", roles=["user", "admin"]
    )
    fake = _FakeOpsClient(fail=True)
    _override(fake)
    try:
        resp = await client.get("/admin/etl/summary", cookies=auth_cookies(str(admin_id)))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["pinvi"]["status"] == "ok"
    assert data["kor_travel_map"]["status"] == "down"
    assert data["kor_travel_map"]["dagster_status"] == "unavailable"
    assert len(data["kor_travel_map"]["errors"]) >= 1


async def test_kor_travel_map_etl_empty_success_is_not_down() -> None:
    summary = await admin_etl_service.build_kor_travel_map_etl_summary(_EmptyOpsClient())

    assert summary.status == "ok"
    assert summary.provider_dataset_count == 0
    assert summary.active_operations == 0
    assert summary.recent_import_jobs == []


async def test_kor_travel_map_etl_preserves_dagster_degraded_error() -> None:
    summary = await admin_etl_service.build_kor_travel_map_etl_summary(_DagsterDegradedOpsClient())

    assert summary.status == "degraded"
    assert summary.dagster_status == "unavailable"
    assert summary.dagster_errors == ["Dagster GraphQL unavailable"]


async def test_admin_provider_sync_proxies_key_filter(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-provider@example.com", roles=["user", "operator"]
    )
    fake = _FakeOpsClient()
    fake.schedule_source_status = "unavailable"
    fake.schedule_source_errors = ["Dagster GraphQL unavailable"]
    _override(fake)
    try:
        resp = await client.get(
            "/admin/provider-sync",
            params={"key": "kma"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert fake.dataset_calls == 1
    assert data["total"] == 1
    assert data["schedule_source_status"] == "unavailable"
    assert data["schedule_source_errors"] == ["Dagster GraphQL unavailable"]
    assert data["items"][0]["provider"] == "kma"
    assert data["items"][0]["dataset_key"] == "special_days"
    assert data["items"][0]["eligible_after"] == "2026-06-13T03:30:00+09:00"
    assert data["items"][0]["schedule_next_scheduled_at"] == "2026-06-14T03:30:00+09:00"


async def test_admin_provider_import_jobs_proxies_filters_and_cursor(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-provider-jobs@example.com", roles=["user", "operator"]
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/provider-sync/import-jobs",
            params={
                "status": "running",
                "page_size": "25",
                "cursor": "cursor-1",
            },
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert fake.import_kwargs == {
        "status_filter": "running",
        "load_batch_id": None,
        "parent_job_id": None,
        "page_size": 25,
        "cursor": "cursor-1",
    }
    assert data["items"][0]["job_id"] == "11111111-1111-4111-8111-111111111111"
    assert data["items"][0]["kind"] == "import_job"
    assert data["items"][0]["projected_job_kind"] == "provider_import"
    assert data["next_cursor"] == "cursor-2"


async def test_admin_provider_import_jobs_normalizes_uuid_filters(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    operator_id = await _create_user(
        session_factory,
        email="operator-provider-job-uuid@example.com",
        roles=["user", "operator"],
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/provider-sync/import-jobs",
            params={
                "load_batch_id": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
                "parent_job_id": "{BBBBBBBB-BBBB-4BBB-8BBB-BBBBBBBBBBBB}",
            },
            cookies=auth_cookies(str(operator_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert fake.import_kwargs is not None
    assert fake.import_kwargs["load_batch_id"] == ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    assert fake.import_kwargs["parent_job_id"] == ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


@pytest.mark.parametrize("query_name", ["load_batch_id", "parent_job_id"])
async def test_admin_provider_import_jobs_rejects_invalid_uuid_filters(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    query_name: str,
) -> None:
    operator_id = await _create_user(
        session_factory,
        email=f"operator-provider-job-bad-uuid-{query_name}@example.com",
        roles=["user", "operator"],
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/provider-sync/import-jobs",
            params={query_name: "not-a-uuid"},
            cookies=auth_cookies(str(operator_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake.import_kwargs is None


@pytest.mark.parametrize(
    "fake",
    [
        _MalformedExecutionPageClient(wrong_url=True),
        _MalformedExecutionPageClient(missing_page=True),
    ],
    ids=["wrong-canonical-url", "missing-page-meta"],
)
async def test_admin_provider_import_jobs_rejects_unproven_page(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    fake: _MalformedExecutionPageClient,
) -> None:
    operator_id = await _create_user(
        session_factory,
        email=f"operator-page-{uuid.uuid4().hex}@example.com",
        roles=["user", "operator"],
    )
    _override(fake)
    try:
        resp = await client.get(
            "/admin/provider-sync/import-jobs?status=running&page_size=25",
            cookies=auth_cookies(str(operator_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 502, resp.text
    assert resp.json()["error"]["code"] == "FEATURE_SERVICE_BAD_GATEWAY"


async def test_admin_provider_import_job_detail_supports_cancellation_reconciliation(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-provider-job-detail@example.com",
        roles=["user", "operator"],
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["job_id"] == "11111111-1111-4111-8111-111111111111"
    assert data["status"] == "running"
    assert data["status_url"].endswith(data["job_id"])


async def test_admin_provider_import_job_cancel_proxies_and_writes_audit(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-provider-cancel@example.com", roles=["user", "admin"]
    )
    request_id = uuid.uuid4()
    fake = _AuditOrderingOpsClient(session_factory, request_id)
    _override(fake)
    try:
        resp = await client.post(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111/cancel",
            json={
                "access_reason": "운영자가 중복 실행을 확인함",
                "kor_travel_map_reason": "duplicate run",
            },
            headers={"X-Request-Id": str(request_id)},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert data["requested_job_id"] == "11111111-1111-4111-8111-111111111111"
    assert data["requested_by"] == "service:pinvi"
    assert fake.cancel_args == (
        "11111111-1111-4111-8111-111111111111",
        {"reason": "duplicate run"},
    )
    assert fake.started_seen_before_dispatch is True

    audits = await _request_audits(session_factory, request_id)
    assert [audit.action for audit in audits] == [
        "provider_import_job.cancel.started",
        "provider_import_job.cancel",
    ]
    started, audit = audits
    assert started.after_state == {
        "phase": "started",
        "outcome": "pending",
        "upstream_reason_supplied": True,
    }
    assert audit.actor_user_id == admin_id
    assert audit.action == "provider_import_job.cancel"
    assert audit.resource_type == "provider_import_job"
    assert audit.resource_id == "11111111-1111-4111-8111-111111111111"
    assert audit.access_reason == "운영자가 중복 실행을 확인함"
    assert audit.after_state == {
        "phase": "finished",
        "outcome": "accepted",
        "status": "completed",
        "root_kind": "import_job",
        "root_id": "11111111-1111-4111-8111-111111111111",
        "cancellation_id": "22222222-2222-4222-8222-222222222222",
        "retryable": False,
        "unresolved_member_count": 0,
    }


async def test_admin_provider_import_job_cancel_conflict_preserves_dispatch_audit(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-provider-cancel-conflict@example.com", roles=["user", "admin"]
    )
    request_id = uuid.uuid4()
    fake = _FakeOpsClient(cancel_conflict=True)
    _override(fake)
    try:
        resp = await client.post(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111/cancel",
            json={"access_reason": "이미 끝난 job 취소 확인"},
            headers={"X-Request-Id": str(request_id)},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 409, resp.text
    audits = await _request_audits(session_factory, request_id)
    assert [audit.action for audit in audits] == [
        "provider_import_job.cancel.started",
        "provider_import_job.cancel.result",
    ]
    assert all(audit.actor_user_id == admin_id for audit in audits)
    assert all(audit.access_reason == "이미 끝난 job 취소 확인" for audit in audits)
    assert audits[1].after_state == {
        "phase": "finished",
        "outcome": "typed_failure",
        "error_type": "KorTravelMapConflict",
        "code": "PIPELINE_CANCELLATION_UNSAFE",
    }


class _TypedCancellationErrorClient(_FakeOpsClient):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def cancel_ops_pipeline_execution(
        self,
        job_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self.cancel_args = (job_id, {"reason": reason})
        raise self.error


class _TransportLossThenReconcileClient(_FakeOpsClient):
    def __init__(self) -> None:
        super().__init__()
        self.reconciliation_calls = 0

    async def cancel_ops_pipeline_execution(
        self,
        job_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self.cancel_args = (job_id, {"reason": reason})
        raise KorTravelMapUnavailable(
            "response lost after dispatch",
            code="PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN",
            details={
                "outcome_certainty": "uncertain",
                "reconciliation": {
                    "method": "GET",
                    "path": f"/v1/ops/pipeline/executions/import_job/{job_id}",
                    "scope": "ops:read",
                },
            },
            status_code=503,
        )

    async def get_ops_pipeline_execution(self, job_id: str) -> dict[str, Any]:
        self.reconciliation_calls += 1
        return await super().get_ops_pipeline_execution(job_id)


class _MalformedCancellationClient(_FakeOpsClient):
    async def cancel_ops_pipeline_execution(
        self,
        job_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        result = await super().cancel_ops_pipeline_execution(job_id, reason=reason)
        result["members"] = []
        return result


_CANCELLATION_ERROR_DETAILS: dict[str, Any] = {
    "cancellation_id": "22222222-2222-4222-8222-222222222222",
    "previous_cancellation_id": None,
    "root": {
        "kind": "import_job",
        "id": "11111111-1111-4111-8111-111111111111",
    },
    "status": "retryable",
    "requested_at": "2026-06-12T00:00:00+09:00",
    "requested_by": "service:pinvi",
    "reason": "operator request",
    "error": {
        "code": "DAGSTER_UNAVAILABLE",
        "message": "Dagster unavailable",
        "details": {},
    },
    "updated_at": "2026-06-12T00:01:00+09:00",
    "finished_at": "2026-06-12T00:01:00+09:00",
    "retryable": True,
    "unresolved_member_count": 1,
    "members": [
        {
            "job_id": "11111111-1111-4111-8111-111111111111",
            "dagster_run_id": "run-1",
            "operation_kind": "provider_import",
            "requires_run_termination": True,
            "initial_status": "running",
            "result": "cancel_failed",
            "terminal_status": None,
            "error": {
                "code": "DAGSTER_UNAVAILABLE",
                "message": "Dagster unavailable",
                "details": {},
            },
            "updated_at": "2026-06-12T00:01:00+09:00",
        }
    ],
    "dagster_runs": [
        {
            "dagster_run_id": "run-1",
            "initial_status": "STARTED",
            "termination_reserved_at": "2026-06-12T00:00:30+09:00",
            "result": "cancel_failed",
            "terminal_status": None,
            "error": {
                "code": "DAGSTER_UNAVAILABLE",
                "message": "Dagster unavailable",
                "details": {},
            },
            "engine_started_at": None,
            "engine_finished_at": None,
            "updated_at": "2026-06-12T00:01:00+09:00",
        }
    ],
    "committed_data_rolled_back": False,
    "warnings": ["committed data is retained"],
}
_CANCELLATION_IN_PROGRESS_DETAILS: dict[str, Any] = {
    **_CANCELLATION_ERROR_DETAILS,
    "status": "in_progress",
    "finished_at": None,
    "retryable": False,
    "error": None,
}


def _cancellation_error_details(code: str) -> dict[str, Any]:
    details = deepcopy(_CANCELLATION_ERROR_DETAILS)
    for error in (
        details["error"],
        details["members"][0]["error"],
        details["dagster_runs"][0]["error"],
    ):
        error["code"] = code
    return details


async def test_admin_provider_cancel_preserves_typed_not_found_problem(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-provider-cancel-not-found@example.com",
        roles=["user", "admin"],
    )
    request_id = uuid.uuid4()
    details = {
        "root": {
            "kind": "import_job",
            "id": "11111111-1111-4111-8111-111111111111",
        },
        "cancellation": None,
    }
    fake = _TypedCancellationErrorClient(
        KorTravelMapFeatureNotFound(
            "missing execution",
            code="PIPELINE_EXECUTION_NOT_FOUND",
            details=details,
        )
    )
    _override(fake)
    try:
        resp = await client.post(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111/cancel",
            json={"access_reason": "존재하지 않는 실행 확인"},
            headers={"X-Request-Id": str(request_id)},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == {
        "code": "PIPELINE_EXECUTION_NOT_FOUND",
        "message": "kor_travel_map import job cancel 대상을 찾을 수 없습니다.",
        "details": details,
    }
    audits = await _request_audits(session_factory, request_id)
    assert [audit.action for audit in audits] == [
        "provider_import_job.cancel.started",
        "provider_import_job.cancel.result",
    ]
    assert audits[1].after_state is not None
    assert audits[1].after_state["outcome"] == "typed_failure"
    assert audits[1].after_state["code"] == "PIPELINE_EXECUTION_NOT_FOUND"
    assert audits[1].after_state["details"] == details


@pytest.mark.parametrize(
    ("upstream_error", "expected_status", "expected_code"),
    [
        pytest.param(
            KorTravelMapConflict(
                "coordinator busy",
                code="PIPELINE_CANCELLATION_IN_PROGRESS",
                details=_CANCELLATION_IN_PROGRESS_DETAILS,
                retry_after_seconds=7,
            ),
            409,
            "PIPELINE_CANCELLATION_IN_PROGRESS",
            id="conflict",
        ),
        pytest.param(
            KorTravelMapUnavailable(
                "dagster termination rejected",
                code="DAGSTER_TERMINATE_FAILED",
                details=_cancellation_error_details("DAGSTER_TERMINATE_FAILED"),
                retry_after_seconds=7,
                status_code=502,
            ),
            502,
            "DAGSTER_TERMINATE_FAILED",
            id="bad-gateway",
        ),
        pytest.param(
            KorTravelMapUnavailable(
                "dagster unavailable",
                code="DAGSTER_UNAVAILABLE",
                details=_cancellation_error_details("DAGSTER_UNAVAILABLE"),
                retry_after_seconds=7,
                status_code=503,
            ),
            503,
            "DAGSTER_UNAVAILABLE",
            id="unavailable",
        ),
        pytest.param(
            KorTravelMapUnavailable(
                "dagster terminal confirmation timeout",
                code="DAGSTER_TERMINATION_TIMEOUT",
                details=_cancellation_error_details("DAGSTER_TERMINATION_TIMEOUT"),
                retry_after_seconds=7,
                status_code=503,
            ),
            503,
            "DAGSTER_TERMINATION_TIMEOUT",
            id="termination-timeout",
        ),
    ],
)
async def test_admin_provider_cancel_preserves_typed_problem_and_retry_after(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    upstream_error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email=f"admin-provider-cancel-{expected_status}@example.com",
        roles=["user", "admin"],
    )
    request_id = uuid.uuid4()
    fake = _TypedCancellationErrorClient(upstream_error)
    _override(fake)
    try:
        resp = await client.post(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111/cancel",
            json={"access_reason": "typed cancellation failure"},
            headers={
                "X-Request-Id": str(request_id),
                "Origin": "http://127.0.0.1:12805",
            },
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == expected_status, resp.text
    assert resp.headers["Retry-After"] == "7"
    assert "Retry-After" in resp.headers["Access-Control-Expose-Headers"]
    assert resp.json()["error"]["code"] == expected_code
    expected_details = (
        _CANCELLATION_IN_PROGRESS_DETAILS
        if expected_code == "PIPELINE_CANCELLATION_IN_PROGRESS"
        else _cancellation_error_details(expected_code)
    )
    assert resp.json()["error"]["details"] == expected_details
    audits = await _request_audits(session_factory, request_id)
    assert [audit.action for audit in audits] == [
        "provider_import_job.cancel.started",
        "provider_import_job.cancel.result",
    ]
    assert all(audit.actor_user_id == admin_id for audit in audits)
    assert all(audit.access_reason == "typed cancellation failure" for audit in audits)
    assert audits[1].after_state is not None
    assert audits[1].after_state["outcome"] == "typed_failure"
    assert audits[1].after_state["code"] == expected_code
    assert audits[1].after_state["details"] == expected_details


async def test_admin_provider_cancel_transport_loss_is_audited_before_reconciliation(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-provider-cancel-transport-loss@example.com",
        roles=["user", "admin"],
    )
    request_id = uuid.uuid4()
    fake = _TransportLossThenReconcileClient()
    _override(fake)
    try:
        cancel_resp = await client.post(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111/cancel",
            json={"access_reason": "응답 유실 상관관계 보존"},
            headers={"X-Request-Id": str(request_id)},
            cookies=auth_cookies(str(admin_id)),
        )
        detail_resp = await client.get(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert cancel_resp.status_code == 503, cancel_resp.text
    assert cancel_resp.json()["error"]["code"] == ("PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN")
    assert detail_resp.status_code == 200, detail_resp.text
    assert fake.reconciliation_calls == 1
    audits = await _request_audits(session_factory, request_id)
    assert [audit.action for audit in audits] == [
        "provider_import_job.cancel.started",
        "provider_import_job.cancel.result",
    ]
    assert all(audit.actor_user_id == admin_id for audit in audits)
    assert all(audit.access_reason == "응답 유실 상관관계 보존" for audit in audits)
    assert audits[1].after_state is not None
    assert audits[1].after_state["outcome"] == "uncertain"
    assert audits[1].after_state["code"] == "PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN"


async def test_admin_provider_cancel_projection_drift_is_audited_uncertain(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-provider-cancel-projection-drift@example.com",
        roles=["user", "admin"],
    )
    request_id = uuid.uuid4()
    fake = _MalformedCancellationClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111/cancel",
            json={"access_reason": "취소 projection 불일치 감사"},
            headers={"X-Request-Id": str(request_id)},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 503, resp.text
    assert resp.json()["error"]["code"] == ("PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN")
    audits = await _request_audits(session_factory, request_id)
    assert [audit.action for audit in audits] == [
        "provider_import_job.cancel.started",
        "provider_import_job.cancel.result",
    ]
    assert all(audit.actor_user_id == admin_id for audit in audits)
    assert all(audit.access_reason == "취소 projection 불일치 감사" for audit in audits)
    assert audits[1].after_state is not None
    assert audits[1].after_state["outcome"] == "uncertain"
    assert audits[1].after_state["code"] == ("PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN")


@pytest.mark.parametrize(
    "response_factory",
    [
        pytest.param(
            lambda: httpx.Response(
                200,
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            ),
            id="invalid-json",
        ),
        pytest.param(
            lambda: httpx.Response(200, json={"meta": {}}),
            id="missing-data-envelope",
        ),
        pytest.param(
            lambda: httpx.Response(
                200,
                json={"data": {"status": "completed"}},
            ),
            id="missing-success-meta",
        ),
        pytest.param(
            lambda: httpx.Response(
                200,
                json={"data": {"status": "completed"}, "meta": None},
            ),
            id="null-success-meta",
        ),
        pytest.param(
            lambda: httpx.Response(
                409,
                json={
                    "code": "PIPELINE_CANCELLATION_IN_PROGRESS",
                    "details": {"status": "retryable", "retryable": True},
                },
            ),
            id="partial-typed-detail",
        ),
        pytest.param(
            lambda: httpx.Response(
                500,
                json={"code": "INTERNAL_ERROR", "status": 500},
            ),
            id="unexpected-500",
        ),
        pytest.param(
            lambda: httpx.Response(
                502,
                json={"code": "ARBITRARY_BAD_GATEWAY", "status": 502},
            ),
            id="generic-502",
        ),
        pytest.param(
            lambda: httpx.Response(
                503,
                json={"code": "ARBITRARY_UNAVAILABLE", "status": 503},
            ),
            id="generic-503",
        ),
    ],
)
async def test_admin_provider_cancel_undecidable_response_is_audited_uncertain(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    response_factory: Callable[[], httpx.Response],
) -> None:
    admin_id = await _create_user(
        session_factory,
        email=f"admin-provider-cancel-decode-{uuid.uuid4().hex}@example.com",
        roles=["user", "admin"],
    )
    request_id = uuid.uuid4()

    def handler(_request: httpx.Request) -> httpx.Response:
        return response_factory()

    upstream_http = httpx.AsyncClient(
        base_url="http://kor-travel-map.test",
        transport=httpx.MockTransport(handler),
    )
    upstream_client = KorTravelMapAdminClient(
        upstream_http,
        ops_read_token="ops-read",
        ops_cancel_token="ops-cancel",
    )
    _override(upstream_client)
    try:
        resp = await client.post(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111/cancel",
            json={"access_reason": "취소 결과 해석 실패 감사"},
            headers={"X-Request-Id": str(request_id)},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()
        await upstream_client.aclose()

    assert resp.status_code == 503, resp.text
    error = resp.json()["error"]
    assert error["code"] == "PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN"
    assert error["details"]["reconciliation"] == {
        "method": "GET",
        "path": ("/v1/ops/pipeline/executions/import_job/11111111-1111-4111-8111-111111111111"),
        "scope": "ops:read",
    }
    audits = await _request_audits(session_factory, request_id)
    assert [audit.action for audit in audits] == [
        "provider_import_job.cancel.started",
        "provider_import_job.cancel.result",
    ]
    assert all(audit.actor_user_id == admin_id for audit in audits)
    assert all(audit.access_reason == "취소 결과 해석 실패 감사" for audit in audits)
    assert audits[1].after_state is not None
    assert audits[1].after_state["outcome"] == "uncertain"
    assert audits[1].after_state["code"] == ("PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN")


async def test_invalid_request_id_rejects_cancel_before_upstream_call(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-provider-invalid-request-id@example.com",
        roles=["user", "admin"],
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111/cancel",
            json={"access_reason": "invalid request id must fail closed"},
            headers={"X-Request-Id": "not-a-uuid"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake.cancel_args is None


async def test_operator_cannot_cancel_provider_import_job(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    operator_id = await _create_user(
        session_factory, email="operator-provider-cancel@example.com", roles=["user", "operator"]
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/provider-sync/import-jobs/11111111-1111-4111-8111-111111111111/cancel",
            json={"access_reason": "권한 검증"},
            cookies=auth_cookies(str(operator_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 404
    assert fake.cancel_args is None


async def test_non_admin_provider_sync_route_is_hidden(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    user_id = await _create_user(session_factory, email="plain-provider@example.com")
    resp = await client.get("/admin/provider-sync", cookies=auth_cookies(str(user_id)))
    assert resp.status_code == 404
