"""ETL raw SQL smoke tests against the migrated app schema."""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


def _load_etl_sql_modules() -> tuple[Any, Any]:
    apps_dir = Path(__file__).resolve().parents[3]
    etl_dir = apps_dir / "etl"
    if str(etl_dir) not in sys.path:
        sys.path.insert(0, str(etl_dir))
    return (
        importlib.import_module("pinvi.etl.sql.outbox"),
        importlib.import_module("pinvi.etl.sql.retention"),
    )


async def test_etl_raw_sql_statements_execute_against_alembic_schema(
    session_factory: Any,
) -> None:
    outbox_sql, retention_sql = _load_etl_sql_modules()
    now = datetime(2026, 6, 29, 4, 30, tzinfo=UTC)
    params = {
        "now": now,
        "stuck_before": now - timedelta(minutes=15),
        "max_attempts": 5,
        "template_window_start": now - timedelta(hours=24),
        "template_limit": 10,
        "category_window_start": now - timedelta(hours=24),
        "category_limit": 10,
        "user_pii_cutoff": now - timedelta(days=30),
        "session_cutoff": now - timedelta(days=30),
        "archive_cutoff": now - timedelta(days=180),
        "purpose_limit": 10,
    }
    statements = [
        outbox_sql.EMAIL_OUTBOX_SUMMARY_SQL,
        outbox_sql.EMAIL_OUTBOX_TEMPLATE_SQL,
        outbox_sql.TELEGRAM_OUTBOX_SUMMARY_SQL,
        outbox_sql.TELEGRAM_OUTBOX_CATEGORY_SQL,
        retention_sql.PII_RETENTION_SUMMARY_SQL,
        retention_sql.LOCATION_LOG_ARCHIVE_SUMMARY_SQL,
        retention_sql.LOCATION_LOG_ARCHIVE_PURPOSE_SQL,
    ]

    async with session_factory() as db:
        for statement in statements:
            await db.execute(statement, params)
