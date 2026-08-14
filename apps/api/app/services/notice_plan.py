"""추천 여행(curated trip plan) 도메인 — listing + 상세 + trip 으로 copy.

외부 `/notice-plans` API 이름은 호환 유지한다. 내부 schema는 ADR-029에 따라
`curated_trip_plans` / `curated_plan_pois` / `curated_plan_attachments`를 쓴다.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import CuratedPlanAttachment
from app.models.curated_plan import CuratedPlanPoi, CuratedTripPlan
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.services import lexorank


class NoticePlanError(Exception):
    code: str = "INTERNAL_ERROR"


class NoticePlanNotFoundError(NoticePlanError):
    code = "RESOURCE_NOT_FOUND"


class NoticePlanCopyError(NoticePlanError):
    code = "NOTICE_PLAN_COPY_ERROR"


class NoticePlanPolicyError(NoticePlanError):
    code = "CURATED_PLAN_POI_POLICY_ERROR"


class NoticePlanVersionConflictError(NoticePlanError):
    code = "VERSION_CONFLICT"


class NoticePlanConflictError(NoticePlanError):
    """DB unique 위반(slug 중복 / (day_index, sort_order) 충돌)을 409로 매핑."""

    code = "CONFLICT"


def _optional_feature_id(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _optional_text(value: object, *, max_length: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if max_length is not None:
        return normalized[:max_length]
    return normalized


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


async def list_published_plans(
    db: AsyncSession,
    *,
    category: str | None = None,
    limit: int = 50,
) -> list[CuratedTripPlan]:
    stmt = select(CuratedTripPlan).where(
        CuratedTripPlan.is_published.is_(True), CuratedTripPlan.deleted_at.is_(None)
    )
    if category is not None:
        stmt = stmt.where(CuratedTripPlan.category == category)
    stmt = stmt.order_by(CuratedTripPlan.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars())


async def get_published_plan(db: AsyncSession, *, notice_plan_id: uuid.UUID) -> CuratedTripPlan:
    plan = await db.scalar(
        select(CuratedTripPlan).where(
            CuratedTripPlan.curated_plan_id == notice_plan_id,
            CuratedTripPlan.is_published.is_(True),
            CuratedTripPlan.deleted_at.is_(None),
        )
    )
    if plan is None:
        raise NoticePlanNotFoundError("추천 여행을 찾을 수 없습니다.")
    return plan


async def list_plan_pois(db: AsyncSession, *, notice_plan_id: uuid.UUID) -> list[CuratedPlanPoi]:
    result = await db.execute(
        select(CuratedPlanPoi)
        .where(
            CuratedPlanPoi.curated_plan_id == notice_plan_id,
            CuratedPlanPoi.deleted_at.is_(None),
        )
        .order_by(CuratedPlanPoi.day_index, CuratedPlanPoi.sort_order)
    )
    return list(result.scalars())


def _escape_like(value: str) -> str:
    """ILIKE 메타문자(`\\`, `%`, `_`)를 escape — ESCAPE '\\' 와 함께 사용."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_admin_plans(
    db: AsyncSession,
    *,
    q: str | None = None,
    category: str | None = None,
    is_published: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CuratedTripPlan]:
    stmt = select(CuratedTripPlan).where(CuratedTripPlan.deleted_at.is_(None))
    normalized_q = _optional_text(q)
    if normalized_q is not None:
        pattern = f"%{_escape_like(normalized_q)}%"
        stmt = stmt.where(
            or_(
                CuratedTripPlan.slug.ilike(pattern, escape="\\"),
                CuratedTripPlan.title.ilike(pattern, escape="\\"),
                CuratedTripPlan.destination.ilike(pattern, escape="\\"),
            )
        )
    if category is not None:
        stmt = stmt.where(CuratedTripPlan.category == category)
    if is_published is not None:
        stmt = stmt.where(CuratedTripPlan.is_published.is_(is_published))
    stmt = (
        stmt.order_by(CuratedTripPlan.updated_at.desc(), CuratedTripPlan.curated_plan_id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
    )
    result = await db.execute(stmt)
    return list(result.scalars())


async def get_admin_plan(
    db: AsyncSession, *, notice_plan_id: uuid.UUID, for_update: bool = False
) -> CuratedTripPlan:
    stmt = select(CuratedTripPlan).where(
        CuratedTripPlan.curated_plan_id == notice_plan_id,
        CuratedTripPlan.deleted_at.is_(None),
    )
    if for_update:
        # 동시 writer 직렬화(lost update 방지) — PATCH / POI mutate / reorder / delete.
        stmt = stmt.with_for_update()
    plan = await db.scalar(stmt)
    if plan is None:
        raise NoticePlanNotFoundError("추천 여행을 찾을 수 없습니다.")
    return plan


def _validate_plan_period(starts_on: date | None, ends_on: date | None) -> None:
    if starts_on is None and ends_on is None:
        return
    if starts_on is None or ends_on is None:
        raise NoticePlanPolicyError("starts_on / ends_on 동시에 채우거나 비워야 합니다.")
    if ends_on < starts_on:
        raise NoticePlanPolicyError("ends_on은 starts_on 이후여야 합니다.")


def _check_version(*, actual: int, expected: int | None) -> None:
    if expected is not None and actual != expected:
        raise NoticePlanVersionConflictError("최신 버전이 아닙니다. 새로고침 후 다시 시도하세요.")


def _require_values(values: Mapping[str, Any]) -> None:
    if not values:
        raise NoticePlanPolicyError("수정할 필드가 필요합니다.")


def _is_canonical_map_plan(plan: CuratedTripPlan) -> bool:
    return plan.source_system == "kor-travel-map"


def _reject_canonical_plan_projection_edit(
    plan: CuratedTripPlan, values: Mapping[str, Any]
) -> None:
    if _is_canonical_map_plan(plan) and set(values) - {"is_published"}:
        raise NoticePlanPolicyError(
            "Map canonical collection의 source-derived plan 필드는 import refresh만 변경할 수 있습니다."
        )


def _reject_canonical_poi_projection_edit(poi: CuratedPlanPoi) -> None:
    if poi.source_curation_item_id is not None:
        raise NoticePlanPolicyError(
            "Map canonical POI는 import refresh만 변경·삭제·재정렬할 수 있습니다."
        )


async def create_admin_plan(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID,
    values: Mapping[str, Any],
) -> CuratedTripPlan:
    _validate_plan_period(
        cast(date | None, values.get("starts_on")),
        cast(date | None, values.get("ends_on")),
    )
    plan = CuratedTripPlan(
        slug=cast(str, values["slug"]),
        title=cast(str, values["title"]),
        category=cast(str, values.get("category") or "recommended"),
        summary=cast(str | None, values.get("summary")),
        source_name=cast(str | None, values.get("source_name")),
        destination=cast(str | None, values.get("destination")),
        starts_on=cast(date | None, values.get("starts_on")),
        ends_on=cast(date | None, values.get("ends_on")),
        is_published=cast(bool, values.get("is_published", False)),
        created_by_admin_id=admin_id,
        updated_by_admin_id=admin_id,
    )
    db.add(plan)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        # uq_curated_trip_plans_slug_active: 활성 plan 간 slug 중복.
        raise NoticePlanConflictError("이미 사용 중인 slug 입니다.") from exc
    await db.refresh(plan)
    return plan


async def update_admin_plan(
    db: AsyncSession,
    *,
    plan: CuratedTripPlan,
    admin_id: uuid.UUID,
    values: Mapping[str, Any],
    expected_version: int | None = None,
) -> CuratedTripPlan:
    _require_values(values)
    _check_version(actual=plan.version, expected=expected_version)
    _reject_canonical_plan_projection_edit(plan, values)
    next_starts_on = cast(date | None, values.get("starts_on", plan.starts_on))
    next_ends_on = cast(date | None, values.get("ends_on", plan.ends_on))
    _validate_plan_period(next_starts_on, next_ends_on)
    for field in (
        "title",
        "category",
        "summary",
        "source_name",
        "destination",
        "starts_on",
        "ends_on",
        "is_published",
    ):
        if field in values:
            setattr(plan, field, values[field])
    plan.updated_by_admin_id = admin_id
    plan.version += 1
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise NoticePlanConflictError("이미 사용 중인 값과 충돌합니다.") from exc
    await db.refresh(plan)
    return plan


async def soft_delete_admin_plan(
    db: AsyncSession,
    *,
    plan: CuratedTripPlan,
    admin_id: uuid.UUID,
    expected_version: int | None = None,
) -> CuratedTripPlan:
    _check_version(actual=plan.version, expected=expected_version)
    if _is_canonical_map_plan(plan):
        raise NoticePlanPolicyError(
            "Map canonical collection plan은 generic delete로 제거할 수 없습니다."
        )
    plan.deleted_at = datetime.now(UTC)
    plan.updated_by_admin_id = admin_id
    plan.version += 1
    await db.flush()
    await db.refresh(plan)
    return plan


async def get_admin_poi(
    db: AsyncSession,
    *,
    notice_plan_id: uuid.UUID,
    notice_poi_id: uuid.UUID,
) -> CuratedPlanPoi:
    poi = await db.scalar(
        select(CuratedPlanPoi).where(
            CuratedPlanPoi.curated_plan_id == notice_plan_id,
            CuratedPlanPoi.curated_poi_id == notice_poi_id,
            CuratedPlanPoi.deleted_at.is_(None),
        )
    )
    if poi is None:
        raise NoticePlanNotFoundError("추천 여행 POI를 찾을 수 없습니다.")
    return poi


async def create_admin_poi(
    db: AsyncSession,
    *,
    plan: CuratedTripPlan,
    admin_id: uuid.UUID,
    values: Mapping[str, Any],
) -> CuratedPlanPoi:
    poi = CuratedPlanPoi(
        curated_plan_id=plan.curated_plan_id,
        day_index=cast(int, values.get("day_index", 1)),
        sort_order=cast(str, values["sort_order"]),
        feature_id=_optional_feature_id(values.get("feature_id")),
        feature_snapshot=dict(_mapping(values.get("feature_snapshot"))),
        memo=cast(str | None, values.get("memo")),
        budget_amount=values.get("budget_amount"),
        currency=cast(str, values.get("currency") or "KRW"),
        user_url=cast(str | None, values.get("user_url")),
        custom_marker_color=cast(str | None, values.get("custom_marker_color")),
        custom_marker_icon=cast(str | None, values.get("custom_marker_icon")),
    )
    db.add(poi)
    plan.updated_by_admin_id = admin_id
    plan.version += 1
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        # uq_curated_plan_pois_plan_day_sort: (day_index, sort_order) 충돌.
        raise NoticePlanConflictError(
            "같은 위치(day_index, sort_order)에 이미 POI가 있습니다."
        ) from exc
    await db.refresh(poi)
    return poi


async def update_admin_poi(
    db: AsyncSession,
    *,
    plan: CuratedTripPlan,
    poi: CuratedPlanPoi,
    admin_id: uuid.UUID,
    values: Mapping[str, Any],
    expected_version: int | None = None,
) -> CuratedPlanPoi:
    _require_values(values)
    _check_version(actual=poi.version, expected=expected_version)
    _reject_canonical_poi_projection_edit(poi)
    if "feature_id" in values:
        poi.feature_id = _optional_feature_id(values.get("feature_id"))
    if "feature_snapshot" in values:
        poi.feature_snapshot = dict(_mapping(values.get("feature_snapshot")))
    for field in (
        "day_index",
        "sort_order",
        "memo",
        "budget_amount",
        "currency",
        "user_url",
        "custom_marker_color",
        "custom_marker_icon",
    ):
        if field in values:
            setattr(poi, field, values[field])
    poi.version += 1
    plan.updated_by_admin_id = admin_id
    plan.version += 1
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise NoticePlanConflictError(
            "같은 위치(day_index, sort_order)에 이미 POI가 있습니다."
        ) from exc
    await db.refresh(poi)
    return poi


async def soft_delete_admin_poi(
    db: AsyncSession,
    *,
    plan: CuratedTripPlan,
    poi: CuratedPlanPoi,
    admin_id: uuid.UUID,
    expected_version: int | None = None,
) -> CuratedPlanPoi:
    _check_version(actual=poi.version, expected=expected_version)
    _reject_canonical_poi_projection_edit(poi)
    poi.deleted_at = datetime.now(UTC)
    poi.version += 1
    plan.updated_by_admin_id = admin_id
    plan.version += 1
    await db.flush()
    await db.refresh(poi)
    return poi


async def reorder_admin_pois(
    db: AsyncSession,
    *,
    plan: CuratedTripPlan,
    admin_id: uuid.UUID,
    items: list[Mapping[str, Any]],
) -> list[CuratedPlanPoi]:
    ids = [cast(uuid.UUID, item["notice_poi_id"]) for item in items]
    if len(set(ids)) != len(ids):
        raise NoticePlanPolicyError("중복된 POI가 있습니다.")
    result = await db.execute(
        select(CuratedPlanPoi).where(
            CuratedPlanPoi.curated_plan_id == plan.curated_plan_id,
            CuratedPlanPoi.curated_poi_id.in_(ids),
            CuratedPlanPoi.deleted_at.is_(None),
        )
    )
    rows = list(result.scalars())
    by_id = {row.curated_poi_id: row for row in rows}
    if set(by_id) != set(ids):
        raise NoticePlanNotFoundError("추천 여행 POI를 찾을 수 없습니다.")
    if any(row.source_curation_item_id is not None for row in rows):
        raise NoticePlanPolicyError(
            "Map canonical POI는 import refresh만 변경·삭제·재정렬할 수 있습니다."
        )

    # `uq_curated_plan_pois_plan_day_sort`는 partial unique index라 non-deferrable —
    # row-by-row UPDATE 중간 상태에서 검사된다. 두 POI를 swap(A:001↔B:002)하면
    # A→002 UPDATE가 아직 안 옮겨진 B의 002와 충돌한다. 따라서 2단계로 적용한다:
    # (1) 먼저 모든 대상 POI의 sort_order를 plan 안에서 절대 안 겹치는 임시값으로
    #     옮겨 flush, (2) 그 다음 실제 (day_index, sort_order)로 옮겨 flush.
    try:
        for idx, item in enumerate(items):
            poi = by_id[cast(uuid.UUID, item["notice_poi_id"])]
            poi.sort_order = f"tmp-{idx}-{poi.curated_poi_id}"
        await db.flush()
        for item in items:
            poi = by_id[cast(uuid.UUID, item["notice_poi_id"])]
            poi.day_index = cast(int, item["day_index"])
            poi.sort_order = cast(str, item["sort_order"])
            poi.version += 1
        plan.updated_by_admin_id = admin_id
        plan.version += 1
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise NoticePlanConflictError(
            "같은 위치(day_index, sort_order)에 이미 POI가 있습니다."
        ) from exc
    ordered = [by_id[poi_id] for poi_id in ids]
    for poi in ordered:
        await db.refresh(poi)
    return ordered


async def copy_plan_to_trip(
    db: AsyncSession,
    *,
    notice_plan_id: uuid.UUID,
    user_id: uuid.UUID,
    target_trip_id: uuid.UUID | None,
    trip_title: str | None,
    trip_start_date: date | None,
    trip_end_date: date | None,
    poi_ids: list[uuid.UUID],
) -> tuple[Trip, bool, list[uuid.UUID], int]:
    """notice plan 의 POI 를 사용자 trip 으로 복사.

    - target_trip_id 가 있으면 그 trip(소유자 검증)에 추가, 없으면 새 trip 생성.
    - poi_ids 가 비어 있으면 plan 전체 POI 복사, 있으면 해당 POI 만.
    - curated_poi 의 curated_plan_attachments 도 새 trip_poi 로 복제.
    반환: (trip, created_trip, copied_poi_ids, copied_attachment_count)
    """
    plan = await get_published_plan(db, notice_plan_id=notice_plan_id)
    source_pois = await list_plan_pois(db, notice_plan_id=notice_plan_id)
    if poi_ids:
        wanted = set(poi_ids)
        source_pois = [p for p in source_pois if p.curated_poi_id in wanted]
        if len(source_pois) != len(wanted):
            raise NoticePlanCopyError("일부 POI 가 추천 여행에 없습니다.")
    if not source_pois:
        raise NoticePlanCopyError("복사할 POI 가 없습니다.")

    # 대상 trip 결정
    created_trip = False
    if target_trip_id is not None:
        trip = await db.scalar(
            select(Trip).where(Trip.trip_id == target_trip_id, Trip.deleted_at.is_(None))
        )
        if trip is None:
            raise NoticePlanNotFoundError("대상 여행을 찾을 수 없습니다.")
        if trip.owner_user_id != user_id:
            raise NoticePlanCopyError("대상 여행에 대한 권한이 없습니다.")
    else:
        trip = Trip(
            owner_user_id=user_id,
            title=trip_title or plan.title,
            description=plan.summary,
            region_hint=plan.destination,
            start_date=trip_start_date,
            end_date=trip_end_date,
            visibility="private",
        )
        db.add(trip)
        await db.flush()
        created_trip = True

    copied_poi_ids: list[uuid.UUID] = []
    copied_attachment_count = 0

    # day_index 별 마지막 sort_order 추적 (LexoRank append)
    last_sort: dict[int, str | None] = {}

    for src in source_pois:
        day_index = src.day_index
        # trip_day 보장
        day = await db.scalar(
            select(TripDay).where(TripDay.trip_id == trip.trip_id, TripDay.day_index == day_index)
        )
        if day is None:
            db.add(TripDay(trip_id=trip.trip_id, day_index=day_index))
            await db.flush()

        if day_index not in last_sort:
            last_sort[day_index] = await _max_sort_order(db, trip.trip_id, day_index)
        new_sort = lexorank.between(last_sort[day_index], None)
        last_sort[day_index] = new_sort

        new_poi = TripDayPoi(
            trip_id=trip.trip_id,
            day_index=day_index,
            sort_order=new_sort,
            feature_id=src.feature_id,
            feature_snapshot=src.feature_snapshot,
            custom_marker_color=src.custom_marker_color,
            custom_marker_icon=src.custom_marker_icon,
            user_note=src.memo,
            budget_amount=src.budget_amount,
            currency=src.currency,
            user_url=src.user_url,
            added_by_user_id=user_id,
        )
        db.add(new_poi)
        await db.flush()
        copied_poi_ids.append(new_poi.attachment_id)

        # 첨부 복제 (curated_poi → 새 trip_poi)
        attachments = await db.execute(
            select(CuratedPlanAttachment).where(
                CuratedPlanAttachment.curated_poi_id == src.curated_poi_id,
                CuratedPlanAttachment.deleted_at.is_(None),
            )
        )
        for att in attachments.scalars():
            db.add(
                CuratedPlanAttachment(
                    trip_poi_id=new_poi.attachment_id,
                    source_attachment_id=att.attachment_id,
                    bucket=att.bucket,
                    storage_key=att.storage_key,
                    original_filename=att.original_filename,
                    content_type=att.content_type,
                    byte_size=att.byte_size,
                    public_url=att.public_url,
                    checksum_sha256=att.checksum_sha256,
                    role=att.role,
                    description=att.description,
                    sort_order=att.sort_order,
                    uploaded_by_user_id=user_id,
                )
            )
            copied_attachment_count += 1

    await db.commit()
    await db.refresh(trip)
    return trip, created_trip, copied_poi_ids, copied_attachment_count


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


async def ensure_plan_poi_for_feature(
    db: AsyncSession,
    *,
    curated_plan_id: uuid.UUID,
    feature_id: str,
    day_index: int,
    sort_order: str,
    feature_snapshot: dict[str, Any] | None = None,
    memo: str | None = None,
    budget_amount: Any | None = None,
    currency: str = "KRW",
    user_url: str | None = None,
    custom_marker_color: str | None = None,
    custom_marker_icon: str | None = None,
) -> CuratedPlanPoi:
    """외부 연계에서 feature-backed curated POI를 보장.

    POI 자체는 `feature_id` 없이도 존재할 수 있다. 다만 kor-travel-map import처럼
    feature를 알고 들어오는 경우, 같은 plan에 해당 feature POI가 이미 있으면 재사용하고
    없으면 새 `curated_plan_pois` row를 만든다.
    """
    normalized_feature_id = _optional_feature_id(feature_id)
    if normalized_feature_id is None:
        raise NoticePlanPolicyError("feature 연계 POI 생성에는 feature_id가 필요합니다.")
    existing = await db.scalar(
        select(CuratedPlanPoi).where(
            CuratedPlanPoi.curated_plan_id == curated_plan_id,
            CuratedPlanPoi.feature_id == normalized_feature_id,
            CuratedPlanPoi.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing

    poi = CuratedPlanPoi(
        curated_plan_id=curated_plan_id,
        day_index=day_index,
        sort_order=sort_order,
        feature_id=normalized_feature_id,
        feature_snapshot=feature_snapshot or {},
        memo=memo,
        budget_amount=budget_amount,
        currency=currency,
        user_url=user_url,
        custom_marker_color=custom_marker_color,
        custom_marker_icon=custom_marker_icon,
    )
    db.add(poi)
    await db.flush()
    return poi


async def _next_curated_sort_order(
    db: AsyncSession,
    curated_plan_id: uuid.UUID,
    day_index: int,
    last_sort_by_day: dict[int, str | None],
) -> str:
    if day_index not in last_sort_by_day:
        last_sort_by_day[day_index] = await _max_curated_sort_order(db, curated_plan_id, day_index)
    sort_order = lexorank.between(last_sort_by_day[day_index], None)
    last_sort_by_day[day_index] = sort_order
    return sort_order


async def _max_curated_sort_order(
    db: AsyncSession, curated_plan_id: uuid.UUID, day_index: int
) -> str | None:
    result = await db.execute(
        select(CuratedPlanPoi.sort_order)
        .where(
            CuratedPlanPoi.curated_plan_id == curated_plan_id,
            CuratedPlanPoi.day_index == day_index,
            CuratedPlanPoi.deleted_at.is_(None),
        )
        .order_by(CuratedPlanPoi.sort_order.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# Admin 용 생성 helper (Sprint 3 admin UI 보강 전 최소 — seed/테스트용)
async def create_plan_with_pois(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID,
    slug: str,
    title: str,
    category: str = "recommended",
    summary: str | None = None,
    destination: str | None = None,
    is_published: bool = True,
    pois: list[dict[str, Any]] | None = None,
) -> CuratedTripPlan:
    plan = CuratedTripPlan(
        slug=slug,
        title=title,
        category=category,
        summary=summary,
        destination=destination,
        is_published=is_published,
        created_by_admin_id=admin_id,
        updated_by_admin_id=admin_id,
    )
    db.add(plan)
    await db.flush()
    for item in pois or []:
        feature_id = _optional_feature_id(item.get("feature_id"))
        if feature_id is not None:
            await ensure_plan_poi_for_feature(
                db,
                curated_plan_id=plan.curated_plan_id,
                day_index=item.get("day_index", 1),
                sort_order=item["sort_order"],
                feature_id=feature_id,
                feature_snapshot=item.get("feature_snapshot", {}),
                memo=item.get("memo"),
                budget_amount=item.get("budget_amount"),
                currency=item.get("currency", "KRW"),
                user_url=item.get("user_url"),
                custom_marker_color=item.get("custom_marker_color"),
                custom_marker_icon=item.get("custom_marker_icon"),
            )
            continue
        db.add(
            CuratedPlanPoi(
                curated_plan_id=plan.curated_plan_id,
                day_index=item.get("day_index", 1),
                sort_order=item["sort_order"],
                feature_id=None,
                feature_snapshot=item.get("feature_snapshot", {}),
                memo=item.get("memo"),
                budget_amount=item.get("budget_amount"),
                currency=item.get("currency", "KRW"),
                user_url=item.get("user_url"),
                custom_marker_color=item.get("custom_marker_color"),
                custom_marker_icon=item.get("custom_marker_icon"),
            )
        )
    await db.commit()
    await db.refresh(plan)
    return plan
