"""일자 단위 KASI 해·달 출몰시각 적재 asset(ADR-055 §6, T-305).

`app.trip_day_rise_sets` 중 채울 대상(`status='pending_fetch'` 또는 `stale`)을 배치로 가져와
`python-kasi-api`의 위치별 출몰시각(`location_rise_set`)으로 채운다. per-POI job(`jobs.py`)과 동일한
KASI 파싱을 쓰되, 일자 단위(`(trip_id, day_index)`)로 배치 처리하고 완료 카운트를 signal로 낸다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from dagster import Backoff, RetryPolicy, asset
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection

from pinvi.etl.resources import KasiResource, PinviDatabaseResource

KST = ZoneInfo("Asia/Seoul")


@asset(
    group_name="pinvi_kasi",
    retry_policy=RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL),
    description="일자 단위 KASI 해·달 출몰시각을 채운다(pending_fetch/stale 대상, ADR-055 §6)",
)
async def pinvi_trip_day_rise_sets(  # type: ignore[no-untyped-def]
    context,
    db: PinviDatabaseResource,
    kasi: KasiResource,
) -> dict[str, int]:
    limit = int(context.op_config.get("batch_limit", 500))
    engine = db.create_engine()
    client = kasi.create_client()
    filled = 0
    failed = 0
    try:
        async with engine.begin() as conn:
            rows = await _select_fillable(conn, limit=limit)
        for row in rows:
            result = await _fill_one(conn_engine=engine, client=client, row=row)
            if result == "success":
                filled += 1
            elif result == "failed":
                failed += 1
    finally:
        await client.aclose()
        await engine.dispose()

    context.add_output_metadata({"filled": filled, "failed": failed, "candidates": len(rows)})
    return {"filled": filled, "failed": failed}


async def _select_fillable(conn: AsyncConnection, *, limit: int) -> list[dict[str, Any]]:
    result = await conn.execute(
        text(
            """
            SELECT trip_id, day_index, locdate, longitude, latitude
            FROM app.trip_day_rise_sets
            WHERE (status = 'pending_fetch' OR stale)
              AND locdate IS NOT NULL
              AND longitude IS NOT NULL
              AND latitude IS NOT NULL
            ORDER BY updated_at ASC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [dict(m) for m in result.mappings()]


async def _fill_one(*, conn_engine: Any, client: Any, row: dict[str, Any]) -> str:
    """단일 (trip_id, day_index) 행을 KASI로 채운다. 행별 독립 트랜잭션(부분 실패 격리)."""
    params = {"trip_id": str(row["trip_id"]), "day_index": row["day_index"]}
    try:
        page = await client.location_rise_set(
            locdate=row["locdate"],
            longitude=row["longitude"],
            latitude=row["latitude"],
        )
        item = page.first
        if item is None:
            async with conn_engine.begin() as conn:
                await _mark_failed(conn, params, error={"message": "KASI 응답 없음"})
            return "failed"
        payload = _rise_set_payload(item)
        async with conn_engine.begin() as conn:
            await conn.execute(
                _UPDATE_SUCCESS,
                {
                    **params,
                    "sunrise_at": _parse_kasi_time(row["locdate"], getattr(item, "sunrise", None)),
                    "sunset_at": _parse_kasi_time(row["locdate"], getattr(item, "sunset", None)),
                    "moonrise_at": _parse_kasi_time(
                        row["locdate"], getattr(item, "moonrise", None)
                    ),
                    "moonset_at": _parse_kasi_time(row["locdate"], getattr(item, "moonset", None)),
                    "raw_payload": payload,
                    "fetched_at": datetime.now(UTC),
                },
            )
        return "success"
    except Exception as exc:
        async with conn_engine.begin() as conn:
            await _mark_failed(
                conn, params, error={"type": type(exc).__name__, "message": str(exc)}
            )
        return "failed"


_UPDATE_SUCCESS = text(
    """
        UPDATE app.trip_day_rise_sets
        SET sunrise_at = :sunrise_at,
            sunset_at = :sunset_at,
            moonrise_at = :moonrise_at,
            moonset_at = :moonset_at,
            status = 'success',
            stale = false,
            raw_payload = :raw_payload,
            error = NULL,
            fetched_at = :fetched_at,
            updated_at = now()
        WHERE trip_id = :trip_id AND day_index = :day_index
        """
).bindparams(bindparam("raw_payload", type_=JSONB))


async def _mark_failed(
    conn: AsyncConnection, params: dict[str, Any], *, error: dict[str, str]
) -> None:
    stmt = text(
        """
        UPDATE app.trip_day_rise_sets
        SET status = 'failed',
            stale = false,
            error = :error,
            fetched_at = :fetched_at,
            updated_at = now()
        WHERE trip_id = :trip_id AND day_index = :day_index
        """
    ).bindparams(bindparam("error", type_=JSONB))
    await conn.execute(stmt, {**params, "error": error, "fetched_at": datetime.now(UTC)})


def _rise_set_payload(item: Any) -> dict[str, Any]:
    raw = getattr(item, "raw", {}) or {}
    return raw if isinstance(raw, dict) else dict(raw)


def _parse_kasi_time(locdate: date, value: object) -> datetime | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if len(text_value) != 4 or not text_value.isdigit():
        return None
    hour = int(text_value[:2])
    minute = int(text_value[2:])
    if hour > 23 or minute > 59:
        return None
    return datetime.combine(locdate, time(hour=hour, minute=minute), tzinfo=KST)
