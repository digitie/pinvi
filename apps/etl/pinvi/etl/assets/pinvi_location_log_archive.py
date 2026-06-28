"""위치 접근 로그 archive 후보 dry-run asset."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from dagster import Backoff, RetryPolicy, asset
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from pinvi.etl.resources import PinviDatabaseResource

DEFAULT_LOCATION_RETENTION_MONTHS = 6
PURPOSE_STATS_LIMIT = 10


@dataclass(frozen=True, slots=True)
class LocationLogArchivePurposeStats:
    purpose: str
    total: int


@dataclass(frozen=True, slots=True)
class LocationLogArchiveSummary:
    generated_at: datetime
    archive_cutoff: datetime
    location_retention_months: int
    total_candidates: int
    oldest_candidate_at: datetime | None
    newest_candidate_at: datetime | None
    archive_tail_log_id: int | None
    archive_tail_content_hash: str | None
    active_head_log_id: int | None
    active_head_prev_hash: str | None
    active_rows_after_cutoff: int
    pending_outbox_total: int
    pending_outbox_before_cutoff: int
    oldest_pending_outbox_at: datetime | None
    purpose_stats: tuple[LocationLogArchivePurposeStats, ...]

    @property
    def chain_bridge_required(self) -> bool:
        return self.archive_tail_log_id is not None and self.active_head_log_id is not None

    @property
    def bridge_anchor_matches(self) -> bool | None:
        if not self.chain_bridge_required:
            return None
        return self.active_head_prev_hash == self.archive_tail_content_hash

    @property
    def archive_blocked_by_pending_outbox(self) -> bool:
        return self.pending_outbox_before_cutoff > 0

    def result(self) -> dict[str, Any]:
        return {
            "dry_run": True,
            "total_candidates": self.total_candidates,
            "chain_bridge_required": self.chain_bridge_required,
            "bridge_anchor_matches": self.bridge_anchor_matches,
            "archive_blocked_by_pending_outbox": self.archive_blocked_by_pending_outbox,
            "pending_outbox_before_cutoff": self.pending_outbox_before_cutoff,
        }

    def metadata(self) -> dict[str, Any]:
        return {
            **self.result(),
            "generated_at": self.generated_at.isoformat(),
            "archive_cutoff": self.archive_cutoff.isoformat(),
            "location_retention_months": self.location_retention_months,
            "oldest_candidate_at": _isoformat(self.oldest_candidate_at),
            "newest_candidate_at": _isoformat(self.newest_candidate_at),
            "archive_tail_log_id": self.archive_tail_log_id,
            "archive_tail_content_hash": self.archive_tail_content_hash,
            "active_head_log_id": self.active_head_log_id,
            "active_head_prev_hash": self.active_head_prev_hash,
            "active_rows_after_cutoff": self.active_rows_after_cutoff,
            "pending_outbox_total": self.pending_outbox_total,
            "oldest_pending_outbox_at": _isoformat(self.oldest_pending_outbox_at),
            "purpose_counts": {item.purpose: item.total for item in self.purpose_stats},
        }


async def collect_location_log_archive_summary(
    conn: AsyncConnection,
    *,
    now: datetime,
    location_retention_months: int = DEFAULT_LOCATION_RETENTION_MONTHS,
) -> LocationLogArchiveSummary:
    """`app.location_access_log` archive 후보를 파괴 작업 없이 집계합니다."""

    archive_cutoff = subtract_months(now, location_retention_months)
    params = {
        "archive_cutoff": archive_cutoff,
        "purpose_limit": PURPOSE_STATS_LIMIT,
    }
    summary_row = (await conn.execute(_LOCATION_LOG_ARCHIVE_SUMMARY_SQL, params)).mappings().one()
    purpose_rows = list((await conn.execute(_LOCATION_LOG_ARCHIVE_PURPOSE_SQL, params)).mappings())
    return location_log_archive_summary_from_rows(
        summary_row,
        purpose_rows,
        generated_at=now,
        archive_cutoff=archive_cutoff,
        location_retention_months=location_retention_months,
    )


def location_log_archive_summary_from_rows(
    summary_row: Mapping[str, Any],
    purpose_rows: Sequence[Mapping[str, Any]],
    *,
    generated_at: datetime,
    archive_cutoff: datetime,
    location_retention_months: int,
) -> LocationLogArchiveSummary:
    return LocationLogArchiveSummary(
        generated_at=generated_at,
        archive_cutoff=archive_cutoff,
        location_retention_months=location_retention_months,
        total_candidates=_as_int(summary_row["total_candidates"]),
        oldest_candidate_at=summary_row["oldest_candidate_at"],
        newest_candidate_at=summary_row["newest_candidate_at"],
        archive_tail_log_id=_optional_int(summary_row["archive_tail_log_id"]),
        archive_tail_content_hash=_optional_str(summary_row["archive_tail_content_hash"]),
        active_head_log_id=_optional_int(summary_row["active_head_log_id"]),
        active_head_prev_hash=_optional_str(summary_row["active_head_prev_hash"]),
        active_rows_after_cutoff=_as_int(summary_row["active_rows_after_cutoff"]),
        pending_outbox_total=_as_int(summary_row["pending_outbox_total"]),
        pending_outbox_before_cutoff=_as_int(summary_row["pending_outbox_before_cutoff"]),
        oldest_pending_outbox_at=summary_row["oldest_pending_outbox_at"],
        purpose_stats=tuple(_purpose_stats_from_rows(purpose_rows)),
    )


@asset(
    group_name="pinvi_retention",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="location_access_log archive 후보와 hash-chain bridge 상태를 dry-run으로 집계",
)
async def pinvi_location_log_archive(  # type: ignore[no-untyped-def]
    context,
    db: PinviDatabaseResource,
) -> dict[str, Any]:
    current = datetime.now(UTC)
    location_retention_months = int(
        context.op_config.get(
            "location_retention_months",
            DEFAULT_LOCATION_RETENTION_MONTHS,
        )
    )

    engine = db.create_engine()
    try:
        async with engine.connect() as conn:
            summary = await collect_location_log_archive_summary(
                conn,
                now=current,
                location_retention_months=location_retention_months,
            )
    finally:
        await engine.dispose()

    context.add_output_metadata(summary.metadata())
    return summary.result()


def subtract_months(value: datetime, months: int) -> datetime:
    month_index = value.month - months - 1
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _purpose_stats_from_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[LocationLogArchivePurposeStats]:
    return [
        LocationLogArchivePurposeStats(
            purpose=str(row["purpose"]),
            total=_as_int(row["total"]),
        )
        for row in rows
    ]


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _as_int(value: Any) -> int:
    return int(value or 0)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


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
