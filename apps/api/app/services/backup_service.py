"""Postgres backup snapshot service — ADR-022 Sprint 5 1차."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
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
_DATABASE_URL_RE = re.compile(r"postgresql(?:\+asyncpg)?://[^\s]+")
_DUMP_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:/[A-Za-z0-9_.@%+=:,~-]+)+\.dump")
_RESTORE_PHASE_RE = re.compile(
    r"^RESTORE_PHASE=(?P<name>[a-z_]+):(?P<status>[a-z_]+)(?::(?P<message>.*))?$",
    re.MULTILINE,
)
_SNAPSHOT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_CATALOG_FILENAME_RE = re.compile(r"^pinvi-[A-Za-z0-9_.-]+\.dump$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RESTORE_PHASES: tuple[RestorePhaseName, ...] = (
    "preparing",
    "restoring",
    "validating",
    "draining",
    "switching",
)
_SAFE_EXECUTION_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_STRICT_BACKUP_ENVIRONMENTS = {"staging", "production"}


class BackupServiceError(Exception):
    """backup script 실행 / 결과 확인 실패."""

    code = "BACKUP_FAILED"


class BackupSnapshotNotFoundError(BackupServiceError):
    """선택한 backup snapshot을 찾을 수 없음."""

    code = "BACKUP_SNAPSHOT_NOT_FOUND"


class BackupSnapshotUnverifiedError(BackupServiceError):
    """checksum sidecar로 검증되지 않은 snapshot은 schema swap에 사용할 수 없음."""

    code = "BACKUP_SNAPSHOT_UNVERIFIED"


class BackupDiskGuardError(BackupServiceError):
    """backup 대상 volume 여유 공간 부족."""

    code = "BACKUP_DISK_GUARD_FAILED"


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
        if (parent / "package.json").is_file() and (parent / "scripts" / "backup-db.sh").is_file():
            return parent
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


def _validated_backup_script() -> Path:
    script = backup_script_path()
    canonical = repo_root() / "scripts" / "backup-db.sh"
    if script.is_symlink() or not script.is_file() or not os.access(script, os.X_OK):
        raise BackupServiceError("backup script must be a regular executable")
    if settings.pinvi_environment in _STRICT_BACKUP_ENVIRONMENTS:
        if script.resolve() != canonical.resolve():
            raise BackupServiceError("운영 backup script는 repository canonical 경로여야 합니다.")
    return script


def restore_hotswap_script_path() -> Path:
    return resolve_repo_path(settings.pinvi_restore_hotswap_script_path)


def _checksum_for(path: Path) -> str | None:
    checksum_file = Path(f"{path}.sha256")
    if checksum_file.is_symlink() or not checksum_file.is_file():
        return None
    first = checksum_file.read_text(encoding="utf-8").strip().split(maxsplit=1)[0]
    expected = first or None
    if expected is None:
        return None
    actual = _sha256_file(path)
    return expected if actual == expected else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate catalog key")
        result[key] = value
    return result


def _strict_backup_catalog_snapshots(*, limit: int) -> list[BackupSnapshot]:
    """ordinary API에는 root producer의 metadata-only catalog만 보인다.

    raw dump와 manifest는 restore runner에만 mount된다. catalog가 없거나 신뢰 경계가 틀리면
    운영 UI는 빈 목록으로 fail-close하며 artifact 경로나 내용은 열지 않는다.
    """

    directory = backup_dir()
    catalog_path = directory / "current.json"
    descriptor = -1
    try:
        directory_metadata = directory.stat()
        if (
            not directory.is_absolute()
            or directory.is_symlink()
            or not directory.is_dir()
            or directory_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(directory_metadata.st_mode) != 0o700
            or catalog_path.is_symlink()
        ):
            return []
        descriptor = os.open(
            catalog_path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size < 1
            or metadata.st_size > 256 * 1024
        ):
            return []
        raw = os.read(descriptor, metadata.st_size + 1)
        if len(raw) != metadata.st_size:
            return []
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return []
    finally:
        if descriptor != -1:
            os.close(descriptor)
    if not isinstance(document, dict) or set(document) != {"snapshots", "version"}:
        return []
    snapshots = document.get("snapshots")
    if document.get("version") != 1 or not isinstance(snapshots, list) or len(snapshots) > 200:
        return []
    result: list[BackupSnapshot] = []
    for entry in snapshots:
        if not isinstance(entry, dict) or set(entry) != {
            "checksum_sha256",
            "created_at",
            "filename",
            "size_bytes",
            "snapshot_id",
            "status",
        }:
            return []
        filename = entry.get("filename")
        snapshot_id = entry.get("snapshot_id")
        checksum = entry.get("checksum_sha256")
        created_at = entry.get("created_at")
        size_bytes = entry.get("size_bytes")
        if (
            not isinstance(filename, str)
            or _CATALOG_FILENAME_RE.fullmatch(filename) is None
            or not isinstance(snapshot_id, str)
            or _SNAPSHOT_ID_RE.fullmatch(snapshot_id) is None
            or snapshot_id != Path(filename).stem
            or not isinstance(checksum, str)
            or _SHA256_RE.fullmatch(checksum) is None
            or entry.get("status") != "verified"
            or type(size_bytes) is not int
            or size_bytes < 1
            or not isinstance(created_at, str)
        ):
            return []
        try:
            parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return []
        if parsed_created_at.tzinfo is None:
            return []
        result.append(
            BackupSnapshot(
                snapshot_id=snapshot_id,
                filename=filename,
                path=f"backup://{filename}",
                size_bytes=size_bytes,
                checksum_sha256=checksum,
                status="verified",
                created_at=parsed_created_at.astimezone(UTC),
            )
        )
    result.sort(key=lambda snapshot: snapshot.created_at, reverse=True)
    return result[:limit]


def list_backup_snapshots(*, limit: int = 50) -> list[BackupSnapshot]:
    if settings.pinvi_environment in _STRICT_BACKUP_ENVIRONMENTS:
        return _strict_backup_catalog_snapshots(limit=limit)
    directory = backup_dir()
    if not directory.exists():
        return []
    snapshots = [
        _snapshot_from_file(path)
        for path in directory.glob("*.dump")
        if path.is_file() and not path.is_symlink()
    ]
    snapshots.sort(key=lambda snapshot: snapshot.created_at, reverse=True)
    return snapshots[:limit]


def mask_backup_path(path: str) -> str:
    """Return a stable non-host path for Admin responses and audits."""

    filename = Path(path).name
    return f"backup://{filename}" if filename else "backup://snapshot"


def sanitize_backup_message(message: str) -> str:
    """Remove local paths and database credentials from operator-facing errors."""

    sanitized = message
    for database_url in (
        settings.pinvi_database_url,
        settings.pinvi_restore_database_url,
        settings.pinvi_restore_fence_database_url,
    ):
        if database_url:
            sanitized = sanitized.replace(database_url, "postgresql://[masked]")
    sanitized = _DATABASE_URL_RE.sub("postgresql://[masked]", sanitized)
    sanitized = _DUMP_PATH_RE.sub(lambda match: mask_backup_path(match.group(0)), sanitized)

    backup_root = backup_dir()
    for path, replacement in ((backup_root, "<backup-dir>"), (repo_root(), "<repo>")):
        path_text = str(path)
        if path_text:
            sanitized = sanitized.replace(path_text, replacement)

    return sanitized


def get_backup_snapshot(*, snapshot_id: str) -> BackupSnapshot:
    if not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise BackupSnapshotNotFoundError("backup snapshot id 형식이 올바르지 않습니다.")
    if settings.pinvi_environment in _STRICT_BACKUP_ENVIRONMENTS:
        raise BackupSnapshotNotFoundError(
            "staging/production snapshot artifact는 root restore runner에서만 선택할 수 있습니다."
        )
    path = backup_dir() / f"{snapshot_id}.dump"
    if path.is_symlink() or not path.is_file():
        raise BackupSnapshotNotFoundError(f"backup snapshot을 찾을 수 없습니다: {snapshot_id}")
    return _snapshot_from_file(path)


@contextmanager
def _verified_snapshot_copy(snapshot: BackupSnapshot) -> Iterator[Path]:
    """검증된 dump를 private directory로 복사해 restore 중 TOCTOU를 차단한다."""

    if snapshot.checksum_sha256 is None:
        raise BackupSnapshotUnverifiedError("checksum sidecar로 검증되지 않은 snapshot입니다.")
    temporary_dir = Path(tempfile.mkdtemp(prefix="pinvi-restore-", dir="/tmp"))
    target = temporary_dir / snapshot.filename
    source_fd = -1
    target_fd = -1
    digest = hashlib.sha256()
    try:
        source_fd = os.open(
            snapshot.path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise BackupSnapshotUnverifiedError("backup snapshot은 regular file이어야 합니다.")
        target_fd = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(source_fd, "rb") as source, os.fdopen(target_fd, "wb") as destination:
            source_fd = -1
            target_fd = -1
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if digest.hexdigest() != snapshot.checksum_sha256:
            raise BackupSnapshotUnverifiedError(
                "restore 직전 backup snapshot checksum이 바뀌었습니다."
            )
        yield target
    except OSError as exc:
        raise BackupServiceError(
            "backup snapshot을 private restore 영역으로 복사할 수 없습니다."
        ) from exc
    finally:
        if source_fd != -1:
            os.close(source_fd)
        if target_fd != -1:
            os.close(target_fd)
        shutil.rmtree(temporary_dir, ignore_errors=True)


def _snapshot_from_script_result(
    *,
    stdout: str,
    directory: Path,
    before: set[Path],
) -> BackupSnapshot | None:
    directory = directory.resolve()

    def verified_path(value: str) -> Path:
        candidate = Path(value)
        if candidate.is_symlink() or not candidate.is_file():
            raise BackupServiceError("backup script returned a non-regular dump path")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(directory)
        except ValueError as exc:
            raise BackupServiceError(
                "backup script returned a dump outside the approved directory"
            ) from exc
        return resolved

    match = _BACKUP_FILE_RE.search(stdout)
    if match:
        return _snapshot_from_file(verified_path(match.group("path")))

    created = [
        path
        for path in directory.glob("*.dump")
        if path.is_file() and not path.is_symlink() and path.resolve() not in before
    ]
    if created:
        created.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return _snapshot_from_file(created[0])
    return None


async def create_backup_snapshot(*, access_reason: str) -> BackupSnapshot:
    if settings.pinvi_environment in _STRICT_BACKUP_ENVIRONMENTS:
        raise BackupServiceError(
            "staging/production backup은 API 컨테이너에서 만들 수 없습니다. "
            "root-owned trusted backup producer를 사용하세요."
        )
    script = _validated_backup_script()

    directory = backup_dir()
    if settings.pinvi_environment in _STRICT_BACKUP_ENVIRONMENTS and directory.is_symlink():
        raise BackupServiceError("운영 backup directory는 symlink일 수 없습니다.")
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise BackupServiceError("backup directory is not a directory")
    directory = directory.resolve()
    _ensure_backup_disk_space(directory)

    before = {path.resolve() for path in directory.glob("*.dump")}
    env = {
        "PATH": _SAFE_EXECUTION_PATH,
        "PINVI_ENVIRONMENT": settings.pinvi_environment,
        "PINVI_BACKUP_DIR": str(directory),
        "PINVI_BACKUP_SCHEMA": settings.pinvi_backup_schema,
        "PINVI_BACKUP_MIN_FREE_BYTES": str(settings.pinvi_backup_min_free_bytes),
        "PINVI_BACKUP_REASON": access_reason,
        "PINVI_BACKUP_DATABASE_URL": settings.pinvi_database_url,
        "PINVI_DATABASE_URL": "",
        "PINVI_BACKUP_DOCKER_FALLBACK": "0",
    }
    if settings.pinvi_environment in _STRICT_BACKUP_ENVIRONMENTS:
        pg_dump = Path(_pinned_postgres_tool("pg_dump"))
        env.update(
            {
                "PINVI_BACKUP_PG_DUMP_BIN": str(pg_dump),
                "PINVI_BACKUP_PG_DUMP_SHA256": _sha256_file(pg_dump),
                "PINVI_BACKUP_PRIVATE_TOOL_COPY": "0",
            }
        )

    proc = await asyncio.create_subprocess_exec(
        str(script),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(repo_root()),
        start_new_session=True,
    )
    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(
            proc.communicate(),
            timeout=settings.pinvi_backup_timeout_seconds,
        )
    except TimeoutError as exc:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()
        raise BackupServiceError(sanitize_backup_message("backup script timed out")) from exc

    stdout = stdout_raw.decode("utf-8", errors="replace")
    stderr = stderr_raw.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        message = stderr or stdout or f"backup script exited {proc.returncode}"
        raise BackupServiceError(sanitize_backup_message(message))

    snapshot = _snapshot_from_script_result(stdout=stdout, directory=directory, before=before)
    if snapshot:
        return snapshot

    raise BackupServiceError("backup script completed without creating a dump")


def _ensure_backup_disk_space(directory: Path) -> None:
    min_free_bytes = settings.pinvi_backup_min_free_bytes
    if min_free_bytes <= 0:
        return
    free_bytes = shutil.disk_usage(directory).free
    if free_bytes < min_free_bytes:
        raise BackupDiskGuardError(
            f"backup disk guard failed: free_bytes={free_bytes} required_bytes={min_free_bytes}"
        )


# 동시 복원은 동일 DB에 두 개의 비가역 schema-swap을 겹쳐 무결성을 깨뜨린다.
# 이 lock은 같은 API worker를 빠르게 직렬화하고, 프로세스 간 직렬화는
# restore-hotswap.sh가 전체 실행 동안 보유하는 DB advisory lock이 담당한다.
_restore_lock = asyncio.Lock()


def _asyncpg_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return f"postgresql+asyncpg://{database_url.removeprefix('postgresql://')}"
    return database_url


def _restore_lock_database_url() -> str:
    database_url = settings.pinvi_restore_database_url or settings.pinvi_database_url
    return _asyncpg_database_url(database_url)


def _pinned_postgres_tool(name: str) -> str:
    """Return a non-symlink PostgreSQL client from an allowlisted system directory."""

    directories = [Path("/usr/local/bin"), Path("/usr/bin"), Path("/bin")]
    directories.extend(sorted(Path("/usr/lib/postgresql").glob("*/bin")))
    for directory in directories:
        candidate = directory / name
        if not candidate.is_file() or candidate.is_symlink() or not os.access(candidate, os.X_OK):
            continue
        resolved = candidate.resolve()
        if resolved.parent in {
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            Path("/bin"),
        } or re.fullmatch(r"/usr/lib/postgresql/[0-9]+/bin", str(resolved.parent)):
            return str(resolved)
    raise BackupServiceError(f"pinned PostgreSQL tool is missing: {name}")


def _pinned_bash_tool() -> str:
    """Return a non-symlink bash executable from an allowlisted system directory."""

    for directory in (Path("/usr/local/bin"), Path("/usr/bin"), Path("/bin")):
        candidate = directory / "bash"
        if not candidate.is_file() or candidate.is_symlink() or not os.access(candidate, os.X_OK):
            continue
        resolved = candidate.resolve()
        if resolved.parent in {
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            Path("/bin"),
        }:
            return str(resolved)
    raise BackupServiceError("pinned bash tool is missing")


def _process_descendants(root_pid: int) -> list[int]:
    """Return Linux descendants without relying on an untrusted process command."""

    children_by_parent: dict[int, list[int]] = {}
    proc_root = Path("/proc")
    try:
        entries = tuple(proc_root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="utf-8").rsplit(") ", 1)[1].split()
            pid = int(entry.name)
            parent_pid = int(fields[1])
        except (OSError, IndexError, ValueError):
            continue
        children_by_parent.setdefault(parent_pid, []).append(pid)

    descendants: list[int] = []
    pending = [root_pid]
    while pending:
        parent_pid = pending.pop()
        for child_pid in children_by_parent.get(parent_pid, []):
            descendants.append(child_pid)
            pending.append(child_pid)
    return descendants


def _terminate_processes(process_ids: list[int], signum: signal.Signals) -> None:
    for child_pid in reversed(process_ids):
        try:
            os.kill(child_pid, signum)
        except ProcessLookupError:
            pass


async def _terminate_restore_process(
    proc: asyncio.subprocess.Process,
    communicate_task: asyncio.Task[tuple[bytes, bytes]],
) -> tuple[bytes, bytes]:
    """Stop a restore process only after its shell cleanup trap has run."""

    descendant_pids = _process_descendants(proc.pid)
    try:
        proc.send_signal(signal.SIGTERM)
    except ProcessLookupError:
        pass

    shell_exited = False
    try:
        await asyncio.wait_for(proc.wait(), timeout=1.0)
        shell_exited = True
    except TimeoutError:
        pass
    if shell_exited:
        _terminate_processes(descendant_pids, signal.SIGTERM)
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    try:
        return await asyncio.wait_for(
            asyncio.shield(communicate_task),
            timeout=10.0,
        )
    except TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return await communicate_task


async def _database_identity(database_url: str) -> dict[str, str]:
    """Read the immutable database identity used to bind a schema swap."""

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """
                        SELECT
                            current_database() AS database_name,
                            d.oid::text AS database_oid,
                            (pg_control_system()).system_identifier::text AS system_identifier,
                            COALESCE(host(inet_server_addr()), '') AS hostaddr,
                            inet_server_port()::text AS port
                        FROM pg_database d
                        WHERE d.datname = current_database()
                        """
                        )
                    )
                )
                .mappings()
                .one()
            )
    except Exception as exc:
        raise BackupServiceError("restore target identity could not be verified") from exc
    finally:
        await engine.dispose()

    values = {
        "PINVI_RESTORE_EXPECTED_DATABASE_NAME": str(row["database_name"]),
        "PINVI_RESTORE_EXPECTED_DATABASE_OID": str(row["database_oid"]),
        "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER": str(row["system_identifier"]),
        "PINVI_RESTORE_EXPECTED_HOSTADDR": str(row["hostaddr"]),
        "PINVI_RESTORE_EXPECTED_PORT": str(row["port"]),
    }
    if any(not value or value == "None" for value in values.values()):
        raise BackupServiceError("database identity is incomplete")
    return values


async def _restore_target_identity() -> dict[str, str]:
    """Bind the restore target to the same database identity used by the API."""

    application_identity = await _database_identity(
        _asyncpg_database_url(settings.pinvi_database_url)
    )
    target_identity = await _database_identity(_restore_lock_database_url())
    if target_identity != application_identity:
        raise BackupServiceError("restore target is not the application database")
    return target_identity


async def restore_backup_hotswap(
    *,
    snapshot_id: str,
    access_reason: str,
) -> BackupRestoreRun:
    async with _restore_lock:
        return await _restore_backup_hotswap_locked(
            snapshot_id=snapshot_id, access_reason=access_reason
        )


async def _restore_backup_hotswap_locked(
    *,
    snapshot_id: str,
    access_reason: str,
) -> BackupRestoreRun:
    if settings.pinvi_environment in _STRICT_BACKUP_ENVIRONMENTS:
        raise BackupServiceError(
            "staging/production schema-swap은 API 컨테이너에서 실행할 수 없습니다. "
            "root-owned one-shot restore runner를 사용하세요."
        )

    snapshot = get_backup_snapshot(snapshot_id=snapshot_id)
    if snapshot.status != "verified" or snapshot.checksum_sha256 is None:
        raise BackupSnapshotUnverifiedError(
            "checksum sidecar로 검증되지 않은 snapshot은 복구에 사용할 수 없습니다."
        )
    script = restore_hotswap_script_path()
    canonical_script = repo_root() / "scripts" / "restore-hotswap.sh"
    if settings.pinvi_environment in {"staging", "production"} and script != canonical_script:
        raise BackupServiceError("운영 schema-swap script는 repository canonical 경로여야 합니다.")
    if script.is_symlink() or not script.is_file():
        raise BackupServiceError(f"restore hotswap script not found: {script}")
    script_sha256 = _sha256_file(script)
    expected_script_sha256 = settings.pinvi_restore_hotswap_script_sha256
    if settings.pinvi_environment in {"staging", "production"} and (
        not re.fullmatch(r"[0-9a-f]{64}", expected_script_sha256)
        or script_sha256 != expected_script_sha256
    ):
        raise BackupServiceError("운영 schema-swap script digest pin이 없습니다.")

    started_at = datetime.now(UTC)
    # 초 해상도만 쓰면 같은 초에 두 번 복원 시 restore_id(→ 스키마명)가 충돌한다. uuid suffix로 고유화.
    restore_id = f"{started_at.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    schema = settings.pinvi_backup_schema
    restore_schema = f"{schema}_restore_{restore_id}"
    previous_schema = f"{schema}_previous_{restore_id}"
    env = {
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith("PINVI_RESTORE_")
            and key
            not in {
                "BASH_ENV",
                "CDPATH",
                "ENV",
                "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_SYSTEM",
                "GIT_SSH",
                "GIT_SSH_COMMAND",
                "LD_AUDIT",
                "LD_LIBRARY_PATH",
                "LD_PRELOAD",
                "PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST",
                "PINVI_M05_RESTORE_TEST_MODE",
                "PINVI_RESTORE_BASH_BIN",
                "PINVI_RESTORE_BASH_SHA256",
                "PINVI_RESTORE_PG_RESTORE_BIN",
                "PINVI_RESTORE_PSQL_BIN",
                "PINVI_RESTORE_PRIVATE_TOOL_COPY",
                "PINVI_RESTORE_SETSID_BIN",
                "PYTHONHOME",
                "PYTHONPATH",
                "RUBYLIB",
            }
        },
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PINVI_BACKUP_SCHEMA": schema,
        "PINVI_RESTORE_REASON": access_reason,
        "PINVI_RESTORE_ID": restore_id,
        "PINVI_RESTORE_SCHEMA": restore_schema,
        "PINVI_PREVIOUS_SCHEMA": previous_schema,
        "PINVI_DATABASE_URL": settings.pinvi_database_url,
        "PINVI_RESTORE_DATABASE_URL": settings.pinvi_restore_database_url,
        "PINVI_RESTORE_FENCE_DATABASE_URL": settings.pinvi_restore_fence_database_url,
        "PINVI_RESTORE_HOTSWAP_EXECUTE": ("1" if settings.pinvi_restore_hotswap_execute else "0"),
        "PINVI_RESTORE_DRAIN_COMMAND": settings.pinvi_restore_drain_command,
        "PINVI_RESTORE_ALLOW_NO_DRAIN": ("1" if settings.pinvi_restore_allow_no_drain else "0"),
        "PINVI_RESTORE_DRAIN_VERIFIED": ("1" if settings.pinvi_restore_drain_verified else "0"),
        "PINVI_RESTORE_APP_ROLE": settings.pinvi_restore_app_role,
        "PINVI_RESTORE_API_TRIGGER": "1",
        "PINVI_M05_RESTORE_TEST_MODE": "0",
    }
    if settings.pinvi_restore_hotswap_execute:
        target_identity = await _restore_target_identity()
        fence_url = settings.pinvi_restore_fence_database_url
        if not fence_url:
            raise BackupServiceError(
                "schema-swap 실행에는 target database owner fence URL이 필요합니다."
            )
        fence_identity = await _database_identity(_asyncpg_database_url(fence_url))
        if fence_identity != target_identity:
            raise BackupServiceError("database fence target is not the application database")
        env.update(target_identity)
        pg_restore_path = _pinned_postgres_tool("pg_restore")
        psql_path = _pinned_postgres_tool("psql")
        bash_path = _pinned_bash_tool()
        env.update(
            {
                "PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST": "1",
                "PINVI_RESTORE_PG_RESTORE_BIN": pg_restore_path,
                "PINVI_RESTORE_PG_RESTORE_SHA256": _sha256_file(Path(pg_restore_path)),
                "PINVI_RESTORE_PSQL_BIN": psql_path,
                "PINVI_RESTORE_PSQL_SHA256": _sha256_file(Path(psql_path)),
                "PINVI_RESTORE_BASH_BIN": bash_path,
                "PINVI_RESTORE_BASH_SHA256": _sha256_file(Path(bash_path)),
            }
        )

    with _verified_snapshot_copy(snapshot) as verified_snapshot:
        with tempfile.TemporaryDirectory(prefix="pinvi-restore-script-", dir="/tmp") as script_dir:
            verified_script = Path(script_dir) / "restore-hotswap.sh"
            shutil.copyfile(script, verified_script)
            verified_script.chmod(0o700)
            if _sha256_file(verified_script) != script_sha256:
                raise BackupServiceError("restore hotswap script changed during staging")
            proc = await asyncio.create_subprocess_exec(
                env.get("PINVI_RESTORE_BASH_BIN", "/usr/bin/bash"),
                str(verified_script),
                "run",
                str(verified_snapshot),
                restore_schema,
                previous_schema,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(repo_root()),
                start_new_session=True,
            )
            communicate_task = asyncio.create_task(proc.communicate())
            try:
                stdout_raw, stderr_raw = await asyncio.wait_for(
                    asyncio.shield(communicate_task),
                    timeout=settings.pinvi_restore_timeout_seconds,
                )
            except TimeoutError as exc:
                # Signal the shell first so its EXIT trap can release the database
                # fence and advisory lock. SIGKILL on the process group is the
                # final fail-safe after the cleanup grace period.
                await _terminate_restore_process(proc, communicate_task)
                raise BackupServiceError(
                    sanitize_backup_message("restore hotswap script timed out")
                ) from exc
            except asyncio.CancelledError:
                # Cancellation must not abandon a shell that still owns the
                # database fence or advisory-lock session. Finish the same
                # cleanup sequence as the timeout path, then preserve the
                # caller's cancellation semantics.
                await _terminate_restore_process(proc, communicate_task)
                raise

    stdout = stdout_raw.decode("utf-8", errors="replace")
    stderr = stderr_raw.decode("utf-8", errors="replace")
    phases = _parse_restore_phases(stdout)
    completed_at = datetime.now(UTC)
    if proc.returncode != 0:
        message = stderr or stdout or f"restore hotswap script exited {proc.returncode}"
        raise BackupServiceError(sanitize_backup_message(message))

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
