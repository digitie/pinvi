"""Admin backup API hardening tests — T-250."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.api.v1.admin import backup as backup_api
from app.models.audit import AdminAuditLog
from app.models.user import User
from app.services.backup_service import BackupServiceError, BackupSnapshot

pytestmark = pytest.mark.asyncio


async def _create_admin(session_factory: Any) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=f"admin-backup-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def test_create_backup_snapshot_masks_path_and_audits_success(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = await _create_admin(session_factory)
    request_id = uuid.uuid4()

    async def _fake_create_backup_snapshot(*, access_reason: str) -> BackupSnapshot:
        assert access_reason == "배포 전 백업"
        return BackupSnapshot(
            snapshot_id="pinvi-app-test",
            filename="pinvi-app-test.dump",
            path="/var/lib/pinvi/backups/pinvi-app-test.dump",
            size_bytes=128,
            checksum_sha256="a" * 64,
            status="verified",
            created_at=datetime(2026, 6, 28, 12, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(backup_api, "create_backup_snapshot", _fake_create_backup_snapshot)

    resp = await client.post(
        "/admin/backup/snapshot",
        json={"access_reason": "배포 전 백업"},
        headers={"X-Request-Id": str(request_id)},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["path"] == "backup://pinvi-app-test.dump"

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))

    assert audit is not None
    assert audit.action == "backup.snapshot"
    assert audit.after_state["path"] == "backup://pinvi-app-test.dump"


async def test_create_backup_snapshot_failure_writes_sanitized_audit(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = await _create_admin(session_factory)
    request_id = uuid.uuid4()

    async def _fake_create_backup_snapshot(*, access_reason: str) -> BackupSnapshot:
        raise BackupServiceError(
            "failed /var/lib/pinvi/backups/pinvi-app-prod.dump "
            "postgresql://pinvi:credential@example.invalid/pinvi"
        )

    monkeypatch.setattr(backup_api, "create_backup_snapshot", _fake_create_backup_snapshot)

    resp = await client.post(
        "/admin/backup/snapshot",
        json={"access_reason": "실패 기록 테스트"},
        headers={"X-Request-Id": str(request_id)},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["error"]["code"] == "BACKUP_FAILED"
    assert "credential" not in body["error"]["message"]
    assert "backup://pinvi-app-prod.dump" in body["error"]["message"]

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))

    assert audit is not None
    assert audit.action == "backup.snapshot_failed"
    assert audit.access_reason == "실패 기록 테스트"
    message = audit.after_state["error"]["message"]
    assert "credential" not in message
    assert "backup://pinvi-app-prod.dump" in message
