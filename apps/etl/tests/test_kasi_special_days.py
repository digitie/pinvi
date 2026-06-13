"""KASI 특일 asset helper 테스트."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest

from pinvi.etl.assets.pinvi_kasi_special_days import (
    fetch_special_day_records,
    month_buckets,
)


@dataclass(frozen=True)
class _FakeItem:
    date: date | None
    date_name: str | None
    seq: int | None
    is_holiday: bool | None
    raw: dict[str, object]


@dataclass(frozen=True)
class _FakePage:
    items: tuple[_FakeItem, ...]
    next_page_no: int | None = None


class _FakeKasiClient:
    async def holidays(self, **_kwargs):  # type: ignore[no-untyped-def]
        return _FakePage((_FakeItem(date(2026, 5, 5), "어린이날", 1, True, {"seq": "1"}),))

    async def national_holidays(self, **_kwargs):  # type: ignore[no-untyped-def]
        return _FakePage(())

    async def anniversaries(self, **_kwargs):  # type: ignore[no-untyped-def]
        return _FakePage(())

    async def solar_terms_24(self, **_kwargs):  # type: ignore[no-untyped-def]
        return _FakePage(())

    async def sundry_days(self, **_kwargs):  # type: ignore[no-untyped-def]
        return _FakePage(())


def test_month_buckets_inclusive_range() -> None:
    buckets = month_buckets(date(2026, 6, 5), lookback_months=1, lookahead_months=2)

    assert buckets == [
        date(2026, 5, 1),
        date(2026, 6, 1),
        date(2026, 7, 1),
        date(2026, 8, 1),
    ]


@pytest.mark.asyncio
async def test_fetch_special_day_records_uses_all_datasets_without_network() -> None:
    records = await fetch_special_day_records(
        client=_FakeKasiClient(),
        today=date(2026, 5, 1),
        lookback_months=0,
        lookahead_months=0,
        fetched_at=datetime(2026, 5, 1, tzinfo=UTC),
    )

    assert len(records) == 1
    assert records[0].dataset == "holidays"
    assert records[0].sol_date == date(2026, 5, 5)
    assert records[0].name == "어린이날"
    assert records[0].sequence == "1"
