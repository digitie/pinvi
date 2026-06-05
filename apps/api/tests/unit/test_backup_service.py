"""Backup service unit tests — ADR-022 Sprint 5 1차."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.backup_service import (
    BackupServiceError,
    create_backup_snapshot,
    list_backup_snapshots,
)


@pytest.fixture(autouse=True)
def _backup_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tripmate_backup_dir", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "tripmate_backup_schema", "app")
    monkeypatch.setattr(settings, "tripmate_backup_timeout_seconds", 5)
    monkeypatch.setattr(
        settings,
        "tripmate_database_url",
        "postgresql+asyncpg://tripmate:tripmate@localhost:55432/tripmate",
    )


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
mkdir -p "$TRIPMATE_BACKUP_DIR"
file="$TRIPMATE_BACKUP_DIR/tripmate-app-test.dump"
printf 'dump' > "$file"
printf 'abc123  %s\n' "$file" > "$file.sha256"
printf 'BACKUP_FILE=%s\n' "$file"
""",
    )
    monkeypatch.setattr(settings, "tripmate_backup_script_path", str(script))

    snapshot = await create_backup_snapshot(access_reason="테스트 백업")

    assert snapshot.snapshot_id == "tripmate-app-test"
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
    monkeypatch.setattr(settings, "tripmate_backup_script_path", str(script))

    with pytest.raises(BackupServiceError):
        await create_backup_snapshot(access_reason="실패 테스트")


def test_list_backup_snapshots_sorts_recent_first(tmp_path: Path) -> None:
    backup_dir = Path(settings.tripmate_backup_dir)
    backup_dir.mkdir(parents=True)
    old = backup_dir / "tripmate-app-20260601.dump"
    new = backup_dir / "tripmate-app-20260602.dump"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    os.utime(old, (1_000, 1_000))
    os.utime(new, (2_000, 2_000))

    snapshots = list_backup_snapshots()

    assert [snapshot.filename for snapshot in snapshots] == [new.name, old.name]
