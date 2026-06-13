"""KASI 특일 계열 dataset 적재 asset."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from dagster import Backoff, RetryPolicy, asset
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection

from pinvi.etl.resources import KasiResource, PinviDatabaseResource

SPECIAL_DAY_DATASETS: dict[str, str] = {
    "holidays": "holidays",
    "national_holidays": "national_holidays",
    "anniversaries": "anniversaries",
    "solar_terms_24": "solar_terms_24",
    "sundry_days": "sundry_days",
}


@dataclass(frozen=True, slots=True)
class SpecialDayRecord:
    dataset: str
    sol_date: date
    name: str
    sequence: str
    is_holiday: bool | None
    raw_payload: dict[str, Any]
    fetched_at: datetime


def month_buckets(today: date, *, lookback_months: int, lookahead_months: int) -> list[date]:
    """실행일 기준 월 bucket 시작일 목록을 inclusive로 생성합니다."""

    start = _add_months(date(today.year, today.month, 1), -lookback_months)
    end = _add_months(date(today.year, today.month, 1), lookahead_months)
    buckets: list[date] = []
    current = start
    while current <= end:
        buckets.append(current)
        current = _add_months(current, 1)
    return buckets


async def fetch_special_day_records(
    *,
    client: Any,
    today: date,
    lookback_months: int,
    lookahead_months: int,
    fetched_at: datetime | None = None,
) -> list[SpecialDayRecord]:
    """`python-kasi-api` public helper로 특일 record를 수집합니다."""

    collected_at = fetched_at or datetime.now(UTC)
    records: list[SpecialDayRecord] = []
    for month in month_buckets(
        today,
        lookback_months=lookback_months,
        lookahead_months=lookahead_months,
    ):
        for dataset, method_name in SPECIAL_DAY_DATASETS.items():
            fetch_page = getattr(client, method_name)
            async for page in _iter_special_day_pages(
                fetch_page,
                sol_year=month.year,
                sol_month=month.month,
            ):
                for item in page.items:
                    record = _record_from_item(
                        dataset=dataset,
                        item=item,
                        fetched_at=collected_at,
                    )
                    if record is not None:
                        records.append(record)
    return records


async def upsert_special_day_records(
    conn: AsyncConnection,
    records: Sequence[SpecialDayRecord],
) -> int:
    """`app.kasi_special_days`에 삭제 없이 upsert합니다."""

    if not records:
        return 0

    stmt = text(
        """
            INSERT INTO app.kasi_special_days (
              dataset, sol_date, name, sequence, is_holiday, raw_payload, fetched_at
            )
            VALUES (
              :dataset, :sol_date, :name, :sequence, :is_holiday,
              :raw_payload, :fetched_at
            )
            ON CONFLICT (dataset, sol_date, sequence, name)
            DO UPDATE SET
              is_holiday = EXCLUDED.is_holiday,
              raw_payload = EXCLUDED.raw_payload,
              fetched_at = EXCLUDED.fetched_at,
              updated_at = now()
            """
    ).bindparams(bindparam("raw_payload", type_=JSONB))
    await conn.execute(stmt, [_record_params(record) for record in records])
    return len(records)


@asset(
    group_name="pinvi_kasi",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="KASI 특일 정보를 과거 6개월~미래 18개월 범위로 upsert",
)
async def pinvi_kasi_special_days(  # type: ignore[no-untyped-def]
    context,
    db: PinviDatabaseResource,
    kasi: KasiResource,
) -> dict[str, int]:
    today = datetime.now(UTC).date()
    lookback = int(context.op_config.get("lookback_months", 6))
    lookahead = int(context.op_config.get("lookahead_months", 18))

    engine = db.create_engine()
    client = kasi.create_client()
    try:
        records = await fetch_special_day_records(
            client=client,
            today=today,
            lookback_months=lookback,
            lookahead_months=lookahead,
        )
        async with engine.begin() as conn:
            upserted = await upsert_special_day_records(conn, records)
    finally:
        await client.aclose()
        await engine.dispose()

    context.add_output_metadata(
        {
            "records": upserted,
            "lookback_months": lookback,
            "lookahead_months": lookahead,
        }
    )
    return {"records": upserted}


async def _iter_special_day_pages(
    fetch_page: Callable[..., Awaitable[Any]],
    *,
    sol_year: int,
    sol_month: int,
    num_of_rows: int = 100,
) -> AsyncIterator[Any]:
    page_no = 1
    while True:
        page = await fetch_page(
            sol_year=sol_year,
            sol_month=sol_month,
            page_no=page_no,
            num_of_rows=num_of_rows,
        )
        if not page.items:
            break
        yield page
        next_page = page.next_page_no
        if next_page is None:
            break
        page_no = next_page


def _record_from_item(
    *,
    dataset: str,
    item: Any,
    fetched_at: datetime,
) -> SpecialDayRecord | None:
    sol_date = getattr(item, "date", None)
    name = getattr(item, "date_name", None)
    if sol_date is None or not name:
        return None
    raw = getattr(item, "raw", {}) or {}
    if not isinstance(raw, dict):
        raw = dict(raw)
    seq = getattr(item, "seq", None)
    return SpecialDayRecord(
        dataset=dataset,
        sol_date=sol_date,
        name=str(name),
        sequence="" if seq is None else str(seq),
        is_holiday=getattr(item, "is_holiday", None),
        raw_payload=raw,
        fetched_at=fetched_at,
    )


def _record_params(record: SpecialDayRecord) -> dict[str, Any]:
    return {
        "dataset": record.dataset,
        "sol_date": record.sol_date,
        "name": record.name,
        "sequence": record.sequence,
        "is_holiday": record.is_holiday,
        "raw_payload": record.raw_payload,
        "fetched_at": record.fetched_at,
    }


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, 1)
