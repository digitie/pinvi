"""Backup service unit tests — ADR-022 Sprint 5 1차."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import pytest

from app.core.config import settings
from app.services import backup_service
from app.services.backup_service import (
    BackupServiceError,
    BackupSnapshotNotFoundError,
    create_backup_snapshot,
    list_backup_snapshots,
    restore_backup_hotswap,
)


@pytest.fixture(autouse=True)
def _backup_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pinvi_backup_dir", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "pinvi_backup_schema", "app")
    monkeypatch.setattr(settings, "pinvi_backup_timeout_seconds", 5)
    monkeypatch.setattr(settings, "pinvi_restore_timeout_seconds", 5)
    monkeypatch.setattr(
        settings,
        "pinvi_database_url",
        "postgresql+asyncpg://pinvi:pinvi@localhost:5432/pinvi",
    )
    monkeypatch.setattr(settings, "pinvi_restore_database_url", "")
    monkeypatch.setattr(settings, "pinvi_restore_hotswap_execute", False)
    monkeypatch.setattr(settings, "pinvi_restore_drain_command", "")
    monkeypatch.setattr(settings, "pinvi_restore_allow_no_drain", False)
    monkeypatch.setattr(settings, "pinvi_restore_app_role", "")

    @asynccontextmanager
    async def _noop_restore_advisory_lock() -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(backup_service, "_restore_advisory_lock", _noop_restore_advisory_lock)


def _write_script(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


@pytest.mark.asyncio
async def test_create_backup_snapshot_from_script_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "backup.sh"
    _write_script(
        script,
        """#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$PINVI_BACKUP_DIR"
file="$PINVI_BACKUP_DIR/pinvi-app-test.dump"
printf 'dump' > "$file"
printf 'abc123  %s\n' "$file" > "$file.sha256"
printf 'BACKUP_FILE=%s\n' "$file"
""",
    )
    monkeypatch.setattr(settings, "pinvi_backup_script_path", str(script))

    snapshot = await create_backup_snapshot(access_reason="테스트 백업")

    assert snapshot.snapshot_id == "pinvi-app-test"
    assert snapshot.status == "verified"
    assert snapshot.size_bytes == 4
    assert snapshot.checksum_sha256 == "abc123"


@pytest.mark.asyncio
async def test_create_backup_snapshot_raises_for_failed_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "backup.sh"
    _write_script(
        script,
        """#!/usr/bin/env bash
echo failed >&2
exit 9
""",
    )
    monkeypatch.setattr(settings, "pinvi_backup_script_path", str(script))

    with pytest.raises(BackupServiceError):
        await create_backup_snapshot(access_reason="실패 테스트")


def test_list_backup_snapshots_sorts_recent_first(tmp_path: Path) -> None:
    backup_dir = Path(settings.pinvi_backup_dir)
    backup_dir.mkdir(parents=True)
    old = backup_dir / "pinvi-app-20260601.dump"
    new = backup_dir / "pinvi-app-20260602.dump"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    os.utime(old, (1_000, 1_000))
    os.utime(new, (2_000, 2_000))

    snapshots = list_backup_snapshots()

    assert [snapshot.filename for snapshot in snapshots] == [new.name, old.name]


def test_restore_lock_database_url_accepts_psql_driverless_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "pinvi_restore_database_url",
        "postgresql://pinvi:pinvi@localhost:5432/pinvi",
    )

    assert (
        backup_service._restore_lock_database_url()
        == "postgresql+asyncpg://pinvi:pinvi@localhost:5432/pinvi"
    )


@pytest.mark.asyncio
async def test_restore_backup_hotswap_runs_script_and_parses_phases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup_dir = anyio.Path(settings.pinvi_backup_dir)
    await backup_dir.mkdir(parents=True)
    snapshot = backup_dir / "pinvi-app-restore.dump"
    await snapshot.write_text("dump", encoding="utf-8")
    script = tmp_path / "restore-hotswap.sh"
    _write_script(
        script,
        """#!/usr/bin/env bash
set -euo pipefail
test "$1" = run
test -f "$2"
test "${PINVI_RESTORE_API_TRIGGER}" = "1"
printf 'RESTORE_PHASE=preparing:success:checked\\n'
printf 'RESTORE_PHASE=restoring:success:restored %s\\n' "$3"
printf 'RESTORE_PHASE=validating:success:validated\\n'
printf 'RESTORE_PHASE=draining:success:drained\\n'
printf 'RESTORE_PHASE=switching:success:switched %s\\n' "$4"
""",
    )
    monkeypatch.setattr(settings, "pinvi_restore_hotswap_script_path", str(script))

    run = await restore_backup_hotswap(
        snapshot_id="pinvi-app-restore",
        access_reason="복구 훈련",
    )

    assert run.snapshot_id == "pinvi-app-restore"
    assert run.status == "succeeded"
    assert run.restore_schema.startswith("app_restore_")
    assert run.previous_schema.startswith("app_previous_")
    assert [phase.status for phase in run.phases] == ["success"] * 5


@pytest.mark.asyncio
async def test_restore_backup_hotswap_uses_advisory_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup_dir = anyio.Path(settings.pinvi_backup_dir)
    await backup_dir.mkdir(parents=True)
    snapshot = backup_dir / "pinvi-app-lock.dump"
    await snapshot.write_text("dump", encoding="utf-8")
    script = tmp_path / "restore-hotswap.sh"
    _write_script(
        script,
        """#!/usr/bin/env bash
set -euo pipefail
printf 'RESTORE_PHASE=preparing:success:checked\\n'
printf 'RESTORE_PHASE=restoring:success:restored\\n'
printf 'RESTORE_PHASE=validating:success:validated\\n'
printf 'RESTORE_PHASE=draining:skipped:test\\n'
printf 'RESTORE_PHASE=switching:success:switched\\n'
""",
    )
    monkeypatch.setattr(settings, "pinvi_restore_hotswap_script_path", str(script))
    entered = False

    @asynccontextmanager
    async def _recording_restore_advisory_lock() -> AsyncIterator[None]:
        nonlocal entered
        entered = True
        yield

    monkeypatch.setattr(backup_service, "_restore_advisory_lock", _recording_restore_advisory_lock)

    await restore_backup_hotswap(
        snapshot_id="pinvi-app-lock",
        access_reason="락 테스트",
    )

    assert entered is True


@pytest.mark.asyncio
async def test_restore_backup_hotswap_rejects_unknown_snapshot() -> None:
    with pytest.raises(BackupSnapshotNotFoundError):
        await restore_backup_hotswap(
            snapshot_id="../missing",
            access_reason="잘못된 복구",
        )
