"""`scripts/backup-db.sh` smoke tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

BASH_BIN = "/usr/bin/bash"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def _base_env(tmp_path: Path, fake_bin: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "PINVI_BACKUP_DIR": str(tmp_path / "backups"),
            "PINVI_BACKUP_SCHEMA": "app",
            "PINVI_BACKUP_DATABASE_URL": "postgresql+asyncpg://pinvi:credential@db:5432/pinvi",
            "PINVI_BACKUP_MIN_FREE_BYTES": "0",
            "PINVI_BACKUP_PG_DUMP_BIN": "missing-pg-dump-for-test",
        },
    )
    return env


def test_backup_db_script_uses_docker_fallback_when_pg_dump_is_missing(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_args = tmp_path / "docker-args.txt"
    backup_dir = tmp_path / "backups"
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$@" > "$PINVI_TEST_DOCKER_ARGS"
case "$PINVI_BACKUP_DUMP_FILE" in
  /backup/*) ;;
  *) exit 44 ;;
esac
host_target="$PINVI_TEST_BACKUP_DIR/${PINVI_BACKUP_DUMP_FILE#/backup/}"
mkdir -p "$(dirname "$host_target")"
printf 'docker-dump' > "$host_target"
""",
    )
    env = _base_env(tmp_path, fake_bin)
    env.update(
        {
            "PINVI_BACKUP_DOCKER_BIN": "docker",
            "PINVI_BACKUP_DOCKER_IMAGE": "postgis/postgis:16-3.5",
            "PINVI_BACKUP_DOCKER_NETWORK": "pinvi_app_default",
            "PINVI_TEST_BACKUP_DIR": str(backup_dir),
            "PINVI_TEST_DOCKER_ARGS": str(docker_args),
        },
    )

    result = subprocess.run(  # noqa: S603
        [BASH_BIN, str(_repo_root() / "scripts" / "backup-db.sh")],
        cwd=_repo_root(),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "BACKUP_FILE=" in result.stdout
    dumps = list(backup_dir.glob("*.dump"))
    assert len(dumps) == 1
    assert dumps[0].read_text(encoding="utf-8") == "docker-dump"
    assert Path(f"{dumps[0]}.sha256").is_file()

    args = docker_args.read_text(encoding="utf-8")
    assert "--network\npinvi_app_default" in args
    assert "postgis/postgis:16-3.5" in args
    assert "credential" not in args


def test_backup_db_script_can_disable_docker_fallback(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    env = _base_env(tmp_path, fake_bin)
    env["PINVI_BACKUP_DOCKER_FALLBACK"] = "0"

    result = subprocess.run(  # noqa: S603
        [BASH_BIN, str(_repo_root() / "scripts" / "backup-db.sh")],
        cwd=_repo_root(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 127
    assert "pg_dump not found" in result.stderr
    assert not list((tmp_path / "backups").glob("*.dump"))
