"""`/admin/feature-requests/*` — 사용자 feature 제안 검토 큐 (T-179).

사용자 제안(`app.feature_suggestions`, T-177)을 Admin이 검토해 승인/거절한다. correction/closure
새 장소 승인은 Map `/v1/service/feature-requests` 범용 큐에 immutable request를 제출하고,
correction/closure만 kor_travel_map `/v1/admin/features*` change API(전송 client = T-180)로
전달한다. 반환된 feature_id/request_id/state를 `kor_travel_map_ref`에 저장한다.

§7 합의 5건 (kor_travel_map T-217c **확정**, 2026-06-11, kor_travel_map `docs/decisions.md` ADR-051):
- **review_mode**: kor_travel_map 설정(기본 `require_review` 2단 검토 → status=approved, `immediate`면 added)
- **idempotency_key** = suggestion `request_id` (new_place body와 `Idempotency-Key`가 같은 UUID)
- **출처 태깅** = correction/closure만 operator 고정 `"pinvi-admin"`(admin id 미노출, 익명 D-11) +
  reason `[suggestion:<request_id>]` prefix를 change-requests 큐에 남긴다.
- **closure** = soft `DELETE`(provider 재적재 부활 차단). 일시 비활성 deactivate는 미사용
- **admin 인증** = 인프라 계층(12701 `/v1/admin/*`, SSO/IP allowlist; service token은 선택 pass-through)
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapFeatureNotFound,
    KorTravelMapPreconditionFailed,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
)
from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
from app.clients.kor_travel_map_feature_request import (
    FeatureRequestQueueContractError,
    FeatureRequestQueueProblem,
    FeatureRequestQueueUnavailable,
    FeatureRequestServiceClient,
    get_feature_request_service_client,
)
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.feature_suggestion import FeatureSuggestion
from app.models.user import User
from app.schemas.admin_feature_request import (
    AdminFeatureRequestApprove,
    AdminFeatureRequestPagedResponse,
    AdminFeatureRequestReject,
    AdminFeatureRequestResult,
    AdminFeatureRequestSummary,
)
from app.schemas.envelope import Envelope
from app.schemas.feature import (
    Coord,
    ExternalRef,
    FeatureKind,
    FeatureRequestStatus,
    FeatureRequestType,
    FeatureSuggestionKind,
)
from app.services.admin_audit import append_admin_audit
from app.services.admin_users import mask_email
from app.services.feature_request import reconcile_pois_for_external_ref

router = APIRouter(prefix="/admin/feature-requests", tags=["admin"])


def _parse_request_id(value: str | None) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "X-Request-Id 형식이 올바르지 않습니다.",
            },
        ) from exc


@contextmanager
def _map_admin_errors() -> Iterator[None]:
    """kor_travel_map admin 호출 도메인 예외 → HTTP status."""
    try:
        yield
    except KorTravelMapFeatureNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "대상 feature를 kor_travel_map에서 찾을 수 없습니다.",
            },
        ) from exc
    except KorTravelMapRateLimited as exc:
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": "kor_travel_map 요청이 많아 잠시 후 다시 시도하세요.",
            },
            headers=headers,
        ) from exc
    except KorTravelMapPreconditionFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "code": exc.code or "PRECONDITION_FAILED",
                "message": "feature가 변경되었습니다. 최신 정보를 확인한 뒤 다시 시도하세요.",
            },
        ) from exc
    except KorTravelMapBadRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": exc.code or "VALIDATION_ERROR",
                "message": "kor_travel_map가 feature change 요청을 거절했습니다.",
            },
        ) from exc
    except KorTravelMapUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": "kor_travel_map admin 서비스가 일시적으로 사용 불가합니다.",
            },
        ) from exc


@contextmanager
def _map_feature_request_errors() -> Iterator[None]:
    """Map service Feature 요청 오류를 PinVi admin 승인 결과로 안전하게 투영한다."""

    try:
        yield
    except FeatureRequestQueueProblem as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": exc.code or "MAP_FEATURE_REQUEST_CONFLICT",
                    "message": "지도 Feature 요청 큐가 이 제출을 충돌로 거절했습니다.",
                },
            ) from exc
        if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": exc.code or "VALIDATION_ERROR",
                    "message": "지도 Feature 요청 형식이 올바르지 않습니다.",
                },
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "MAP_FEATURE_REQUEST_QUEUE_UNAVAILABLE",
                "message": "지도 Feature 요청 큐 인증 또는 활성화 상태를 확인할 수 없습니다.",
            },
        ) from exc
    except (FeatureRequestQueueUnavailable, FeatureRequestQueueContractError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "MAP_FEATURE_REQUEST_QUEUE_UNAVAILABLE",
                "message": "지도 Feature 요청 큐가 일시적으로 사용 불가합니다.",
            },
        ) from exc


def _summary(row: FeatureSuggestion, email: str | None) -> AdminFeatureRequestSummary:
    return AdminFeatureRequestSummary(
        request_id=row.request_id,
        requester_user_id=row.requester_user_id,
        requester_email_masked=mask_email(email) if email else None,
        type=cast(FeatureRequestType, row.suggestion_type),
        kind=cast(FeatureKind, row.kind),
        name=row.name,
        coord=Coord(lon=float(row.lng), lat=float(row.lat)),
        categories=row.categories,
        note=row.note,
        target_feature_id=row.target_feature_id,
        source=row.source,
        external_ref=ExternalRef.model_validate(row.external_ref) if row.external_ref else None,
        status=cast(FeatureRequestStatus, row.status),
        kor_travel_map_ref=row.kor_travel_map_ref,
        reviewed_by_admin_id=row.reviewed_by_admin_id,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def _result(row: FeatureSuggestion) -> AdminFeatureRequestResult:
    return AdminFeatureRequestResult(
        request_id=row.request_id,
        status=cast(FeatureRequestStatus, row.status),
        kor_travel_map_ref=row.kor_travel_map_ref,
        reviewed_by_admin_id=row.reviewed_by_admin_id,
        resolved_at=row.resolved_at,
    )


async def _load_pending(db: AsyncSession, request_id: uuid.UUID) -> FeatureSuggestion:
    suggestion = await db.scalar(
        select(FeatureSuggestion)
        .where(FeatureSuggestion.request_id == request_id)
        .with_for_update()
    )
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Feature request not found."},
        )
    if suggestion.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INVALID_STATE",
                "message": f"이미 처리된 제안입니다(status={suggestion.status}).",
            },
        )
    return suggestion


@router.get("", response_model=Envelope[AdminFeatureRequestPagedResponse])
async def list_feature_requests_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    status_filter: Annotated[FeatureRequestStatus | None, Query(alias="status")] = "pending",
    page: int = 1,
    limit: int = 50,
) -> Envelope[AdminFeatureRequestPagedResponse]:
    """검토 큐 목록 — 기본 pending. 오래된 순(검토 FIFO). 요청자 이메일은 마스킹."""
    page = max(1, page)
    limit = min(100, max(1, limit))
    rows_q = select(FeatureSuggestion, User.email).join(
        User, User.user_id == FeatureSuggestion.requester_user_id
    )
    count_q = select(func.count(FeatureSuggestion.request_id))
    if status_filter is not None:
        rows_q = rows_q.where(FeatureSuggestion.status == status_filter)
        count_q = count_q.where(FeatureSuggestion.status == status_filter)
    rows_q = (
        rows_q.order_by(FeatureSuggestion.created_at.asc()).offset((page - 1) * limit).limit(limit)
    )
    total = int(await db.scalar(count_q) or 0)
    rows = (await db.execute(rows_q)).all()
    items = [_summary(row[0], row[1]) for row in rows]
    return Envelope.of(
        AdminFeatureRequestPagedResponse(items=items, total=total, page=page, limit=limit)
    )


@router.post("/{request_id}/approve", response_model=Envelope[AdminFeatureRequestResult])
async def approve_feature_request_endpoint(
    request_id: uuid.UUID,
    body: AdminFeatureRequestApprove,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminFeatureRequestResult]:
    """승인 — 새 장소는 Map service 큐, 변경/폐쇄는 Map admin change API로 전송한다.

    Map 호출이 성공하기 전에는 PinVi 제안/audit를 commit하지 않아 retry가 같은 immutable request UUID를
    재사용한다. Map queue 제출은 ``approved``(Map 검토 대기), identity exact conflict만 ``duplicate``다.
    """
    audit_request_id = _parse_request_id(x_request_id)
    suggestion = await _load_pending(db, request_id)
    stype = suggestion.suggestion_type
    if stype == "new_place":
        service_client = get_feature_request_service_client(request)
        try:
            FeatureRequestServiceClient.validate_submission(
                request_id=suggestion.request_id,
                kind=cast(FeatureSuggestionKind, suggestion.kind),
                name=suggestion.name,
                lon=float(suggestion.lng),
                lat=float(suggestion.lat),
                categories=list(suggestion.categories),
                note=suggestion.note,
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "MAP_FEATURE_REQUEST_PAYLOAD_INVALID",
                    "message": "Map 요청 큐 범위를 벗어난 기존 제안입니다. 거절 후 새 제안으로 접수하세요.",
                },
            ) from exc
        with _map_feature_request_errors():
            receipt = await service_client.submit(
                request_id=suggestion.request_id,
                kind=cast(FeatureSuggestionKind, suggestion.kind),
                name=suggestion.name,
                lon=float(suggestion.lng),
                lat=float(suggestion.lat),
                categories=list(suggestion.categories),
                note=suggestion.note,
                correlation_id=audit_request_id,
            )
        record: dict[str, Any] = {
            "feature_id": receipt.feature_id,
            "request_id": str(receipt.request_id),
            "status": receipt.status,
            "review_mode": "feature_request_queue",
            "action": "submit",
        }
    # 출처 태깅 (§7 #3 확정, kor_travel_map T-217c / D-11 익명): operator는 **고정 문자열**(admin id
    # 미노출), suggestion_id는 reason 머리에 `[suggestion:<id>]` prefix로 실어 change-requests
    # 큐에서 출처 식별. kor_travel_map는 개인정보를 저장하지 않고, 역추적은 Pinvi admin이 한다.
    elif stype == "correction":
        admin_client = get_kor_travel_map_admin_client(request)
        operator = "pinvi-admin"
        reason = f"[suggestion:{request_id}] {body.kor_travel_map_reason or body.access_reason}"
        if suggestion.target_feature_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "correction 제안에 target_feature_id가 없습니다.",
                },
            )
        if not any((body.name, body.category, body.marker_color, body.marker_icon)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "정보 수정 승인에는 하나 이상의 변경 필드가 필요합니다.",
                },
            )
        patch: dict[str, Any] = {"reason": reason, "operator": operator}
        if body.name:
            patch["name"] = body.name
        if body.category:
            patch["category"] = body.category
        if body.marker_color:
            patch["marker_color"] = body.marker_color
        if body.marker_icon:
            patch["marker_icon"] = body.marker_icon
        with _map_admin_errors():
            record = await admin_client.patch_feature(suggestion.target_feature_id, patch)
    else:  # closure
        admin_client = get_kor_travel_map_admin_client(request)
        operator = "pinvi-admin"
        reason = f"[suggestion:{request_id}] {body.kor_travel_map_reason or body.access_reason}"
        if suggestion.target_feature_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "closure 제안에 target_feature_id가 없습니다.",
                },
            )
        with _map_admin_errors():
            record = await admin_client.delete_feature(
                suggestion.target_feature_id, reason=reason, operator=operator
            )

    kor_travel_map_state = str(record.get("status") or "")
    # service queue는 Map admin 검토 전 pending으로 돌아오므로 PinVi 승인만 완료한 ``approved``로
    # 남긴다. identity exact conflict는 이미 존재하는 feature로 확정돼 ``duplicate``다.
    if stype == "new_place":
        new_status = "duplicate" if kor_travel_map_state == "exact_conflict" else "approved"
    else:
        # require_review면 kor_travel_map 큐 적재(approved), immediate/applied면 반영 완료(added).
        new_status = "added" if kor_travel_map_state == "applied" else "approved"
    before = {"status": suggestion.status}

    # ADR-054 post-approval reconciliation: feature가 실제로 반영(added)돼 feature_id가 생기면, 이
    # external_ref를 참조하던 미연결 POI들을 새 feature_id에 연결한다(라이브 feature만 연결해 broken 방지).
    # 한계(문서화): kor_travel_map review_mode=require_review이면 승인 시 status='approved'(not added)라
    # 여기서 연결하지 않는다. approved→added 전이를 Pinvi에 알리는 webhook/poll이 아직 없어(범위 밖) 그런
    # POI는 feature_id NULL(자유 snapshot POI)로 남는다 — 표시는 정상이며 broken이 아니다. 이후 같은
    # 외부 장소를 다시 pick하면 auto-fire가 'added' 제안을 만나 즉시 연결한다.
    feature_id_val = record.get("feature_id")
    ref = suggestion.external_ref
    reconciled = 0
    if (
        new_status in {"added", "duplicate"}
        and isinstance(feature_id_val, str)
        and feature_id_val
        and isinstance(ref, dict)
        and isinstance(ref.get("provider"), str)
        and isinstance(ref.get("external_id"), str)
    ):
        reconciled = await reconcile_pois_for_external_ref(
            db,
            provider=ref["provider"],
            external_id=ref["external_id"],
            feature_id=feature_id_val,
        )

    # kor_travel_map_ref는 완성된 뒤 한 번에 대입한다(JSONB 컬럼은 in-place 변경을 추적하지 않음).
    kor_travel_map_ref = {
        "feature_id": record.get("feature_id"),
        "request_id": record.get("request_id"),
        "state": kor_travel_map_state,
        "review_mode": record.get("review_mode"),
        "action": record.get("action"),
        "reconciled_poi_count": reconciled,
    }
    suggestion.status = new_status
    suggestion.kor_travel_map_ref = kor_travel_map_ref
    suggestion.reviewed_by_admin_id = admin.user_id
    suggestion.resolved_at = datetime.now(UTC)

    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="feature_request.approve",
        resource_type="feature_request",
        resource_id=str(request_id),
        before_state=before,
        after_state={"status": new_status, "kor_travel_map_ref": kor_travel_map_ref},
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=audit_request_id,
    )
    await db.commit()
    await db.refresh(suggestion)
    return Envelope.of(_result(suggestion))


@router.post("/{request_id}/reject", response_model=Envelope[AdminFeatureRequestResult])
async def reject_feature_request_endpoint(
    request_id: uuid.UUID,
    body: AdminFeatureRequestReject,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminFeatureRequestResult]:
    """거절 — kor_travel_map 호출 없이 상태만 rejected로. audit."""
    audit_request_id = _parse_request_id(x_request_id)
    suggestion = await _load_pending(db, request_id)
    before = {"status": suggestion.status}
    suggestion.status = "rejected"
    suggestion.reviewed_by_admin_id = admin.user_id
    suggestion.resolved_at = datetime.now(UTC)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="feature_request.reject",
        resource_type="feature_request",
        resource_id=str(request_id),
        before_state=before,
        after_state={"status": "rejected"},
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=audit_request_id,
    )
    await db.commit()
    await db.refresh(suggestion)
    return Envelope.of(_result(suggestion))
