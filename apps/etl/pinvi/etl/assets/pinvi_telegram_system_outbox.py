"""Telegram system outbox 운영 점검 asset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence

from dagster import Backoff, RetryPolicy, asset
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from pinvi.etl.resources import PinviDatabaseResource

DEFAULT_STUCK_THRESHOLD_MINUTES = 15
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_CATEGORY_WINDOW_HOURS = 24
CATEGORY_STATS_LIMIT = 10


@dataclass(frozen=True, slots=True)
class TelegramOutboxCategoryStats:
    category: str
    total: int
    pending: int
    sent: int
    skipped: int
    failed: int
    retry_exhausted: int

    @property
    def retry_exhausted_rate(self) -> float:
        return 0.0 if self.total == 0 else round(self.retry_exhausted / self.total, 4)


@dataclass(frozen=True, slots=True)
class TelegramOutboxSummary:
    total: int
    pending_total: int
    pending_due: int
    pending_backoff: int
    stuck_pending: int
    sent: int
    skipped: int
    failed: int
    retry_exhausted: int
    oldest_pending_scheduled_at: datetime | None
    stuck_threshold_minutes: int
    max_attempts: int
    category_window_hours: int
    category_stats: tuple[TelegramOutboxCategoryStats, ...]

    def result(self) -> dict[str, int]:
        return {
            "total": self.total,
            "pending_due": self.pending_due,
            "pending_backoff": self.pending_backoff,
            "stuck_pending": self.stuck_pending,
            "sent": self.sent,
            "skipped": self.skipped,
            "failed": self.failed,
            "retry_exhausted": self.retry_exhausted,
        }

    def metadata(self) -> dict[str, Any]:
        return {
            **self.result(),
            "pending_total": self.pending_total,
            "stuck_threshold_minutes": self.stuck_threshold_minutes,
            "max_attempts": self.max_attempts,
            "category_window_hours": self.category_window_hours,
            "oldest_pending_scheduled_at": self.oldest_pending_scheduled_at.isoformat()
            if self.oldest_pending_scheduled_at is not None
            else None,
            "category_retry_exhausted_rates": {
                item.category: item.retry_exhausted_rate for item in self.category_stats
            },
            "category_retry_exhausted": {
                item.category: item.retry_exhausted for item in self.category_stats
            },
        }


async def collect_telegram_outbox_summary(
    conn: AsyncConnection,
    *,
    now: datetime,
    stuck_threshold_minutes: int = DEFAULT_STUCK_THRESHOLD_MINUTES,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    category_window_hours: int = DEFAULT_CATEGORY_WINDOW_HOURS,
) -> TelegramOutboxSummary:
    """`app.telegram_system_notification_outbox` 상태를 payload 없이 집계합니다."""

    params = {
        "now": now,
        "stuck_before": now - timedelta(minutes=stuck_threshold_minutes),
        "max_attempts": max_attempts,
        "category_window_start": now - timedelta(hours=category_window_hours),
        "category_limit": CATEGORY_STATS_LIMIT,
    }
    summary_row = (await conn.execute(_TELEGRAM_OUTBOX_SUMMARY_SQL, params)).mappings().one()
    category_rows = list((await conn.execute(_TELEGRAM_OUTBOX_CATEGORY_SQL, params)).mappings())
    return telegram_outbox_summary_from_rows(
        summary_row,
        category_rows,
        stuck_threshold_minutes=stuck_threshold_minutes,
        max_attempts=max_attempts,
        category_window_hours=category_window_hours,
    )


def telegram_outbox_summary_from_rows(
    summary_row: Mapping[str, Any],
    category_rows: Sequence[Mapping[str, Any]],
    *,
    stuck_threshold_minutes: int,
    max_attempts: int,
    category_window_hours: int,
) -> TelegramOutboxSummary:
    return TelegramOutboxSummary(
        total=_as_int(summary_row["total"]),
        pending_total=_as_int(summary_row["pending_total"]),
        pending_due=_as_int(summary_row["pending_due"]),
        pending_backoff=_as_int(summary_row["pending_backoff"]),
        stuck_pending=_as_int(summary_row["stuck_pending"]),
        sent=_as_int(summary_row["sent"]),
        skipped=_as_int(summary_row["skipped"]),
        failed=_as_int(summary_row["failed"]),
        retry_exhausted=_as_int(summary_row["retry_exhausted"]),
        oldest_pending_scheduled_at=summary_row["oldest_pending_scheduled_at"],
        stuck_threshold_minutes=stuck_threshold_minutes,
        max_attempts=max_attempts,
        category_window_hours=category_window_hours,
        category_stats=tuple(_category_stats_from_rows(category_rows)),
    )


@asset(
    group_name="pinvi_telegram",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="telegram_system_notification_outbox retry/backoff/stuck 상태를 payload 없이 집계",
)
async def pinvi_telegram_system_outbox(  # type: ignore[no-untyped-def]
    context,
    db: PinviDatabaseResource,
) -> dict[str, int]:
    current = datetime.now(UTC)
    stuck_threshold_minutes = int(
        context.op_config.get("stuck_threshold_minutes", DEFAULT_STUCK_THRESHOLD_MINUTES)
    )
    max_attempts = int(context.op_config.get("max_attempts", DEFAULT_MAX_ATTEMPTS))
    category_window_hours = int(
        context.op_config.get("category_window_hours", DEFAULT_CATEGORY_WINDOW_HOURS)
    )

    engine = db.create_engine()
    try:
        async with engine.connect() as conn:
            summary = await collect_telegram_outbox_summary(
                conn,
                now=current,
                stuck_threshold_minutes=stuck_threshold_minutes,
                max_attempts=max_attempts,
                category_window_hours=category_window_hours,
            )
    finally:
        await engine.dispose()

    context.add_output_metadata(summary.metadata())
    return summary.result()


def _category_stats_from_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[TelegramOutboxCategoryStats]:
    return [
        TelegramOutboxCategoryStats(
            category=str(row["category"]),
            total=_as_int(row["total"]),
            pending=_as_int(row["pending"]),
            sent=_as_int(row["sent"]),
            skipped=_as_int(row["skipped"]),
            failed=_as_int(row["failed"]),
            retry_exhausted=_as_int(row["retry_exhausted"]),
        )
        for row in rows
    ]


def _as_int(value: Any) -> int:
    return int(value or 0)


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
