"""추천 여행(curated trip plan) 도메인 — listing + 상세 + trip 으로 copy.

외부 `/notice-plans` API 이름은 호환 유지한다. 내부 schema는 ADR-029에 따라
`curated_trip_plans` / `curated_plan_pois` / `curated_plan_attachments`를 쓴다.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
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
            feature_id=src.feature_id or f"curated:{src.curated_poi_id}",
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
        db.add(
            CuratedPlanPoi(
                curated_plan_id=plan.curated_plan_id,
                day_index=item.get("day_index", 1),
                sort_order=item["sort_order"],
                feature_id=item.get("feature_id"),
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
