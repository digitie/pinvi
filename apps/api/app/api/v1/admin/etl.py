"""`/admin/etl/*` — Pinvi + kor-travel-map ETL 운영 요약."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import AdminEtlSummary
from app.schemas.envelope import Envelope
from app.services.admin_etl import build_admin_etl_summary

router = APIRouter(prefix="/admin/etl", tags=["admin"])


@router.get("/summary", response_model=Envelope[AdminEtlSummary])
async def get_admin_etl_summary(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
) -> Envelope[AdminEtlSummary]:
    """Admin ETL 화면용 요약.

    Pinvi app-owned ETL 정의는 로컬 registry에서, feature/provider ETL 상태는
    kor-travel-map `/v1/ops/*`에서 읽는다. upstream 일부 장애는 화면을 막지 않고
    `kor_travel_map.status=degraded|down`으로 반환한다.
    """
    return Envelope.of(await build_admin_etl_summary(admin_client))
