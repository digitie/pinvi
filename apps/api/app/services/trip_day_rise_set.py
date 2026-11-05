"""일자 단위 일출/일몰(`app.trip_day_rise_sets`) 유지 로직(ADR-055 §6, T-305).

기준 좌표는 그 일자 non-deleted POI들의 **centroid**(결정적)이고, 대표 POI(= created_at-earliest,
안정적)를 `reference_label`("XX 장소 기준")로 쓴다. locdate = effective_date(day.date override 또는
start_date+day_index 파생). 좌표/날짜가 바뀐 행은 `stale=True` + `status=pending_fetch`로 표시해
전용 ETL asset이 KASI 출몰시각으로 다시 채우게 한다.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db_session
from app.models.kasi import TripDayRiseSet
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.services.kasi import extract_feature_coordinates

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DayReference:
    longitude: float
    latitude: float
    reference_poi_id: uuid.UUID
    reference_label: str


def resolve_day_reference(pois: list[TripDayPoi]) -> DayReference | None:
    """일자 POI centroid 좌표 + 대표 POI(created_at-earliest). 좌표 있는 POI가 없으면 None.

    `pois`는 non-deleted, (created_at, attachment_id) 오름차순 정렬 가정.
    """
    with_coord: list[tuple[TripDayPoi, tuple[float, float]]] = []
    for poi in pois:
        snapshot = poi.feature_snapshot if isinstance(poi.feature_snapshot, dict) else {}
        coord = extract_feature_coordinates(snapshot)
        if coord is not None:
            with_coord.append((poi, coord))
    if not with_coord:
        return None
    lon = sum(c[1][0] for c in with_coord) / len(with_coord)
    lat = sum(c[1][1] for c in with_coord) / len(with_coord)
    rep = with_coord[0][0]  # created_at-earliest (대표)
    rep_snapshot = rep.feature_snapshot if isinstance(rep.feature_snapshot, dict) else {}
    label = rep_snapshot.get("name") or rep_snapshot.get("title") or "장소"
    return DayReference(
        longitude=lon,
        latitude=lat,
        reference_poi_id=rep.attachment_id,
        reference_label=str(label),
    )


def _status_for(locdate: date | None, reference: DayReference | None) -> str:
    if locdate is None:
        return "pending_date"
    if reference is None:
        return "pending_coord"
    return "pending_fetch"


async def sync_trip_day_rise_sets(*, trip_id: uuid.UUID) -> None:
    """별도 트랜잭션으로 유지한다. 호출자는 먼저 읽기 커넥션을 반환해야 한다.

    사용자 mutation은 이미 커밋되어야 한다. 실패 rollback은 이 유지 세션에만
    적용되며, 호출자가 응답 조립에 쓰는 Trip/POI나 미커밋 변경을 만지지 않는다.
    """
    try:
        async with db_session.async_session_factory() as db, db.begin():
            await _sync_trip_day_rise_sets(db, trip_id=trip_id)
    except Exception as exc:  # best-effort — 다음 열람/ETL에서 보정.
        logger.warning("trip_day_rise_set.sync_failed", extra={"error_type": type(exc).__name__})


async def _sync_trip_day_rise_sets(db: AsyncSession, *, trip_id: uuid.UUID) -> None:
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id))
    if trip is None:
        return
    days = list(
        await db.scalars(
            select(TripDay).where(TripDay.trip_id == trip_id).order_by(TripDay.day_index)
        )
    )
    pois = list(
        await db.scalars(
            select(TripDayPoi)
            .where(TripDayPoi.trip_id == trip_id, TripDayPoi.deleted_at.is_(None))
            .order_by(TripDayPoi.created_at, TripDayPoi.attachment_id)
        )
    )
    pois_by_day: dict[int, list[TripDayPoi]] = {}
    for poi in pois:
        pois_by_day.setdefault(poi.day_index, []).append(poi)

    for day in days:
        if day.date is not None:
            locdate: date | None = day.date
        elif trip.start_date is not None:
            locdate = trip.start_date + timedelta(days=day.day_index - 1)
        else:
            locdate = None
        reference = resolve_day_reference(pois_by_day.get(day.day_index, []))
        statement = insert(TripDayRiseSet).values(
            trip_id=trip_id,
            day_index=day.day_index,
            locdate=locdate,
            reference_poi_id=reference.reference_poi_id if reference else None,
            reference_label=reference.reference_label if reference else None,
            longitude=reference.longitude if reference else None,
            latitude=reference.latitude if reference else None,
            status=_status_for(locdate, reference),
            stale=False,
        )
        incoming = statement.excluded
        # 충돌은 DB가 원자적으로 처리한다. 입력이 같으면 ETL이 채운 success/시각/
        # payload/fetched_at을 그대로 보존하고, 변경된 입력만 재조회 대상으로 삼는다.
        await db.execute(
            statement.on_conflict_do_update(
                constraint="pk_trip_day_rise_sets",
                set_={
                    "locdate": incoming.locdate,
                    "longitude": incoming.longitude,
                    "latitude": incoming.latitude,
                    "reference_poi_id": incoming.reference_poi_id,
                    "reference_label": incoming.reference_label,
                    "status": incoming.status,
                    "stale": True,
                    "updated_at": func.now(),
                },
                where=or_(
                    TripDayRiseSet.locdate.is_distinct_from(incoming.locdate),
                    TripDayRiseSet.longitude.is_distinct_from(incoming.longitude),
                    TripDayRiseSet.latitude.is_distinct_from(incoming.latitude),
                ),
            )
        )
