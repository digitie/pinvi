"""`/admin/debug/logs/*` — kor-travel-map sanitized ops logs read proxy."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from app.api.v1.admin.ops_proxy import map_ops_errors, next_cursor
from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminDebugLogStreamStatus,
    AdminUpstreamApiCallLogRecord,
    AdminUpstreamApiCallLogsResponse,
    AdminUpstreamSystemLogRecord,
    AdminUpstreamSystemLogsResponse,
)
from app.schemas.envelope import Envelope

router = APIRouter(prefix="/admin/debug/logs", tags=["admin"])


@router.get("/stream/status", response_model=Envelope[AdminDebugLogStreamStatus])
async def get_debug_log_stream_status(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
) -> Envelope[AdminDebugLogStreamStatus]:
    """v0.2.0 debug log live mode. Loki는 운영 선택 계층으로 두고 sanitized polling을 사용한다."""
    return Envelope.of(
        AdminDebugLogStreamStatus(
            mode="polling",
            status="ok",
            poll_interval_ms=5000,
            sources=["kor_travel_map_system_logs", "kor_travel_map_api_call_logs"],
            loki_enabled=False,
            sse_enabled=False,
            message="sanitized polling fallback",
        )
    )


@router.get("/system", response_model=Envelope[AdminUpstreamSystemLogsResponse])
async def list_system_logs(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    level: Annotated[
        str | None,
        Query(pattern="^(debug|info|warning|error|critical)$"),
    ] = None,
    source: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    request_id: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> Envelope[AdminUpstreamSystemLogsResponse]:
    """kor-travel-map `/v1/ops/system-logs` proxy."""
    with map_ops_errors(message_subject="kor_travel_map system log"):
        payload = await admin_client.list_system_logs(
            level=level,
            source=source,
            q=q,
            request_id=request_id,
            page_size=page_size,
            cursor=cursor,
        )
    return Envelope.of(
        AdminUpstreamSystemLogsResponse(
            items=_validate_items(
                payload,
                AdminUpstreamSystemLogRecord,
                "kor_travel_map system log item 형식이 올바르지 않습니다.",
            ),
            page_size=page_size,
            next_cursor=next_cursor(_meta(payload)),
        )
    )


@router.get("/api-calls", response_model=Envelope[AdminUpstreamApiCallLogsResponse])
async def list_upstream_api_call_logs(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    method: Annotated[str | None, Query()] = None,
    min_status: Annotated[int | None, Query(ge=100, le=599)] = None,
    path: Annotated[str | None, Query()] = None,
    request_id: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> Envelope[AdminUpstreamApiCallLogsResponse]:
    """kor-travel-map `/v1/ops/api-call-logs` proxy."""
    with map_ops_errors(message_subject="kor_travel_map api call log"):
        payload = await admin_client.list_ops_api_call_logs(
            method=method,
            min_status=min_status,
            path=path,
            request_id=request_id,
            page_size=page_size,
            cursor=cursor,
        )
    return Envelope.of(
        AdminUpstreamApiCallLogsResponse(
            items=_validate_items(
                payload,
                AdminUpstreamApiCallLogRecord,
                "kor_travel_map api call log item 형식이 올바르지 않습니다.",
            ),
            page_size=page_size,
            next_cursor=next_cursor(_meta(payload)),
        )
    )


def _meta(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map log 응답 meta 형식이 올바르지 않습니다.",
            },
        )
    return meta


def _validate_items(
    payload: dict[str, Any],
    model: type[AdminUpstreamSystemLogRecord] | type[AdminUpstreamApiCallLogRecord],
    message: str,
) -> Any:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map log 응답 data 형식이 올바르지 않습니다.",
            },
        )
    items = data.get("items")
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map log 목록에 items가 없습니다.",
            },
        )
    try:
        return [model.model_validate(item) for item in items]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "FEATURE_SERVICE_BAD_GATEWAY", "message": message},
        ) from exc
