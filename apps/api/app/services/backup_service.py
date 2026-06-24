"""Postgres backup snapshot service — ADR-022 Sprint 5 1차."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

SnapshotStatus = Literal["available", "verified"]
RestoreRunStatus = Literal["succeeded", "failed"]
RestorePhaseName = Literal["preparing", "restoring", "validating", "draining", "switching"]
RestorePhaseStatus = Literal["pending", "running", "success", "failed", "skipped"]

_BACKUP_FILE_RE = re.compile(r"^BACKUP_FILE=(?P<path>.+)$", re.MULTILINE)
_RESTORE_PHASE_RE = re.compile(
    r"^RESTORE_PHASE=(?P<name>[a-z_]+):(?P<status>[a-z_]+)(?::(?P<message>.*))?$",
    re.MULTILINE,
)
_SNAPSHOT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_RESTORE_PHASES: tuple[RestorePhaseName, ...] = (
    "preparing",
    "restoring",
    "validating",
    "draining",
    "switching",
)


class BackupServiceError(Exception):
    """backup script 실행 / 결과 확인 실패."""

    code = "BACKUP_FAILED"


class BackupSnapshotNotFoundError(BackupServiceError):
    """선택한 backup snapshot을 찾을 수 없음."""

    code = "BACKUP_SNAPSHOT_NOT_FOUND"


class BackupRestoreAlreadyRunningError(BackupServiceError):
    """동일 DB에서 다른 schema-swap restore가 진행 중."""

    code = "BACKUP_RESTORE_ALREADY_RUNNING"


@dataclass(frozen=True)
class BackupSnapshot:
    snapshot_id: str
    filename: str
    path: str
    size_bytes: int
    checksum_sha256: str | None
    status: SnapshotStatus
    created_at: datetime


@dataclass(frozen=True)
class BackupRestorePhase:
    name: RestorePhaseName
    status: RestorePhaseStatus
    message: str | None = None


@dataclass(frozen=True)
class BackupRestoreRun:
    restore_id: str
    snapshot_id: str
    snapshot_path: str
    restore_schema: str
    previous_schema: str
    status: RestoreRunStatus
    phases: list[BackupRestorePhase]
    started_at: datetime
    completed_at: datetime


def repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "app").is_dir():
            return parent
    return current.parents[min(4, len(current.parents) - 1)]


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root() / path


def backup_dir() -> Path:
    return resolve_repo_path(settings.pinvi_backup_dir)


def backup_script_path() -> Path:
    return resolve_repo_path(settings.pinvi_backup_script_path)


def restore_hotswap_script_path() -> Path:
    return resolve_repo_path(settings.pinvi_restore_hotswap_script_path)


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


def get_backup_snapshot(*, snapshot_id: str) -> BackupSnapshot:
    if not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise BackupSnapshotNotFoundError("backup snapshot id 형식이 올바르지 않습니다.")
    path = backup_dir() / f"{snapshot_id}.dump"
    if not path.is_file():
        raise BackupSnapshotNotFoundError(f"backup snapshot을 찾을 수 없습니다: {snapshot_id}")
    return _snapshot_from_file(path)


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
        "PINVI_BACKUP_DIR": str(directory),
        "PINVI_BACKUP_SCHEMA": settings.pinvi_backup_schema,
        "PINVI_BACKUP_REASON": access_reason,
        "PINVI_DATABASE_URL": settings.pinvi_database_url,
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
            timeout=settings.pinvi_backup_timeout_seconds,
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


# 동시 복원은 동일 DB에 두 개의 비가역 schema-swap을 겹쳐 무결성을 깨뜨린다.
# 프로세스 내 lock + DB advisory lock을 함께 써서 같은 워커와 다중 워커를 모두 막는다.
_restore_lock = asyncio.Lock()
_RESTORE_LOCK_NAMESPACE = 0x54524D54  # "TRMT"
_RESTORE_LOCK_RESOURCE = 0x48535750  # "HSWP"


def _asyncpg_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return f"postgresql+asyncpg://{database_url.removeprefix('postgresql://')}"
    return database_url


def _restore_lock_database_url() -> str:
    database_url = settings.pinvi_restore_database_url or settings.pinvi_database_url
    return _asyncpg_database_url(database_url)


async def restore_backup_hotswap(
    *,
    snapshot_id: str,
    access_reason: str,
) -> BackupRestoreRun:
    async with _restore_lock:
        async with _restore_advisory_lock():
            return await _restore_backup_hotswap_locked(
                snapshot_id=snapshot_id, access_reason=access_reason
            )


@asynccontextmanager
async def _restore_advisory_lock() -> AsyncIterator[None]:
    engine = create_async_engine(_restore_lock_database_url(), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            acquired = await conn.scalar(
                text("SELECT pg_try_advisory_lock(:namespace, :resource)"),
                {"namespace": _RESTORE_LOCK_NAMESPACE, "resource": _RESTORE_LOCK_RESOURCE},
            )
            if acquired is not True:
                raise BackupRestoreAlreadyRunningError("다른 schema-swap restore가 진행 중입니다.")
            try:
                yield
            finally:
                await conn.execute(
                    text("SELECT pg_advisory_unlock(:namespace, :resource)"),
                    {"namespace": _RESTORE_LOCK_NAMESPACE, "resource": _RESTORE_LOCK_RESOURCE},
                )
    finally:
        await engine.dispose()


async def _restore_backup_hotswap_locked(
    *,
    snapshot_id: str,
    access_reason: str,
) -> BackupRestoreRun:
    snapshot = get_backup_snapshot(snapshot_id=snapshot_id)
    script = restore_hotswap_script_path()
    if not script.exists():
        raise BackupServiceError(f"restore hotswap script not found: {script}")

    started_at = datetime.now(UTC)
    # 초 해상도만 쓰면 같은 초에 두 번 복원 시 restore_id(→ 스키마명)가 충돌한다. uuid suffix로 고유화.
    restore_id = f"{started_at.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    schema = settings.pinvi_backup_schema
    restore_schema = f"{schema}_restore_{restore_id}"
    previous_schema = f"{schema}_previous_{restore_id}"
    env = {
        **os.environ,
        "PINVI_BACKUP_SCHEMA": schema,
        "PINVI_RESTORE_REASON": access_reason,
        "PINVI_RESTORE_ID": restore_id,
        "PINVI_RESTORE_SCHEMA": restore_schema,
        "PINVI_PREVIOUS_SCHEMA": previous_schema,
        "PINVI_DATABASE_URL": settings.pinvi_database_url,
        "PINVI_RESTORE_DATABASE_URL": settings.pinvi_restore_database_url,
        "PINVI_RESTORE_HOTSWAP_EXECUTE": ("1" if settings.pinvi_restore_hotswap_execute else "0"),
        "PINVI_RESTORE_DRAIN_COMMAND": settings.pinvi_restore_drain_command,
        "PINVI_RESTORE_ALLOW_NO_DRAIN": ("1" if settings.pinvi_restore_allow_no_drain else "0"),
        "PINVI_RESTORE_APP_ROLE": settings.pinvi_restore_app_role,
        "PINVI_RESTORE_API_TRIGGER": "1",
    }

    proc = await asyncio.create_subprocess_exec(
        str(script),
        "run",
        snapshot.path,
        restore_schema,
        previous_schema,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(repo_root()),
    )
    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(
            proc.communicate(),
            timeout=settings.pinvi_restore_timeout_seconds,
        )
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise BackupServiceError("restore hotswap script timed out") from exc

    stdout = stdout_raw.decode("utf-8", errors="replace")
    stderr = stderr_raw.decode("utf-8", errors="replace")
    phases = _parse_restore_phases(stdout)
    completed_at = datetime.now(UTC)
    if proc.returncode != 0:
        message = stderr or stdout or f"restore hotswap script exited {proc.returncode}"
        raise BackupServiceError(message)

    return BackupRestoreRun(
        restore_id=restore_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_path=snapshot.path,
        restore_schema=restore_schema,
        previous_schema=previous_schema,
        status="succeeded",
        phases=phases,
        started_at=started_at,
        completed_at=completed_at,
    )


def _parse_restore_phases(stdout: str) -> list[BackupRestorePhase]:
    by_name: dict[RestorePhaseName, BackupRestorePhase] = {
        name: BackupRestorePhase(name=name, status="pending") for name in _RESTORE_PHASES
    }
    seen = False
    for match in _RESTORE_PHASE_RE.finditer(stdout):
        raw_name = match.group("name")
        raw_status = match.group("status")
        if raw_name not in _RESTORE_PHASES or raw_status not in {
            "pending",
            "running",
            "success",
            "failed",
            "skipped",
        }:
            continue
        name = cast(RestorePhaseName, raw_name)
        status = cast(RestorePhaseStatus, raw_status)
        by_name[name] = BackupRestorePhase(
            name=name,
            status=status,
            message=match.group("message") or None,
        )
        seen = True
    if not seen:
        return [
            BackupRestorePhase(name=name, status="success", message="script completed")
            for name in _RESTORE_PHASES
        ]
    return [by_name[name] for name in _RESTORE_PHASES]
