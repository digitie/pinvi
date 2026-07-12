"""Trip 도메인 — CRUD + 동반자 + 공유 토큰. `docs/api/trips.md`."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from math import asin, cos, radians, sin, sqrt
from typing import Any, Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_opaque_token
from app.models.attachment import CuratedPlanAttachment
from app.models.comment import TripComment
from app.models.companion import TripCompanion
from app.models.poi import TripDayPoi
from app.models.share_link import TripShareLink
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User
from app.services import lexorank
from app.services.email_service import enqueue_trip_invite_email
from app.services.hash_chain import sha256_hex
from app.services.rustfs_storage import InvalidStorageRefError, validate_attachment_storage_ref
from app.services.storage_policy import AttachmentQuotaError, assert_attachment_quota


class TripError(Exception):
    code: str = "INTERNAL_ERROR"


class TripNotFoundError(TripError):
    code = "RESOURCE_NOT_FOUND"


class TripVersionConflictError(TripError):
    code = "VERSION_CONFLICT"


class TripPermissionError(TripError):
    code = "PERMISSION_DENIED"


class TripCompanionConflictError(TripError):
    code = "COMPANION_ALREADY_EXISTS"


class TripCommentNotFoundError(TripError):
    code = "RESOURCE_NOT_FOUND"


class TripDayConflictError(TripError):
    code = "TRIP_DAY_CONFLICT"


class TripDayValidationError(TripError):
    code = "VALIDATION_ERROR"


class TripDayNotFoundError(TripError):
    code = "RESOURCE_NOT_FOUND"


class TripCopyError(TripError):
    code = "TRIP_COPY_ERROR"


class TripAttachmentNotFoundError(TripError):
    code = "RESOURCE_NOT_FOUND"


class TripAttachmentLimitError(TripError):
    code = "ATTACHMENT_LIMIT_EXCEEDED"


class TripAttachmentStorageRefError(TripError):
    code = "INVALID_ATTACHMENT_STORAGE_REF"


class TripAttachmentQuotaError(TripError):
    code = "ATTACHMENT_QUOTA_EXCEEDED"


class TripOptimizeError(TripError):
    code = "TRIP_OPTIMIZE_ERROR"


_SHARE_LAST_USED_THROTTLE = timedelta(minutes=1)

TripBucket = Literal["future", "past", "all"]
TripListSort = Literal["-updated_at", "start_date", "-start_date", "title"]
TripStatus = Literal["draft", "planned", "in_progress", "completed", "archived"]
TripVisibility = Literal["private", "unlisted", "public"]
TripCopyScope = Literal["all", "day", "range"]


async def create_trip(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    title: str,
    description: str | None,
    region_hint: str | None,
    primary_region_code: str | None,
    start_date: date | None,
    end_date: date | None,
    visibility: str,
) -> Trip:
    trip = Trip(
        owner_user_id=owner_user_id,
        title=title,
        description=description,
        region_hint=region_hint,
        primary_region_code=primary_region_code,
        primary_region_source="manual" if primary_region_code is not None else None,
        start_date=start_date,
        end_date=end_date,
        visibility=visibility,
    )
    db.add(trip)
    await db.flush()
    if start_date is not None and end_date is not None:
        for offset in range((end_date - start_date).days + 1):
            db.add(
                TripDay(
                    trip_id=trip.trip_id,
                    day_index=offset + 1,
                    date=start_date + timedelta(days=offset),
                )
            )
    await db.commit()
    await db.refresh(trip)
    return trip


async def get_trip_owned_by_user(
    db: AsyncSession, *, trip_id: uuid.UUID, user_id: uuid.UUID
) -> Trip:
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)))
    if trip is None:
        raise TripNotFoundError("여행을 찾을 수 없습니다.")
    if trip.owner_user_id != user_id:
        raise TripPermissionError("여행 소유자만 수행할 수 있습니다.")
    return trip


async def get_trip_for_user(db: AsyncSession, *, trip_id: uuid.UUID, user_id: uuid.UUID) -> Trip:
    trip, _ = await get_trip_access(db, trip_id=trip_id, user_id=user_id)
    return trip


# 역할 권한: owner = 소유자, co_owner/editor = 편집 가능, viewer = 읽기 전용.
TripRole = Literal["owner", "co_owner", "editor", "viewer"]
_WRITE_ROLES: frozenset[str] = frozenset({"owner", "co_owner", "editor"})
_MANAGEMENT_ROLES: frozenset[str] = frozenset({"owner", "co_owner"})


async def get_trip_access(
    db: AsyncSession, *, trip_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Trip, TripRole]:
    """여행 + 호출자의 유효 역할을 반환. 멤버가 아니면 PermissionError."""
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)))
    if trip is None:
        raise TripNotFoundError("여행을 찾을 수 없습니다.")
    if trip.owner_user_id == user_id:
        return trip, "owner"
    role = await _companion_role(db, trip_id, user_id)
    if role not in {"co_owner", "editor", "viewer"}:
        raise TripPermissionError("이 여행에 대한 권한이 없습니다.")
    return trip, role  # type: ignore[return-value]


async def get_trip_for_user_write(
    db: AsyncSession, *, trip_id: uuid.UUID, user_id: uuid.UUID
) -> Trip:
    """편집(쓰기) 권한 검증 — owner/co_owner/editor만 허용, viewer는 거부."""
    trip, role = await get_trip_access(db, trip_id=trip_id, user_id=user_id)
    if role not in _WRITE_ROLES:
        raise TripPermissionError("이 여행을 편집할 권한이 없습니다.")
    return trip


def can_manage_trip(role: TripRole) -> bool:
    """owner/co_owner만 동반자 PII·공유 링크 등 관리 정보를 볼 수 있다."""
    return role in _MANAGEMENT_ROLES


@dataclass(frozen=True)
class TripListCursor:
    """페이지네이션 커서. 기본 정렬(-updated_at)은 keyset, 그 외는 offset."""

    offset: int = 0
    updated_at: datetime | None = None
    trip_id: uuid.UUID | None = None


def _escape_like(value: str) -> str:
    # ilike 와일드카드(% _)와 escape(\)를 리터럴로 취급 — 검색어 의미 변질 방지.
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_trips_for_owner(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    bucket: TripBucket = "future",
    q: str | None = None,
    status_filter: TripStatus | None = None,
    visibility_filter: TripVisibility | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: TripListSort = "-updated_at",
    limit: int = 20,
    cursor: TripListCursor | None = None,
) -> tuple[list[Trip], bool]:
    cursor = cursor or TripListCursor()
    today = datetime.now(UTC).date()
    filters = [Trip.owner_user_id == user_id, Trip.deleted_at.is_(None)]
    if bucket == "future":
        filters.append(or_(Trip.end_date.is_(None), Trip.end_date >= today))
    elif bucket == "past":
        filters.append(Trip.end_date < today)
    normalized_q = q.strip() if q is not None else None
    if normalized_q:
        needle = f"%{_escape_like(normalized_q)}%"
        filters.append(
            or_(
                Trip.title.ilike(needle, escape="\\"),
                Trip.description.ilike(needle, escape="\\"),
                Trip.region_hint.ilike(needle, escape="\\"),
            )
        )
    if status_filter is not None:
        filters.append(Trip.status == status_filter)
    if visibility_filter is not None:
        filters.append(Trip.visibility == visibility_filter)
    if date_from is not None:
        filters.append(Trip.end_date >= date_from)
    if date_to is not None:
        filters.append(Trip.start_date <= date_to)

    # 기본 -updated_at 정렬은 keyset(updated_at, trip_id)으로 — 동시 쓰기 시 page skip/중복 회피.
    use_keyset = sort == "-updated_at"
    if use_keyset and cursor.updated_at is not None and cursor.trip_id is not None:
        filters.append(
            or_(
                Trip.updated_at < cursor.updated_at,
                and_(Trip.updated_at == cursor.updated_at, Trip.trip_id > cursor.trip_id),
            )
        )
    stmt = select(Trip).where(*filters).order_by(*_trip_list_ordering(sort)).limit(limit + 1)
    if not use_keyset:
        stmt = stmt.offset(cursor.offset)
    result = await db.execute(stmt)
    rows = list(result.scalars())
    return rows[:limit], len(rows) > limit


def _trip_list_ordering(sort: TripListSort) -> tuple[Any, ...]:
    if sort == "start_date":
        return Trip.start_date.is_(None).asc(), Trip.start_date.asc(), Trip.trip_id.asc()
    if sort == "-start_date":
        return Trip.start_date.is_(None).asc(), Trip.start_date.desc(), Trip.trip_id.asc()
    if sort == "title":
        return func.lower(Trip.title).asc(), Trip.trip_id.asc()
    return Trip.updated_at.desc(), Trip.trip_id.asc()


async def update_trip(
    db: AsyncSession,
    *,
    trip: Trip,
    expected_version: int,
    patch: dict[str, Any],
) -> Trip:
    if trip.version != expected_version:
        raise TripVersionConflictError("동시 편집 충돌 — 다시 불러와 주세요.")
    if "primary_region_code" in patch:
        primary_region_code = patch.pop("primary_region_code")
        trip.primary_region_code = primary_region_code
        trip.primary_region_source = "manual" if primary_region_code is not None else None
    for key, value in patch.items():
        if value is not None or key in {
            "description",
            "region_hint",
            "cover_attachment_id",
        }:
            setattr(trip, key, value)
    trip.version += 1
    await db.commit()
    await db.refresh(trip)
    return trip


async def delete_or_transfer_trip(
    db: AsyncSession,
    *,
    trip: Trip,
    actor_user_id: uuid.UUID,
    mode: str,
    new_owner_user_id: uuid.UUID | None,
) -> Trip:
    if mode == "soft_delete":
        trip.status = "archived"
        trip.deleted_at = datetime.now(UTC)
        trip.version += 1
        await db.commit()
        await db.refresh(trip)
        return trip

    if new_owner_user_id is None:
        raise TripCopyError("새 owner가 필요합니다.")
    new_owner = await db.scalar(
        select(User).where(User.user_id == new_owner_user_id, User.deleted_at.is_(None))
    )
    if new_owner is None:
        raise TripNotFoundError("새 owner 사용자를 찾을 수 없습니다.")
    if new_owner.user_id == trip.owner_user_id:
        raise TripCopyError("현재 owner와 동일한 사용자에게 이전할 수 없습니다.")

    new_owner_companion = await db.scalar(
        select(TripCompanion).where(
            TripCompanion.trip_id == trip.trip_id,
            TripCompanion.user_id == new_owner.user_id,
        )
    )
    if new_owner_companion is not None:
        await db.delete(new_owner_companion)

    former_owner_companion = await db.scalar(
        select(TripCompanion).where(
            TripCompanion.trip_id == trip.trip_id,
            TripCompanion.user_id == actor_user_id,
        )
    )
    if former_owner_companion is None:
        now = datetime.now(UTC)
        db.add(
            TripCompanion(
                trip_id=trip.trip_id,
                user_id=actor_user_id,
                role="co_owner",
                invited_at=now,
                joined_at=now,
            )
        )
    else:
        former_owner_companion.role = "co_owner"
        former_owner_companion.joined_at = former_owner_companion.joined_at or datetime.now(UTC)

    trip.owner_user_id = new_owner.user_id
    trip.version += 1
    await db.commit()
    await db.refresh(trip)
    return trip


async def create_trip_day(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_index: int,
    date_value: date | None,
    title: str | None,
    note: str | None,
) -> TripDay:
    day = TripDay(trip_id=trip_id, day_index=day_index, date=date_value, title=title, note=note)
    db.add(day)
    await _bump_trip_version(db, trip_id=trip_id)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise TripDayConflictError("이미 존재하는 day_index입니다.") from exc
    await db.refresh(day)
    return day


def trip_day_limit(start_date: date | None, end_date: date | None) -> int | None:
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days + 1


def default_trip_day_date(start_date: date | None, day_index: int) -> date | None:
    if start_date is None:
        return None
    return start_date + timedelta(days=day_index - 1)


async def validate_trip_day_payload(
    db: AsyncSession,
    *,
    trip: Trip,
    day_index: int,
    date_value: date | None,
    exclude_day_index: int | None = None,
) -> None:
    limit = trip_day_limit(trip.start_date, trip.end_date)
    if limit is not None and day_index > limit:
        raise TripDayValidationError(f"여행 기간은 최대 {limit}일입니다.")

    if date_value is None:
        if trip.start_date is not None and trip.end_date is not None:
            raise TripDayValidationError("여행 기간이 있는 경우 일자 날짜가 필요합니다.")
        return
    if trip.start_date is not None and date_value < trip.start_date:
        raise TripDayValidationError("일자 날짜는 여행 시작일 이후여야 합니다.")
    if trip.end_date is not None and date_value > trip.end_date:
        raise TripDayValidationError("일자 날짜는 여행 종료일 이전이어야 합니다.")

    filters = [TripDay.trip_id == trip.trip_id, TripDay.date == date_value]
    if exclude_day_index is not None:
        filters.append(TripDay.day_index != exclude_day_index)
    existing = await db.scalar(select(TripDay.day_index).where(*filters).limit(1))
    if existing is not None:
        raise TripDayConflictError("이미 같은 날짜 일자가 있습니다.")


async def next_available_trip_day_index(db: AsyncSession, *, trip: Trip) -> int:
    result = await db.execute(
        select(TripDay.day_index)
        .where(TripDay.trip_id == trip.trip_id)
        .order_by(TripDay.day_index.asc())
    )
    used = set(result.scalars())
    limit = trip_day_limit(trip.start_date, trip.end_date)
    max_candidate = limit if limit is not None else (max(used) if used else 0) + 1
    for day_index in range(1, max_candidate + 1):
        if day_index not in used:
            return day_index
    if limit is not None:
        raise TripDayValidationError(f"여행 기간 {limit}일의 일자가 모두 만들어졌습니다.")
    return max_candidate + 1


async def get_trip_day(db: AsyncSession, *, trip_id: uuid.UUID, day_index: int) -> TripDay:
    day = await db.scalar(
        select(TripDay).where(TripDay.trip_id == trip_id, TripDay.day_index == day_index)
    )
    if day is None:
        raise TripDayNotFoundError("여행 day를 찾을 수 없습니다.")
    return day


async def update_trip_day(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_index: int,
    expected_version: int,
    patch: dict[str, Any],
) -> TripDay:
    day = await get_trip_day(db, trip_id=trip_id, day_index=day_index)
    if day.version != expected_version:
        raise TripVersionConflictError("동시 편집 충돌 — 다시 불러와 주세요.")
    for key, value in patch.items():
        setattr(day, key, value)
    day.version += 1
    await _bump_trip_version(db, trip_id=trip_id)
    await db.commit()
    await db.refresh(day)
    return day


async def delete_trip_day(
    db: AsyncSession, *, trip_id: uuid.UUID, day_index: int, expected_version: int
) -> None:
    day = await get_trip_day(db, trip_id=trip_id, day_index=day_index)
    if day.version != expected_version:
        raise TripVersionConflictError("동시 편집 충돌 — 다시 불러와 주세요.")
    await db.delete(day)
    await _bump_trip_version(db, trip_id=trip_id)
    await db.commit()


async def copy_trip(
    db: AsyncSession,
    *,
    source_trip: Trip,
    actor_user_id: uuid.UUID,
    title: str | None,
    scope: TripCopyScope,
    day_index: int | None,
    start_day_index: int | None,
    end_day_index: int | None,
    date_shift_days: int,
    target_trip_id: uuid.UUID | None,
    commit: bool = True,
) -> tuple[Trip, bool, int, int, int]:
    days = await _select_copy_days(
        db,
        trip_id=source_trip.trip_id,
        scope=scope,
        day_index=day_index,
        start_day_index=start_day_index,
        end_day_index=end_day_index,
    )
    source_day_indexes = None if scope == "all" else [day.day_index for day in days]

    created_trip = False
    if target_trip_id is None:
        target_trip = Trip(
            owner_user_id=actor_user_id,
            title=title or f"{source_trip.title} copy",
            description=source_trip.description,
            region_hint=source_trip.region_hint,
            primary_region_code=source_trip.primary_region_code,
            primary_region_source=source_trip.primary_region_source,
            start_date=_shift_date(source_trip.start_date, date_shift_days),
            end_date=_shift_date(source_trip.end_date, date_shift_days),
            visibility="private",
            status="draft",
        )
        db.add(target_trip)
        await db.flush()
        created_trip = True
    else:
        existing_target_trip = await db.scalar(
            select(Trip).where(Trip.trip_id == target_trip_id, Trip.deleted_at.is_(None))
        )
        if existing_target_trip is None:
            raise TripNotFoundError("대상 여행을 찾을 수 없습니다.")
        if existing_target_trip.owner_user_id != actor_user_id:
            raise TripPermissionError("대상 여행 소유자만 합칠 수 있습니다.")
        target_trip = existing_target_trip

    copied_day_count = 0
    for source_day in days:
        target_day = await db.scalar(
            select(TripDay).where(
                TripDay.trip_id == target_trip.trip_id,
                TripDay.day_index == source_day.day_index,
            )
        )
        if target_day is None:
            db.add(
                TripDay(
                    trip_id=target_trip.trip_id,
                    day_index=source_day.day_index,
                    date=_shift_date(source_day.date, date_shift_days),
                    title=source_day.title,
                    note=source_day.note,
                )
            )
            copied_day_count += 1

    source_pois = await _list_copy_pois(
        db,
        trip_id=source_trip.trip_id,
        day_indexes=source_day_indexes,
    )
    last_sort: dict[int, str | None] = {}
    poi_id_map: dict[uuid.UUID, uuid.UUID] = {}
    copied_poi_count = 0
    for source_poi in source_pois:
        if not created_trip and source_poi.day_index not in last_sort:
            last_sort[source_poi.day_index] = await _max_sort_order(
                db,
                target_trip.trip_id,
                source_poi.day_index,
            )
        sort_order = source_poi.sort_order
        if not created_trip:
            sort_order = lexorank.between(last_sort[source_poi.day_index], None)
            last_sort[source_poi.day_index] = sort_order
        copied = TripDayPoi(
            trip_id=target_trip.trip_id,
            day_index=source_poi.day_index,
            sort_order=sort_order,
            feature_id=source_poi.feature_id,
            feature_link_broken_at=source_poi.feature_link_broken_at,
            feature_snapshot=source_poi.feature_snapshot,
            custom_marker_color=source_poi.custom_marker_color,
            custom_marker_icon=source_poi.custom_marker_icon,
            planned_arrival_at=_shift_datetime(source_poi.planned_arrival_at, date_shift_days),
            planned_departure_at=_shift_datetime(source_poi.planned_departure_at, date_shift_days),
            user_note=source_poi.user_note,
            budget_amount=source_poi.budget_amount,
            actual_amount=source_poi.actual_amount,
            currency=source_poi.currency,
            user_url=source_poi.user_url,
            added_by_user_id=actor_user_id,
        )
        db.add(copied)
        await db.flush()
        poi_id_map[source_poi.attachment_id] = copied.attachment_id
        copied_poi_count += 1

    copied_attachment_count = await _copy_trip_attachments(
        db,
        source_trip_id=source_trip.trip_id,
        target_trip_id=target_trip.trip_id,
        source_day_indexes=source_day_indexes,
        poi_id_map=poi_id_map,
        actor_user_id=actor_user_id,
        include_trip_level=scope == "all",
    )
    target_trip.version += 1
    if commit:
        await db.commit()
        await db.refresh(target_trip)
    else:
        await db.flush()
    return target_trip, created_trip, copied_day_count, copied_poi_count, copied_attachment_count


async def get_trip_for_share_token(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    token: str,
) -> tuple[Trip, TripShareLink]:
    share = await db.scalar(
        select(TripShareLink).where(
            TripShareLink.trip_id == trip_id,
            TripShareLink.token_hash == sha256_hex(token),
            TripShareLink.revoked_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    if share is None or (share.expires_at is not None and share.expires_at <= now):
        raise TripNotFoundError("공유 토큰을 찾을 수 없습니다.")
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)))
    if trip is None:
        raise TripNotFoundError("여행을 찾을 수 없습니다.")
    # last_used_at 갱신은 best-effort throttle — 매 요청 write/commit(증폭 DoS) 회피.
    last_used = share.last_used_at
    if last_used is None or (now - last_used) >= _SHARE_LAST_USED_THROTTLE:
        share.last_used_at = now
        await db.commit()
        await db.refresh(share)
    return trip, share


async def list_attachments(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID | None = None,
    trip_day_index: int | None = None,
    trip_poi_id: uuid.UUID | None = None,
) -> list[CuratedPlanAttachment]:
    filters: list[Any] = [CuratedPlanAttachment.deleted_at.is_(None)]
    if trip_id is not None:
        filters.append(CuratedPlanAttachment.trip_id == trip_id)
        if trip_day_index is None and trip_poi_id is None:
            filters.append(CuratedPlanAttachment.trip_day_index.is_(None))
    if trip_day_index is not None:
        filters.append(CuratedPlanAttachment.trip_day_index == trip_day_index)
    if trip_poi_id is not None:
        filters.append(CuratedPlanAttachment.trip_poi_id == trip_poi_id)
    result = await db.execute(
        select(CuratedPlanAttachment)
        .where(*filters)
        .order_by(CuratedPlanAttachment.sort_order.asc(), CuratedPlanAttachment.created_at.asc())
    )
    return list(result.scalars())


async def _count_attachments(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID | None,
    trip_day_index: int | None,
    trip_poi_id: uuid.UUID | None,
) -> int:
    filters: list[Any] = [CuratedPlanAttachment.deleted_at.is_(None)]
    if trip_id is not None:
        filters.append(CuratedPlanAttachment.trip_id == trip_id)
        if trip_day_index is None and trip_poi_id is None:
            filters.append(CuratedPlanAttachment.trip_day_index.is_(None))
    if trip_day_index is not None:
        filters.append(CuratedPlanAttachment.trip_day_index == trip_day_index)
    if trip_poi_id is not None:
        filters.append(CuratedPlanAttachment.trip_poi_id == trip_poi_id)
    return int(
        await db.scalar(select(func.count(CuratedPlanAttachment.attachment_id)).where(*filters))
        or 0
    )


async def create_attachment(
    db: AsyncSession,
    *,
    uploaded_by_user_id: uuid.UUID,
    trip_id: uuid.UUID | None,
    trip_day_index: int | None = None,
    trip_poi_id: uuid.UUID | None = None,
    quota_trip_id: uuid.UUID | None = None,
    payload: dict[str, Any],
) -> CuratedPlanAttachment:
    # 대상(trip 또는 POI)당 첨부 개수 상한 — 남용/저장소 비대 방지(T-105).
    limit = settings.pinvi_max_attachments_per_target
    if (
        await _count_attachments(
            db,
            trip_id=trip_id,
            trip_day_index=trip_day_index,
            trip_poi_id=trip_poi_id,
        )
        >= limit
    ):
        raise TripAttachmentLimitError(f"첨부는 대상당 최대 {limit}개까지 등록할 수 있습니다.")
    _validate_attachment_storage_ref(
        uploaded_by_user_id=uploaded_by_user_id,
        trip_id=trip_id,
        trip_day_index=trip_day_index,
        trip_poi_id=trip_poi_id,
        payload=payload,
    )
    uploader = await db.scalar(
        select(User).where(User.user_id == uploaded_by_user_id, User.deleted_at.is_(None))
    )
    if uploader is None:
        raise TripAttachmentStorageRefError("업로드 사용자를 찾을 수 없습니다.")
    if quota_trip_id is None:
        raise TripAttachmentStorageRefError("첨부 용량을 계산할 여행계획이 필요합니다.")
    try:
        await assert_attachment_quota(
            db,
            user=uploader,
            trip_id=quota_trip_id,
            byte_size=int(payload.get("byte_size") or 0),
        )
    except AttachmentQuotaError as exc:
        raise TripAttachmentQuotaError(str(exc)) from exc
    attachment = CuratedPlanAttachment(
        trip_id=trip_id,
        trip_day_index=trip_day_index,
        trip_poi_id=trip_poi_id,
        uploaded_by_user_id=uploaded_by_user_id,
        **payload,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


def _validate_attachment_storage_ref(
    *,
    uploaded_by_user_id: uuid.UUID,
    trip_id: uuid.UUID | None,
    trip_day_index: int | None,
    trip_poi_id: uuid.UUID | None,
    payload: dict[str, Any],
) -> None:
    if trip_id is None and trip_poi_id is None:
        raise TripAttachmentStorageRefError("첨부 대상이 필요합니다.")
    if trip_poi_id is not None:
        purpose = "poi_attachment"
    elif trip_day_index is not None:
        purpose = "trip_day_attachment"
    else:
        purpose = "trip_attachment"
    try:
        validate_attachment_storage_ref(
            bucket=payload.get("bucket"),
            storage_key=payload.get("storage_key"),
            purpose=purpose,
            user_id=uploaded_by_user_id,
        )
    except InvalidStorageRefError as exc:
        raise TripAttachmentStorageRefError(str(exc)) from exc


async def update_attachment(
    db: AsyncSession,
    *,
    attachment_id: uuid.UUID,
    trip_id: uuid.UUID | None = None,
    trip_day_index: int | None = None,
    trip_poi_id: uuid.UUID | None = None,
    patch: dict[str, Any],
) -> CuratedPlanAttachment:
    """첨부 메타 수정 — sort_order(재정렬) / description."""
    filters: list[Any] = [
        CuratedPlanAttachment.attachment_id == attachment_id,
        CuratedPlanAttachment.deleted_at.is_(None),
    ]
    if trip_id is not None:
        filters.append(CuratedPlanAttachment.trip_id == trip_id)
        if trip_day_index is None and trip_poi_id is None:
            filters.append(CuratedPlanAttachment.trip_day_index.is_(None))
    if trip_day_index is not None:
        filters.append(CuratedPlanAttachment.trip_day_index == trip_day_index)
    if trip_poi_id is not None:
        filters.append(CuratedPlanAttachment.trip_poi_id == trip_poi_id)
    attachment = await db.scalar(select(CuratedPlanAttachment).where(*filters))
    if attachment is None:
        raise TripAttachmentNotFoundError("첨부를 찾을 수 없습니다.")
    for key, value in patch.items():
        setattr(attachment, key, value)
    await db.commit()
    await db.refresh(attachment)
    return attachment


async def get_attachment(
    db: AsyncSession,
    *,
    attachment_id: uuid.UUID,
    trip_id: uuid.UUID | None = None,
    trip_day_index: int | None = None,
    trip_poi_id: uuid.UUID | None = None,
) -> CuratedPlanAttachment:
    """단건 첨부 조회(스코프 한정). 없으면 NotFound."""
    filters: list[Any] = [
        CuratedPlanAttachment.attachment_id == attachment_id,
        CuratedPlanAttachment.deleted_at.is_(None),
    ]
    if trip_id is not None:
        filters.append(CuratedPlanAttachment.trip_id == trip_id)
        if trip_day_index is None and trip_poi_id is None:
            filters.append(CuratedPlanAttachment.trip_day_index.is_(None))
    if trip_day_index is not None:
        filters.append(CuratedPlanAttachment.trip_day_index == trip_day_index)
    if trip_poi_id is not None:
        filters.append(CuratedPlanAttachment.trip_poi_id == trip_poi_id)
    attachment = await db.scalar(select(CuratedPlanAttachment).where(*filters))
    if attachment is None:
        raise TripAttachmentNotFoundError("첨부를 찾을 수 없습니다.")
    return attachment


async def delete_attachment(
    db: AsyncSession,
    *,
    attachment_id: uuid.UUID,
    trip_id: uuid.UUID | None = None,
    trip_day_index: int | None = None,
    trip_poi_id: uuid.UUID | None = None,
) -> None:
    filters = [
        CuratedPlanAttachment.attachment_id == attachment_id,
        CuratedPlanAttachment.deleted_at.is_(None),
    ]
    if trip_id is not None:
        filters.append(CuratedPlanAttachment.trip_id == trip_id)
        if trip_day_index is None and trip_poi_id is None:
            filters.append(CuratedPlanAttachment.trip_day_index.is_(None))
    if trip_day_index is not None:
        filters.append(CuratedPlanAttachment.trip_day_index == trip_day_index)
    if trip_poi_id is not None:
        filters.append(CuratedPlanAttachment.trip_poi_id == trip_poi_id)
    attachment = await db.scalar(select(CuratedPlanAttachment).where(*filters))
    if attachment is None:
        raise TripAttachmentNotFoundError("첨부를 찾을 수 없습니다.")
    attachment.deleted_at = datetime.now(UTC)
    await db.commit()


async def build_distance_matrix(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_index: int,
) -> tuple[list[TripDayPoi], list[list[int | None]], list[str]]:
    pois = await _list_day_pois(db, trip_id=trip_id, day_index=day_index)
    coords = [_extract_coord(poi.feature_snapshot) for poi in pois]
    warnings: list[str] = []
    missing = sum(1 for coord in coords if coord is None)
    if missing:
        warnings.append(f"{missing}개 POI는 좌표가 없어 거리 계산에서 제외됩니다.")
    matrix: list[list[int | None]] = []
    for left in coords:
        row: list[int | None] = []
        for right in coords:
            row.append(None if left is None or right is None else _distance_meters(left, right))
        matrix.append(row)
    return pois, matrix, warnings


async def optimize_trip_day(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_index: int,
    start_poi_id: uuid.UUID | None,
    persist: bool,
    strategy: str = "two_opt",
) -> tuple[list[TripDayPoi], list[tuple[TripDayPoi, str, str]], int | None, int | None, list[str]]:
    pois = await _list_day_pois(db, trip_id=trip_id, day_index=day_index)
    if not pois:
        raise TripDayNotFoundError("최적화할 POI가 없습니다.")
    ordered, total_distance, previous_distance, warnings = _optimize_day_order(
        pois, start_poi_id=start_poi_id, strategy=strategy
    )
    moves: list[tuple[TripDayPoi, str, str]] = []
    next_sort: str | None = None
    for poi in ordered:
        old_sort = poi.sort_order
        new_sort = lexorank.between(next_sort, None)
        next_sort = new_sort
        if old_sort != new_sort:
            moves.append((poi, old_sort, new_sort))
        if persist:
            poi.sort_order = new_sort
            poi.version += 1
    if persist and moves:
        await db.commit()
        for poi, _, _ in moves:
            await db.refresh(poi)
    return ordered, moves, total_distance, previous_distance, warnings


async def invite_companion(
    db: AsyncSession,
    *,
    trip: Trip,
    invited_by_user_id: uuid.UUID,
    email: str,
    display_name: str | None,
    role: str,
) -> TripCompanion:
    normalized_email = email.strip().lower()
    matched_user = await db.scalar(
        select(User).where(
            func.lower(User.email) == normalized_email,
            User.deleted_at.is_(None),
        )
    )
    if matched_user is not None and matched_user.user_id == trip.owner_user_id:
        raise TripCompanionConflictError("여행 소유자는 동반자로 초대할 수 없습니다.")

    duplicate_filters = [func.lower(TripCompanion.invited_email) == normalized_email]
    if matched_user is not None:
        duplicate_filters.append(TripCompanion.user_id == matched_user.user_id)
    existing = await db.scalar(
        select(TripCompanion.companion_id).where(
            TripCompanion.trip_id == trip.trip_id,
            or_(*duplicate_filters),
        )
    )
    if existing is not None:
        raise TripCompanionConflictError("이미 초대된 동반자입니다.")

    companion = TripCompanion(
        trip_id=trip.trip_id,
        invited_email=normalized_email,
        user_id=None if matched_user is None else matched_user.user_id,
        invited_nickname=display_name,
        role=role,
        invited_at=datetime.now(UTC),
        joined_at=datetime.now(UTC) if matched_user is not None else None,
    )
    db.add(companion)
    await db.flush()
    await enqueue_trip_invite_email(
        db,
        to_email=normalized_email,
        trip_id=trip.trip_id,
        trip_title=trip.title,
        companion_id=companion.companion_id,
        invited_by_user_id=invited_by_user_id,
        target_user_id=None if matched_user is None else matched_user.user_id,
    )
    await db.commit()
    await db.refresh(companion)
    return companion


async def remove_companion(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    companion_id: uuid.UUID,
) -> None:
    companion = await db.scalar(
        select(TripCompanion).where(
            TripCompanion.trip_id == trip_id,
            TripCompanion.companion_id == companion_id,
        )
    )
    if companion is None:
        raise TripNotFoundError("동반자를 찾을 수 없습니다.")
    await db.delete(companion)
    await db.commit()


async def issue_share_link(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    visibility: str,
    expires_at: datetime | None,
) -> tuple[TripShareLink, str]:
    raw_token = generate_opaque_token(32)
    share = TripShareLink(
        trip_id=trip_id,
        token_hash=sha256_hex(raw_token),
        created_by_user_id=created_by_user_id,
        visibility=visibility,
        expires_at=expires_at,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share, raw_token


async def revoke_share_link(db: AsyncSession, *, share_id: uuid.UUID, trip_id: uuid.UUID) -> None:
    share = await db.scalar(
        select(TripShareLink).where(
            TripShareLink.share_id == share_id, TripShareLink.trip_id == trip_id
        )
    )
    if share is None:
        raise TripNotFoundError("공유 토큰을 찾을 수 없습니다.")
    if share.revoked_at is None:
        share.revoked_at = datetime.now(UTC)
        await db.commit()


async def list_comments(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    limit: int = 50,
) -> list[TripComment]:
    result = await db.execute(
        select(TripComment)
        .where(TripComment.trip_id == trip_id, TripComment.deleted_at.is_(None))
        .order_by(TripComment.created_at.asc(), TripComment.comment_id.asc())
        .limit(limit)
    )
    return list(result.scalars())


async def create_comment(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    author_user_id: uuid.UUID,
    body: str,
    target_type: str,
    target_id: uuid.UUID | None,
    day_index: int | None,
) -> TripComment:
    comment = TripComment(
        trip_id=trip_id,
        author_user_id=author_user_id,
        body=body.strip(),
        target_type=target_type,
        target_id=target_id,
        day_index=day_index,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def delete_comment(
    db: AsyncSession,
    *,
    trip: Trip,
    comment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> TripComment:
    comment = await db.scalar(
        select(TripComment).where(
            TripComment.trip_id == trip.trip_id,
            TripComment.comment_id == comment_id,
            TripComment.deleted_at.is_(None),
        )
    )
    if comment is None:
        raise TripCommentNotFoundError("댓글을 찾을 수 없습니다.")
    if comment.author_user_id != actor_user_id and trip.owner_user_id != actor_user_id:
        raise TripPermissionError("댓글 작성자 또는 여행 소유자만 삭제할 수 있습니다.")
    comment.deleted_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(comment)
    return comment


async def _bump_trip_version(db: AsyncSession, *, trip_id: uuid.UUID) -> None:
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id))
    if trip is not None:
        trip.version += 1


async def _select_copy_days(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    scope: TripCopyScope,
    day_index: int | None,
    start_day_index: int | None,
    end_day_index: int | None,
) -> list[TripDay]:
    stmt = select(TripDay).where(TripDay.trip_id == trip_id)
    if scope == "day":
        if day_index is None:
            raise TripCopyError("day_index가 필요합니다.")
        stmt = stmt.where(TripDay.day_index == day_index)
    elif scope == "range":
        if start_day_index is None or end_day_index is None:
            raise TripCopyError("start_day_index/end_day_index가 필요합니다.")
        stmt = stmt.where(
            TripDay.day_index >= start_day_index,
            TripDay.day_index <= end_day_index,
        )
    result = await db.execute(stmt.order_by(TripDay.day_index.asc()))
    days = list(result.scalars())
    if scope != "all" and not days:
        raise TripDayNotFoundError("복사할 day를 찾을 수 없습니다.")
    return days


async def _list_copy_pois(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_indexes: list[int] | None,
) -> list[TripDayPoi]:
    if day_indexes == []:
        return []
    filters: list[Any] = [
        TripDayPoi.trip_id == trip_id,
        TripDayPoi.deleted_at.is_(None),
    ]
    if day_indexes is not None:
        filters.append(TripDayPoi.day_index.in_(day_indexes))
    result = await db.execute(
        select(TripDayPoi)
        .where(*filters)
        .order_by(TripDayPoi.day_index.asc(), TripDayPoi.sort_order.asc())
    )
    return list(result.scalars())


async def _copy_trip_attachments(
    db: AsyncSession,
    *,
    source_trip_id: uuid.UUID,
    target_trip_id: uuid.UUID,
    source_day_indexes: list[int] | None,
    poi_id_map: dict[uuid.UUID, uuid.UUID],
    actor_user_id: uuid.UUID,
    include_trip_level: bool,
) -> int:
    copied = 0
    target_filters: list[Any] = []
    if include_trip_level:
        target_filters.append(
            CuratedPlanAttachment.trip_id == source_trip_id,
        )
    elif source_day_indexes:
        target_filters.append(
            (CuratedPlanAttachment.trip_id == source_trip_id)
            & (CuratedPlanAttachment.trip_day_index.in_(source_day_indexes))
        )
    if poi_id_map:
        target_filters.append(CuratedPlanAttachment.trip_poi_id.in_(list(poi_id_map.keys())))
    if not target_filters:
        return 0
    filters: list[Any] = [CuratedPlanAttachment.deleted_at.is_(None), or_(*target_filters)]
    result = await db.execute(select(CuratedPlanAttachment).where(*filters))
    for attachment in result.scalars():
        source_poi_id = attachment.trip_poi_id
        trip_poi_id = (
            poi_id_map[source_poi_id]
            if source_poi_id is not None and source_poi_id in poi_id_map
            else None
        )
        trip_id = None
        trip_day_index = None
        if trip_poi_id is None and attachment.trip_id == source_trip_id:
            trip_id = target_trip_id
            trip_day_index = attachment.trip_day_index
        if trip_id is None and trip_poi_id is None:
            continue
        db.add(
            CuratedPlanAttachment(
                trip_id=trip_id,
                trip_day_index=trip_day_index,
                trip_poi_id=trip_poi_id,
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
                uploaded_by_user_id=actor_user_id,
            )
        )
        copied += 1
    return copied


async def _max_sort_order(db: AsyncSession, trip_id: uuid.UUID, day_index: int) -> str | None:
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


def _shift_date(value: date | None, days: int) -> date | None:
    return None if value is None else value + timedelta(days=days)


def _shift_datetime(value: datetime | None, days: int) -> datetime | None:
    return None if value is None else value + timedelta(days=days)


async def _list_day_pois(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_index: int,
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


Coord = tuple[float, float]


def _extract_coord(snapshot: dict[str, Any]) -> Coord | None:
    containers: list[Any] = [snapshot, snapshot.get("coord"), snapshot.get("location")]
    for item in containers:
        if not isinstance(item, dict):
            continue
        lon = item.get("longitude", item.get("lon"))
        lat = item.get("latitude", item.get("lat"))
        if isinstance(lon, int | float) and isinstance(lat, int | float):
            return float(lon), float(lat)
    return None


def _distance_meters(left: Coord, right: Coord) -> int:
    lon1, lat1 = left
    lon2, lat2 = right
    radius_m = 6_371_000
    dlon = radians(lon2 - lon1)
    dlat = radians(lat2 - lat1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return round(2 * radius_m * asin(sqrt(a)))


_TWO_OPT_MAX_POIS = 60


def _path_distance_m(
    order: list[TripDayPoi],
    coord_by_id: dict[uuid.UUID, Coord | None],
) -> int:
    total = 0
    for left, right in pairwise(order):
        left_coord = coord_by_id[left.attachment_id]
        right_coord = coord_by_id[right.attachment_id]
        if left_coord is None or right_coord is None:
            continue
        total += _distance_meters(left_coord, right_coord)
    return total


def _nearest_neighbor_seed(
    with_coords: list[TripDayPoi],
    coord_by_id: dict[uuid.UUID, Coord | None],
    *,
    start_poi_id: uuid.UUID | None,
) -> list[TripDayPoi]:
    remaining = with_coords[:]
    if start_poi_id is not None:
        start = next((poi for poi in remaining if poi.attachment_id == start_poi_id), None)
        if start is None:
            raise TripOptimizeError("start_poi_id가 해당 day에 없거나 좌표가 없습니다.")
    else:
        start = remaining[0]

    ordered = [start]
    remaining.remove(start)
    while remaining:
        current_coord = coord_by_id[ordered[-1].attachment_id]
        assert current_coord is not None

        def distance_from_current(poi: TripDayPoi, base_coord: Coord = current_coord) -> int:
            candidate_coord = coord_by_id[poi.attachment_id]
            assert candidate_coord is not None
            return _distance_meters(base_coord, candidate_coord)

        nearest = min(remaining, key=distance_from_current)
        ordered.append(nearest)
        remaining.remove(nearest)
    return ordered


def _two_opt_improve(
    order: list[TripDayPoi],
    coord_by_id: dict[uuid.UUID, Coord | None],
    *,
    fix_start: bool,
) -> list[TripDayPoi]:
    """Open-path 2-opt local search — 교차 구간을 뒤집어 총 이동거리를 줄인다.

    `fix_start`이면 index 0(시작 POI)을 고정한다. trip day의 POI 수가 적어
    후보마다 전체 거리를 재계산해도 충분히 빠르다(`_TWO_OPT_MAX_POIS`로 상한).
    """
    n = len(order)
    if n < 4:
        return order
    best = list(order)
    best_dist = _path_distance_m(best, coord_by_id)
    start_i = 1 if fix_start else 0
    improved = True
    passes = 0
    while improved and passes < n:
        improved = False
        passes += 1
        for i in range(start_i, n - 1):
            for j in range(i + 1, n):
                candidate = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                dist = _path_distance_m(candidate, coord_by_id)
                if dist < best_dist:
                    best = candidate
                    best_dist = dist
                    improved = True
    return best


def _optimize_day_order(
    pois: list[TripDayPoi],
    *,
    start_poi_id: uuid.UUID | None,
    strategy: str,
) -> tuple[list[TripDayPoi], int | None, int | None, list[str]]:
    """좌표 보유 POI를 nearest-neighbor seed 후 (two_opt면) 2-opt로 정렬한다.

    좌표가 없는 POI는 기존 순서로 뒤에 둔다. 반환: (정렬 순서, 최적 거리,
    기존 순서 거리, warnings). 거리는 haversine 직선거리(m).
    """
    coord_by_id: dict[uuid.UUID, Coord | None] = {
        poi.attachment_id: _extract_coord(poi.feature_snapshot) for poi in pois
    }
    with_coords = [poi for poi in pois if coord_by_id[poi.attachment_id] is not None]
    without_coords = [poi for poi in pois if coord_by_id[poi.attachment_id] is None]
    warnings: list[str] = []
    if without_coords:
        warnings.append(f"{len(without_coords)}개 POI는 좌표가 없어 기존 순서로 뒤에 둡니다.")
    if not with_coords:
        return pois, None, None, warnings

    previous_distance = _path_distance_m(with_coords, coord_by_id)
    seed = _nearest_neighbor_seed(with_coords, coord_by_id, start_poi_id=start_poi_id)
    if strategy == "two_opt" and len(seed) <= _TWO_OPT_MAX_POIS:
        optimized = _two_opt_improve(seed, coord_by_id, fix_start=start_poi_id is not None)
    else:
        if strategy == "two_opt" and len(seed) > _TWO_OPT_MAX_POIS:
            warnings.append("POI가 많아 2-opt 미세조정은 생략하고 근접 휴리스틱만 적용합니다.")
        optimized = seed
    total = _path_distance_m(optimized, coord_by_id)
    return optimized + without_coords, total, previous_distance, warnings


async def _is_companion(db: AsyncSession, trip_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = await db.scalar(
        select(TripCompanion.companion_id).where(
            TripCompanion.trip_id == trip_id,
            TripCompanion.user_id == user_id,
        )
    )
    return row is not None


async def _companion_role(db: AsyncSession, trip_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    role: str | None = await db.scalar(
        select(TripCompanion.role).where(
            TripCompanion.trip_id == trip_id,
            TripCompanion.user_id == user_id,
        )
    )
    return role
