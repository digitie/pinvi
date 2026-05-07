from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.place import MapFeature
from app.models.tour import TourServingPublicCulturalFestival
from app.models.trip import Trip, TripDay, TripPlanItem
from app.models.user import User
from app.schemas.trip import TripPlanItemCreateRequest

FUTURE_RESOURCE_TYPES = {"trail", "scenic_road", "route"}


class TripPlanError(Exception):
    pass


class TripPlanNotFoundError(TripPlanError):
    pass


class TripPlanAccessDeniedError(TripPlanError):
    pass


class TripPlanValidationError(TripPlanError):
    pass


def create_trip_plan_item(
    db: Session,
    *,
    current_user: User,
    trip_id: UUID,
    trip_day_id: UUID,
    payload: TripPlanItemCreateRequest,
) -> TripPlanItem:
    trip_day = db.get(TripDay, trip_day_id)
    if trip_day is None or trip_day.trip_id != trip_id:
        raise TripPlanNotFoundError("여행 날짜를 찾을 수 없다.")

    trip = db.get(Trip, trip_id)
    if trip is None:
        raise TripPlanNotFoundError("여행을 찾을 수 없다.")
    if trip.user_id != current_user.id and not current_user.is_admin:
        raise TripPlanAccessDeniedError("해당 여행을 수정할 권한이 없다.")

    resolved = _resolve_resource_snapshot(db, payload)
    sort_order = payload.sort_order or _next_sort_order(db, trip_day_id)
    item = TripPlanItem(
        trip_day_id=trip_day_id,
        resource_type=payload.resource_type,
        sort_order=sort_order,
        map_feature_id=payload.map_feature_id,
        festival_id=payload.festival_id,
        resource_key=payload.resource_key,
        title_snapshot=resolved.title,
        address_snapshot=resolved.address,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        operating_hours_snapshot=resolved.operating_hours,
        longitude=resolved.longitude,
        latitude=resolved.latitude,
        note=payload.note,
        resource_metadata=payload.resource_metadata,
    )
    db.add(item)
    db.flush()
    return item


def _next_sort_order(db: Session, trip_day_id: UUID) -> int:
    current_max = db.scalar(
        select(func.max(TripPlanItem.sort_order)).where(TripPlanItem.trip_day_id == trip_day_id)
    )
    return int(current_max or 0) + 1


class _ResolvedResourceSnapshot:
    def __init__(
        self,
        *,
        title: str,
        address: str | None,
        operating_hours: str | None,
        longitude: Decimal | None,
        latitude: Decimal | None,
    ) -> None:
        self.title = title
        self.address = address
        self.operating_hours = operating_hours
        self.longitude = longitude
        self.latitude = latitude


def _resolve_resource_snapshot(
    db: Session,
    payload: TripPlanItemCreateRequest,
) -> _ResolvedResourceSnapshot:
    if payload.resource_type == "festival":
        return _resolve_festival_snapshot(db, payload)
    if payload.resource_type in {"place", "event", "route", "area", "notice"}:
        return _resolve_map_feature_snapshot(db, payload)
    if payload.resource_type in FUTURE_RESOURCE_TYPES:
        return _resolve_future_resource_snapshot(payload)
    return _resolve_custom_snapshot(payload)


def _resolve_festival_snapshot(
    db: Session,
    payload: TripPlanItemCreateRequest,
) -> _ResolvedResourceSnapshot:
    if payload.festival_id is None:
        raise TripPlanValidationError("축제 일정 항목에는 festival_id가 필요하다.")
    if payload.map_feature_id is not None or payload.resource_key is not None:
        raise TripPlanValidationError(
            "축제 일정 항목에는 map_feature_id/resource_key를 함께 넣지 않는다."
        )

    festival = db.get(TourServingPublicCulturalFestival, payload.festival_id)
    if festival is None or not festival.is_active:
        raise TripPlanNotFoundError("축제 정보를 찾을 수 없다.")

    return _ResolvedResourceSnapshot(
        title=payload.title_snapshot or festival.festival_name,
        address=payload.address_snapshot
        or festival.address_snapshot
        or festival.road_address
        or festival.jibun_address,
        operating_hours=payload.operating_hours_snapshot,
        longitude=payload.longitude if payload.longitude is not None else festival.longitude,
        latitude=payload.latitude if payload.latitude is not None else festival.latitude,
    )


def _resolve_map_feature_snapshot(
    db: Session,
    payload: TripPlanItemCreateRequest,
) -> _ResolvedResourceSnapshot:
    if payload.map_feature_id is None:
        raise TripPlanValidationError("지도 객체 일정 항목에는 map_feature_id가 필요하다.")
    if payload.festival_id is not None or payload.resource_key is not None:
        raise TripPlanValidationError(
            "지도 객체 일정 항목에는 festival_id/resource_key를 함께 넣지 않는다."
        )

    feature = db.get(MapFeature, payload.map_feature_id)
    if (
        feature is None
        or feature.feature_type != payload.resource_type
        or feature.status == "deleted"
        or not feature.is_visible
    ):
        raise TripPlanNotFoundError("지도 객체 정보를 찾을 수 없다.")

    return _ResolvedResourceSnapshot(
        title=payload.title_snapshot or feature.display_name,
        address=payload.address_snapshot or feature.address,
        operating_hours=payload.operating_hours_snapshot,
        longitude=payload.longitude if payload.longitude is not None else feature.longitude,
        latitude=payload.latitude if payload.latitude is not None else feature.latitude,
    )


def _resolve_future_resource_snapshot(
    payload: TripPlanItemCreateRequest,
) -> _ResolvedResourceSnapshot:
    if payload.map_feature_id is not None or payload.festival_id is not None:
        raise TripPlanValidationError(
            "미래 리소스 타입에는 map_feature_id/festival_id를 함께 넣지 않는다."
        )
    if payload.resource_key is None:
        raise TripPlanValidationError("미래 리소스 타입에는 resource_key가 필요하다.")
    if not payload.title_snapshot:
        raise TripPlanValidationError("미래 리소스 타입에는 title_snapshot이 필요하다.")
    return _payload_snapshot(payload)


def _resolve_custom_snapshot(payload: TripPlanItemCreateRequest) -> _ResolvedResourceSnapshot:
    if payload.map_feature_id is not None or payload.festival_id is not None:
        raise TripPlanValidationError(
            "직접 입력 일정 항목에는 map_feature_id/festival_id를 함께 넣지 않는다."
        )
    if not payload.title_snapshot:
        raise TripPlanValidationError("직접 입력 일정 항목에는 title_snapshot이 필요하다.")
    return _payload_snapshot(payload)


def _payload_snapshot(payload: TripPlanItemCreateRequest) -> _ResolvedResourceSnapshot:
    title = payload.title_snapshot
    if not title:
        raise TripPlanValidationError("일정 항목 제목이 필요하다.")
    return _ResolvedResourceSnapshot(
        title=title,
        address=payload.address_snapshot,
        operating_hours=payload.operating_hours_snapshot,
        longitude=payload.longitude,
        latitude=payload.latitude,
    )
