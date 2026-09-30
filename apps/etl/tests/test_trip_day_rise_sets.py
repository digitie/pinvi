"""일자 rise/set asset helper 테스트 (ADR-055 §6)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from dagster import build_asset_context
from kasi.parser import parse_function_response

from pinvi.etl.assets.pinvi_trip_day_rise_sets import (
    _MARK_FAILED,
    _UPDATE_SUCCESS,
    _parse_kasi_time,
    _rise_set_payload,
    pinvi_trip_day_rise_sets,
)
from pinvi.etl.resources import KasiResource, PinviDatabaseResource


def test_fill_updates_are_snapshot_guarded() -> None:
    """select~fill 사이 좌표/날짜 변경 시 stale 좌표로 덮어쓰지 않도록 UPDATE에 snapshot guard가 있어야 한다."""
    for stmt in (_UPDATE_SUCCESS, _MARK_FAILED):
        sql = str(stmt)
        assert "locdate = :g_locdate" in sql
        assert "longitude = :g_longitude" in sql
        assert "latitude = :g_latitude" in sql


def test_parse_kasi_time_hhmm_to_kst() -> None:
    parsed = _parse_kasi_time(date(2026, 6, 10), "0530")
    assert parsed is not None
    assert parsed.year == 2026 and parsed.month == 6 and parsed.day == 10
    assert parsed.hour == 5 and parsed.minute == 30
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 9 * 3600  # KST


def test_parse_kasi_time_rejects_invalid() -> None:
    assert _parse_kasi_time(date(2026, 6, 10), None) is None
    assert _parse_kasi_time(date(2026, 6, 10), "530") is None  # 4자리 아님
    assert _parse_kasi_time(date(2026, 6, 10), "2560") is None  # 분 60
    assert _parse_kasi_time(date(2026, 6, 10), "2400") is None  # 시 24
    assert _parse_kasi_time(date(2026, 6, 10), "abcd") is None


@dataclass(frozen=True)
class _Item:
    raw: dict[str, object]


def test_rise_set_payload_returns_raw_dict() -> None:
    assert _rise_set_payload(_Item({"sunrise": "0530"})) == {"sunrise": "0530"}
    assert _rise_set_payload(_Item({})) == {}


# 2026-09-30 n150에서 `getLCRiseSetInfo`(서울시청, locdate 20261003, `_type=json`)가 실제로
# 돌려준 response.body — 단건이라 `item`이 dict이고 시각 값에 공백 패딩이 붙는다.
_REAL_LOCATION_RISE_SET_BODY: dict[str, Any] = {
    "items": {
        "item": {
            "aste": "1940  ",
            "astm": "0502  ",
            "civile": "1839  ",
            "civilm": "0603  ",
            "latitude": 3734,
            "latitudeNum": "37.5666660",
            "location": "서울",
            "locdate": 20261003,
            "longitude": 12659,
            "longitudeNum": "126.9833330",
            "moonrise": "2300  ",
            "moonset": "1341  ",
            "moontransit": "0548  ",
            "naute": "1909  ",
            "nautm": "0532  ",
            "sunrise": "0629  ",
            "sunset": "1813  ",
            "suntransit": 122113,
        }
    },
    "numOfRows": 10,
    "pageNo": 1,
    "totalCount": 1,
}

# DB 컬럼 타입 그대로(date, numeric -> Decimal).
_FILLABLE_ROW: dict[str, Any] = {
    "trip_id": "00000000-0000-0000-0000-000000000001",
    "day_index": 0,
    "locdate": date(2026, 10, 3),
    "longitude": Decimal("126.9780"),
    "latitude": Decimal("37.5665"),
}

_SELECT_PARAMS: list[dict[str, Any]] = []
_UPDATES: list[tuple[str, dict[str, Any]]] = []


class _SelectResult:
    def mappings(self) -> list[dict[str, Any]]:
        return [_FILLABLE_ROW]


class _RecordingConn:
    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> Any:
        if stmt is _UPDATE_SUCCESS:
            _UPDATES.append(("success", params or {}))
            return None
        if stmt is _MARK_FAILED:
            _UPDATES.append(("failed", params or {}))
            return None
        _SELECT_PARAMS.append(params or {})
        return _SelectResult()


class _RecordingEngine:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[_RecordingConn]:
        yield _RecordingConn()

    async def dispose(self) -> None:
        return None


class _RealShapeRiseSetClient:
    async def location_rise_set(self, **_kwargs: Any) -> Any:
        return parse_function_response("location_rise_set", _REAL_LOCATION_RISE_SET_BODY)

    async def aclose(self) -> None:
        return None


class _FakeDb(PinviDatabaseResource):
    def create_engine(self) -> Any:
        return _RecordingEngine()


class _FakeKasi(KasiResource):
    def create_client(self) -> Any:
        return _RealShapeRiseSetClient()


def test_asset_runs_without_run_config() -> None:
    """스케줄·smoke launch처럼 run config 없이 돌아도 기본 batch_limit로 채운다.

    회귀: config schema가 없어 `context.op_config`가 None이었고, 첫 줄
    `context.op_config.get("batch_limit", 500)`에서 AttributeError로 재시도만 반복했다
    (2026-09-30 prod smoke run ebb94997). KASI resource·응답 파싱과는 무관했다.
    """
    _SELECT_PARAMS.clear()
    _UPDATES.clear()

    # 직접 호출(invocation)로 돌린다 — materialize는 asset RetryPolicy(60s/180s/420s 대기)를
    # 그대로 따라 실패 시 수 분을 잔다. 스케줄 경로(빈 run config) 자체는
    # test_definitions의 validate_run_config 검사가 본다.
    result = asyncio.run(
        pinvi_trip_day_rise_sets(
            build_asset_context(),
            db=_FakeDb(dsn="postgresql+asyncpg://unused/unused"),
            kasi=_FakeKasi(service_key="unused"),
        )
    )

    assert result == {"filled": 1, "failed": 0}
    assert _SELECT_PARAMS == [{"limit": 500}]
    assert [kind for kind, _params in _UPDATES] == ["success"]
    params = _UPDATES[0][1]
    kst_sunrise = params["sunrise_at"]
    assert isinstance(kst_sunrise, datetime)
    assert (kst_sunrise.hour, kst_sunrise.minute) == (6, 29)
    assert (params["sunset_at"].hour, params["sunset_at"].minute) == (18, 13)
    assert (params["moonrise_at"].hour, params["moonrise_at"].minute) == (23, 0)
    assert (params["moonset_at"].hour, params["moonset_at"].minute) == (13, 41)
    assert params["raw_payload"]["location"] == "서울"
