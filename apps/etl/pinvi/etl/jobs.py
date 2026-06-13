"""Pinvi Dagster one-shot job 정의."""

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from dagster import Config, OpExecutionContext, job, op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

KST = ZoneInfo("Asia/Seoul")


class PoiRiseSetConfig(Config):
    poi_id: str


@op(required_resource_keys={"db", "kasi"})
async def fetch_trip_poi_rise_set(
    context: OpExecutionContext,
    config: PoiRiseSetConfig,
) -> dict[str, str]:
    """단일 POI의 KASI 위치별 해·달 출몰시각을 가져와 저장합니다."""

    poi_id = str(UUID(config.poi_id))
    db = context.resources.db
    kasi = context.resources.kasi
    engine = db.create_engine()
    client = kasi.create_client()
    try:
        async with engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """
                        SELECT poi_id, locdate, longitude, latitude, status
                        FROM app.trip_poi_rise_sets
                        WHERE poi_id = :poi_id
                        FOR UPDATE
                        """
                        ),
                        {"poi_id": poi_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise ValueError(f"trip_poi_rise_sets row 없음: {poi_id}")
            if row["locdate"] is None:
                await _mark_status(conn, poi_id=poi_id, status="pending_date")
                return {"status": "pending_date"}
            if row["longitude"] is None or row["latitude"] is None:
                await _mark_status(conn, poi_id=poi_id, status="pending_coord")
                return {"status": "pending_coord"}

            try:
                page = await client.location_rise_set(
                    locdate=row["locdate"],
                    longitude=row["longitude"],
                    latitude=row["latitude"],
                )
                item = page.first
                if item is None:
                    await _mark_failed(conn, poi_id=poi_id, error={"message": "KASI 응답 없음"})
                    return {"status": "failed"}
                payload = _rise_set_payload(item)
                await conn.execute(
                    _UPDATE_RISE_SET_SUCCESS,
                    {
                        "poi_id": poi_id,
                        "sunrise_at": _parse_kasi_time(
                            row["locdate"], getattr(item, "sunrise", None)
                        ),
                        "sunset_at": _parse_kasi_time(
                            row["locdate"], getattr(item, "sunset", None)
                        ),
                        "moonrise_at": _parse_kasi_time(
                            row["locdate"], getattr(item, "moonrise", None)
                        ),
                        "moonset_at": _parse_kasi_time(
                            row["locdate"], getattr(item, "moonset", None)
                        ),
                        "raw_payload": payload,
                        "fetched_at": datetime.now(UTC),
                    },
                )
                return {"status": "success"}
            except Exception as exc:
                await _mark_failed(
                    conn,
                    poi_id=poi_id,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
                raise
    finally:
        await client.aclose()
        await engine.dispose()


@job
def kasi_poi_rise_set_job() -> None:
    fetch_trip_poi_rise_set()


_UPDATE_RISE_SET_SUCCESS = text(
    """
        UPDATE app.trip_poi_rise_sets
        SET sunrise_at = :sunrise_at,
            sunset_at = :sunset_at,
            moonrise_at = :moonrise_at,
            moonset_at = :moonset_at,
            status = 'success',
            raw_payload = :raw_payload,
            error = NULL,
            fetched_at = :fetched_at,
            updated_at = now()
        WHERE poi_id = :poi_id
        """
).bindparams(bindparam("raw_payload", type_=JSONB))


async def _mark_status(conn: Any, *, poi_id: str, status: str) -> None:
    await conn.execute(
        text(
            """
            UPDATE app.trip_poi_rise_sets
            SET status = :status,
                updated_at = now()
            WHERE poi_id = :poi_id
            """
        ),
        {"poi_id": poi_id, "status": status},
    )


async def _mark_failed(conn: Any, *, poi_id: str, error: dict[str, str]) -> None:
    stmt = text(
        """
            UPDATE app.trip_poi_rise_sets
            SET status = 'failed',
                error = :error,
                fetched_at = :fetched_at,
                updated_at = now()
            WHERE poi_id = :poi_id
            """
    ).bindparams(bindparam("error", type_=JSONB))
    await conn.execute(stmt, {"poi_id": poi_id, "error": error, "fetched_at": datetime.now(UTC)})


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
