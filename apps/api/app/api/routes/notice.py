from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.auth import require_current_user
from app.db.session import get_db
from app.models.trip import NoticePlan, NoticePoi, PlanPoiAttachment
from app.models.user import User
from app.schemas.notice import (
    NoticePlanCopyRequest,
    NoticePlanCopyResponse,
    NoticePlanListResponse,
    NoticePlanResponse,
    NoticePoiResponse,
)
from app.services.notice_plan import (
    NoticePlanAccessDeniedError,
    NoticePlanNotFoundError,
    copy_notice_plan_to_trip,
)
from app.services.plan_poi_attachment import (
    attachments_by_notice_plan,
    attachments_by_notice_poi,
    to_attachment_response,
)

router = APIRouter(prefix="/notice-plans", tags=["notice-plans"])


@router.get("", response_model=NoticePlanListResponse)
def list_notice_plans(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_current_user)],
    category: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> NoticePlanListResponse:
    query = select(NoticePlan).where(
        NoticePlan.deleted_at.is_(None),
        NoticePlan.is_published.is_(True),
    )
    if category:
        query = query.where(NoticePlan.category == category)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    plans = db.scalars(
        query.order_by(NoticePlan.updated_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    pois_by_plan = _pois_by_plan(db, [plan.id for plan in plans])
    plan_attachments = attachments_by_notice_plan(db, [plan.id for plan in plans])
    poi_ids = [poi.id for pois in pois_by_plan.values() for poi in pois]
    poi_attachments = attachments_by_notice_poi(db, poi_ids)

    return NoticePlanListResponse(
        items=[
            _to_notice_plan_response(
                plan,
                pois_by_plan.get(plan.id, []),
                attachments=plan_attachments.get(plan.id, []),
                poi_attachments_by_poi=poi_attachments,
            )
            for plan in plans
        ],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{plan_id}", response_model=NoticePlanResponse)
def get_notice_plan(
    plan_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_current_user)],
) -> NoticePlanResponse:
    plan = _published_notice_plan_or_404(db, plan_id)
    pois = _notice_pois(db, plan.id)
    return _to_notice_plan_response(
        plan,
        pois,
        attachments=attachments_by_notice_plan(db, [plan.id]).get(plan.id, []),
        poi_attachments_by_poi=attachments_by_notice_poi(db, [poi.id for poi in pois]),
    )


@router.post("/{plan_id}/copy", response_model=NoticePlanCopyResponse)
def copy_notice_plan(
    plan_id: UUID,
    payload: NoticePlanCopyRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_current_user)],
) -> NoticePlanCopyResponse:
    plan = _published_notice_plan_or_404(db, plan_id)
    try:
        return copy_notice_plan_to_trip(
            db,
            current_user=current_user,
            notice_plan=plan,
            payload=payload,
        )
    except NoticePlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoticePlanAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def _published_notice_plan_or_404(db: Session, plan_id: UUID) -> NoticePlan:
    plan = db.get(NoticePlan, plan_id)
    if plan is None or plan.deleted_at is not None or not plan.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공지 계획을 찾을 수 없다.",
        )
    return plan


def _notice_pois(db: Session, plan_id: UUID) -> list[NoticePoi]:
    return list(
        db.scalars(
            select(NoticePoi)
            .where(NoticePoi.notice_plan_id == plan_id, NoticePoi.deleted_at.is_(None))
            .order_by(NoticePoi.day_index.asc(), NoticePoi.sort_order.asc())
        ).all()
    )


def _pois_by_plan(db: Session, plan_ids: list[UUID]) -> dict[UUID, list[NoticePoi]]:
    if not plan_ids:
        return {}
    pois = db.scalars(
        select(NoticePoi)
        .where(NoticePoi.notice_plan_id.in_(plan_ids), NoticePoi.deleted_at.is_(None))
        .order_by(NoticePoi.day_index.asc(), NoticePoi.sort_order.asc())
    ).all()
    grouped: dict[UUID, list[NoticePoi]] = {}
    for poi in pois:
        grouped.setdefault(poi.notice_plan_id, []).append(poi)
    return grouped


def _to_notice_plan_response(
    plan: NoticePlan,
    pois: list[NoticePoi],
    *,
    attachments: list[PlanPoiAttachment] | None = None,
    poi_attachments_by_poi: dict[UUID, list[PlanPoiAttachment]] | None = None,
) -> NoticePlanResponse:
    resolved_attachments = attachments or []
    resolved_poi_attachments = poi_attachments_by_poi or {}
    return NoticePlanResponse(
        id=plan.id,
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
        attachments=[to_attachment_response(attachment) for attachment in resolved_attachments],
        pois=[
            _to_notice_poi_response(poi, resolved_poi_attachments.get(poi.id, []))
            for poi in pois
        ],
    )


def _to_notice_poi_response(
    poi: NoticePoi,
    attachments: list[PlanPoiAttachment] | None = None,
) -> NoticePoiResponse:
    resolved_attachments = attachments or []
    return NoticePoiResponse(
        id=poi.id,
        notice_plan_id=poi.notice_plan_id,
        day_index=poi.day_index,
        sort_order=poi.sort_order,
        feature_id=poi.feature_id,
        map_feature_id=poi.map_feature_id,
        snapshot=poi.snapshot,
        memo=poi.memo,
        budget=poi.budget,
        currency=poi.currency,
        user_url=poi.user_url,
        custom_marker_color=poi.custom_marker_color,
        custom_marker_icon=poi.custom_marker_icon,
        version=poi.version,
        created_at=poi.created_at,
        updated_at=poi.updated_at,
        attachments=[to_attachment_response(attachment) for attachment in resolved_attachments],
    )
