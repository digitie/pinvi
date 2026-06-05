"""Postgres backup snapshot service — ADR-022 Sprint 5 1차."""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.core.config import settings

SnapshotStatus = Literal["available", "verified"]

_BACKUP_FILE_RE = re.compile(r"^BACKUP_FILE=(?P<path>.+)$", re.MULTILINE)


class BackupServiceError(Exception):
    """backup script 실행 / 결과 확인 실패."""

    code = "BACKUP_FAILED"


@dataclass(frozen=True)
class BackupSnapshot:
    snapshot_id: str
    filename: str
    path: str
    size_bytes: int
    checksum_sha256: str | None
    status: SnapshotStatus
    created_at: datetime


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root() / path


def backup_dir() -> Path:
    return resolve_repo_path(settings.tripmate_backup_dir)


def backup_script_path() -> Path:
    return resolve_repo_path(settings.tripmate_backup_script_path)


def _checksum_for(path: Path) -> str | None:
    checksum_file = Path(f"{path}.sha256")
    if not checksum_file.exists():
        return None
    first = checksum_file.read_text(encoding="utf-8").strip().split(maxsplit=1)[0]
    return first or None


def _snapshot_from_file(path: Path) -> BackupSnapshot:
    stat = path.stat()
    checksum = _checksum_for(path)
    return BackupSnapshot(
        snapshot_id=path.stem,
        filename=path.name,
        path=str(path),
        size_bytes=stat.st_size,
        checksum_sha256=checksum,
        status="verified" if checksum else "available",
        created_at=datetime.fromtimestamp(stat.st_mtime, UTC),
    )


def list_backup_snapshots(*, limit: int = 50) -> list[BackupSnapshot]:
    directory = backup_dir()
    if not directory.exists():
        return []
    snapshots = [_snapshot_from_file(path) for path in directory.glob("*.dump") if path.is_file()]
    snapshots.sort(key=lambda snapshot: snapshot.created_at, reverse=True)
    return snapshots[:limit]


def _snapshot_from_script_result(
    *,
    stdout: str,
    directory: Path,
    before: set[Path],
) -> BackupSnapshot | None:
    match = _BACKUP_FILE_RE.search(stdout)
    if match:
        path = Path(match.group("path")).resolve()
        if path.exists():
            return _snapshot_from_file(path)

    created = [path for path in directory.glob("*.dump") if path.resolve() not in before]
    if created:
        created.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return _snapshot_from_file(created[0])
    return None


async def create_backup_snapshot(*, access_reason: str) -> BackupSnapshot:
    script = backup_script_path()
    if not script.exists():
        raise BackupServiceError(f"backup script not found: {script}")

    directory = backup_dir()
    directory.mkdir(parents=True, exist_ok=True)

    before = {path.resolve() for path in directory.glob("*.dump")}
    env = {
        **os.environ,
        "TRIPMATE_BACKUP_DIR": str(directory),
        "TRIPMATE_BACKUP_SCHEMA": settings.tripmate_backup_schema,
        "TRIPMATE_BACKUP_REASON": access_reason,
        "TRIPMATE_DATABASE_URL": settings.tripmate_database_url,
    }

    proc = await asyncio.create_subprocess_exec(
        str(script),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(repo_root()),
    )
    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(
            proc.communicate(),
            timeout=settings.tripmate_backup_timeout_seconds,
        )
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise BackupServiceError("backup script timed out") from exc

    stdout = stdout_raw.decode("utf-8", errors="replace")
    stderr = stderr_raw.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise BackupServiceError(stderr or stdout or f"backup script exited {proc.returncode}")

    snapshot = _snapshot_from_script_result(stdout=stdout, directory=directory, before=before)
    if snapshot:
        return snapshot

    raise BackupServiceError("backup script completed without creating a dump")
