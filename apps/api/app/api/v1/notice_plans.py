"""`/notice-plans/*` — 추천 여행 listing + 상세 + trip 으로 copy (ADR-013).

`docs/api/notice-plans.md`. notice plan ≠ notice feature.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUserId, DbSession
from app.schemas.envelope import Envelope
from app.schemas.notice import (
    NoticePlanCopyRequest,
    NoticePlanCopyResponse,
    NoticePlanResponse,
    NoticePoiResponse,
)
from app.services.notice_plan import (
    NoticePlanCopyError,
    NoticePlanNotFoundError,
    copy_plan_to_trip,
    get_published_plan,
    list_plan_pois,
    list_published_plans,
)

router = APIRouter(prefix="/notice-plans", tags=["notice-plans"])


def _poi_to_response(poi) -> NoticePoiResponse:  # type: ignore[no-untyped-def]
    return NoticePoiResponse(
        notice_poi_id=poi.notice_poi_id,
        notice_plan_id=poi.notice_plan_id,
        day_index=poi.day_index,
        sort_order=poi.sort_order,
        feature_id=poi.feature_id,
        feature_snapshot=poi.feature_snapshot,
        memo=poi.memo,
        budget_amount=poi.budget_amount,
        currency=poi.currency,
        user_url=poi.user_url,
        custom_marker_color=poi.custom_marker_color,
        custom_marker_icon=poi.custom_marker_icon,
        version=poi.version,
        created_at=poi.created_at,
        updated_at=poi.updated_at,
    )


def _plan_to_response(plan, pois) -> NoticePlanResponse:  # type: ignore[no-untyped-def]
    return NoticePlanResponse(
        notice_plan_id=plan.notice_plan_id,
        slug=plan.slug,
        title=plan.title,
        category=plan.category,
        summary=plan.summary,
        source_name=plan.source_name,
        destination=plan.destination,
        starts_on=plan.starts_on,
        ends_on=plan.ends_on,
        is_published=plan.is_published,
        version=plan.version,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        pois=[_poi_to_response(p) for p in pois],
    )


@router.get("", response_model=Envelope[list[NoticePlanResponse]])
async def list_plans(
    db: DbSession,
    category: str | None = None,
    limit: int = 50,
) -> Envelope[list[NoticePlanResponse]]:
    plans = await list_published_plans(db, category=category, limit=limit)
    # 목록은 POI 없이 (경량). 상세에서 POI 포함.
    return Envelope.of([_plan_to_response(p, []) for p in plans])


@router.get("/{notice_plan_id}", response_model=Envelope[NoticePlanResponse])
async def get_plan(notice_plan_id: uuid.UUID, db: DbSession) -> Envelope[NoticePlanResponse]:
    try:
        plan = await get_published_plan(db, notice_plan_id=notice_plan_id)
    except NoticePlanNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    pois = await list_plan_pois(db, notice_plan_id=notice_plan_id)
    return Envelope.of(_plan_to_response(plan, pois))


@router.post(
    "/{notice_plan_id}/copy",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[NoticePlanCopyResponse],
)
async def copy_plan(
    notice_plan_id: uuid.UUID,
    body: NoticePlanCopyRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[NoticePlanCopyResponse]:
    try:
        trip, created, copied_poi_ids, attachment_count = await copy_plan_to_trip(
            db,
            notice_plan_id=notice_plan_id,
            user_id=uuid.UUID(current_user_id),
            target_trip_id=body.target_trip_id,
            trip_title=body.trip_title,
            trip_start_date=body.trip_start_date,
            trip_end_date=body.trip_end_date,
            poi_ids=body.poi_ids,
        )
    except NoticePlanNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except NoticePlanCopyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(
        NoticePlanCopyResponse(
            trip_id=trip.trip_id,
            created_trip=created,
            copied_poi_ids=copied_poi_ids,
            copied_attachment_count=attachment_count,
        )
    )
