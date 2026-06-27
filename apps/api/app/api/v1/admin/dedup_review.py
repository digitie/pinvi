"""`/admin/dedup-review/*` — kor-travel-map dedup review read proxy."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError

from app.api.v1.admin.ops_proxy import map_ops_errors, next_cursor, parse_request_id
from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminDedupDecisionRequest,
    AdminDedupDecisionResponse,
    AdminDedupReviewPagedResponse,
    AdminDedupReviewRecord,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit

router = APIRouter(prefix="/admin/dedup-review", tags=["admin"])


@router.get("", response_model=Envelope[AdminDedupReviewPagedResponse])
async def list_dedup_reviews(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    provider: Annotated[list[str] | None, Query()] = None,
    dataset_key: Annotated[list[str] | None, Query()] = None,
    kind: Annotated[list[str] | None, Query()] = None,
    category: Annotated[list[str] | None, Query()] = None,
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    max_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    q: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> Envelope[AdminDedupReviewPagedResponse]:
    """kor-travel-map `/v1/admin/dedup-reviews` queue proxy."""
    with map_ops_errors(message_subject="kor_travel_map dedup review"):
        payload = await admin_client.list_dedup_reviews(
            statuses=status_filter,
            providers=provider,
            dataset_keys=dataset_key,
            kinds=kind,
            categories=category,
            min_score=min_score,
            max_score=max_score,
            q=q,
            page_size=page_size,
            cursor=cursor,
        )
    data = payload.get("data")
    meta = payload.get("meta")
    if not isinstance(data, dict) or not isinstance(meta, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map dedup review 응답 형식이 올바르지 않습니다.",
            },
        )
    items = data.get("items")
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map dedup review 목록에 items가 없습니다.",
            },
        )
    try:
        records = [AdminDedupReviewRecord.model_validate(item) for item in items]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map dedup review item 형식이 올바르지 않습니다.",
            },
        ) from exc
    return Envelope.of(
        AdminDedupReviewPagedResponse(
            items=records,
            page_size=page_size,
            next_cursor=next_cursor(meta),
        )
    )


@router.post("/{review_id}/verdict", response_model=Envelope[AdminDedupDecisionResponse])
async def decide_dedup_review(
    review_id: str,
    body: AdminDedupDecisionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    admin_client: KorTravelMapAdminClientDep,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminDedupDecisionResponse]:
    """kor-travel-map dedup review verdict relay + Pinvi audit."""
    reason = body.kor_travel_map_reason or body.access_reason
    with map_ops_errors(message_subject="kor_travel_map dedup decision"):
        data = await admin_client.decide_dedup_review(
            review_id,
            decision=body.decision,
            decision_reason=reason,
            master_feature_id=body.master_feature_id,
            reviewed_by="pinvi-admin",
        )
    try:
        result = AdminDedupDecisionResponse.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map dedup decision 응답 형식이 올바르지 않습니다.",
            },
        ) from exc

    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="dedup_review.decide",
        resource_type="dedup_review",
        resource_id=review_id,
        before_state=None,
        after_state={
            "decision": result.decision,
            "changed": result.changed,
            "master_feature_id": result.master_feature_id,
            "loser_feature_id": result.loser_feature_id,
            "merge_id": result.merge_id,
        },
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=parse_request_id(x_request_id),
    )
    await db.commit()
    return Envelope.of(result)
