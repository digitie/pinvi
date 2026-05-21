from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.mixins import kst_now
from app.models.place import Feature
from app.models.trip import NoticePlan, NoticePoi, Trip, TripDay, TripPoi
from app.models.user import User
from app.schemas.notice import NoticePlanCopyRequest, NoticePlanCopyResponse


class NoticePlanError(Exception):
    pass


class NoticePlanNotFoundError(NoticePlanError):
    pass


class NoticePlanAccessDeniedError(NoticePlanError):
    pass


def copy_notice_plan_to_trip(
    db: Session,
    *,
    current_user: User,
    notice_plan: NoticePlan,
    payload: NoticePlanCopyRequest,
) -> NoticePlanCopyResponse:
    pois = _selected_notice_pois(db, notice_plan.id, payload.poi_ids)
    max_day_index = max([poi.day_index for poi in pois], default=1)
    if payload.target_trip_id is None:
        trip = _create_trip_from_notice(db, current_user, notice_plan, payload, max_day_index)
        created_trip = True
    else:
        trip = _copy_target_trip(db, current_user, payload.target_trip_id)
        _ensure_trip_days(db, trip, max_day_index=max_day_index)
        created_trip = False

    copied_ids: list[UUID] = []
    for index, poi in enumerate(pois, start=1):
        feature_id = _copyable_feature_id(db, poi.feature_id)
        broken_at = None if feature_id is not None or poi.feature_id is None else kst_now()
        sort_order = (
            poi.sort_order
            if created_trip
            else _next_poi_sort_order(db, trip.id, poi.day_index, index)
        )
        copied = TripPoi(
            trip_id=trip.id,
            day_index=poi.day_index,
            sort_order=sort_order,
            feature_id=feature_id,
            feature_link_broken_at=broken_at,
            snapshot=_notice_poi_snapshot(poi),
            custom_marker_color=poi.custom_marker_color,
            custom_marker_icon=poi.custom_marker_icon,
            added_by_user_id=current_user.id,
            memo=poi.memo,
            budget=poi.budget,
            actual_spent=None,
            currency=poi.currency,
            user_url=poi.user_url,
            version=1,
        )
        db.add(copied)
        db.flush()
        copied_ids.append(copied.id)

    db.commit()
    return NoticePlanCopyResponse(
        target_trip_id=trip.id,
        created_trip=created_trip,
        copied_poi_ids=copied_ids,
    )


def _selected_notice_pois(
    db: Session,
    notice_plan_id: UUID,
    poi_ids: list[UUID] | None,
) -> list[NoticePoi]:
    query = select(NoticePoi).where(
        NoticePoi.notice_plan_id == notice_plan_id,
        NoticePoi.deleted_at.is_(None),
    )
    if poi_ids is not None:
        query = query.where(NoticePoi.id.in_(poi_ids))
    pois = db.scalars(query.order_by(NoticePoi.day_index.asc(), NoticePoi.sort_order.asc())).all()
    if poi_ids is not None and {poi.id for poi in pois} != set(poi_ids):
        raise NoticePlanNotFoundError("공지 POI를 찾을 수 없다.")
    return list(pois)


def _create_trip_from_notice(
    db: Session,
    current_user: User,
    notice_plan: NoticePlan,
    payload: NoticePlanCopyRequest,
    max_day_index: int,
) -> Trip:
    trip = Trip(
        user_id=current_user.id,
        leader_id=current_user.id,
        title=payload.target_trip_title or notice_plan.title,
        name=payload.target_trip_title or notice_plan.title,
        destination=payload.target_trip_destination or notice_plan.destination or notice_plan.title,
        start_date=notice_plan.starts_on,
        end_date=notice_plan.ends_on,
        fuel_types=[],
        planning_status="planning",
    )
    db.add(trip)
    db.flush()
    _ensure_trip_days(db, trip, max_day_index=max_day_index)
    return trip


def _copy_target_trip(db: Session, current_user: User, target_trip_id: UUID) -> Trip:
    trip = db.get(Trip, target_trip_id)
    if trip is None or trip.deleted_at is not None:
        raise NoticePlanNotFoundError("여행을 찾을 수 없다.")
    if trip.user_id != current_user.id and not current_user.is_admin:
        raise NoticePlanAccessDeniedError("해당 여행에 공지 POI를 복사할 권한이 없다.")
    return trip


def _ensure_trip_days(db: Session, trip: Trip, *, max_day_index: int) -> None:
    existing = {
        day.day_index for day in db.scalars(select(TripDay).where(TripDay.trip_id == trip.id)).all()
    }
    event_day_count = _event_day_count(trip)
    day_count = max(max_day_index, event_day_count, 1)
    for offset in range(day_count):
        day_index = offset + 1
        if day_index in existing:
            continue
        db.add(
            TripDay(
                trip_id=trip.id,
                day_index=day_index,
                date=_trip_day_date(trip, offset),
            )
        )
    db.flush()


def _event_day_count(trip: Trip) -> int:
    if trip.start_date is None or trip.end_date is None:
        return 0
    return (trip.end_date - trip.start_date).days + 1


def _trip_day_date(trip: Trip, offset: int):
    if trip.start_date is None or trip.end_date is None:
        return None
    day = trip.start_date + timedelta(days=offset)
    if day > trip.end_date:
        return None
    return day


def _next_poi_sort_order(db: Session, trip_id: UUID, day_index: int, index: int) -> str:
    current_count = db.scalar(
        select(func.count()).where(TripPoi.trip_id == trip_id, TripPoi.day_index == day_index)
    )
    return f"{int(current_count or 0) + index:08d}"


def _notice_poi_snapshot(poi: NoticePoi) -> dict:
    snapshot = dict(poi.snapshot or {})
    if poi.feature_id is not None:
        snapshot.setdefault("notice_feature_id", poi.feature_id)
    if poi.map_feature_id is not None:
        snapshot.setdefault("tripmate_map_feature_id", str(poi.map_feature_id))
    snapshot.setdefault("notice_poi_id", str(poi.id))
    snapshot.setdefault("copied_from", "notice_plan")
    snapshot.setdefault("copied_at", kst_now().isoformat())
    return snapshot


def _copyable_feature_id(db: Session, feature_id: str | None) -> str | None:
    if feature_id is None:
        return None
    if db.get(Feature, feature_id) is None:
        return None
    return feature_id
