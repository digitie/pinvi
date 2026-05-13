from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict
from uuid import UUID, uuid4

from geoalchemy2.elements import WKTElement
from sqlalchemy import String, func, or_, select
from sqlalchemy import cast as sa_cast
from sqlalchemy.orm import Session

from app.core.json_types import JsonValue
from app.models.mixins import kst_now
from app.models.place import Feature
from app.models.trip import Trip, TripDay, TripPoi
from app.models.user import User
from app.schemas.admin import AdminEntityKind
from app.services.admin_auth import hash_password

MAX_ADMIN_PAGE_SIZE = 100
DEFAULT_ADMIN_LIMIT = 25
MAX_TRIP_DAY_SPAN = 31

ACCOUNT_STATUSES = {
    "pending_email_verification",
    "invited",
    "active",
    "disabled",
    "deleted",
}
SYSTEM_ROLES = {"admin", "planner", "participant"}
FEATURE_KINDS = {"place", "event", "notice", "price", "weather", "route", "area"}
FEATURE_STATUSES = {"active", "hidden", "broken"}
TRIP_PLANNING_STATUSES = {"idea", "draft", "active", "completed", "archived"}


class AdminEntityValidationError(Exception):
    pass


class AdminEntityNotFoundError(Exception):
    pass


class AdminEntityMapPointData(TypedDict):
    latitude: float
    longitude: float


class AdminEntityLinkData(TypedDict):
    entity: AdminEntityKind
    relation: str
    id: str | None
    label: str
    query: dict[str, str]


class AdminEntityItemData(TypedDict):
    entity: AdminEntityKind
    id: str
    label: str
    subtitle: str | None
    status: str | None
    fields: dict[str, JsonValue]
    links: list[AdminEntityLinkData]
    map: AdminEntityMapPointData | None


class AdminEntityListData(TypedDict):
    entity: AdminEntityKind
    items: list[AdminEntityItemData]
    page: int
    limit: int
    total: int


class AdminEntityRelatedGroupData(TypedDict):
    label: str
    entity: AdminEntityKind
    query: dict[str, str]
    count: int
    sample: list[AdminEntityItemData]


class AdminEntityDetailData(TypedDict):
    entity: AdminEntityKind
    item: AdminEntityItemData
    related: list[AdminEntityRelatedGroupData]


def list_admin_entities(
    db: Session,
    *,
    entity: AdminEntityKind,
    page: int,
    limit: int,
    search: str | None,
    filters: Mapping[str, str],
) -> AdminEntityListData:
    resolved_page = max(page, 1)
    resolved_limit = min(max(limit, 1), MAX_ADMIN_PAGE_SIZE)
    if entity == "users":
        return _list_users(
            db,
            page=resolved_page,
            limit=resolved_limit,
            search=search,
            filters=filters,
        )
    if entity == "features":
        return _list_features(
            db,
            page=resolved_page,
            limit=resolved_limit,
            search=search,
            filters=filters,
        )
    if entity == "trips":
        return _list_trips(
            db,
            page=resolved_page,
            limit=resolved_limit,
            search=search,
            filters=filters,
        )
    return _list_pois(
        db,
        page=resolved_page,
        limit=resolved_limit,
        search=search,
        filters=filters,
    )


def get_admin_entity_detail(
    db: Session,
    *,
    entity: AdminEntityKind,
    item_id: str,
) -> AdminEntityDetailData:
    if entity == "users":
        return _get_user_detail(db, item_id)
    if entity == "features":
        return _get_feature_detail(db, item_id)
    if entity == "trips":
        return _get_trip_detail(db, item_id)
    return _get_poi_detail(db, item_id)


def create_admin_entity(
    db: Session,
    *,
    entity: AdminEntityKind,
    values: Mapping[str, JsonValue],
) -> str:
    if entity == "users":
        return str(_create_user(db, values).id)
    if entity == "features":
        return _create_feature(db, values).feature_id
    if entity == "trips":
        return str(_create_trip(db, values).id)
    return str(_create_poi(db, values).id)


def update_admin_entity(
    db: Session,
    *,
    entity: AdminEntityKind,
    item_id: str,
    values: Mapping[str, JsonValue],
    current_user: User,
) -> str:
    if entity == "users":
        return str(_update_user(db, item_id, values, current_user=current_user).id)
    if entity == "features":
        return _update_feature(db, item_id, values).feature_id
    if entity == "trips":
        return str(_update_trip(db, item_id, values).id)
    return str(_update_poi(db, item_id, values).id)


def delete_admin_entity(
    db: Session,
    *,
    entity: AdminEntityKind,
    item_id: str,
    current_user: User,
) -> str:
    if entity == "users":
        user = _get_user_or_raise(db, item_id)
        if user.id == current_user.id:
            raise AdminEntityValidationError("자기 자신의 관리자 계정은 삭제할 수 없다.")
        user.account_status = "deleted"
        user.status = "disabled"
        user.is_active = False
        return str(user.id)
    if entity == "features":
        feature = _get_feature_or_raise(db, item_id)
        feature.status = "hidden"
        feature.deleted_at = kst_now()
        return feature.feature_id
    if entity == "trips":
        trip = _get_trip_or_raise(db, item_id)
        trip.deleted_at = kst_now()
        trip.planning_status = "archived"
        return str(trip.id)

    poi = _get_poi_or_raise(db, item_id)
    deleted_id = str(poi.id)
    db.delete(poi)
    return deleted_id


