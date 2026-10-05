"""KASI 특일 asset helper 테스트."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pytest
from dagster import build_asset_context
from kasi.parser import parse_function_response

from pinvi.etl.assets.pinvi_kasi_special_days import (
    SPECIAL_DAY_DATASETS,
    fetch_special_day_records,
    month_buckets,
    pinvi_kasi_special_days,
)
from pinvi.etl.resources import KasiResource, PinviDatabaseResource


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


# 2026-09-30 n150에서 `getRestDeInfo`(solMonth별, `_type=json`)가 실제로 돌려준 response.body
# 세 가지 모양 — 특일 없는 달은 `items: ""`, 1건이면 `item`이 dict, 여러 건이면 list다.
_REAL_EMPTY_MONTH_BODY: dict[str, Any] = {
    "items": "",
    "numOfRows": 100,
    "pageNo": 1,
    "totalCount": 0,
}
_REAL_2026_10_BODY: dict[str, Any] = {
    "items": {
        "item": [
            {
                "dateKind": "01",
                "dateName": "개천절",
                "isHoliday": "Y",
                "locdate": 20261003,
                "seq": 1,
            },
            {
                "dateKind": "01",
                "dateName": "대체공휴일(개천절)",
                "isHoliday": "Y",
                "locdate": 20261005,
                "seq": 1,
            },
            {
                "dateKind": "01",
                "dateName": "한글날",
                "isHoliday": "Y",
                "locdate": 20261009,
                "seq": 1,
            },
        ]
    },
    "numOfRows": 100,
    "pageNo": 1,
    "totalCount": 3,
}
_REAL_2026_12_BODY: dict[str, Any] = {
    "items": {
        "item": {
            "dateKind": "01",
            "dateName": "기독탄신일",
            "isHoliday": "Y",
            "locdate": 20261225,
            "seq": 1,
        }
    },
    "numOfRows": 100,
    "pageNo": 1,
    "totalCount": 1,
}

_CALLS: list[tuple[str, int, int]] = []
_UPSERTED: list[dict[str, Any]] = []


class _RealShapeKasiClient:
    """`python-kasi-api`의 fixture 파서로 실제 응답 body를 `Page`로 만들어 돌려준다."""

    def __getattr__(self, name: str) -> Any:
        if name not in SPECIAL_DAY_DATASETS.values():
            raise AttributeError(name)

        async def fetch(*, sol_year: int, sol_month: int, **_kwargs: Any) -> Any:
            _CALLS.append((name, sol_year, sol_month))
            body = _REAL_EMPTY_MONTH_BODY
            if name == "holidays" and sol_month == 10:
                body = _REAL_2026_10_BODY
            elif name == "holidays" and sol_month == 12:
                body = _REAL_2026_12_BODY
            return parse_function_response(name, body)

        return fetch

    async def aclose(self) -> None:
        return None


class _RecordingConn:
    async def execute(self, _stmt: Any, params: list[dict[str, Any]] | None = None) -> None:
        _UPSERTED.extend(params or [])


class _RecordingEngine:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[_RecordingConn]:
        yield _RecordingConn()

    async def dispose(self) -> None:
        return None


class _FakeDb(PinviDatabaseResource):
    def create_engine(self) -> Any:
        return _RecordingEngine()


class _FakeKasi(KasiResource):
    def create_client(self) -> Any:
        return _RealShapeKasiClient()


def test_asset_runs_without_run_config() -> None:
    """스케줄·smoke launch처럼 run config 없이 돌아도 기본 범위로 적재한다.

    회귀: config schema가 없어 `context.op_config`가 None이었고, 첫 줄
    `context.op_config.get("lookback_months", 6)`에서 AttributeError로 재시도만 반복했다
    (2026-09-30 prod smoke run 8cf775c2).
    """
    _CALLS.clear()
    _UPSERTED.clear()

    # 직접 호출(invocation)로 돌린다 — materialize는 asset RetryPolicy(60s/180s/420s 대기)를
    # 그대로 따라 실패 시 수 분을 잔다. 스케줄 경로(빈 run config) 자체는
    # test_definitions의 validate_run_config 검사가 본다.
    result = asyncio.run(
        pinvi_kasi_special_days(
            build_asset_context(),
            db=_FakeDb(dsn="postgresql+asyncpg://unused/unused"),
            kasi=_FakeKasi(service_key="unused"),
        )
    )

    today = datetime.now(UTC).date()
    months = month_buckets(today, lookback_months=6, lookahead_months=18)
    assert len(months) == 25
    assert len(_CALLS) == len(months) * len(SPECIAL_DAY_DATASETS)
    octobers = sum(1 for month in months if month.month == 10)
    decembers = sum(1 for month in months if month.month == 12)
    assert len(_UPSERTED) == 3 * octobers + decembers
    assert {row["dataset"] for row in _UPSERTED} == {"holidays"}
    assert {row["name"] for row in _UPSERTED} == {
        "개천절",
        "대체공휴일(개천절)",
        "한글날",
        "기독탄신일",
    }
    assert result == {"records": len(_UPSERTED)}


def test_month_range_cannot_allocate_unbounded_buckets() -> None:
    for invalid in [-1, 37, 10000000, True]:
        with pytest.raises(ValueError):
            month_buckets(date(2026, 5, 1), lookback_months=invalid, lookahead_months=0)


@pytest.mark.asyncio
async def test_nonadvancing_provider_page_is_rejected() -> None:
    from pinvi.etl.assets.pinvi_kasi_special_days import iter_special_day_records

    class Loop(_FakeKasiClient):
        async def holidays(self, **kwargs):
            return _FakePage((_FakeItem(date(2026, 5, 5), "휴일", 1, True, {}),), next_page_no=1)

    with pytest.raises(ValueError, match="진행"):
        _ = [
            record
            async for record in iter_special_day_records(
                client=Loop(), today=date(2026, 5, 1), lookback_months=0, lookahead_months=0
            )
        ]


def test_large_run_flushes_bounded_batches_and_keeps_python_peak_bounded():
    import tracemalloc

    sizes = []

    class Client:
        async def holidays(self, **kwargs):
            number = kwargs["page_no"]
            items = tuple(
                _FakeItem(
                    date(2026, 5, 5),
                    f"휴일-{number}-{i}",
                    i,
                    True,
                    {"value": str(number * 100 + i) + "x" * 8192},
                )
                for i in range(100)
            )
            return _FakePage(items, next_page_no=number + 1 if number < 50 else None)

        async def national_holidays(self, **kwargs):
            return _FakePage(())

        anniversaries = national_holidays
        solar_terms_24 = national_holidays
        sundry_days = national_holidays

        async def aclose(self):
            pass

    class Engine:
        @asynccontextmanager
        async def begin(self):
            yield self

        async def execute(self, statement, rows):
            sizes.append(len(rows))
            assert len(rows) <= 100

        async def dispose(self):
            pass

    engine = Engine()

    class Db(PinviDatabaseResource):
        def create_engine(self):
            return engine

    class Kasi(KasiResource):
        def create_client(self):
            return Client()

    with build_asset_context(asset_config={"lookback_months": 0, "lookahead_months": 0}) as context:
        tracemalloc.start()
        try:
            result = asyncio.run(
                pinvi_kasi_special_days(
                    context,
                    db=Db(dsn="postgresql+asyncpg://unused/unused"),
                    kasi=Kasi(service_key="unused"),
                )
            )
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    assert result == {"records": 5000}
    assert sum(sizes) == 5000 and max(sizes) <= 100
    assert peak < 8 * 1024 * 1024, peak
    print(f"bounded 5000-record Python allocation peak: {peak} bytes")
