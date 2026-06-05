"""`/admin/backup/*` — ADR-022 manual snapshot trigger."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import AdminBackupSnapshot, AdminBackupSnapshotRequest
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit
from app.services.backup_service import (
    BackupServiceError,
    BackupSnapshot,
    create_backup_snapshot,
    list_backup_snapshots,
)

router = APIRouter(prefix="/admin/backup", tags=["admin"])


def _to_snapshot(snapshot: BackupSnapshot) -> AdminBackupSnapshot:
    return AdminBackupSnapshot(
        snapshot_id=snapshot.snapshot_id,
        filename=snapshot.filename,
        path=snapshot.path,
        size_bytes=snapshot.size_bytes,
        checksum_sha256=snapshot.checksum_sha256,
        status=snapshot.status,
        created_at=snapshot.created_at,
    )


@router.get("/snapshots", response_model=Envelope[list[AdminBackupSnapshot]])
async def list_backup_snapshots_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Envelope[list[AdminBackupSnapshot]]:
    snapshots = list_backup_snapshots(limit=limit)
    return Envelope.of([_to_snapshot(snapshot) for snapshot in snapshots])


@router.post(
    "/snapshot",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[AdminBackupSnapshot],
)
async def create_backup_snapshot_endpoint(
    body: AdminBackupSnapshotRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminBackupSnapshot]:
    try:
        snapshot = await create_backup_snapshot(access_reason=body.access_reason)
    except BackupServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    if x_request_id is None:
        x_request_id = str(uuid.uuid4())
    response = _to_snapshot(snapshot)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="backup.snapshot",
        resource_type="backup_snapshot",
        resource_id=snapshot.snapshot_id,
        before_state=None,
        after_state=response.model_dump(mode="json"),
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=uuid.UUID(x_request_id),
    )
    return Envelope.of(response)
