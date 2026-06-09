"""Read-only MCP tool dispatch."""

from __future__ import annotations

import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from datetime import date, datetime
from json import JSONDecodeError, dumps, loads
from typing import Any, Literal

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.krtour_map import KrtourMapClient
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User
from app.schemas.mcp import McpToolDescriptor
from app.services.admin_users import mask_email
from app.services.trip import (
    TripBucket,
    TripListCursor,
    TripListSort,
    TripNotFoundError,
    TripPermissionError,
    TripStatus,
    TripVisibility,
    get_trip_for_user,
    list_trips_for_owner,
)
from app.services.trip_view_builder import build_trip_view

_TRIP_CURSOR_VERSION = 1

TOOL_DESCRIPTORS: list[McpToolDescriptor] = [
    McpToolDescriptor(
        name="list_trips",
        description="사용자 본인의 trip 목록",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["draft", "planned", "in_progress", "completed", "archived"],
                },
                "bucket": {
                    "type": "string",
                    "enum": ["future", "past", "all"],
                    "default": "future",
                },
                "q": {"type": "string", "minLength": 2, "maxLength": 120},
                "visibility": {"type": "string", "enum": ["private", "unlisted", "public"]},
                "date_from": {"type": "string", "format": "date"},
                "date_to": {"type": "string", "format": "date"},
                "sort": {
                    "type": "string",
                    "enum": ["-updated_at", "start_date", "-start_date", "title"],
                    "default": "-updated_at",
                },
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                "cursor": {"type": "string"},
            },
        },
    ),
    McpToolDescriptor(
        name="get_trip",
        description="trip + day + POI 트리 전체",
        inputSchema={
            "type": "object",
            "properties": {"trip_id": {"type": "string", "format": "uuid"}},
            "required": ["trip_id"],
        },
    ),
    McpToolDescriptor(
        name="list_pois",
        description="trip 또는 특정 day의 POI 목록",
        inputSchema={
            "type": "object",
            "properties": {
                "trip_id": {"type": "string", "format": "uuid"},
                "day_index": {"type": "integer", "minimum": 1},
            },
            "required": ["trip_id"],
        },
    ),
    McpToolDescriptor(
        name="search_features",
        description="krtour-map OpenAPI HTTP feature 검색",
        inputSchema={
            "type": "object",
            "properties": {
                "q": {"type": "string", "minLength": 1, "maxLength": 200},
                "kind": {
                    "type": "string",
                    "enum": ["place", "event", "notice", "price", "weather", "route", "area"],
                },
                "bounds": {"type": "string"},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 50},
            },
            "required": ["q"],
        },
    ),
    McpToolDescriptor(
        name="get_user_profile",
        description="본인 프로필",
        inputSchema={"type": "object", "properties": {}},
    ),
]


class ListTripsArgs(BaseModel):
    bucket: TripBucket = "future"
    q: str | None = Field(default=None, min_length=2, max_length=120)
    status: TripStatus | None = None
    visibility: TripVisibility | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort: TripListSort = "-updated_at"
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=512)


class TripIdArgs(BaseModel):
    trip_id: uuid.UUID


class ListPoisArgs(TripIdArgs):
    day_index: int | None = Field(default=None, ge=1)


class SearchFeaturesArgs(BaseModel):
    q: str = Field(min_length=1, max_length=200)
    kind: Literal["place", "event", "notice", "price", "weather", "route", "area"] | None = None
    bounds: str | None = None
    limit: int = Field(default=20, ge=1, le=50)


async def call_tool(
    *,
    name: str,
    arguments: dict[str, Any],
    user_id: uuid.UUID,
    db: AsyncSession,
    request: Request,
) -> dict[str, Any]:
    try:
        if name == "list_trips":
            return await _list_trips(
                db=db, user_id=user_id, args=ListTripsArgs.model_validate(arguments)
            )
        if name == "get_trip":
            return await _get_trip(
                db=db, user_id=user_id, args=TripIdArgs.model_validate(arguments)
            )
        if name == "list_pois":
            return await _list_pois(
                db=db, user_id=user_id, args=ListPoisArgs.model_validate(arguments)
            )
        if name == "search_features":
            return await _search_features(
                request=request,
                args=SearchFeaturesArgs.model_validate(arguments),
            )
        if name == "get_user_profile":
            return await _get_user_profile(db=db, user_id=user_id)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "tool arguments가 올바르지 않습니다.",
                "details": {"errors": exc.errors()},
            },
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "RESOURCE_NOT_FOUND", "message": "MCP tool을 찾을 수 없습니다."},
    )


async def _list_trips(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    args: ListTripsArgs,
) -> dict[str, Any]:
    if args.date_from is not None and args.date_to is not None and args.date_to < args.date_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": "date_to는 date_from 이후여야 합니다."},
        )
    trip_cursor = _decode_trip_cursor(args.cursor)
    trips, has_more = await list_trips_for_owner(
        db,
        user_id=user_id,
        bucket=args.bucket,
        q=args.q,
        status_filter=args.status,
        visibility_filter=args.visibility,
        date_from=args.date_from,
        date_to=args.date_to,
        sort=args.sort,
        limit=args.limit,
        cursor=trip_cursor,
    )
    day_counts, poi_counts = await _trip_counts(db, [trip.trip_id for trip in trips])
    return {
        "items": [
            {
                "trip_id": str(trip.trip_id),
                "title": trip.title,
                "status": trip.status,
                "start_date": trip.start_date.isoformat() if trip.start_date else None,
                "end_date": trip.end_date.isoformat() if trip.end_date else None,
                "day_count": day_counts.get(trip.trip_id, 0),
                "poi_count": poi_counts.get(trip.trip_id, 0),
                "updated_at": trip.updated_at.isoformat(),
            }
            for trip in trips
        ],
        "next_cursor": _next_trip_cursor(args.sort, trip_cursor, args.limit, trips, has_more),
        "has_more": has_more,
    }


