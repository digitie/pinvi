"""`/admin/rbac` — 권한 매트릭스 조회."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import AdminPermissionMatrixResponse
from app.schemas.envelope import Envelope
from app.services.admin_rbac import get_permission_matrix

router = APIRouter(prefix="/admin/rbac", tags=["admin"])


@router.get("/permission-matrix", response_model=Envelope[AdminPermissionMatrixResponse])
async def get_admin_permission_matrix(
    _admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
) -> Envelope[AdminPermissionMatrixResponse]:
    return Envelope.of(get_permission_matrix())
