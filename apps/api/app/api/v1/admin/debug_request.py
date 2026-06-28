"""`/admin/debug/request/{request_id}` — Pinvi request timeline."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import AdminRequestTimelineResponse
from app.schemas.envelope import Envelope
from app.services.admin_request_timeline import (
    build_request_timeline,
    has_degraded_source,
    has_timeline_events,
)

router = APIRouter(prefix="/admin/debug/request", tags=["admin"])


@router.get("/{request_id}", response_model=Envelope[AdminRequestTimelineResponse])
async def get_request_timeline(
    request_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    admin_client: KorTravelMapAdminClientDep,
) -> Envelope[AdminRequestTimelineResponse]:
    """Pinvi request id 중심 timeline. Upstream logs는 보조 event source로만 붙인다."""
    timeline = await build_request_timeline(db, request_id=request_id, admin_client=admin_client)
    if not has_timeline_events(timeline) and not has_degraded_source(timeline):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "request timeline event를 찾을 수 없습니다.",
            },
        )
    return Envelope.of(timeline)
