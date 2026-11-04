"""관리자 전용 30일 휴지통/첨부 파일 정리."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.envelope import Envelope
from app.schemas.storage_retention import (
    StorageRetentionExecuteRequest,
    StorageRetentionResult,
    StorageRetentionStatus,
)
from app.services.admin_audit import append_admin_audit
from app.services.attachment_retention import execute_attachment_retention, retention_status

router = APIRouter(prefix="/admin/storage-retention", tags=["admin"])


@router.get("", response_model=Envelope[StorageRetentionStatus])
async def status(
    db: DbSession,
    admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
) -> Envelope[StorageRetentionStatus]:
    data = await retention_status(db)
    data["can_execute"] = bool(set(admin.roles or []) & {"admin", "cpo"})
    return Envelope.of(StorageRetentionStatus.model_validate(data))


@router.post("/execute", response_model=Envelope[StorageRetentionResult])
async def execute(
    body: StorageRetentionExecuteRequest,
    request: Request,
    db: DbSession,
    admin: Annotated[User, Depends(require_role("admin", "cpo"))],
) -> Envelope[StorageRetentionResult]:
    reason = body.access_reason.strip()
    if len(reason) < 5:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "정리 사유를 5자 이상 입력해 주세요."},
        )
    request_id = uuid.uuid4()
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="storage.retention_requested",
        resource_type="attachment_retention",
        resource_id=str(request_id),
        before_state=None,
        after_state={"requested": True},
        access_reason=reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
    await db.commit()
    result = await execute_attachment_retention(db)
    result["status"]["can_execute"] = True
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="storage.retention_completed",
        resource_type="attachment_retention",
        resource_id=str(request_id),
        before_state=None,
        after_state=result,
        access_reason=reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=uuid.uuid4(),
    )
    await db.commit()
    return Envelope.of(StorageRetentionResult.model_validate(result))