async def _get_trip(*, db: AsyncSession, user_id: uuid.UUID, args: TripIdArgs) -> dict[str, Any]:
    try:
        trip = await get_trip_for_user(db, trip_id=args.trip_id, user_id=user_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        raise _trip_http(exc) from exc
    return await build_trip_view(db, trip=trip, krtour_client=None)


async def _list_pois(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    args: ListPoisArgs,
) -> dict[str, Any]:
    try:
        await get_trip_for_user(db, trip_id=args.trip_id, user_id=user_id)
    except (TripNotFoundError, TripPermissionError) as exc:
        raise _trip_http(exc) from exc
    filters: list[Any] = [TripDayPoi.trip_id == args.trip_id, TripDayPoi.deleted_at.is_(None)]
    if args.day_index is not None:
        filters.append(TripDayPoi.day_index == args.day_index)
    result = await db.execute(
        select(TripDayPoi).where(*filters).order_by(TripDayPoi.day_index, TripDayPoi.sort_order)
    )
    return {
        "items": [
            {
                "poi_id": str(poi.attachment_id),
                "trip_id": str(poi.trip_id),
                "day_index": poi.day_index,
                "feature_id": poi.feature_id,
                "feature_snapshot": poi.feature_snapshot,
                "sort_order": poi.sort_order,
                "user_note": poi.user_note,
                "planned_arrival_at": poi.planned_arrival_at.isoformat()
                if poi.planned_arrival_at
                else None,
                "planned_departure_at": poi.planned_departure_at.isoformat()
                if poi.planned_departure_at
                else None,
            }
            for poi in result.scalars()
        ]
    }


async def _search_features(*, request: Request, args: SearchFeaturesArgs) -> dict[str, Any]:
    client = getattr(request.app.state, "krtour_map_client", None)
    if not isinstance(client, KrtourMapClient):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": "지도 feature 서비스가 일시적으로 사용 불가합니다.",
            },
        )
    kinds = [args.kind] if args.kind else None
    return await client.search_features(
        q=args.q,
        bbox=args.bounds,
        kinds=kinds,
        limit=args.limit,
    )


async def _get_user_profile(*, db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."},
        )
    return {
        "user_id": str(user.user_id),
        "email": mask_email(user.email),
        "nickname": user.nickname,
        "status": user.status,
        "roles": user.roles,
        "avatar_kind": user.avatar_kind,
        "created_at": user.created_at.isoformat(),
    }


async def _trip_counts(
    db: AsyncSession, trip_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    if not trip_ids:
        return {}, {}
    day_result = await db.execute(
        select(TripDay.trip_id, func.count(TripDay.day_index))
        .where(TripDay.trip_id.in_(trip_ids))
        .group_by(TripDay.trip_id)
    )
    poi_result = await db.execute(
        select(TripDayPoi.trip_id, func.count(TripDayPoi.attachment_id))
        .where(TripDayPoi.trip_id.in_(trip_ids), TripDayPoi.deleted_at.is_(None))
        .group_by(TripDayPoi.trip_id)
    )
    return (
        {row[0]: int(row[1]) for row in day_result.all()},
        {row[0]: int(row[1]) for row in poi_result.all()},
    )


def _trip_http(exc: TripNotFoundError | TripPermissionError) -> HTTPException:
    if isinstance(exc, TripNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": exc.code, "message": str(exc)},
    )


def _next_trip_cursor(
    sort: TripListSort,
    trip_cursor: TripListCursor,
    limit: int,
    trips: list[Trip],
    has_more: bool,
) -> str | None:
    if not has_more or not trips:
        return None
    if sort == "-updated_at":
        last = trips[-1]
        return _encode_keyset_trip_cursor(last.updated_at, last.trip_id)
    return _encode_offset_trip_cursor(trip_cursor.offset + limit)


def _encode_offset_trip_cursor(offset: int) -> str:
    raw = dumps({"v": _TRIP_CURSOR_VERSION, "off": offset}, separators=(",", ":")).encode()
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _encode_keyset_trip_cursor(updated_at: datetime, trip_id: uuid.UUID) -> str:
    raw = dumps(
        {"v": _TRIP_CURSOR_VERSION, "ua": updated_at.isoformat(), "id": str(trip_id)},
        separators=(",", ":"),
    ).encode()
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_trip_cursor(cursor: str | None) -> TripListCursor:
    if cursor is None:
        return TripListCursor()
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = loads(urlsafe_b64decode(f"{cursor}{padding}"))
    except (BinasciiError, JSONDecodeError, ValueError, TypeError) as exc:
        raise _invalid_trip_cursor() from exc
    if not isinstance(payload, dict) or payload.get("v") != _TRIP_CURSOR_VERSION:
        raise _invalid_trip_cursor()
    if "ua" in payload or "id" in payload:
        try:
            updated_at = datetime.fromisoformat(str(payload["ua"]))
            trip_id = uuid.UUID(str(payload["id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise _invalid_trip_cursor() from exc
        return TripListCursor(updated_at=updated_at, trip_id=trip_id)
    offset = payload.get("off")
    if not isinstance(offset, int) or offset < 0:
        raise _invalid_trip_cursor()
    return TripListCursor(offset=offset)


def _invalid_trip_cursor() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "VALIDATION_ERROR", "message": "cursor 형식이 올바르지 않습니다."},
    )
