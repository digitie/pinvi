"""Admin trip/day/POI copy, move, delete orchestration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import CuratedPlanAttachment
from app.models.comment import TripComment
from app.models.poi import TripDayPoi
from app.models.share_link import TripShareLink
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User
from app.schemas.admin import AdminOperationImpact, AdminOperationPolicyOption, AdminOperationResult
from app.services import lexorank
from app.services.trip import TripCopyError, copy_trip


class AdminTripOperationError(Exception):
    code = "INTERNAL_ERROR"


class AdminTripOperationNotFoundError(AdminTripOperationError):
    code = "RESOURCE_NOT_FOUND"


class AdminTripOperationConflictError(AdminTripOperationError):
    code = "OPERATION_CONFLICT"


@dataclass(frozen=True)
class OperationState:
    before: dict[str, object]
    after: dict[str, object]
    result: AdminOperationResult


async def trip_impact(db: AsyncSession, *, trip_id: uuid.UUID) -> AdminOperationImpact:
    trip = await _get_trip(db, trip_id=trip_id)
    counts = await _trip_counts(db, trip_id=trip.trip_id)
    return AdminOperationImpact(
        target_type="trip",
        target_id=trip.trip_id,
        trip_id=trip.trip_id,
        counts=counts,
        policy_options={
            "child_policy": [
                _option("keep", "하위 항목 유지", True),
                _option("delete", "하위 항목 함께 삭제", True),
                _option(
                    "move",
                    "다른 여행으로 이동",
                    False,
                    "여행계획 전체 이동은 owner 이전으로 처리합니다.",
                ),
                _option(
                    "orphan",
                    "orphan으로 유지",
                    False,
                    "trip_id FK 때문에 orphan 여행 하위 항목은 허용하지 않습니다.",
                ),
            ]
        },
        warnings=["여행계획 삭제는 soft delete이며, RustFS object는 즉시 삭제하지 않습니다."],
    )


async def day_impact(
    db: AsyncSession, *, trip_id: uuid.UUID, day_index: int
) -> AdminOperationImpact:
    await _get_day(db, trip_id=trip_id, day_index=day_index)
    counts = await _day_counts(db, trip_id=trip_id, day_index=day_index)
    policy = [
        _option("move", "대상 여행/날짜로 이동", True),
        _option("delete", "함께 삭제", True),
        _option("orphan", "orphan으로 유지", False, "POI와 날짜 첨부는 day FK가 필수입니다."),
    ]
    return AdminOperationImpact(
        target_type="day",
        trip_id=trip_id,
        day_index=day_index,
        counts=counts,
        policy_options={
            "poi_policy": policy,
            "attachment_policy": policy,
            "comment_policy": [
                _option("move", "대상 날짜로 이동", True),
                _option("delete", "함께 삭제", True),
                _option(
                    "orphan",
                    "orphan으로 유지",
                    False,
                    "day comment는 화면/조회 정합성을 위해 orphan을 허용하지 않습니다.",
                ),
            ],
        },
    )


async def poi_impact(db: AsyncSession, *, poi_id: uuid.UUID) -> AdminOperationImpact:
    poi = await _get_poi(db, poi_id=poi_id)
    counts = await _poi_counts(db, poi_id=poi.attachment_id)
    policy = [
        _option("move", "대상 날짜로 이동", True),
        _option("delete", "함께 삭제", True),
        _option("orphan", "orphan으로 유지", False, "POI 첨부와 댓글은 POI 문맥이 필요합니다."),
    ]
    return AdminOperationImpact(
        target_type="poi",
        target_id=poi.attachment_id,
        trip_id=poi.trip_id,
        day_index=poi.day_index,
        counts=counts,
        policy_options={"attachment_policy": policy, "comment_policy": policy},
    )


async def copy_admin_trip(
    db: AsyncSession,
    *,
    source_trip_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    owner_user_id: uuid.UUID | None,
    title: str | None,
    scope: Literal["all", "day", "range"],
    day_index: int | None,
    start_day_index: int | None,
    end_day_index: int | None,
    date_shift_days: int,
    target_trip_id: uuid.UUID | None,
) -> OperationState:
    source = await _get_trip(db, trip_id=source_trip_id)
    actor_user_id = owner_user_id or source.owner_user_id
    if target_trip_id is not None:
        target = await _get_trip(db, trip_id=target_trip_id)
        actor_user_id = target.owner_user_id
    else:
        await _get_user(db, user_id=actor_user_id)

    before: dict[str, object] = {
        "source": _trip_state(source),
        "target_trip_id": str(target_trip_id) if target_trip_id else None,
    }
    try:
        target_trip, created, day_count, poi_count, attachment_count = await copy_trip(
            db,
            source_trip=source,
            actor_user_id=actor_user_id,
            title=title,
            scope=scope,
            day_index=day_index,
            start_day_index=start_day_index,
            end_day_index=end_day_index,
            date_shift_days=date_shift_days,
            target_trip_id=target_trip_id,
            commit=False,
        )
    except TripCopyError as exc:
        raise AdminTripOperationConflictError(str(exc)) from exc
    await db.flush()
    result = AdminOperationResult(
        target_type="trip",
        action="copy",
        source_trip_id=source.trip_id,
        target_trip_id=target_trip.trip_id,
        target_id=target_trip.trip_id,
        affected={
            "created_trip": 1 if created else 0,
            "days": day_count,
            "pois": poi_count,
            "attachments": attachment_count,
        },
    )
    return OperationState(before=before, after={"target": _trip_state(target_trip)}, result=result)


async def move_admin_trip_owner(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> OperationState:
    trip = await _get_trip(db, trip_id=trip_id)
    owner = await _get_user(db, user_id=owner_user_id)
    if trip.owner_user_id == owner.user_id:
        raise AdminTripOperationConflictError("이미 해당 사용자가 소유자입니다.")
    before = _trip_state(trip)
    trip.owner_user_id = owner.user_id
    trip.version += 1
    await db.flush()
    result = AdminOperationResult(
        target_type="trip",
        action="move",
        source_trip_id=trip.trip_id,
        target_trip_id=trip.trip_id,
        target_id=trip.trip_id,
        affected={"owner_changed": 1},
    )
    return OperationState(before=before, after=_trip_state(trip), result=result)


async def delete_admin_trip(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    child_policy: Literal["keep", "delete"],
) -> OperationState:
    trip = await _get_trip(db, trip_id=trip_id)
    before = {"trip": _trip_state(trip), "counts": await _trip_counts(db, trip_id=trip_id)}
    affected: dict[str, int] = {}
    now = datetime.now(UTC)
    if child_policy == "delete":
        affected.update(await _soft_delete_trip_children(db, trip_id=trip_id, now=now))
    trip.status = "archived"
    trip.deleted_at = now
    trip.version += 1
    affected["trips"] = 1
    await db.flush()
    result = AdminOperationResult(
        target_type="trip",
        action="delete",
        source_trip_id=trip.trip_id,
        target_id=trip.trip_id,
        affected=affected,
    )
    return OperationState(before=before, after={"trip": _trip_state(trip)}, result=result)


async def copy_admin_day(
    db: AsyncSession,
    *,
    source_trip_id: uuid.UUID,
    day_index: int,
    target_trip_id: uuid.UUID,
    target_day_index: int,
    admin_user_id: uuid.UUID,
    include_pois: bool,
    include_attachments: bool,
) -> OperationState:
    source_day = await _get_day(db, trip_id=source_trip_id, day_index=day_index)
    target_trip = await _get_trip(db, trip_id=target_trip_id)
    if await _day_exists(db, trip_id=target_trip_id, day_index=target_day_index):
        raise AdminTripOperationConflictError("대상 day_index가 이미 존재합니다.")
    target_day = TripDay(
        trip_id=target_trip_id,
        day_index=target_day_index,
        date=source_day.date,
        title=source_day.title,
        note=source_day.note,
    )
    db.add(target_day)
    await db.flush()
    affected = {"days": 1, "pois": 0, "attachments": 0}
    poi_id_map: dict[uuid.UUID, uuid.UUID] = {}
    if include_pois:
        pois = await _list_day_pois(db, trip_id=source_trip_id, day_index=day_index)
        last_sort = await _max_sort_order(db, trip_id=target_trip_id, day_index=target_day_index)
        for poi in pois:
            last_sort = lexorank.between(last_sort, None)
            copied = _clone_poi(
                poi,
                trip_id=target_trip_id,
                day_index=target_day_index,
                sort_order=last_sort,
                added_by_user_id=admin_user_id,
            )
            db.add(copied)
            await db.flush()
            poi_id_map[poi.attachment_id] = copied.attachment_id
            affected["pois"] += 1
    if include_attachments:
        affected["attachments"] = await _copy_day_and_poi_attachments(
            db,
            source_trip_id=source_trip_id,
            source_day_index=day_index,
            target_trip_id=target_trip_id,
            target_day_index=target_day_index,
            poi_id_map=poi_id_map,
            uploaded_by_user_id=admin_user_id,
        )
    target_trip.version += 1
    result = AdminOperationResult(
        target_type="day",
        action="copy",
        source_trip_id=source_trip_id,
        target_trip_id=target_trip_id,
        day_index=target_day_index,
        affected=affected,
    )
    return OperationState(
        before={"source": _day_state(source_day)},
        after={"target": _day_state(target_day)},
        result=result,
    )


async def move_admin_day(
    db: AsyncSession,
    *,
    source_trip_id: uuid.UUID,
    day_index: int,
    target_trip_id: uuid.UUID,
    target_day_index: int,
    poi_policy: Literal["move", "delete"],
    attachment_policy: Literal["move", "delete"],
    comment_policy: Literal["move", "delete"],
) -> OperationState:
    source_day = await _get_day(db, trip_id=source_trip_id, day_index=day_index)
    if source_trip_id == target_trip_id and day_index == target_day_index:
        raise AdminTripOperationConflictError("같은 날짜로 이동할 수 없습니다.")
    target_trip = await _get_trip(db, trip_id=target_trip_id)
    target_day = await _ensure_day_like(
        db,
        source_day=source_day,
        target_trip_id=target_trip_id,
        target_day_index=target_day_index,
    )
    now = datetime.now(UTC)
    affected = {"days": 1, "pois": 0, "attachments": 0, "comments": 0}
    pois = await _list_day_pois(db, trip_id=source_trip_id, day_index=day_index)
    source_poi_ids = [poi.attachment_id for poi in pois]
    if poi_policy == "move":
        last_sort = await _max_sort_order(db, trip_id=target_trip_id, day_index=target_day_index)
        for poi in pois:
            last_sort = lexorank.between(last_sort, None)
            poi.trip_id = target_trip_id
            poi.day_index = target_day_index
            poi.sort_order = last_sort
            poi.version += 1
            affected["pois"] += 1
    else:
        for poi in pois:
            affected["attachments"] += await _move_or_delete_poi_attachments(
                db,
                poi_id=poi.attachment_id,
                policy="delete",
                now=now,
            )
            poi.deleted_at = now
            affected["pois"] += 1
    affected["attachments"] += await _move_or_delete_day_attachments(
        db,
        source_trip_id=source_trip_id,
        source_day_index=day_index,
        target_trip_id=target_trip_id,
        target_day_index=target_day_index,
        policy=attachment_policy,
        now=now,
    )
    affected["comments"] = await _move_or_delete_day_comments(
        db,
        source_trip_id=source_trip_id,
        source_day_index=day_index,
        target_trip_id=target_trip_id,
        target_day_index=target_day_index,
        policy=comment_policy,
        now=now,
        source_poi_ids=source_poi_ids,
    )
    await db.delete(source_day)
    target_trip.version += 1
    if source_trip_id != target_trip_id:
        source_trip = await _get_trip(db, trip_id=source_trip_id)
        source_trip.version += 1
    result = AdminOperationResult(
        target_type="day",
        action="move",
        source_trip_id=source_trip_id,
        target_trip_id=target_trip_id,
        day_index=target_day_index,
        affected=affected,
    )
    return OperationState(
        before={"source": _day_state(source_day)},
        after={"target": _day_state(target_day)},
        result=result,
    )


async def delete_admin_day(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_index: int,
) -> OperationState:
    day = await _get_day(db, trip_id=trip_id, day_index=day_index)
    before = {
        "day": _day_state(day),
        "counts": await _day_counts(db, trip_id=trip_id, day_index=day_index),
    }
    now = datetime.now(UTC)
    pois = await _list_day_pois(db, trip_id=trip_id, day_index=day_index)
    poi_attachment_count = 0
    for poi in pois:
        poi_attachment_count += await _move_or_delete_poi_attachments(
            db,
            poi_id=poi.attachment_id,
            policy="delete",
            now=now,
        )
        poi.deleted_at = now
    attachments = await _move_or_delete_day_attachments(
        db,
        source_trip_id=trip_id,
        source_day_index=day_index,
        target_trip_id=trip_id,
        target_day_index=day_index,
        policy="delete",
        now=now,
    )
    comments = await _move_or_delete_day_comments(
        db,
        source_trip_id=trip_id,
        source_day_index=day_index,
        target_trip_id=trip_id,
        target_day_index=day_index,
        policy="delete",
        now=now,
        source_poi_ids=[poi.attachment_id for poi in pois],
    )
    await db.delete(day)
    trip = await _get_trip(db, trip_id=trip_id)
    trip.version += 1
    result = AdminOperationResult(
        target_type="day",
        action="delete",
        source_trip_id=trip_id,
        day_index=day_index,
        affected={
            "days": 1,
            "pois": len(pois),
            "attachments": attachments + poi_attachment_count,
            "comments": comments,
        },
    )
    return OperationState(before=before, after={"deleted": True}, result=result)


async def copy_admin_poi(
    db: AsyncSession,
    *,
    poi_id: uuid.UUID,
    target_trip_id: uuid.UUID,
    target_day_index: int,
    admin_user_id: uuid.UUID,
    include_attachments: bool,
) -> OperationState:
    poi = await _get_poi(db, poi_id=poi_id)
    target_trip = await _get_trip(db, trip_id=target_trip_id)
    await _ensure_day(db, trip_id=target_trip_id, day_index=target_day_index)
    sort_order = lexorank.between(
        await _max_sort_order(db, trip_id=target_trip_id, day_index=target_day_index), None
    )
    copied = _clone_poi(
        poi,
        trip_id=target_trip_id,
        day_index=target_day_index,
        sort_order=sort_order,
        added_by_user_id=admin_user_id,
    )
    db.add(copied)
    await db.flush()
    attachment_count = 0
    if include_attachments:
        attachment_count = await _copy_poi_attachments(
            db,
            source_poi_id=poi.attachment_id,
            target_poi_id=copied.attachment_id,
            uploaded_by_user_id=admin_user_id,
        )
    target_trip.version += 1
    result = AdminOperationResult(
        target_type="poi",
        action="copy",
        source_trip_id=poi.trip_id,
        target_trip_id=target_trip_id,
        target_id=copied.attachment_id,
        day_index=target_day_index,
        affected={"pois": 1, "attachments": attachment_count},
    )
    return OperationState(
        before={"source": _poi_state(poi)}, after={"target": _poi_state(copied)}, result=result
    )


async def move_admin_poi(
    db: AsyncSession,
    *,
    poi_id: uuid.UUID,
    target_trip_id: uuid.UUID,
    target_day_index: int,
    attachment_policy: Literal["move", "delete"],
    comment_policy: Literal["move", "delete"],
) -> OperationState:
    poi = await _get_poi(db, poi_id=poi_id)
    if poi.trip_id == target_trip_id and poi.day_index == target_day_index:
        raise AdminTripOperationConflictError("같은 날짜로 이동할 수 없습니다.")
    target_trip = await _get_trip(db, trip_id=target_trip_id)
    await _ensure_day(db, trip_id=target_trip_id, day_index=target_day_index)
    before = _poi_state(poi)
    now = datetime.now(UTC)
    attachments = await _move_or_delete_poi_attachments(
        db,
        poi_id=poi.attachment_id,
        policy=attachment_policy,
        now=now,
    )
    comments = await _move_or_delete_poi_comments(
        db,
        poi_id=poi.attachment_id,
        target_trip_id=target_trip_id,
        target_day_index=target_day_index,
        policy=comment_policy,
        now=now,
    )
    source_trip_id = poi.trip_id
    poi.trip_id = target_trip_id
    poi.day_index = target_day_index
    poi.sort_order = lexorank.between(
        await _max_sort_order(db, trip_id=target_trip_id, day_index=target_day_index), None
    )
    poi.version += 1
    target_trip.version += 1
    if source_trip_id != target_trip_id:
        source_trip = await _get_trip(db, trip_id=source_trip_id)
        source_trip.version += 1
    result = AdminOperationResult(
        target_type="poi",
        action="move",
        source_trip_id=source_trip_id,
        target_trip_id=target_trip_id,
        target_id=poi.attachment_id,
        day_index=target_day_index,
        affected={"pois": 1, "attachments": attachments, "comments": comments},
    )
    return OperationState(before=before, after=_poi_state(poi), result=result)


async def delete_admin_poi(
    db: AsyncSession,
    *,
    poi_id: uuid.UUID,
) -> OperationState:
    poi = await _get_poi(db, poi_id=poi_id)
    before = {"poi": _poi_state(poi), "counts": await _poi_counts(db, poi_id=poi_id)}
    now = datetime.now(UTC)
    attachments = await _move_or_delete_poi_attachments(db, poi_id=poi_id, policy="delete", now=now)
    comments = await _move_or_delete_poi_comments(
        db,
        poi_id=poi_id,
        target_trip_id=poi.trip_id,
        target_day_index=poi.day_index,
        policy="delete",
        now=now,
    )
    poi.deleted_at = now
    poi.version += 1
    trip = await _get_trip(db, trip_id=poi.trip_id)
    trip.version += 1
    result = AdminOperationResult(
        target_type="poi",
        action="delete",
        source_trip_id=poi.trip_id,
        target_id=poi.attachment_id,
        day_index=poi.day_index,
        affected={"pois": 1, "attachments": attachments, "comments": comments},
    )
    return OperationState(before=before, after={"poi": _poi_state(poi)}, result=result)


def _option(
    value: Literal["move", "delete", "keep", "orphan"],
    label: str,
    allowed: bool,
    reason: str | None = None,
) -> AdminOperationPolicyOption:
    return AdminOperationPolicyOption(value=value, label=label, allowed=allowed, reason=reason)


async def _get_trip(db: AsyncSession, *, trip_id: uuid.UUID) -> Trip:
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)))
    if trip is None:
        raise AdminTripOperationNotFoundError("여행을 찾을 수 없습니다.")
    return trip


async def _get_user(db: AsyncSession, *, user_id: uuid.UUID) -> User:
    user = await db.scalar(
        select(User).where(
            User.user_id == user_id, User.deleted_at.is_(None), User.is_active.is_(True)
        )
    )
    if user is None:
        raise AdminTripOperationNotFoundError("사용자를 찾을 수 없습니다.")
    return user


async def _get_day(db: AsyncSession, *, trip_id: uuid.UUID, day_index: int) -> TripDay:
    day = await db.scalar(
        select(TripDay).where(TripDay.trip_id == trip_id, TripDay.day_index == day_index)
    )
    if day is None:
        raise AdminTripOperationNotFoundError("날짜를 찾을 수 없습니다.")
    return day


async def _get_poi(db: AsyncSession, *, poi_id: uuid.UUID) -> TripDayPoi:
    poi = await db.scalar(
        select(TripDayPoi).where(
            TripDayPoi.attachment_id == poi_id, TripDayPoi.deleted_at.is_(None)
        )
    )
    if poi is None:
        raise AdminTripOperationNotFoundError("POI를 찾을 수 없습니다.")
    return poi


async def _ensure_day(db: AsyncSession, *, trip_id: uuid.UUID, day_index: int) -> TripDay:
    day = await db.scalar(
        select(TripDay).where(TripDay.trip_id == trip_id, TripDay.day_index == day_index)
    )
    if day is not None:
        return day
    day = TripDay(trip_id=trip_id, day_index=day_index)
    db.add(day)
    await db.flush()
    return day


async def _ensure_day_like(
    db: AsyncSession,
    *,
    source_day: TripDay,
    target_trip_id: uuid.UUID,
    target_day_index: int,
) -> TripDay:
    day = await db.scalar(
        select(TripDay).where(
            TripDay.trip_id == target_trip_id, TripDay.day_index == target_day_index
        )
    )
    if day is not None:
        return day
    day = TripDay(
        trip_id=target_trip_id,
        day_index=target_day_index,
        date=source_day.date,
        title=source_day.title,
        note=source_day.note,
    )
    db.add(day)
    await db.flush()
    return day


async def _day_exists(db: AsyncSession, *, trip_id: uuid.UUID, day_index: int) -> bool:
    found = await db.scalar(
        select(TripDay.day_index).where(TripDay.trip_id == trip_id, TripDay.day_index == day_index)
    )
    return found is not None


async def _trip_counts(db: AsyncSession, *, trip_id: uuid.UUID) -> dict[str, int]:
    poi_ids = select(TripDayPoi.attachment_id).where(TripDayPoi.trip_id == trip_id)
    return {
        "days": await _count(
            db, select(func.count(TripDay.day_index)).where(TripDay.trip_id == trip_id)
        ),
        "pois": await _count(
            db,
            select(func.count(TripDayPoi.attachment_id)).where(
                TripDayPoi.trip_id == trip_id, TripDayPoi.deleted_at.is_(None)
            ),
        ),
        "attachments": await _count(
            db,
            select(func.count(CuratedPlanAttachment.attachment_id)).where(
                CuratedPlanAttachment.deleted_at.is_(None),
                or_(
                    CuratedPlanAttachment.trip_id == trip_id,
                    CuratedPlanAttachment.trip_poi_id.in_(poi_ids),
                ),
            ),
        ),
        "comments": await _count(
            db,
            select(func.count(TripComment.comment_id)).where(
                TripComment.trip_id == trip_id, TripComment.deleted_at.is_(None)
            ),
        ),
        "share_links": await _count(
            db, select(func.count(TripShareLink.share_id)).where(TripShareLink.trip_id == trip_id)
        ),
    }


async def _day_counts(db: AsyncSession, *, trip_id: uuid.UUID, day_index: int) -> dict[str, int]:
    poi_ids = select(TripDayPoi.attachment_id).where(
        TripDayPoi.trip_id == trip_id, TripDayPoi.day_index == day_index
    )
    return {
        "pois": await _count(
            db,
            select(func.count(TripDayPoi.attachment_id)).where(
                TripDayPoi.trip_id == trip_id,
                TripDayPoi.day_index == day_index,
                TripDayPoi.deleted_at.is_(None),
            ),
        ),
        "attachments": await _count(
            db,
            select(func.count(CuratedPlanAttachment.attachment_id)).where(
                CuratedPlanAttachment.deleted_at.is_(None),
                or_(
                    (CuratedPlanAttachment.trip_id == trip_id)
                    & (CuratedPlanAttachment.trip_day_index == day_index),
                    CuratedPlanAttachment.trip_poi_id.in_(poi_ids),
                ),
            ),
        ),
        "comments": await _count(
            db,
            select(func.count(TripComment.comment_id)).where(
                TripComment.trip_id == trip_id,
                TripComment.deleted_at.is_(None),
                or_(TripComment.day_index == day_index, TripComment.target_id.in_(poi_ids)),
            ),
        ),
    }


async def _poi_counts(db: AsyncSession, *, poi_id: uuid.UUID) -> dict[str, int]:
    return {
        "attachments": await _count(
            db,
            select(func.count(CuratedPlanAttachment.attachment_id)).where(
                CuratedPlanAttachment.trip_poi_id == poi_id,
                CuratedPlanAttachment.deleted_at.is_(None),
            ),
        ),
        "comments": await _count(
            db,
            select(func.count(TripComment.comment_id)).where(
                TripComment.target_id == poi_id,
                TripComment.deleted_at.is_(None),
            ),
        ),
    }


async def _count(db: AsyncSession, stmt: Any) -> int:
    return int(await db.scalar(stmt) or 0)


async def _list_day_pois(
    db: AsyncSession, *, trip_id: uuid.UUID, day_index: int
) -> list[TripDayPoi]:
    result = await db.execute(
        select(TripDayPoi)
        .where(
            TripDayPoi.trip_id == trip_id,
            TripDayPoi.day_index == day_index,
            TripDayPoi.deleted_at.is_(None),
        )
        .order_by(TripDayPoi.sort_order.asc(), TripDayPoi.attachment_id.asc())
    )
    return list(result.scalars())


async def _max_sort_order(db: AsyncSession, *, trip_id: uuid.UUID, day_index: int) -> str | None:
    result = await db.execute(
        select(TripDayPoi.sort_order)
        .where(
            TripDayPoi.trip_id == trip_id,
            TripDayPoi.day_index == day_index,
            TripDayPoi.deleted_at.is_(None),
        )
        .order_by(TripDayPoi.sort_order.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _clone_poi(
    poi: TripDayPoi,
    *,
    trip_id: uuid.UUID,
    day_index: int,
    sort_order: str,
    added_by_user_id: uuid.UUID,
) -> TripDayPoi:
    return TripDayPoi(
        trip_id=trip_id,
        day_index=day_index,
        sort_order=sort_order,
        feature_id=poi.feature_id,
        feature_link_broken_at=poi.feature_link_broken_at,
        feature_snapshot=poi.feature_snapshot,
        custom_marker_color=poi.custom_marker_color,
        custom_marker_icon=poi.custom_marker_icon,
        planned_arrival_at=poi.planned_arrival_at,
        planned_departure_at=poi.planned_departure_at,
        user_note=poi.user_note,
        budget_amount=poi.budget_amount,
        actual_amount=poi.actual_amount,
        currency=poi.currency,
        user_url=poi.user_url,
        added_by_user_id=added_by_user_id,
    )


async def _copy_day_and_poi_attachments(
    db: AsyncSession,
    *,
    source_trip_id: uuid.UUID,
    source_day_index: int,
    target_trip_id: uuid.UUID,
    target_day_index: int,
    poi_id_map: dict[uuid.UUID, uuid.UUID],
    uploaded_by_user_id: uuid.UUID,
) -> int:
    copied = 0
    target_filters: list[Any] = [
        (CuratedPlanAttachment.trip_id == source_trip_id)
        & (CuratedPlanAttachment.trip_day_index == source_day_index)
    ]
    if poi_id_map:
        target_filters.append(CuratedPlanAttachment.trip_poi_id.in_(list(poi_id_map.keys())))
    filters = [CuratedPlanAttachment.deleted_at.is_(None), or_(*target_filters)]
    result = await db.execute(select(CuratedPlanAttachment).where(*filters))
    for attachment in result.scalars():
        target_poi_id = (
            poi_id_map[attachment.trip_poi_id]
            if attachment.trip_poi_id is not None and attachment.trip_poi_id in poi_id_map
            else None
        )
        db.add(
            CuratedPlanAttachment(
                trip_id=target_trip_id if target_poi_id is None else None,
                trip_day_index=target_day_index if target_poi_id is None else None,
                trip_poi_id=target_poi_id,
                source_attachment_id=attachment.attachment_id,
                bucket=attachment.bucket,
                storage_key=attachment.storage_key,
                original_filename=attachment.original_filename,
                content_type=attachment.content_type,
                byte_size=attachment.byte_size,
                public_url=attachment.public_url,
                checksum_sha256=attachment.checksum_sha256,
                role=attachment.role,
                description=attachment.description,
                sort_order=attachment.sort_order,
                uploaded_by_user_id=uploaded_by_user_id,
            )
        )
        copied += 1
    return copied


async def _copy_poi_attachments(
    db: AsyncSession,
    *,
    source_poi_id: uuid.UUID,
    target_poi_id: uuid.UUID,
    uploaded_by_user_id: uuid.UUID,
) -> int:
    copied = 0
    result = await db.execute(
        select(CuratedPlanAttachment).where(
            CuratedPlanAttachment.trip_poi_id == source_poi_id,
            CuratedPlanAttachment.deleted_at.is_(None),
        )
    )
    for attachment in result.scalars():
        db.add(
            CuratedPlanAttachment(
                trip_poi_id=target_poi_id,
                source_attachment_id=attachment.attachment_id,
                bucket=attachment.bucket,
                storage_key=attachment.storage_key,
                original_filename=attachment.original_filename,
                content_type=attachment.content_type,
                byte_size=attachment.byte_size,
                public_url=attachment.public_url,
                checksum_sha256=attachment.checksum_sha256,
                role=attachment.role,
                description=attachment.description,
                sort_order=attachment.sort_order,
                uploaded_by_user_id=uploaded_by_user_id,
            )
        )
        copied += 1
    return copied


async def _move_or_delete_day_attachments(
    db: AsyncSession,
    *,
    source_trip_id: uuid.UUID,
    source_day_index: int,
    target_trip_id: uuid.UUID,
    target_day_index: int,
    policy: Literal["move", "delete"],
    now: datetime,
) -> int:
    result = await db.execute(
        select(CuratedPlanAttachment).where(
            CuratedPlanAttachment.trip_id == source_trip_id,
            CuratedPlanAttachment.trip_day_index == source_day_index,
            CuratedPlanAttachment.deleted_at.is_(None),
        )
    )
    count = 0
    for attachment in result.scalars():
        if policy == "move":
            attachment.trip_id = target_trip_id
            attachment.trip_day_index = target_day_index
        else:
            attachment.deleted_at = now
        count += 1
    return count


async def _move_or_delete_poi_attachments(
    db: AsyncSession,
    *,
    poi_id: uuid.UUID,
    policy: Literal["move", "delete"],
    now: datetime,
) -> int:
    result = await db.execute(
        select(CuratedPlanAttachment).where(
            CuratedPlanAttachment.trip_poi_id == poi_id,
            CuratedPlanAttachment.deleted_at.is_(None),
        )
    )
    count = 0
    for attachment in result.scalars():
        if policy == "delete":
            attachment.deleted_at = now
        count += 1
    return count


async def _move_or_delete_day_comments(
    db: AsyncSession,
    *,
    source_trip_id: uuid.UUID,
    source_day_index: int,
    target_trip_id: uuid.UUID,
    target_day_index: int,
    policy: Literal["move", "delete"],
    now: datetime,
    source_poi_ids: list[uuid.UUID],
) -> int:
    target_filters: list[Any] = [TripComment.day_index == source_day_index]
    if source_poi_ids:
        target_filters.append(TripComment.target_id.in_(source_poi_ids))
    result = await db.execute(
        select(TripComment).where(
            TripComment.trip_id == source_trip_id,
            TripComment.deleted_at.is_(None),
            or_(*target_filters),
        )
    )
    count = 0
    for comment in result.scalars():
        if policy == "move":
            comment.trip_id = target_trip_id
            if comment.day_index == source_day_index:
                comment.day_index = target_day_index
        else:
            comment.deleted_at = now
        count += 1
    return count


async def _move_or_delete_poi_comments(
    db: AsyncSession,
    *,
    poi_id: uuid.UUID,
    target_trip_id: uuid.UUID,
    target_day_index: int,
    policy: Literal["move", "delete"],
    now: datetime,
) -> int:
    result = await db.execute(
        select(TripComment).where(
            TripComment.target_id == poi_id,
            TripComment.deleted_at.is_(None),
        )
    )
    count = 0
    for comment in result.scalars():
        if policy == "move":
            comment.trip_id = target_trip_id
            comment.day_index = target_day_index
        else:
            comment.deleted_at = now
        count += 1
    return count


async def _soft_delete_trip_children(
    db: AsyncSession, *, trip_id: uuid.UUID, now: datetime
) -> dict[str, int]:
    affected = {"pois": 0, "attachments": 0, "comments": 0, "share_links": 0}
    pois = await db.execute(
        select(TripDayPoi).where(TripDayPoi.trip_id == trip_id, TripDayPoi.deleted_at.is_(None))
    )
    for poi in pois.scalars():
        poi.deleted_at = now
        affected["pois"] += 1
    poi_ids = select(TripDayPoi.attachment_id).where(TripDayPoi.trip_id == trip_id)
    attachments = await db.execute(
        select(CuratedPlanAttachment).where(
            CuratedPlanAttachment.deleted_at.is_(None),
            or_(
                CuratedPlanAttachment.trip_id == trip_id,
                CuratedPlanAttachment.trip_poi_id.in_(poi_ids),
            ),
        )
    )
    for attachment in attachments.scalars():
        attachment.deleted_at = now
        affected["attachments"] += 1
    comments = await db.execute(
        select(TripComment).where(TripComment.trip_id == trip_id, TripComment.deleted_at.is_(None))
    )
    for comment in comments.scalars():
        comment.deleted_at = now
        affected["comments"] += 1
    shares = await db.execute(
        select(TripShareLink).where(
            TripShareLink.trip_id == trip_id,
            TripShareLink.revoked_at.is_(None),
        )
    )
    for share in shares.scalars():
        share.revoked_at = now
        affected["share_links"] += 1
    return affected


def _trip_state(trip: Trip) -> dict[str, object]:
    return {
        "trip_id": str(trip.trip_id),
        "owner_user_id": str(trip.owner_user_id),
        "title": trip.title,
        "status": trip.status,
        "version": trip.version,
        "deleted_at": trip.deleted_at.isoformat() if trip.deleted_at else None,
    }


def _day_state(day: TripDay) -> dict[str, object]:
    return {
        "trip_id": str(day.trip_id),
        "day_index": day.day_index,
        "date": day.date.isoformat() if day.date else None,
        "title": day.title,
    }


def _poi_state(poi: TripDayPoi) -> dict[str, object]:
    return {
        "poi_id": str(poi.attachment_id),
        "trip_id": str(poi.trip_id),
        "day_index": poi.day_index,
        "sort_order": poi.sort_order,
        "feature_id": poi.feature_id,
        "version": poi.version,
        "deleted_at": poi.deleted_at.isoformat() if poi.deleted_at else None,
    }