def _list_users(
    db: Session,
    *,
    page: int,
    limit: int,
    search: str | None,
    filters: Mapping[str, str],
) -> AdminEntityListData:
    query = select(User)
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search.lower()}%"
        query = query.where(
            or_(
                func.lower(User.email).like(pattern),
                func.lower(func.coalesce(User.nickname, "")).like(pattern),
                func.lower(func.coalesce(User.name, "")).like(pattern),
                func.lower(func.coalesce(User.display_name, "")).like(pattern),
                sa_cast(User.id, String).ilike(f"%{normalized_search}%"),
            )
        )
    account_status = filters.get("account_status")
    system_role = filters.get("system_role")
    if account_status:
        query = query.where(User.account_status == account_status)
    if system_role:
        query = query.where(User.system_role == system_role)

    total = _count_query(db, query)
    users = db.scalars(
        query.order_by(User.created_at.desc(), User.email.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return {
        "entity": "users",
        "items": [_user_item(db, user) for user in users],
        "page": page,
        "limit": limit,
        "total": total,
    }


def _list_features(
    db: Session,
    *,
    page: int,
    limit: int,
    search: str | None,
    filters: Mapping[str, str],
) -> AdminEntityListData:
    query = select(Feature)
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        query = query.where(
            or_(
                Feature.feature_id.ilike(pattern),
                Feature.name.ilike(pattern),
                Feature.category.ilike(pattern),
                func.coalesce(Feature.address_road, "").ilike(pattern),
                func.coalesce(Feature.address_jibun, "").ilike(pattern),
            )
        )
    kind = filters.get("kind")
    status = filters.get("status")
    feature_id = filters.get("feature_id")
    if kind:
        query = query.where(Feature.kind == kind)
    if status:
        query = query.where(Feature.status == status)
    if feature_id:
        query = query.where(Feature.feature_id == feature_id)

    total = _count_query(db, query)
    features = db.scalars(
        query.order_by(Feature.updated_at.desc(), Feature.feature_id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return {
        "entity": "features",
        "items": [_feature_item(db, feature) for feature in features],
        "page": page,
        "limit": limit,
        "total": total,
    }


def _list_trips(
    db: Session,
    *,
    page: int,
    limit: int,
    search: str | None,
    filters: Mapping[str, str],
) -> AdminEntityListData:
    query = select(Trip)
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        query = query.where(
            or_(
                sa_cast(Trip.id, String).ilike(pattern),
                Trip.title.ilike(pattern),
                func.coalesce(Trip.name, "").ilike(pattern),
                Trip.destination.ilike(pattern),
            )
        )
    user_id = filters.get("user_id")
    planning_status = filters.get("planning_status")
    if user_id:
        query = query.where(Trip.user_id == _parse_uuid(user_id, "user_id"))
    if planning_status:
        query = query.where(Trip.planning_status == planning_status)

    total = _count_query(db, query)
    trips = db.scalars(
        query.order_by(Trip.created_at.desc(), Trip.start_date.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return {
        "entity": "trips",
        "items": [_trip_item(db, trip) for trip in trips],
        "page": page,
        "limit": limit,
        "total": total,
    }


def _list_pois(
    db: Session,
    *,
    page: int,
    limit: int,
    search: str | None,
    filters: Mapping[str, str],
) -> AdminEntityListData:
    query = select(TripPoi)
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        query = query.where(
            or_(
                sa_cast(TripPoi.id, String).ilike(pattern),
                sa_cast(TripPoi.trip_id, String).ilike(pattern),
                func.coalesce(TripPoi.feature_id, "").ilike(pattern),
                func.coalesce(TripPoi.memo, "").ilike(pattern),
                sa_cast(TripPoi.snapshot, String).ilike(pattern),
            )
        )
    trip_id = filters.get("trip_id")
    feature_id = filters.get("feature_id")
    user_id = filters.get("user_id")
    if trip_id:
        query = query.where(TripPoi.trip_id == _parse_uuid(trip_id, "trip_id"))
    if feature_id:
        query = query.where(TripPoi.feature_id == feature_id)
    if user_id:
        query = query.where(TripPoi.added_by_user_id == _parse_uuid(user_id, "user_id"))

    total = _count_query(db, query)
    pois = db.scalars(
        query.order_by(TripPoi.created_at.desc(), TripPoi.trip_id.asc(), TripPoi.sort_order.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return {
        "entity": "pois",
        "items": [_poi_item(db, poi) for poi in pois],
        "page": page,
        "limit": limit,
        "total": total,
    }


def _get_user_detail(db: Session, item_id: str) -> AdminEntityDetailData:
    user = _get_user_or_raise(db, item_id)
    return {
        "entity": "users",
        "item": _user_item(db, user),
        "related": [
            _related_group(
                db,
                label="사용자의 여행",
                entity="trips",
                query={"user_id": str(user.id)},
            ),
            _related_group(
                db,
                label="사용자가 추가한 POI",
                entity="pois",
                query={"user_id": str(user.id)},
            ),
        ],
    }


def _get_feature_detail(db: Session, item_id: str) -> AdminEntityDetailData:
    feature = _get_feature_or_raise(db, item_id)
    return {
        "entity": "features",
        "item": _feature_item(db, feature),
        "related": [
            _related_group(
                db,
                label="이 feature를 참조하는 POI",
                entity="pois",
                query={"feature_id": feature.feature_id},
            )
        ],
    }


def _get_trip_detail(db: Session, item_id: str) -> AdminEntityDetailData:
    trip = _get_trip_or_raise(db, item_id)
    return {
        "entity": "trips",
        "item": _trip_item(db, trip),
        "related": [
            _related_group(
                db,
                label="여행 소유자",
                entity="users",
                query={"search": str(trip.user_id)},
            ),
            _related_group(
                db,
                label="여행 POI",
                entity="pois",
                query={"trip_id": str(trip.id)},
            ),
        ],
    }


def _get_poi_detail(db: Session, item_id: str) -> AdminEntityDetailData:
    poi = _get_poi_or_raise(db, item_id)
    related = [
        _related_group(db, label="연결된 여행", entity="trips", query={"search": str(poi.trip_id)}),
        _related_group(
            db,
            label="추가한 사용자",
            entity="users",
            query={"search": str(poi.added_by_user_id)},
        ),
    ]
    if poi.feature_id:
        related.append(
            _related_group(
                db,
                label="연결된 feature",
                entity="features",
                query={"feature_id": poi.feature_id},
            )
        )
    return {
        "entity": "pois",
        "item": _poi_item(db, poi),
        "related": related,
    }


def _create_user(db: Session, values: Mapping[str, JsonValue]) -> User:
    email = _require_str(values, "email", max_length=320).lower()
    password = _optional_str(values, "password", max_length=120)
    account_status = _enum_value(
        _optional_str(values, "account_status", max_length=32) or "active",
        ACCOUNT_STATUSES,
        "account_status",
    )
    system_role = _enum_value(
        _optional_str(values, "system_role", max_length=32) or "planner",
        SYSTEM_ROLES,
        "system_role",
    )
    nickname = _optional_str(values, "nickname", max_length=80)
    name = _optional_str(values, "name", max_length=80)
    email_verified = _optional_bool(values, "email_verified") or account_status == "active"
    user = User(
        email=email,
        password_hash=hash_password(password) if password else None,
        display_name=nickname or name or email,
        account_status=account_status,
        status="active" if account_status == "active" else "pending_verification",
        system_role=system_role,
        nickname=nickname,
        name=name,
        birth_year_month=_optional_str(values, "birth_year_month", max_length=6),
        birth_yyyymm=_optional_str(values, "birth_yyyymm", max_length=6),
        gender=_optional_str(values, "gender", max_length=32),
        residence_sigungu_code=_optional_str(values, "residence_sigungu_code", max_length=10),
        email_verified=email_verified,
        email_verified_at=kst_now() if email_verified else None,
        is_active=account_status not in {"disabled", "deleted"},
        is_admin=system_role == "admin",
        is_privileged=system_role == "admin",
    )
    db.add(user)
    db.flush()
    return user


def _update_user(
    db: Session,
    item_id: str,
    values: Mapping[str, JsonValue],
    *,
    current_user: User,
) -> User:
    user = _get_user_or_raise(db, item_id)
    requested_status = _optional_str(values, "account_status", max_length=32)
    requested_role = _optional_str(values, "system_role", max_length=32)
    if user.id == current_user.id:
        if requested_status in {"disabled", "deleted"}:
            raise AdminEntityValidationError("자기 자신의 관리자 계정은 비활성화할 수 없다.")
        if requested_role is not None and requested_role != "admin":
            raise AdminEntityValidationError("자기 자신의 관리자 권한은 제거할 수 없다.")

    if "email" in values:
        user.email = _require_str(values, "email", max_length=320).lower()
    if "password" in values:
        password = _optional_str(values, "password", max_length=120)
        if password:
            user.password_hash = hash_password(password)
    if requested_status is not None:
        user.account_status = _enum_value(requested_status, ACCOUNT_STATUSES, "account_status")
        user.status = "active" if user.account_status == "active" else "disabled"
        user.is_active = user.account_status not in {"disabled", "deleted"}
    if requested_role is not None:
        user.system_role = _enum_value(requested_role, SYSTEM_ROLES, "system_role")
        user.is_admin = user.system_role == "admin"
        user.is_privileged = user.system_role == "admin"
    for field_name in (
        "nickname",
        "name",
        "birth_year_month",
        "birth_yyyymm",
        "gender",
        "residence_sigungu_code",
    ):
        if field_name in values:
            setattr(user, field_name, _optional_str(values, field_name, max_length=80))
    if user.nickname is not None:
        user.display_name = user.nickname
    elif user.name is not None:
        user.display_name = user.name
    if "email_verified" in values:
        email_verified = _optional_bool(values, "email_verified") or False
        user.email_verified = email_verified
        user.email_verified_at = kst_now() if email_verified else None
    db.flush()
    return user


def _create_feature(db: Session, values: Mapping[str, JsonValue]) -> Feature:
    feature_id = _optional_str(values, "feature_id", max_length=120) or f"admin:{uuid4()}"
    lon = _require_decimal(values, "longitude")
    lat = _require_decimal(values, "latitude")
    feature = Feature(
        feature_id=feature_id,
        kind=_enum_value(
            _optional_str(values, "kind", max_length=32) or "place",
            FEATURE_KINDS,
            "kind",
        ),
        name=_require_str(values, "name", max_length=255),
        bjd_code=_optional_str(values, "bjd_code", max_length=10),
        coord=_point(lon, lat),
        address_road=_optional_str(values, "address_road", max_length=700),
        address_jibun=_optional_str(values, "address_jibun", max_length=700),
        category=_optional_str(values, "category", max_length=120) or "admin",
        parent_feature_id=_optional_str(values, "parent_feature_id", max_length=120),
        urls=_json_object(values, "urls"),
        marker_icon=_optional_str(values, "marker_icon", max_length=80) or "pin",
        marker_color=_optional_str(values, "marker_color", max_length=16) or "#0f766e",
        detail=_json_object_or_none(values, "detail"),
        raw_refs=_json_object_list(values, "raw_refs"),
        status=_enum_value(
            _optional_str(values, "status", max_length=32) or "active",
            FEATURE_STATUSES,
            "status",
        ),
    )
    db.add(feature)
    db.flush()
    return feature


def _update_feature(db: Session, item_id: str, values: Mapping[str, JsonValue]) -> Feature:
    feature = _get_feature_or_raise(db, item_id)
    if "kind" in values:
        feature.kind = _enum_value(
            _require_str(values, "kind", max_length=32),
            FEATURE_KINDS,
            "kind",
        )
    for field_name in ("name", "category", "marker_icon", "marker_color"):
        if field_name in values:
            setattr(feature, field_name, _require_str(values, field_name, max_length=700))
    for field_name in ("bjd_code", "address_road", "address_jibun", "parent_feature_id"):
        if field_name in values:
            setattr(feature, field_name, _optional_str(values, field_name, max_length=700))
    if "status" in values:
        feature.status = _enum_value(
            _require_str(values, "status", max_length=32),
            FEATURE_STATUSES,
            "status",
        )
    if "urls" in values:
        feature.urls = _json_object(values, "urls")
    if "detail" in values:
        feature.detail = _json_object_or_none(values, "detail")
    if "raw_refs" in values:
        feature.raw_refs = _json_object_list(values, "raw_refs")
    if "longitude" in values or "latitude" in values:
        lon, lat = _feature_coordinates(db, feature.feature_id)
        next_lon = _optional_decimal(values, "longitude")
        next_lat = _optional_decimal(values, "latitude")
        feature.coord = _point(
            next_lon if next_lon is not None else Decimal(str(lon)),
            next_lat if next_lat is not None else Decimal(str(lat)),
        )
    feature.updated_at = kst_now()
    db.flush()
    return feature


def _create_trip(db: Session, values: Mapping[str, JsonValue]) -> Trip:
    user_id = _require_uuid(values, "user_id")
    user = db.get(User, user_id)
    if user is None:
        raise AdminEntityValidationError("여행 소유 사용자를 찾을 수 없다.")
    start_date = _require_date(values, "start_date")
    end_date = _require_date(values, "end_date")
    if end_date < start_date:
        raise AdminEntityValidationError("여행 종료일은 시작일보다 빠를 수 없다.")
    _validate_trip_span(start_date, end_date)
    leader_id = _optional_uuid(values, "leader_id") or user_id
    trip = Trip(
        user_id=user_id,
        leader_id=leader_id,
        title=_require_str(values, "title", max_length=120),
        name=_optional_str(values, "name", max_length=255),
        destination=_require_str(values, "destination", max_length=120),
        start_date=start_date,
        end_date=end_date,
        fuel_types=_string_list(values, "fuel_types"),
        planning_status=_enum_value(
            _optional_str(values, "planning_status", max_length=32) or "idea",
            TRIP_PLANNING_STATUSES,
            "planning_status",
        ),
    )
    db.add(trip)
    db.flush()
    _ensure_trip_days(db, trip)
    return trip


def _update_trip(db: Session, item_id: str, values: Mapping[str, JsonValue]) -> Trip:
    trip = _get_trip_or_raise(db, item_id)
    if "user_id" in values:
        user_id = _require_uuid(values, "user_id")
        if db.get(User, user_id) is None:
            raise AdminEntityValidationError("여행 소유 사용자를 찾을 수 없다.")
        trip.user_id = user_id
    if "leader_id" in values:
        trip.leader_id = _optional_uuid(values, "leader_id")
    if "title" in values:
        trip.title = _require_str(values, "title", max_length=120)
    if "name" in values:
        trip.name = _optional_str(values, "name", max_length=255)
    if "destination" in values:
        trip.destination = _require_str(values, "destination", max_length=120)
    if "start_date" in values:
        trip.start_date = _require_date(values, "start_date")
    if "end_date" in values:
        trip.end_date = _require_date(values, "end_date")
    if trip.end_date < trip.start_date:
        raise AdminEntityValidationError("여행 종료일은 시작일보다 빠를 수 없다.")
    _validate_trip_span(trip.start_date, trip.end_date)
    if "fuel_types" in values:
        trip.fuel_types = _string_list(values, "fuel_types")
    if "planning_status" in values:
        trip.planning_status = _enum_value(
            _require_str(values, "planning_status", max_length=32),
            TRIP_PLANNING_STATUSES,
            "planning_status",
        )
    _ensure_trip_days(db, trip)
    db.flush()
    return trip


def _create_poi(db: Session, values: Mapping[str, JsonValue]) -> TripPoi:
    trip_id = _require_uuid(values, "trip_id")
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise AdminEntityValidationError("POI를 넣을 여행을 찾을 수 없다.")
    day_index = _optional_int(values, "day_index") or 1
    if _get_trip_day(db, trip_id, day_index) is None:
        raise AdminEntityValidationError("POI를 넣을 여행 날짜를 찾을 수 없다.")
    added_by = _optional_uuid(values, "added_by_user_id") or trip.user_id
    if db.get(User, added_by) is None:
        raise AdminEntityValidationError("POI 추가 사용자를 찾을 수 없다.")
    feature_id = _optional_str(values, "feature_id", max_length=120)
    feature = db.get(Feature, feature_id) if feature_id else None
    if feature_id and feature is None:
        raise AdminEntityValidationError("연결할 feature를 찾을 수 없다.")
    poi = TripPoi(
        trip_id=trip_id,
        day_index=day_index,
        sort_order=_optional_str(values, "sort_order", max_length=80)
        or _next_poi_sort_order(db, trip_id, day_index),
        feature_id=feature_id,
        snapshot=_poi_snapshot(values, feature),
        custom_marker_color=_optional_str(values, "custom_marker_color", max_length=16),
        custom_marker_icon=_optional_str(values, "custom_marker_icon", max_length=255),
        added_by_user_id=added_by,
        memo=_optional_str(values, "memo", max_length=1000),
        budget=_optional_decimal(values, "budget"),
        actual_spent=_optional_decimal(values, "actual_spent"),
        currency=_optional_str(values, "currency", max_length=3) or "KRW",
        user_url=_optional_str(values, "user_url", max_length=700),
    )
    db.add(poi)
    db.flush()
    return poi


def _update_poi(db: Session, item_id: str, values: Mapping[str, JsonValue]) -> TripPoi:
    poi = _get_poi_or_raise(db, item_id)
    if "trip_id" in values:
        trip_id = _require_uuid(values, "trip_id")
        if db.get(Trip, trip_id) is None:
            raise AdminEntityValidationError("POI를 넣을 여행을 찾을 수 없다.")
        poi.trip_id = trip_id
    if "day_index" in values:
        day_index = _require_int(values, "day_index")
        if _get_trip_day(db, poi.trip_id, day_index) is None:
            raise AdminEntityValidationError("POI를 넣을 여행 날짜를 찾을 수 없다.")
        poi.day_index = day_index
    if "sort_order" in values:
        poi.sort_order = _require_str(values, "sort_order", max_length=80)
    if "feature_id" in values:
        feature_id = _optional_str(values, "feature_id", max_length=120)
        if feature_id and db.get(Feature, feature_id) is None:
            raise AdminEntityValidationError("연결할 feature를 찾을 수 없다.")
        poi.feature_id = feature_id
        poi.feature_link_broken_at = None if feature_id else kst_now()
    if "added_by_user_id" in values:
        added_by = _require_uuid(values, "added_by_user_id")
        if db.get(User, added_by) is None:
            raise AdminEntityValidationError("POI 추가 사용자를 찾을 수 없다.")
        poi.added_by_user_id = added_by
    for field_name in (
        "custom_marker_color",
        "custom_marker_icon",
        "memo",
        "currency",
        "user_url",
    ):
        if field_name in values:
            setattr(poi, field_name, _optional_str(values, field_name, max_length=1000))
    if "snapshot" in values:
        poi.snapshot = _json_object(values, "snapshot")
    if "budget" in values:
        poi.budget = _optional_decimal(values, "budget")
    if "actual_spent" in values:
        poi.actual_spent = _optional_decimal(values, "actual_spent")
    poi.version += 1
    db.flush()
    return poi


def _user_item(db: Session, user: User) -> AdminEntityItemData:
    trip_count = _count_rows(db, select(Trip).where(Trip.user_id == user.id))
    poi_count = _count_rows(db, select(TripPoi).where(TripPoi.added_by_user_id == user.id))
    return {
        "entity": "users",
        "id": str(user.id),
        "label": user.display_name or user.nickname or user.name or user.email,
        "subtitle": user.email,
        "status": user.account_status,
        "fields": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "nickname": user.nickname,
            "name": user.name,
            "account_status": user.account_status,
            "system_role": user.system_role,
            "status": user.status,
            "email_verified": user.email_verified,
            "email_verified_at": _iso(user.email_verified_at),
            "birth_year_month": user.birth_year_month,
            "gender": user.gender,
            "residence_sigungu_code": user.residence_sigungu_code,
            "is_active": user.is_active,
            "is_admin": user.is_admin,
            "is_privileged": user.is_privileged,
            "trip_count": trip_count,
            "poi_count": poi_count,
            "created_at": _iso(user.created_at),
            "updated_at": _iso(user.updated_at),
        },
        "links": [
            _link("trips", "user_trips", f"여행 {trip_count}건", query={"user_id": str(user.id)}),
            _link("pois", "user_pois", f"POI {poi_count}건", query={"user_id": str(user.id)}),
        ],
        "map": None,
    }


def _feature_item(db: Session, feature: Feature) -> AdminEntityItemData:
    lon, lat = _feature_coordinates(db, feature.feature_id)
    poi_count = _count_rows(db, select(TripPoi).where(TripPoi.feature_id == feature.feature_id))
    return {
        "entity": "features",
        "id": feature.feature_id,
        "label": feature.name,
        "subtitle": f"{feature.kind} / {feature.category}",
        "status": feature.status,
        "fields": {
            "feature_id": feature.feature_id,
            "kind": feature.kind,
            "name": feature.name,
            "category": feature.category,
            "status": feature.status,
            "bjd_code": feature.bjd_code,
            "address_road": feature.address_road,
            "address_jibun": feature.address_jibun,
            "longitude": lon,
            "latitude": lat,
            "parent_feature_id": feature.parent_feature_id,
            "marker_icon": feature.marker_icon,
            "marker_color": feature.marker_color,
            "urls": _json_value(feature.urls),
            "detail": _json_value(feature.detail),
            "raw_refs": _json_value(feature.raw_refs),
            "poi_count": poi_count,
            "created_at": _iso(feature.created_at),
            "updated_at": _iso(feature.updated_at),
            "deleted_at": _iso(feature.deleted_at),
        },
        "links": [
            _link(
                "pois",
                "feature_pois",
                f"참조 POI {poi_count}건",
                query={"feature_id": feature.feature_id},
            )
        ],
        "map": {"latitude": lat, "longitude": lon},
    }


def _trip_item(db: Session, trip: Trip) -> AdminEntityItemData:
    user = db.get(User, trip.user_id)
    day_count = _count_rows(db, select(TripDay).where(TripDay.trip_id == trip.id))
    poi_count = _count_rows(db, select(TripPoi).where(TripPoi.trip_id == trip.id))
    subtitle = f"{trip.destination} / {trip.start_date.isoformat()}~{trip.end_date.isoformat()}"
    return {
        "entity": "trips",
        "id": str(trip.id),
        "label": trip.title,
        "subtitle": subtitle,
        "status": "deleted" if trip.deleted_at else trip.planning_status,
        "fields": {
            "id": str(trip.id),
            "user_id": str(trip.user_id),
            "leader_id": str(trip.leader_id) if trip.leader_id else None,
            "owner_email": user.email if user else None,
            "title": trip.title,
            "name": trip.name,
            "destination": trip.destination,
            "start_date": trip.start_date.isoformat(),
            "end_date": trip.end_date.isoformat(),
            "fuel_types": _json_value(trip.fuel_types or []),
            "planning_status": trip.planning_status,
            "day_count": day_count,
            "poi_count": poi_count,
            "deleted_at": _iso(trip.deleted_at),
            "created_at": _iso(trip.created_at),
            "updated_at": _iso(trip.updated_at),
        },
        "links": [
            _link("users", "owner", user.email if user else "소유자", id=str(trip.user_id)),
            _link("pois", "trip_pois", f"POI {poi_count}건", query={"trip_id": str(trip.id)}),
        ],
        "map": None,
    }


def _poi_item(db: Session, poi: TripPoi) -> AdminEntityItemData:
    feature = db.get(Feature, poi.feature_id) if poi.feature_id else None
    trip = db.get(Trip, poi.trip_id)
    label = _poi_label(poi, feature)
    map_point = _feature_map_point(db, feature) if feature else None
    return {
        "entity": "pois",
        "id": str(poi.id),
        "label": label,
        "subtitle": f"{trip.title if trip else poi.trip_id} / day {poi.day_index}",
        "status": "broken" if poi.feature_link_broken_at else "active",
        "fields": {
            "id": str(poi.id),
            "trip_id": str(poi.trip_id),
            "day_index": poi.day_index,
            "sort_order": poi.sort_order,
            "feature_id": poi.feature_id,
            "feature_name": feature.name if feature else None,
            "feature_link_broken_at": _iso(poi.feature_link_broken_at),
            "snapshot": _json_value(poi.snapshot),
            "custom_marker_color": poi.custom_marker_color,
            "custom_marker_icon": poi.custom_marker_icon,
            "added_by_user_id": str(poi.added_by_user_id),
            "memo": poi.memo,
            "budget": _decimal_text(poi.budget),
            "actual_spent": _decimal_text(poi.actual_spent),
            "currency": poi.currency,
            "user_url": poi.user_url,
            "version": poi.version,
            "created_at": _iso(poi.created_at),
            "updated_at": _iso(poi.updated_at),
        },
        "links": [
            _link("trips", "trip", trip.title if trip else "여행", id=str(poi.trip_id)),
            _link("users", "added_by", "추가 사용자", id=str(poi.added_by_user_id)),
            *(
                [_link("features", "feature", feature.name, id=feature.feature_id)]
                if feature is not None
                else []
            ),
        ],
        "map": map_point,
    }


def _related_group(
    db: Session,
    *,
    label: str,
    entity: AdminEntityKind,
    query: dict[str, str],
) -> AdminEntityRelatedGroupData:
    search = query.get("search")
    filters = {key: value for key, value in query.items() if key != "search"}
    related = list_admin_entities(
        db,
        entity=entity,
        page=1,
        limit=5,
        search=search,
        filters=filters,
    )
    return {
        "label": label,
        "entity": entity,
        "query": query,
        "count": related["total"],
        "sample": related["items"],
    }


def _get_user_or_raise(db: Session, item_id: str) -> User:
    user = db.get(User, _parse_uuid(item_id, "id"))
    if user is None:
        raise AdminEntityNotFoundError("사용자를 찾을 수 없다.")
    return user


def _get_feature_or_raise(db: Session, item_id: str) -> Feature:
    feature = db.get(Feature, item_id)
    if feature is None:
        raise AdminEntityNotFoundError("feature를 찾을 수 없다.")
    return feature


def _get_trip_or_raise(db: Session, item_id: str) -> Trip:
    trip = db.get(Trip, _parse_uuid(item_id, "id"))
    if trip is None:
        raise AdminEntityNotFoundError("여행을 찾을 수 없다.")
    return trip


def _get_poi_or_raise(db: Session, item_id: str) -> TripPoi:
    poi = db.get(TripPoi, _parse_uuid(item_id, "id"))
    if poi is None:
        raise AdminEntityNotFoundError("POI를 찾을 수 없다.")
    return poi


def _get_trip_day(db: Session, trip_id: UUID, day_index: int) -> TripDay | None:
    return db.scalar(
        select(TripDay).where(TripDay.trip_id == trip_id, TripDay.day_index == day_index)
    )


def _ensure_trip_days(db: Session, trip: Trip) -> None:
    existing = {
        day.day_index for day in db.scalars(select(TripDay).where(TripDay.trip_id == trip.id)).all()
    }
    day_count = (trip.end_date - trip.start_date).days + 1
    for offset in range(day_count):
        day_index = offset + 1
        if day_index in existing:
            continue
        db.add(
            TripDay(
                trip_id=trip.id,
                day_index=day_index,
                date=trip.start_date + timedelta(days=offset),
            )
        )
    db.flush()


def _validate_trip_span(start_date: date, end_date: date) -> None:
    if (end_date - start_date).days + 1 > MAX_TRIP_DAY_SPAN:
        raise AdminEntityValidationError("관리자 테스트 여행은 최대 31일까지 만들 수 있다.")


def _next_poi_sort_order(db: Session, trip_id: UUID, day_index: int) -> str:
    current_count = _count_rows(
        db,
        select(TripPoi).where(TripPoi.trip_id == trip_id, TripPoi.day_index == day_index),
    )
    return f"{current_count + 1:04d}"


def _feature_coordinates(db: Session, feature_id: str) -> tuple[float, float]:
    row = db.execute(
        select(func.ST_X(Feature.coord), func.ST_Y(Feature.coord)).where(
            Feature.feature_id == feature_id
        )
    ).one()
    return (float(row[0]), float(row[1]))


def _feature_map_point(db: Session, feature: Feature) -> AdminEntityMapPointData:
    lon, lat = _feature_coordinates(db, feature.feature_id)
    return {"latitude": lat, "longitude": lon}


def _point(lon: Decimal, lat: Decimal) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def _poi_snapshot(values: Mapping[str, JsonValue], feature: Feature | None) -> dict[str, JsonValue]:
    if "snapshot" in values:
        return _json_object(values, "snapshot")
    if feature is None:
        return {}
    return {
        "name": feature.name,
        "feature_id": feature.feature_id,
        "address_road": feature.address_road,
        "address_jibun": feature.address_jibun,
        "category": feature.category,
    }


def _poi_label(poi: TripPoi, feature: Feature | None) -> str:
    if feature is not None:
        return feature.name
    name = poi.snapshot.get("name")
    if isinstance(name, str) and name:
        return name
    title = poi.snapshot.get("title")
    if isinstance(title, str) and title:
        return title
    return f"POI {poi.sort_order}"


def _link(
    entity: AdminEntityKind,
    relation: str,
    label: str,
    *,
    id: str | None = None,
    query: dict[str, str] | None = None,
) -> AdminEntityLinkData:
    return {
        "entity": entity,
        "relation": relation,
        "id": id,
        "label": label,
        "query": query or {},
    }


def _count_query(db: Session, query: Any) -> int:
    count_value = db.scalar(select(func.count()).select_from(query.subquery()))
    return int(count_value or 0)


def _count_rows(db: Session, query: Any) -> int:
    count_value = db.scalar(select(func.count()).select_from(query.subquery()))
    return int(count_value or 0)


def _iso(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _json_value(value: object) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return str(value)


def _require_str(values: Mapping[str, JsonValue], key: str, *, max_length: int) -> str:
    value = _optional_str(values, key, max_length=max_length)
    if value is None or not value:
        raise AdminEntityValidationError(f"{key} 값이 필요하다.")
    return value


def _optional_str(values: Mapping[str, JsonValue], key: str, *, max_length: int) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise AdminEntityValidationError(f"{key} 값은 {max_length}자 이하여야 한다.")
    return normalized


def _optional_bool(values: Mapping[str, JsonValue], key: str) -> bool | None:
    value = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    raise AdminEntityValidationError(f"{key} 값은 boolean이어야 한다.")


def _require_uuid(values: Mapping[str, JsonValue], key: str) -> UUID:
    value = _optional_uuid(values, key)
    if value is None:
        raise AdminEntityValidationError(f"{key} 값이 필요하다.")
    return value


def _optional_uuid(values: Mapping[str, JsonValue], key: str) -> UUID | None:
    value = _optional_str(values, key, max_length=80)
    if value is None:
        return None
    return _parse_uuid(value, key)


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise AdminEntityValidationError(f"{field_name} 값은 UUID여야 한다.") from exc


def _require_date(values: Mapping[str, JsonValue], key: str) -> date:
    value = _optional_str(values, key, max_length=10)
    if value is None:
        raise AdminEntityValidationError(f"{key} 값이 필요하다.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AdminEntityValidationError(f"{key} 값은 YYYY-MM-DD 형식이어야 한다.") from exc


def _require_decimal(values: Mapping[str, JsonValue], key: str) -> Decimal:
    value = _optional_decimal(values, key)
    if value is None:
        raise AdminEntityValidationError(f"{key} 값이 필요하다.")
    return value


def _optional_decimal(values: Mapping[str, JsonValue], key: str) -> Decimal | None:
    value = values.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise AdminEntityValidationError(f"{key} 값은 숫자여야 한다.")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise AdminEntityValidationError(f"{key} 값은 숫자여야 한다.") from exc


def _require_int(values: Mapping[str, JsonValue], key: str) -> int:
    value = _optional_int(values, key)
    if value is None:
        raise AdminEntityValidationError(f"{key} 값이 필요하다.")
    return value


def _optional_int(values: Mapping[str, JsonValue], key: str) -> int | None:
    value = values.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise AdminEntityValidationError(f"{key} 값은 정수여야 한다.")
    try:
        parsed = int(str(value))
    except ValueError as exc:
        raise AdminEntityValidationError(f"{key} 값은 정수여야 한다.") from exc
    return parsed


def _json_object(values: Mapping[str, JsonValue], key: str) -> dict[str, JsonValue]:
    value = values.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AdminEntityValidationError(f"{key} 값은 JSON 객체여야 한다.")
    return {str(item_key): _json_value(item_value) for item_key, item_value in value.items()}


def _json_object_or_none(values: Mapping[str, JsonValue], key: str) -> dict[str, JsonValue] | None:
    if values.get(key) is None:
        return None
    return _json_object(values, key)


def _json_object_list(values: Mapping[str, JsonValue], key: str) -> list[dict[str, JsonValue]]:
    value = values.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdminEntityValidationError(f"{key} 값은 JSON 배열이어야 한다.")
    result: list[dict[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, dict):
            raise AdminEntityValidationError(f"{key} 값은 JSON 객체 배열이어야 한다.")
        result.append(
            {str(item_key): _json_value(item_value) for item_key, item_value in item.items()}
        )
    return result


def _string_list(values: Mapping[str, JsonValue], key: str) -> list[str] | None:
    value = values.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise AdminEntityValidationError(f"{key} 값은 문자열 배열이어야 한다.")


def _enum_value(value: str, allowed: set[str], field_name: str) -> str:
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise AdminEntityValidationError(f"{field_name} 값은 {allowed_values} 중 하나여야 한다.")
    return value
