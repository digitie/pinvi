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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def sync_trip_day_rise_sets(db: AsyncSession, *, trip_id: uuid.UUID) -> None:
    """trip의 모든 일자 rise/set 행을 재계산·upsert한다. 좌표/날짜 변경 행만 refetch 표시.

    best-effort 유지 작업 — 예외를 전파하지 않는다(사용자 mutation은 이미 커밋됨, ETL/다음 sync가 보정).
    """
    try:
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

        existing = {
            row.day_index: row
            for row in await db.scalars(
                select(TripDayRiseSet).where(TripDayRiseSet.trip_id == trip_id)
            )
        }

        for day in days:
            if day.date is not None:
                locdate: date | None = day.date
            elif trip.start_date is not None:
                locdate = trip.start_date + timedelta(days=day.day_index - 1)
            else:
                locdate = None
            reference = resolve_day_reference(pois_by_day.get(day.day_index, []))
            lon = reference.longitude if reference else None
            lat = reference.latitude if reference else None
            status = _status_for(locdate, reference)

            row = existing.get(day.day_index)
            if row is None:
                db.add(
                    TripDayRiseSet(
                        trip_id=trip_id,
                        day_index=day.day_index,
                        locdate=locdate,
                        reference_poi_id=reference.reference_poi_id if reference else None,
                        reference_label=reference.reference_label if reference else None,
                        longitude=lon,
                        latitude=lat,
                        status=status,
                        stale=False,
                    )
                )
                continue
            # 좌표/날짜가 바뀌면 refetch 대상으로 표시(변화 없으면 success를 보존).
            if row.locdate != locdate or row.longitude != lon or row.latitude != lat:
                row.locdate = locdate
                row.longitude = lon
                row.latitude = lat
                row.reference_poi_id = reference.reference_poi_id if reference else None
                row.reference_label = reference.reference_label if reference else None
                row.status = status
                row.stale = True
        await db.commit()
    except Exception as exc:  # best-effort 유지 — 사용자 흐름을 깨지 않는다.
        await db.rollback()
        logger.warning("trip_day_rise_set.sync_failed", extra={"error": str(exc)})
