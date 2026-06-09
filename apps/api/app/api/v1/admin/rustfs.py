"""`/admin/rustfs/*` — RustFS(S3) 객체 관리 (T-105 #3). `docs/api/storage.md` §6.

ListObjectsV2 / DeleteObject. DB 참조(CuratedPlanAttachment.storage_key) 있는 객체는 `force=true`
없이는 삭제 거부. 삭제는 admin_audit chain에 기록.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.attachment import CuratedPlanAttachment
from app.models.user import User
from app.schemas.envelope import Envelope
from app.schemas.storage import RustfsObjectList
from app.services.admin_audit import append_admin_audit
from app.services.rustfs_admin import delete_object, list_objects

router = APIRouter(prefix="/admin/rustfs", tags=["admin"])


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


@router.get("/objects", response_model=Envelope[RustfsObjectList])
async def list_rustfs_objects(
    _admin: Annotated[User, Depends(require_role("admin"))],
    prefix: str = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    continuation_token: str | None = None,
) -> Envelope[RustfsObjectList]:
    data = await list_objects(prefix=prefix, limit=limit, continuation_token=continuation_token)
    return Envelope.of(RustfsObjectList.model_validate(data))


@router.delete("/objects", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rustfs_object(
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    request: Request,
    key: str,
    reason: str,
    force: bool = False,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> None:
    """RustFS 객체 삭제. DB 첨부가 참조 중이면 `force=true` 없이는 409. 감사 기록 필수(reason)."""
    if not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": "삭제 사유(reason)가 필요합니다."},
        )
    referencing = await db.scalar(
        select(CuratedPlanAttachment.attachment_id).where(
            CuratedPlanAttachment.storage_key == key,
            CuratedPlanAttachment.deleted_at.is_(None),
        )
    )
    if referencing is not None and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "OBJECT_REFERENCED",
                "message": f"첨부 {referencing}가 참조 중입니다. force=true로 강제 삭제하세요.",
            },
        )
    await delete_object(key=key)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="rustfs.object_deleted",
        resource_type="rustfs_object",
        resource_id=key,
        before_state={"referenced_by": str(referencing) if referencing else None, "force": force},
        after_state=None,
        access_reason=reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
