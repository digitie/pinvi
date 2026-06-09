"""`/admin/backup/*` — ADR-022 manual snapshot trigger."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminBackupRestoreRequest,
    AdminBackupRestoreRun,
    AdminBackupSnapshot,
    AdminBackupSnapshotRequest,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit, append_admin_audit_to_schema
from app.services.backup_service import (
    BackupRestoreRun,
    BackupServiceError,
    BackupSnapshot,
    BackupSnapshotNotFoundError,
    create_backup_snapshot,
    list_backup_snapshots,
    restore_backup_hotswap,
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


def _to_restore_run(run: BackupRestoreRun) -> AdminBackupRestoreRun:
    return AdminBackupRestoreRun(
        restore_id=run.restore_id,
        snapshot_id=run.snapshot_id,
        snapshot_path=run.snapshot_path,
        restore_schema=run.restore_schema,
        previous_schema=run.previous_schema,
        status=run.status,
        phases=[
            {"name": phase.name, "status": phase.status, "message": phase.message}
            for phase in run.phases
        ],
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _request_uuid(value: str | None) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except ValueError:
        return uuid.uuid4()


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
        request_id=_request_uuid(x_request_id),
    )
    await db.commit()
    return Envelope.of(response)


@router.post("/restore-hotswap", response_model=Envelope[AdminBackupRestoreRun])
async def restore_backup_hotswap_endpoint(
    body: AdminBackupRestoreRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminBackupRestoreRun]:
    request_id = _request_uuid(x_request_id)
    if not body.confirm_schema_swap:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "schema-swap 복구 확인이 필요합니다.",
            },
        )

    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="backup.restore_hotswap_started",
        resource_type="backup_snapshot",
        resource_id=body.snapshot_id,
        before_state=None,
        after_state={"snapshot_id": body.snapshot_id, "confirm_schema_swap": True},
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
    await db.commit()

    try:
        run = await restore_backup_hotswap(
            snapshot_id=body.snapshot_id,
            access_reason=body.access_reason,
        )
    except BackupSnapshotNotFoundError as exc:
        await append_admin_audit(
            db,
            actor_user_id=admin.user_id,
            action="backup.restore_hotswap_failed",
            resource_type="backup_snapshot",
            resource_id=body.snapshot_id,
            before_state=None,
            after_state={"error": {"code": exc.code, "message": str(exc)}},
            access_reason=body.access_reason,
            target_pii_fields=None,
            ip_hash_input=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent"),
            request_id=request_id,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except BackupServiceError as exc:
        await append_admin_audit(
            db,
            actor_user_id=admin.user_id,
            action="backup.restore_hotswap_failed",
            resource_type="backup_snapshot",
            resource_id=body.snapshot_id,
            before_state=None,
            after_state={"error": {"code": exc.code, "message": str(exc)}},
            access_reason=body.access_reason,
            target_pii_fields=None,
            ip_hash_input=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent"),
            request_id=request_id,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    response = _to_restore_run(run)
    await append_admin_audit_to_schema(
        db,
        schema=run.previous_schema,
        actor_user_id=admin.user_id,
        action="backup.restore_hotswap",
        resource_type="backup_snapshot",
        resource_id=run.snapshot_id,
        before_state=None,
        after_state={
            **response.model_dump(mode="json"),
            "audit_reflection_schema": run.previous_schema,
            "canonical_schema_after_restore": "app",
        },
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
    await db.commit()
    return Envelope.of(response)
