"""Dagster run-failure sensor — ADR-050 실패 알림 (Sentry + system outbox).

app-owned Dagster job의 run이 retry를 모두 소진하고 실패하면, PII/secret 없는 요약을
`app.telegram_system_notification_outbox`(status=pending)로 적재해 기존 outbox worker가
전송하게 하고, Sentry가 구성돼 있으면 함께 통지한다. 예외 message/stack은 행 데이터나
비밀을 담을 수 있어 payload에 넣지 않고 **예외 클래스명**과 run 식별자만 남긴다.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import Any

from dagster import DefaultSensorStatus, RunFailureSensorContext, run_failure_sensor
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

OUTBOX_CATEGORY = "etl_run_failure"
_MAX_ERROR_CLASS_LEN = 200

_INSERT_OUTBOX_SQL = text(
    """
    INSERT INTO app.telegram_system_notification_outbox (category, payload)
    VALUES (:category, CAST(:payload AS jsonb))
    """
)


def build_run_failure_payload(
    *,
    job_name: str,
    run_id: str,
    error_class: str | None,
    occurred_at: datetime,
) -> dict[str, Any]:
    """PII/secret-free 실패 알림 payload — run 식별자와 예외 '클래스'만 담는다.

    예외 message/stack은 행 데이터·자격증명을 담을 수 있어 제외한다(ADR-050).
    outbox worker 계약(`telegram_outbox.py`)에 맞춰 `audience="admin"` + `text`를 포함해야
    admin target으로 전송된다. text/structured 모두 operational identifier만 담는다.
    """
    cls = (error_class or "UnknownError")[:_MAX_ERROR_CLASS_LEN]
    occurred = occurred_at.astimezone(UTC).isoformat()
    text = (
        f"[Pinvi ETL] Dagster run 실패 — job={job_name}, error={cls}, "
        f"run_id={run_id}, at={occurred}"
    )
    return {
        "audience": "admin",
        "text": text,
        "kind": OUTBOX_CATEGORY,
        "job_name": job_name,
        "run_id": run_id,
        "error_class": cls,
        "occurred_at": occurred,
    }


def _error_class_from_context(context: RunFailureSensorContext) -> str | None:
    event = context.failure_event
    data = getattr(event, "event_specific_data", None)
    error = getattr(data, "error", None)
    cls_name = getattr(error, "cls_name", None)
    return cls_name if isinstance(cls_name, str) else None


async def _insert_outbox(dsn: str, payload: dict[str, Any]) -> None:
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                _INSERT_OUTBOX_SQL,
                {"category": OUTBOX_CATEGORY, "payload": json.dumps(payload)},
            )
    finally:
        await engine.dispose()


def _capture_sentry(payload: dict[str, Any]) -> bool:
    """Sentry는 선택 사항 — DSN 미설정이거나 sentry-sdk 미설치면 skip한다."""
    if not os.getenv("SENTRY_DSN"):
        return False
    try:
        import sentry_sdk
    except ImportError:
        return False
    sentry_sdk.capture_message(
        f"Pinvi ETL run failure: {payload['job_name']} ({payload['error_class']})",
        level="error",
    )
    return True


@run_failure_sensor(
    name="pinvi_run_failure_sensor",
    description=(
        "ADR-050: app-owned Dagster job 실패를 Sentry + "
        "app.telegram_system_notification_outbox로 통지"
    ),
    default_status=DefaultSensorStatus.RUNNING,
)
def pinvi_run_failure_sensor(context: RunFailureSensorContext) -> None:
    payload = build_run_failure_payload(
        job_name=context.dagster_run.job_name,
        run_id=context.dagster_run.run_id,
        error_class=_error_class_from_context(context),
        occurred_at=datetime.now(UTC),
    )

    # Sentry/outbox 둘 다 best-effort — 통지 실패가 daemon tick을 깨지 않게 한다.
    try:
        _capture_sentry(payload)
    except Exception:  # best-effort: notification failure must not break the daemon tick
        context.log.exception("sentry capture failed for ETL run failure")

    dsn = os.getenv("PINVI_DATABASE_URL")
    if not dsn:
        context.log.error("PINVI_DATABASE_URL unset — run failure notification not enqueued")
        return
    try:
        asyncio.run(_insert_outbox(dsn, payload))
    except Exception:  # best-effort: notification failure must not break the daemon tick
        context.log.exception("failed to enqueue ETL run failure notification to outbox")
