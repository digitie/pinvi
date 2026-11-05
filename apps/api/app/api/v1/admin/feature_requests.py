"""사용자 Feature 제안 검토 — 신규 큐 제출·직접 변경·형식 검증·완료 이력 정리.

신규 장소는 Map service 큐에 immutable UUID로 제출한다. 수정·폐쇄는 현재 Map의
직접 command receipt를 소비한다. 입력·If-Match를 선저장하여 응답 유실 후에도
동일 Idempotency-Key와 fingerprint로 재생하며 미확정 명령은 거절·삭제하지 않는다.
dry-run은 외부 호출·상태 전이·감사 쓰기 없이 저장된 payload 형식만 검증한다.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapConflict,
    KorTravelMapError,
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
    AdminFeatureRequestReconcile,
    AdminFeatureRequestReconcileResult,
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


def _request_correlation_id(request: Request, header_value: str | None) -> uuid.UUID:
    """응답·audit·upstream 호출이 한 request ID를 공유하게 한다."""

    middleware_value = getattr(request.state, "request_id", None)
    return _parse_request_id(header_value if header_value is not None else middleware_value)


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
    except KorTravelMapConflict as exc:
        messages = {
            "LEGACY_FINGERPRINT_UNVERIFIABLE": "과거 Map 명령에는 필드 존재 기록이 없어 안전하게 확정할 수 없습니다. 운영 검토가 필요합니다.",
            "IDEMPOTENCY_KEY_REUSED": "저장된 Map 명령과 입력이 다릅니다. 기존 명령을 보존했습니다.",
        }
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code or "MAP_COMMAND_CONFLICT",
                "message": messages.get(
                    exc.code or "",
                    "Map 명령이 충돌했습니다. 기존 제출 내용으로 재시도하거나 운영 검토가 필요합니다.",
                ),
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
    except KorTravelMapError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "MAP_COMMAND_RECEIPT_INVALID",
                "message": "Map 처리 결과를 확인할 수 없습니다. 기존 제출 내용으로 다시 확인하세요.",
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


async def _load_request(db: AsyncSession, request_id: uuid.UUID) -> FeatureSuggestion:
    suggestion = await db.scalar(
        select(FeatureSuggestion)
        .where(FeatureSuggestion.request_id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Feature request not found."},
        )
    return suggestion


async def _load_pending(db: AsyncSession, request_id: uuid.UUID) -> FeatureSuggestion:
    suggestion = await _load_request(db, request_id)
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


def _direct_payload(
    suggestion: FeatureSuggestion, body: AdminFeatureRequestApprove
) -> dict[str, Any]:
    if suggestion.target_feature_id is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "변경·폐쇄 제안에 target_feature_id가 없습니다.",
            },
        )
    payload: dict[str, Any] = {
        "reason": f"[suggestion:{suggestion.request_id}] {body.kor_travel_map_reason or body.access_reason}",
        "operator": "pinvi-admin",
    }
    if suggestion.suggestion_type == "correction":
        fields = {
            key: value
            for key in ("name", "category", "marker_color", "marker_icon")
            if (value := getattr(body, key))
        }
        if not fields:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "정보 수정 승인에는 하나 이상의 변경 필드가 필요합니다.",
                },
            )
        payload.update(fields)
    return payload


def _dispatch_error(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": code, "message": message})


def _command_attempt_key(suggestion: FeatureSuggestion) -> str:
    ref = suggestion.kor_travel_map_ref or {}
    dispatch = ref.get("dispatch")
    raw = (
        dispatch.get("command_key", str(suggestion.request_id))
        if isinstance(dispatch, dict)
        else ref.get("next_command_key", str(suggestion.request_id))
    )
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise _dispatch_error(
            "MAP_COMMAND_PENDING", "저장된 명령 키의 운영 검토가 필요합니다."
        ) from exc


def _check_expected_attempt(
    suggestion: FeatureSuggestion,
    expected: uuid.UUID | None,
) -> None:
    current = _command_attempt_key(suggestion)
    ref = suggestion.kor_travel_map_ref or {}
    # 과거 소비자의 첫 시도만 호환한다. 한 번 전진한 시도는 명시 키 없이는 실행하지 않는다.
    initial_compat = (
        expected is None
        and current == str(suggestion.request_id)
        and "next_command_key" not in ref
        and "last_resolution" not in ref
        and "last_rejected_command" not in ref
    )
    if not initial_compat and (expected is None or str(expected) != current):
        raise _dispatch_error(
            "MAP_COMMAND_ATTEMPT_CHANGED",
            "검토 중 명령 시도가 변경되었습니다. 최신 제안을 다시 열어 확인하세요.",
        )


def _dispatch_identity(
    suggestion: FeatureSuggestion,
    *,
    current_actor: str,
) -> tuple[dict[str, Any], str, str]:
    value = (suggestion.kor_travel_map_ref or {}).get("dispatch")
    if not isinstance(value, dict):
        raise _dispatch_error("MAP_COMMAND_PENDING", "저장된 Map 명령의 운영 검토가 필요합니다.")
    actor = value.get("actor")
    if not isinstance(actor, str) or not actor:
        raise _dispatch_error(
            "MAP_COMMAND_ACTOR_UNVERIFIABLE",
            "과거 명령에 원래 Map 운영자 정보가 없어 자동 확인·해제할 수 없습니다. 운영 검토가 필요합니다.",
        )
    if actor != current_actor:
        raise _dispatch_error(
            "MAP_COMMAND_ACTOR_CHANGED",
            "원래 명령과 현재 Map 인증 운영자가 다릅니다. 명령을 보존했습니다.",
        )
    try:
        key = str(uuid.UUID(value["command_key"]))
        original = AdminFeatureRequestApprove.model_validate(value["input"])
        if (
            value.get("feature_id") != suggestion.target_feature_id
            or value.get("type") != suggestion.suggestion_type
            or not isinstance(value.get("expected_revision"), str)
            or value.get("payload") != _direct_payload(suggestion, original)
        ):
            raise ValueError("stored command mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        raise _dispatch_error(
            "MAP_COMMAND_PENDING",
            "저장된 Map 명령의 입력을 검증하지 못했습니다. 운영 검토가 필요합니다.",
        ) from exc
    return value, key, actor


async def _direct_submission(
    db: AsyncSession,
    suggestion: FeatureSuggestion,
    body: AdminFeatureRequestApprove,
    request: Request,
    admin: User,
    correlation_id: uuid.UUID,
) -> dict[str, Any]:
    """명령 payload·If-Match를 선저장하여 응답 유실 뒤에도 동일 command를 재생한다."""
    client = get_kor_travel_map_admin_client(request)
    payload = _direct_payload(suggestion, body)
    target_feature_id = suggestion.target_feature_id
    assert target_feature_id is not None
    approval_input = {
        key: value
        for key, value in body.model_dump(
            mode="json", exclude_none=True, exclude={"expected_command_key"}
        ).items()
        if value != ""
    }
    ref = suggestion.kor_travel_map_ref or {}
    dispatch = ref.get("dispatch")
    if dispatch is not None:
        if (
            not isinstance(dispatch, dict)
            or dispatch.get("input") != approval_input
            or dispatch.get("feature_id") != target_feature_id
            or dispatch.get("type") != suggestion.suggestion_type
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "MAP_COMMAND_PENDING",
                    "message": "결과 미확정 명령이 있습니다. 저장된 제출 내용으로 먼저 재시도하세요.",
                },
            )
        expected_revision = dispatch.get("expected_revision")
        if not isinstance(expected_revision, str) or not isinstance(dispatch.get("payload"), dict):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "MAP_COMMAND_PENDING",
                    "message": "저장된 Map 명령에 대한 운영 검토가 필요합니다.",
                },
            )
        _, command_key, _ = _dispatch_identity(suggestion, current_actor=client.actor)
        payload = dispatch["payload"]
    else:
        try:
            command_key = str(uuid.UUID(ref.get("next_command_key") or str(suggestion.request_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise _dispatch_error(
                "MAP_COMMAND_PENDING", "다음 Map 명령 키의 운영 검토가 필요합니다."
            ) from exc
        with _map_admin_errors():
            expected_revision = await client.get_feature_revision_etag(target_feature_id)
        suggestion.kor_travel_map_ref = {
            **ref,
            "dispatch": {
                "actor": client.actor,
                "command_key": command_key,
                "input": approval_input,
                "feature_id": target_feature_id,
                "type": suggestion.suggestion_type,
                "payload": payload,
                "expected_revision": expected_revision,
            },
        }
        prepared_dispatch = suggestion.kor_travel_map_ref["dispatch"]
        await append_admin_audit(
            db,
            actor_user_id=admin.user_id,
            action="feature_request.dispatch",
            resource_type="feature_request",
            resource_id=str(suggestion.request_id),
            before_state={"status": "pending"},
            after_state={
                "status": "pending",
                "expected_revision": expected_revision,
                "payload_sha256": hashlib.sha256(
                    json.dumps(payload, sort_keys=True).encode()
                ).hexdigest(),
            },
            access_reason=body.access_reason,
            target_pii_fields=None,
            ip_hash_input=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent"),
            request_id=correlation_id,
        )
        await db.commit()
        original_type = suggestion.suggestion_type
        suggestion = await _load_pending(db, suggestion.request_id)
        if (
            (suggestion.kor_travel_map_ref or {}).get("dispatch") != prepared_dispatch
            or suggestion.suggestion_type != original_type
            or suggestion.target_feature_id != target_feature_id
            or _direct_payload(suggestion, body) != payload
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "MAP_COMMAND_PENDING",
                    "message": "제안이 변경되어 저장된 명령의 운영 검토가 필요합니다.",
                },
            )
    with _map_admin_errors():
        try:
            if suggestion.suggestion_type == "correction":
                return await client.patch_feature(
                    target_feature_id,
                    payload,
                    expected_revision=expected_revision,
                    idempotency_key=command_key,
                )
            return await client.delete_feature(
                target_feature_id,
                reason=payload["reason"],
                operator="pinvi-admin",
                expected_revision=expected_revision,
                idempotency_key=command_key,
            )
        except (
            KorTravelMapBadRequest,
            KorTravelMapFeatureNotFound,
            KorTravelMapPreconditionFailed,
        ) as exc:
            # 확정 4xx 뒤에도 봉인 이력과 전진한 세대를 보존한다. 최초 request_id로 돌아가지 않는다.
            next_ref = dict(suggestion.kor_travel_map_ref or {})
            next_ref.pop("dispatch", None)
            next_ref["next_command_key"] = str(uuid.uuid4())
            next_ref["last_rejected_command"] = {
                "command_key": command_key,
                "actor": client.actor,
                "code": exc.code,
            }
            suggestion.kor_travel_map_ref = next_ref
            await db.commit()
            raise


async def _finalize_feature_request(
    db: AsyncSession,
    suggestion: FeatureSuggestion,
    record: dict[str, Any],
    request: Request,
    admin: User,
    audit_request_id: uuid.UUID,
    *,
    access_reason: str,
    audit_action: str = "feature_request.approve",
    resolution_info: dict[str, Any] | None = None,
) -> AdminFeatureRequestResult:
    stype = suggestion.suggestion_type
    request_id = suggestion.request_id
    kor_travel_map_state = str(record.get("status") or ("applied" if stype != "new_place" else ""))
    # 신규 장소의 approved는 Map 검토 대기이며 직접 명령의 added는 commit receipt가 확정한 결과다.
    if stype == "new_place":
        new_status = "duplicate" if kor_travel_map_state == "exact_conflict" else "approved"
    else:
        new_status = "added"
    before = {"status": suggestion.status}

    # 최종 Feature를 받은 경우에만 외부 참조 POI를 연결한다. 큐 검토 대기는 연결하지 않는다.
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

    if stype == "new_place":
        kor_travel_map_ref = {
            "feature_id": record.get("feature_id"),
            "request_id": record.get("request_id"),
            "state": kor_travel_map_state,
            "review_mode": "feature_request_queue",
            "action": "submit",
            "reconciled_poi_count": reconciled,
        }
    else:
        # receipt의 정본 필드는 보존하고 PinVi의 처리 방식만 명시한다.
        kor_travel_map_ref = {
            **record,
            "review_mode": "direct",
            "action": stype,
            "reconciled_poi_count": reconciled,
            "last_resolution": resolution_info
            or {
                "state": "completed",
                "actor": (suggestion.kor_travel_map_ref or {}).get("dispatch", {}).get("actor"),
                "command_key": (suggestion.kor_travel_map_ref or {})
                .get("dispatch", {})
                .get("command_key"),
            },
        }
    suggestion.status = new_status
    suggestion.kor_travel_map_ref = kor_travel_map_ref
    suggestion.reviewed_by_admin_id = admin.user_id
    suggestion.resolved_at = datetime.now(UTC)

    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action=audit_action,
        resource_type="feature_request",
        resource_id=str(request_id),
        before_state=before,
        after_state={"status": new_status, "kor_travel_map_ref": kor_travel_map_ref},
        access_reason=access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=audit_request_id,
    )
    await db.commit()
    await db.refresh(suggestion)
    return _result(suggestion)


@router.post("/{request_id}/approve", response_model=Envelope[AdminFeatureRequestResult])
async def approve_feature_request_endpoint(
    request_id: uuid.UUID,
    body: AdminFeatureRequestApprove,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    dry_run: Annotated[bool, Query()] = False,
) -> Envelope[AdminFeatureRequestResult]:
    """검증은 외부 부작용 없이 수행하고 승인은 immutable 명령으로 전송한다."""
    audit_request_id = _request_correlation_id(request, x_request_id)
    suggestion = await _load_pending(db, request_id)
    stype = suggestion.suggestion_type
    if stype != "new_place":
        _check_expected_attempt(suggestion, body.expected_command_key)
    if stype == "new_place":
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
                status_code=422,
                detail={
                    "code": "MAP_FEATURE_REQUEST_PAYLOAD_INVALID",
                    "message": "Map 요청 큐 범위를 벗어난 기존 제안입니다. 거절 후 새 제안으로 접수하세요.",
                },
            ) from exc
    else:
        _direct_payload(suggestion, body)
    if dry_run:
        return Envelope.of(_result(suggestion).model_copy(update={"dry_run": True}))
    if stype == "new_place":
        service_client = get_feature_request_service_client(request)
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
    else:
        record = await _direct_submission(db, suggestion, body, request, admin, audit_request_id)

    return Envelope.of(
        await _finalize_feature_request(
            db,
            suggestion,
            record,
            request,
            admin,
            audit_request_id,
            access_reason=body.access_reason,
        )
    )


def _known_resolution(
    suggestion: FeatureSuggestion,
) -> Literal["abandoned", "completed"] | None:
    ref = suggestion.kor_travel_map_ref or {}
    if ref.get("dispatch") is not None:
        return None
    saved = ref.get("last_resolution")
    if not isinstance(saved, dict):
        return None
    if saved.get("state") == "completed" and suggestion.status == "added":
        return "completed"
    if saved.get("state") == "abandoned" and suggestion.status == "pending":
        try:
            next_key = str(uuid.UUID(ref["next_command_key"]))
            old_key = str(uuid.UUID(saved["command_key"]))
            if next_key != old_key and isinstance(saved.get("actor"), str):
                return "abandoned"
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
    return None


def _reconciliation_result(
    suggestion: FeatureSuggestion,
    resolution: Literal["abandoned", "pending", "completed"],
) -> Envelope[AdminFeatureRequestReconcileResult]:
    return Envelope.of(
        AdminFeatureRequestReconcileResult(
            **_result(suggestion).model_dump(),
            resolution=resolution,
        )
    )


@router.post(
    "/{request_id}/reconcile-map-command",
    response_model=Envelope[AdminFeatureRequestReconcileResult],
)
async def reconcile_feature_request_command_endpoint(
    request_id: uuid.UUID,
    body: AdminFeatureRequestReconcile,
    request: Request,
    db: DbSession,
    admin: Annotated[User, Depends(require_role("admin"))],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminFeatureRequestReconcileResult]:
    audit_request_id = _request_correlation_id(request, x_request_id)
    suggestion = await _load_request(db, request_id)
    known = _known_resolution(suggestion)
    saved_resolution = (suggestion.kor_travel_map_ref or {}).get("last_resolution") or {}
    if known is not None and saved_resolution.get("command_key") == str(body.expected_command_key):
        return _reconciliation_result(suggestion, known)
    _check_expected_attempt(suggestion, body.expected_command_key)
    if suggestion.status != "pending" or suggestion.suggestion_type not in {
        "correction",
        "closure",
    }:
        raise _dispatch_error(
            "INVALID_STATE", "미확정 직접 Map 명령이 있는 대기 제안만 확인할 수 있습니다."
        )
    client = get_kor_travel_map_admin_client(request)
    dispatch, command_key, actor = _dispatch_identity(suggestion, current_actor=client.actor)
    original = deepcopy(dispatch)
    operation: Literal["admin.feature.patch", "admin.feature.delete"] = (
        "admin.feature.patch"
        if suggestion.suggestion_type == "correction"
        else "admin.feature.delete"
    )
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="feature_request.command_reconcile_requested",
        resource_type="feature_request",
        resource_id=str(request_id),
        before_state={"status": "pending"},
        after_state={
            "command_key": command_key,
            "actor": actor,
            "operation": operation,
            "saved_dispatch_sha256": hashlib.sha256(
                json.dumps(original, sort_keys=True).encode()
            ).hexdigest(),
        },
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=audit_request_id,
    )
    await db.commit()
    # 요청 감사의 commit이 잠금을 풀었으므로 같은 dispatch인지 새 잠금 아래 다시 대조한다.
    suggestion = await _load_request(db, request_id)
    fresh = (suggestion.kor_travel_map_ref or {}).get("dispatch")
    if suggestion.status != "pending" or fresh != original:
        known = _known_resolution(suggestion)
        saved = (suggestion.kor_travel_map_ref or {}).get("last_resolution") or {}
        if (
            known is not None
            and saved.get("command_key") == command_key
            and saved.get("actor") == actor
        ):
            return _reconciliation_result(suggestion, known)
        raise _dispatch_error(
            "MAP_COMMAND_PENDING", "확인 중 명령이 변경되었습니다. 상태를 다시 불러와 주세요."
        )
    dispatch, _, _ = _dispatch_identity(suggestion, current_actor=client.actor)
    with _map_admin_errors():
        resolution = await client.reconcile_feature_command(
            feature_id=dispatch["feature_id"],
            operation=operation,
            payload=dispatch["payload"],
            expected_revision=dispatch["expected_revision"],
            idempotency_key=command_key,
            expected_actor=actor,
            access_reason=body.access_reason,
        )
    state = resolution.get("state")
    if state not in {"pending", "abandoned", "completed"}:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "MAP_COMMAND_RECEIPT_INVALID",
                "message": "Map 명령의 확인 결과를 검증하지 못했습니다.",
            },
        )
    info = {
        "state": state,
        "actor": actor,
        "command_key": command_key,
        "operation": operation,
        "command_id": resolution["command_id"],
        "checked_at": datetime.now(UTC).isoformat(),
    }
    if state == "completed":
        record = resolution.get("receipt")
        if not isinstance(record, dict):
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "MAP_COMMAND_RECEIPT_INVALID",
                    "message": "확정된 Map 명령의 결과를 검증하지 못했습니다.",
                },
            )
        result = await _finalize_feature_request(
            db,
            suggestion,
            record,
            request,
            admin,
            audit_request_id,
            access_reason=body.access_reason,
            audit_action="feature_request.command_reconcile_completed",
            resolution_info=info,
        )
        return Envelope.of(
            AdminFeatureRequestReconcileResult(
                **result.model_dump(),
                resolution="completed",
            )
        )
    before = {"status": suggestion.status, "command_key": command_key, "actor": actor}
    if state == "abandoned":
        ref = dict(suggestion.kor_travel_map_ref or {})
        ref.pop("dispatch", None)
        ref["next_command_key"] = str(uuid.uuid4())
        ref["last_resolution"] = info
        suggestion.kor_travel_map_ref = ref
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action=f"feature_request.command_reconcile_{state}",
        resource_type="feature_request",
        resource_id=str(request_id),
        before_state=before,
        after_state={"status": suggestion.status, **info},
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=audit_request_id,
    )
    await db.commit()
    return _reconciliation_result(suggestion, cast(Literal["pending", "abandoned"], state))


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
    audit_request_id = _request_correlation_id(request, x_request_id)
    suggestion = await _load_pending(db, request_id)
    if (suggestion.kor_travel_map_ref or {}).get("dispatch") is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MAP_COMMAND_PENDING",
                "message": "Map 처리 결과를 확인한 뒤 거절할 수 있습니다. 저장된 내용으로 재시도하세요.",
            },
        )
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


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature_request_endpoint(
    request_id: uuid.UUID,
    body: AdminFeatureRequestReject,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Response:
    """처리 완료 제안을 삭제하며 Map·POI와 append-only 감사는 보존한다."""
    suggestion = await db.scalar(
        select(FeatureSuggestion)
        .where(FeatureSuggestion.request_id == request_id)
        .with_for_update()
    )
    if suggestion is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "제안을 찾을 수 없습니다."},
        )
    if (
        suggestion.status not in {"rejected", "added", "duplicate"}
        or (suggestion.kor_travel_map_ref or {}).get("dispatch") is not None
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_STATE",
                "message": "검토·Map 처리 중인 제안은 삭제할 수 없습니다.",
            },
        )
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="feature_request.delete",
        resource_type="feature_request",
        resource_id=str(request_id),
        before_state={
            "status": suggestion.status,
            "type": suggestion.suggestion_type,
            "kor_travel_map_ref": suggestion.kor_travel_map_ref,
        },
        after_state=None,
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_request_correlation_id(request, x_request_id),
    )
    await db.delete(suggestion)
    await db.commit()
    return Response(status_code=204)
