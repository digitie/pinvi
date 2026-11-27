"""POI 도메인 — CRUD + reorder (LexoRank)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import TripComment
from app.models.poi import TripDayPoi
from app.models.poi_place_detail import TripPoiPlaceDetail
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.services.poi_region import carry_geo_region
from app.services.sun_times import snapshot_coord, sun_rise_set_dict
from app.services.trip import TripNotFoundError, validate_trip_day_payload

_REGION_CODE_RE = re.compile(r"^[0-9]{2,10}$")
_REGION_CODE_KEYS = (
    "legal_dong_code",
    "bjd_code",
    "bjd_cd",
    "region_code",
    "sigungu_code",
    "sig_cd",
    "sido_code",
)
_REGION_CONTAINER_KEYS = ("region", "address", "location")


async def _lock_active_trip(db: AsyncSession, trip_id: uuid.UUID) -> Trip | None:
    """POI 쓰기를 여행 행 잠금으로 직렬화하고, 잠금 뒤 휴지통 이동 여부를 다시 확인한다.

    권한 확인은 잠금 전에 끝나므로 같은 시각 여행 삭제와 경주하면 휴지통 여행에 쓰기가
    남는다 — 잠금을 잡은 뒤의 `deleted_at`이 정본이다.
    """
    trip: Trip | None = await db.scalar(
        select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)).with_for_update()
    )
    return trip


class PoiError(Exception):
    code: str = "INTERNAL_ERROR"


class PoiNotFoundError(PoiError):
    code = "RESOURCE_NOT_FOUND"


class PoiVersionConflictError(PoiError):
    code = "VERSION_CONFLICT"


class SortOrderConflictError(PoiError):
    code = "SORT_ORDER_CONFLICT"


async def _lock_poi_in_observed_trip(db: AsyncSession, poi: TripDayPoi) -> TripDayPoi:
    """권한을 확인한 여행을 고정한다. 잠금 대기 중 관리자 이동을 따라가지 않는다."""
    source_trip_id = poi.trip_id
    poi_id = poi.attachment_id
    if await _lock_active_trip(db, source_trip_id) is None:
        raise PoiNotFoundError("POI를 찾을 수 없습니다.")
    locked = await db.scalar(
        select(TripDayPoi)
        .where(
            TripDayPoi.attachment_id == poi_id,
            TripDayPoi.trip_id == source_trip_id,
            TripDayPoi.deleted_at.is_(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise PoiNotFoundError("POI를 찾을 수 없습니다.")
    return locked


async def ensure_trip_day(db: AsyncSession, *, trip_id: uuid.UUID, day_index: int) -> TripDay:
    day = await db.scalar(
        select(TripDay).where(TripDay.trip_id == trip_id, TripDay.day_index == day_index)
    )
    if day is None:
        trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id))
        if trip is None:
            raise TripNotFoundError("여행을 찾을 수 없습니다.")
        await validate_trip_day_payload(
            db, trip=trip, day_index=day_index, date_value=None, exclude_day_index=day_index
        )
        # ADR-055: date는 override-only. auto-create는 NULL로 두고 effective_date를 파생한다.
        day = TripDay(trip_id=trip_id, day_index=day_index)
        db.add(day)
        await db.flush()
    return day


async def trip_day_effective_locdate(
    db: AsyncSession, *, trip_id: uuid.UUID, day_index: int, override: date | None
) -> date | None:
    """일자 effective 날짜(ADR-055) — POI 응답의 해·달 출몰 계산용.

    day.date override가 있으면 그것, 없으면 trip.start_date + (day_index-1)로 파생한다.
    trip.start_date가 없으면 None(rise/set은 pending_date).
    """
    if override is not None:
        return override
    start_date = await db.scalar(select(Trip.start_date).where(Trip.trip_id == trip_id))
    if start_date is None:
        return None
    return start_date + timedelta(days=day_index - 1)


async def create_poi(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    day_index: int,
    sort_order: str,
    feature_id: str | None,
    feature_snapshot: dict[str, Any],
    added_by_user_id: uuid.UUID,
    custom_marker_color: str | None = None,
    custom_marker_icon: str | None = None,
    planned_arrival_at: datetime | None = None,
    planned_departure_at: datetime | None = None,
    user_note: str | None = None,
    budget_amount: Decimal | None = None,
    actual_amount: Decimal | None = None,
    currency: str = "KRW",
    user_url: str | None = None,
    source: str | None = None,
    external_ref: dict[str, Any] | None = None,
) -> TripDayPoi:
    if await _lock_active_trip(db, trip_id) is None:
        raise TripNotFoundError("여행을 찾을 수 없습니다.")
    await ensure_trip_day(db, trip_id=trip_id, day_index=day_index)
    poi = TripDayPoi(
        trip_id=trip_id,
        day_index=day_index,
        sort_order=sort_order,
        feature_id=feature_id,
        feature_snapshot=feature_snapshot,
        custom_marker_color=custom_marker_color,
        custom_marker_icon=custom_marker_icon,
        source=source
        or (
            "feature" if feature_id else external_ref.get("provider") if external_ref else "manual"
        ),
        external_ref=external_ref,
        planned_arrival_at=planned_arrival_at,
        planned_departure_at=planned_departure_at,
        user_note=user_note,
        budget_amount=budget_amount,
        actual_amount=actual_amount,
        currency=currency,
        user_url=user_url,
        added_by_user_id=added_by_user_id,
    )
    db.add(poi)
    await _fill_trip_primary_region_from_snapshot(
        db,
        trip_id=trip_id,
        feature_snapshot=feature_snapshot,
    )
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # (trip_id, day_index, sort_order COLLATE "C") UNIQUE 위반
        raise SortOrderConflictError("같은 위치(sort_order)에 이미 POI가 있습니다.") from exc
    await db.refresh(poi)
    return poi


async def get_poi(db: AsyncSession, *, attachment_id: uuid.UUID, trip_id: uuid.UUID) -> TripDayPoi:
    poi = await db.scalar(
        select(TripDayPoi).where(
            TripDayPoi.attachment_id == attachment_id,
            TripDayPoi.trip_id == trip_id,
            TripDayPoi.deleted_at.is_(None),
        )
    )
    if poi is None:
        raise PoiNotFoundError("POI를 찾을 수 없습니다.")
    return poi


async def _carry_poi_comments(
    db: AsyncSession, *, trip_id: uuid.UUID, poi_id: uuid.UUID, day_index: int
) -> None:
    """장소에 단 댓글의 일자를 장소를 따라 옮긴다.

    일자 단위 관리자 작업(일자 삭제·다른 여행으로 이동)이 `day_index`로 댓글을 고르므로, 두면 옮긴 장소의
    댓글이 출발 일자와 함께 지워지거나 딸려 간다(관리자 이동 `_move_or_delete_poi_comments`와 같은 규칙).
    """
    await db.execute(
        update(TripComment)
        .where(
            TripComment.trip_id == trip_id,
            TripComment.target_id == poi_id,
            TripComment.deleted_at.is_(None),
        )
        .values(day_index=day_index)
    )


async def update_poi(
    db: AsyncSession,
    *,
    poi: TripDayPoi,
    expected_version: int,
    patch: dict[str, Any],
) -> TripDayPoi:
    poi = await _lock_poi_in_observed_trip(db, poi)
    if poi.version != expected_version:
        raise PoiVersionConflictError("동시 편집 충돌 — 다시 불러와 주세요.")
    destination = patch.get("day_index")
    moved = destination is not None and destination != poi.day_index
    if moved:
        day = await db.scalar(
            select(TripDay).where(TripDay.trip_id == poi.trip_id, TripDay.day_index == destination)
        )
        if day is None:
            raise PoiNotFoundError("이동할 여행 일자를 찾을 수 없습니다.")
        if patch.get("sort_order") is None:
            last = await db.scalar(
                select(TripDayPoi.sort_order)
                .where(
                    TripDayPoi.trip_id == poi.trip_id,
                    TripDayPoi.day_index == destination,
                    TripDayPoi.deleted_at.is_(None),
                )
                .order_by(TripDayPoi.sort_order.desc())
                .limit(1)
            )
            patch = {**patch, "sort_order": last + "0" if last is not None else "a0"}
            if len(patch["sort_order"]) > 80:
                raise SortOrderConflictError("이동할 일자의 정렬 위치를 다시 정리해 주세요.")
    new_snapshot = patch.get("feature_snapshot")
    if isinstance(new_snapshot, dict):
        patch = {**patch, "feature_snapshot": carry_geo_region(poi.feature_snapshot, new_snapshot)}
    for key, value in patch.items():
        if value is None and key not in {
            "custom_marker_color",
            "custom_marker_icon",
            "user_note",
            "planned_arrival_at",
            "planned_departure_at",
            "budget_amount",
            "actual_amount",
            "user_url",
            "feature_snapshot",
        }:
            continue
        setattr(poi, key, value)
    poi.version += 1
    try:
        if moved:
            await _carry_poi_comments(
                db, trip_id=poi.trip_id, poi_id=poi.attachment_id, day_index=poi.day_index
            )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise SortOrderConflictError(
            "정렬 위치가 충돌했습니다. 다시 불러온 후 시도해 주세요."
        ) from exc
    await db.refresh(poi)
    return poi


async def soft_delete_poi(db: AsyncSession, *, poi: TripDayPoi) -> None:
    # 일자 기준 유지/추가/이동과 같은 Trip→POI 순서로 직렬화한다.
    poi = await _lock_poi_in_observed_trip(db, poi)
    poi.deleted_at = datetime.now(UTC)
    # 장소에 붙은 영업 정보 사본도 함께 지운다 — 다시 넣으면 새로 받는다(전역 보관 금지).
    await db.execute(
        delete(TripPoiPlaceDetail).where(TripPoiPlaceDetail.poi_id == poi.attachment_id)
    )
    await db.commit()


async def poi_rise_sets(
    db: AsyncSession, pois: Iterable[TripDayPoi]
) -> dict[uuid.UUID, dict[str, Any]]:
    """POI 응답의 해·달 출몰 — 일자 effective 날짜와 저장 좌표로 astral 계산한다(`services/sun_times.py`).

    trip 상세 응답은 `trip_view_builder`가 최신 feature 좌표로 같은 계산을 한다.
    """
    out: dict[uuid.UUID, dict[str, Any]] = {}
    locdates: dict[tuple[uuid.UUID, int], date | None] = {}
    for poi in pois:
        key = (poi.trip_id, poi.day_index)
        if key not in locdates:
            override = await db.scalar(
                select(TripDay.date).where(
                    TripDay.trip_id == poi.trip_id, TripDay.day_index == poi.day_index
                )
            )
            locdates[key] = await trip_day_effective_locdate(
                db, trip_id=poi.trip_id, day_index=poi.day_index, override=override
            )
        out[poi.attachment_id] = sun_rise_set_dict(
            locdate=locdates[key], coord=snapshot_coord(poi.feature_snapshot)
        )
    return out


async def reorder_pois(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    moves: list[tuple[uuid.UUID, str]],
    day_index: int,
) -> list[TripDayPoi]:
    if await _lock_active_trip(db, trip_id) is None:
        raise PoiNotFoundError("정렬할 POI를 찾을 수 없습니다.")
    poi_ids = [pid for pid, _ in moves]
    if len(set(poi_ids)) != len(poi_ids):
        raise SortOrderConflictError("같은 POI를 두 번 정렬할 수 없습니다.")
    result = await db.execute(
        select(TripDayPoi)
        .where(
            TripDayPoi.attachment_id.in_(poi_ids),
            TripDayPoi.trip_id == trip_id,
            TripDayPoi.deleted_at.is_(None),
        )
        .with_for_update()
    )
    pois = {p.attachment_id: p for p in result.scalars()}
    if len(pois) != len(poi_ids):
        raise PoiNotFoundError("정렬할 POI를 찾을 수 없습니다.")
    if any(p.day_index != day_index for p in pois.values()):
        raise SortOrderConflictError("장소의 일자가 변경됐습니다. 다시 불러온 후 정렬해 주세요.")
    final_positions = [(pois[pid].day_index, rank) for pid, rank in moves]
    if len(set(final_positions)) != len(final_positions):
        raise SortOrderConflictError("같은 일자의 정렬 위치가 중복됩니다.")
    updated = [pois[pid] for pid in poi_ids]
    try:
        # 하나의 트랜잭션에서 임시 고유 위치로 옮긴 뒤 최종 순서를 적용한다.
        nonce = uuid.uuid4().hex
        for index, poi in enumerate(updated):
            poi.sort_order = f"reorder_{nonce}_{index}"
        await db.flush()
        for poi_id, new_sort in moves:
            pois[poi_id].sort_order = new_sort
            pois[poi_id].version += 1
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise SortOrderConflictError(
            "정렬 위치가 충돌했습니다. 다시 불러온 후 시도해 주세요."
        ) from exc

    for poi in updated:
        await db.refresh(poi)
    return updated


class PoiMoveValidationError(PoiError):
    code = "VALIDATION_ERROR"


# `packages/domain/src/poiRank.ts` `evenRanks`와 같은 키: (i+1)*100을 base36 4자리로.
_RANK_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
_RANK_SPACING = 100
_RANK_WIDTH = 4
# 클라이언트 키 상한(`PoiCreate.sort_order` max_length)과 같다.
_RANK_MAX_LENGTH = 80


def _base36(value: int) -> str:
    digits = ""
    while value:
        value, remainder = divmod(value, 36)
        digits = _RANK_DIGITS[remainder] + digits
    return digits or "0"


def even_ranks(count: int) -> list[str]:
    """`count`개의 균등 간격 정렬 키(오름차순). 고정폭 0 채움이라 COLLATE "C" 순서 == 수치 순서.

    4자리가 넘칠 만큼 많으면(약 1.6만 개) 모든 키를 같은 넓은 폭으로 맞춘다.
    """
    width = max(_RANK_WIDTH, len(_base36(count * _RANK_SPACING)))
    return [_base36((index + 1) * _RANK_SPACING).rjust(width, "0") for index in range(count)]


def rank_between(prev: str | None, next_: str | None) -> str | None:
    """`prev` < 키 < `next_`인 새 정렬 키(COLLATE "C"). 만들 수 없으면 None.

    fractional indexing 중간값 — 이웃 키 사이에 넣어 **옮긴 장소 한 행만** 쓰기 위한 것이다. 새로 붙이는
    자리는 base36 문자이고, 두 이웃이 함께 가진 앞부분은 그대로 복사한다. 클라이언트가 만든
    키(`a0`·`last+'m'`·`evenRanks`)가 섞여 있어 사이가 없을 수도 있으므로(예: `p`와 `p0`) 결과를 비교로
    검증하고, 실패하면 None을 돌려 호출자가 그 일자를 다시 매기게 한다.
    """
    if prev is None and next_ is None:
        return even_ranks(1)[0]
    try:
        key = _midpoint(prev or "", next_)
    except (ValueError, IndexError):
        return None
    if not key or len(key) > _RANK_MAX_LENGTH:
        return None
    if prev is not None and not prev < key:
        return None
    if next_ is not None and not key < next_:
        return None
    return key


def _midpoint(low: str, high: str | None) -> str:
    """`low` < 결과 < `high`(None = 끝없음). 자릿수 문자는 `_RANK_DIGITS`만 허용한다."""
    zero = _RANK_DIGITS[0]
    if high is not None:
        shared = 0
        while shared < len(high) and (low[shared] if shared < len(low) else zero) == high[shared]:
            shared += 1
        if shared > 0:
            return high[:shared] + _midpoint(low[shared:], high[shared:])
    low_digit = _RANK_DIGITS.index(low[0]) if low else 0
    high_digit = _RANK_DIGITS.index(high[0]) if high is not None else len(_RANK_DIGITS)
    if high_digit - low_digit > 1:
        return _RANK_DIGITS[(low_digit + high_digit) // 2]
    if high is not None and len(high) > 1:
        return high[0]
    return _RANK_DIGITS[low_digit] + _midpoint(low[1:], None)


@dataclass(frozen=True)
class PoiMoveResult:
    poi: TripDayPoi
    from_day_index: int
    # 정렬 키나 일자가 바뀐 POI 전부(도착 일자 순서). 옮긴 장소는 실제로 옮겼으면 언제나 들어 있다.
    # 보통은 옮긴 장소 하나뿐이고, 이웃 키 사이에 자리가 없을 때만 도착 일자를 다시 매겨 더 늘어난다.
    # 순서가 그대로인 이동이면 빈 목록.
    changed: list[TripDayPoi]


async def move_poi(
    db: AsyncSession,
    *,
    poi: TripDayPoi,
    expected_version: int,
    day_index: int,
    before_poi_id: uuid.UUID | None,
) -> PoiMoveResult:
    """POI 하나를 `day_index` 일자의 `before_poi_id` 바로 앞(없으면 맨 끝)으로 옮긴다.

    같은 일자 안 순서 변경과 다른 일자로의 이동이 같은 경로다. 위치는 서버가 잠근 최신 순서에
    기준 장소(`before_poi_id`)로 정하므로, 그 사이 다른 사람이 도착 일자에 장소를 더해도 덮어쓰지
    않는다. 보통은 이웃 키 사이의 새 키로 **옮긴 장소 한 행만** 쓴다 — 순서와 무관한 다른 장소의
    version을 올리면 그 장소를 편집 중인 동행이 엉뚱한 409를 받기 때문이다. 이웃 사이에 자리가 없을
    때만 도착 일자를 균등 키로 다시 매겨 바뀐 행을 쓴다. 출발 일자는 빠진 자리만 남아 쓰지 않는다.

    잠금: Trip 행 → (옮길 장소 + 도착 일자 장소)를 한 문장에서 `attachment_id` 순으로. POI를 id 순으로
    잠그는 다른 경로(feature reference reconciliation)와 교착하지 않게 같은 순서를 쓴다.
    """
    source_trip_id = poi.trip_id
    poi_id = poi.attachment_id
    if before_poi_id == poi_id:
        raise PoiMoveValidationError("장소를 자기 자신 앞으로 옮길 수 없습니다.")
    if await _lock_active_trip(db, source_trip_id) is None:
        raise PoiNotFoundError("POI를 찾을 수 없습니다.")
    rows = list(
        (
            await db.execute(
                select(TripDayPoi)
                .where(
                    TripDayPoi.trip_id == source_trip_id,
                    TripDayPoi.deleted_at.is_(None),
                    or_(TripDayPoi.attachment_id == poi_id, TripDayPoi.day_index == day_index),
                )
                .order_by(TripDayPoi.attachment_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )
    locked = next((row for row in rows if row.attachment_id == poi_id), None)
    if locked is None:
        raise PoiNotFoundError("POI를 찾을 수 없습니다.")
    poi = locked
    if poi.version != expected_version:
        raise PoiVersionConflictError("동시 편집 충돌 — 다시 불러와 주세요.")
    from_day_index = poi.day_index
    if day_index != from_day_index:
        day = await db.scalar(
            select(TripDay.day_index).where(
                TripDay.trip_id == source_trip_id, TripDay.day_index == day_index
            )
        )
        if day is None:
            raise PoiNotFoundError("이동할 여행 일자를 찾을 수 없습니다.")
    # 정렬은 키 순(COLLATE "C" == ASCII 문자열 비교, 활성 행 키는 유일).
    others = sorted(
        (row for row in rows if row.attachment_id != poi_id and row.day_index == day_index),
        key=lambda row: row.sort_order,
    )
    if before_poi_id is None:
        insert_at = len(others)
    else:
        anchor = next(
            (i for i, other in enumerate(others) if other.attachment_id == before_poi_id), None
        )
        if anchor is None:
            raise SortOrderConflictError(
                "기준 장소가 그 일자에 없습니다. 다시 불러온 후 옮겨 주세요."
            )
        insert_at = anchor
    ordered = [*others[:insert_at], poi, *others[insert_at:]]
    if day_index == from_day_index:
        current = sorted([*others, poi], key=lambda row: row.sort_order)
        if [row.attachment_id for row in current] == [row.attachment_id for row in ordered]:
            # 순서가 그대로인 드롭 — 아무것도 쓰지 않는다(version 불변). rollback은 읽은 객체를
            # 만료시키므로 쓰기 없는 commit으로 잠금만 푼다.
            await db.commit()
            return PoiMoveResult(poi=poi, from_day_index=from_day_index, changed=[])

    prev_key = others[insert_at - 1].sort_order if insert_at > 0 else None
    next_key = others[insert_at].sort_order if insert_at < len(others) else None
    new_key = rank_between(prev_key, next_key)
    try:
        if new_key is not None:
            changed = [poi]
            poi.sort_order = new_key
        else:
            # 이웃 사이에 자리가 없다 — 도착 일자를 균등 키로 다시 매긴다. 부분 UNIQUE(trip, day,
            # sort_order)는 즉시 검사라 바뀌는 행을 임시 고유 키로 옮긴 뒤 최종 키를 쓴다.
            ranks = even_ranks(len(ordered))
            targets = {row.attachment_id: ranks[i] for i, row in enumerate(ordered)}
            changed = [
                row for row in ordered if row is poi or row.sort_order != targets[row.attachment_id]
            ]
            nonce = uuid.uuid4().hex
            for index, row in enumerate(changed):
                row.sort_order = f"move_{nonce}_{index}"
            await db.flush()
            for row in changed:
                row.sort_order = targets[row.attachment_id]
        poi.day_index = day_index
        for row in changed:
            row.version += 1
        if day_index != from_day_index:
            await _carry_poi_comments(
                db, trip_id=source_trip_id, poi_id=poi_id, day_index=day_index
            )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise SortOrderConflictError(
            "정렬 위치가 충돌했습니다. 다시 불러온 후 시도해 주세요."
        ) from exc
    for row in changed:
        await db.refresh(row)
    return PoiMoveResult(poi=poi, from_day_index=from_day_index, changed=changed)


async def _fill_trip_primary_region_from_snapshot(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    feature_snapshot: Mapping[str, Any],
) -> None:
    region_code = _extract_region_code(feature_snapshot)
    if region_code is None:
        return
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id))
    if trip is None or trip.primary_region_code is not None:
        return
    trip.primary_region_code = region_code
    trip.primary_region_source = "poi_snapshot"
    trip.version += 1


def _extract_region_code(feature_snapshot: Mapping[str, Any]) -> str | None:
    direct = _extract_region_code_from_mapping(feature_snapshot)
    if direct is not None:
        return direct
    for key in _REGION_CONTAINER_KEYS:
        value = feature_snapshot.get(key)
        if isinstance(value, Mapping):
            nested = _extract_region_code_from_mapping(value)
            if nested is not None:
                return nested
    return None


def _extract_region_code_from_mapping(value: Mapping[str, Any]) -> str | None:
    for key in _REGION_CODE_KEYS:
        candidate = value.get(key)
        if isinstance(candidate, str) and _REGION_CODE_RE.fullmatch(candidate):
            return candidate
    return None
