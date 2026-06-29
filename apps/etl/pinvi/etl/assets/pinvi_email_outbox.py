"""Email outbox 운영 점검 asset."""

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
DEFAULT_TEMPLATE_WINDOW_HOURS = 24
TEMPLATE_STATS_LIMIT = 10


@dataclass(frozen=True, slots=True)
class EmailOutboxTemplateStats:
    template: str
    total: int
    pending: int
    sent: int
    delivered: int
    failed: int
    bounced: int
    complained: int

    @property
    def failure_count(self) -> int:
        return self.failed + self.bounced + self.complained

    @property
    def failure_rate(self) -> float:
        return 0.0 if self.total == 0 else round(self.failure_count / self.total, 4)


@dataclass(frozen=True, slots=True)
class EmailOutboxSummary:
    total: int
    pending_total: int
    pending_due: int
    pending_backoff: int
    stuck_pending: int
    failed: int
    bounced: int
    complained: int
    retry_exhausted: int
    oldest_pending_scheduled_at: datetime | None
    stuck_threshold_minutes: int
    max_attempts: int
    template_window_hours: int
    template_stats: tuple[EmailOutboxTemplateStats, ...]

    def result(self) -> dict[str, int]:
        return {
            "total": self.total,
            "pending_due": self.pending_due,
            "pending_backoff": self.pending_backoff,
            "stuck_pending": self.stuck_pending,
            "failed": self.failed,
            "bounced": self.bounced,
            "complained": self.complained,
            "retry_exhausted": self.retry_exhausted,
        }

    def metadata(self) -> dict[str, Any]:
        return {
            **self.result(),
            "pending_total": self.pending_total,
            "stuck_threshold_minutes": self.stuck_threshold_minutes,
            "max_attempts": self.max_attempts,
            "template_window_hours": self.template_window_hours,
            "oldest_pending_scheduled_at": self.oldest_pending_scheduled_at.isoformat()
            if self.oldest_pending_scheduled_at is not None
            else None,
            "template_failure_rates": {
                item.template: item.failure_rate for item in self.template_stats
            },
            "template_failures": {
                item.template: item.failure_count for item in self.template_stats
            },
        }


async def collect_email_outbox_summary(
    conn: AsyncConnection,
    *,
    now: datetime,
    stuck_threshold_minutes: int = DEFAULT_STUCK_THRESHOLD_MINUTES,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    template_window_hours: int = DEFAULT_TEMPLATE_WINDOW_HOURS,
) -> EmailOutboxSummary:
    """`app.email_queue` 상태를 PII 없이 bounded metadata로 집계합니다."""

    params = {
        "now": now,
        "stuck_before": now - timedelta(minutes=stuck_threshold_minutes),
        "max_attempts": max_attempts,
        "template_window_start": now - timedelta(hours=template_window_hours),
        "template_limit": TEMPLATE_STATS_LIMIT,
    }
    summary_row = (await conn.execute(_EMAIL_OUTBOX_SUMMARY_SQL, params)).mappings().one()
    template_rows = list((await conn.execute(_EMAIL_OUTBOX_TEMPLATE_SQL, params)).mappings())
    return email_outbox_summary_from_rows(
        summary_row,
        template_rows,
        stuck_threshold_minutes=stuck_threshold_minutes,
        max_attempts=max_attempts,
        template_window_hours=template_window_hours,
    )


def email_outbox_summary_from_rows(
    summary_row: Mapping[str, Any],
    template_rows: Sequence[Mapping[str, Any]],
    *,
    stuck_threshold_minutes: int,
    max_attempts: int,
    template_window_hours: int,
) -> EmailOutboxSummary:
    return EmailOutboxSummary(
        total=_as_int(summary_row["total"]),
        pending_total=_as_int(summary_row["pending_total"]),
        pending_due=_as_int(summary_row["pending_due"]),
        pending_backoff=_as_int(summary_row["pending_backoff"]),
        stuck_pending=_as_int(summary_row["stuck_pending"]),
        failed=_as_int(summary_row["failed"]),
        bounced=_as_int(summary_row["bounced"]),
        complained=_as_int(summary_row["complained"]),
        retry_exhausted=_as_int(summary_row["retry_exhausted"]),
        oldest_pending_scheduled_at=summary_row["oldest_pending_scheduled_at"],
        stuck_threshold_minutes=stuck_threshold_minutes,
        max_attempts=max_attempts,
        template_window_hours=template_window_hours,
        template_stats=tuple(_template_stats_from_rows(template_rows)),
    )


@asset(
    group_name="pinvi_email",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="email_queue pending/backoff/stuck/failed 상태를 PII 없이 집계",
)
async def pinvi_email_outbox(  # type: ignore[no-untyped-def]
    context,
    db: PinviDatabaseResource,
) -> dict[str, int]:
    current = datetime.now(UTC)
    stuck_threshold_minutes = int(
        context.op_config.get("stuck_threshold_minutes", DEFAULT_STUCK_THRESHOLD_MINUTES)
    )
    max_attempts = int(context.op_config.get("max_attempts", DEFAULT_MAX_ATTEMPTS))
    template_window_hours = int(
        context.op_config.get("template_window_hours", DEFAULT_TEMPLATE_WINDOW_HOURS)
    )

    engine = db.create_engine()
    try:
        async with engine.connect() as conn:
            summary = await collect_email_outbox_summary(
                conn,
                now=current,
                stuck_threshold_minutes=stuck_threshold_minutes,
                max_attempts=max_attempts,
                template_window_hours=template_window_hours,
            )
    finally:
        await engine.dispose()

    context.add_output_metadata(summary.metadata())
    return summary.result()


def _template_stats_from_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[EmailOutboxTemplateStats]:
    return [
        EmailOutboxTemplateStats(
            template=str(row["template"]),
            total=_as_int(row["total"]),
            pending=_as_int(row["pending"]),
            sent=_as_int(row["sent"]),
            delivered=_as_int(row["delivered"]),
            failed=_as_int(row["failed"]),
            bounced=_as_int(row["bounced"]),
            complained=_as_int(row["complained"]),
        )
        for row in rows
    ]


def _as_int(value: Any) -> int:
    return int(value or 0)


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
