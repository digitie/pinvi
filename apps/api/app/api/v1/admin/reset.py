"""Dev/staging-only Admin reset dry-run routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.v1.admin.dev_safety import (
    ensure_dev_safety_route_enabled,
    reject_confirmation,
    reject_non_dry_run,
)
from app.api.v1.admin.ops_proxy import parse_request_id
from app.core.config import settings
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminDevSafetyActionResult,
    AdminResetRunRequest,
    AdminResetStatusResponse,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit

router = APIRouter(prefix="/admin/reset", tags=["admin"])

_RESET_STEPS = [
    "현재 app schema 상태 확인",
    "alembic downgrade base 계획",
    "alembic upgrade head 계획",
    "new_user_first_trip seed 적용 계획",
]


@router.get("/status", response_model=Envelope[AdminResetStatusResponse])
async def get_reset_status(
    _admin: Annotated[User, Depends(require_role("admin"))],
) -> Envelope[AdminResetStatusResponse]:
    ensure_dev_safety_route_enabled()
    return Envelope.of(
        AdminResetStatusResponse(
            environment=settings.pinvi_environment,
            enabled=settings.pinvi_enable_seed,
        )
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Envelope[AdminDevSafetyActionResult],
)
async def run_reset_dry_run(
    body: AdminResetRunRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminDevSafetyActionResult]:
    ensure_dev_safety_route_enabled()
    if body.confirm != "RESET":
        reject_confirmation()
    if not body.dry_run:
        reject_non_dry_run()

    steps = list(_RESET_STEPS)
    if not body.include_seed:
        steps = [step for step in steps if "seed" not in step]

    audit = await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="dev_reset.dry_run",
        resource_type="reset",
        resource_id="app",
        before_state=None,
        after_state={
            "dry_run": True,
            "target_schemas": ["app"],
            "include_seed": body.include_seed,
            "steps": steps,
            "environment": settings.pinvi_environment,
        },
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=parse_request_id(x_request_id),
    )
    await db.commit()
    return Envelope.of(
        AdminDevSafetyActionResult(
            action="dev_reset.dry_run",
            target="app",
            status="dry_run",
            audit_log_id=audit.log_id,
            would_execute=steps,
            message="reset dry-run을 기록했습니다.",
        )
    )
