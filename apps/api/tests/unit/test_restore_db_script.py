"""`scripts/restore-db.sh` fresh-destination bootstrap regression."""

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


def test_restore_db_bootstraps_schema_and_regrants_explicit_runtime_role(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    invocation_log = tmp_path / "invocations.log"
    snapshot = tmp_path / "m05.dump"
    snapshot.write_bytes(b"custom-format-fixture")
    _write_executable(
        fake_bin / "psql",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"FROM pg_roles"* ]]; then
  printf 't\\n'
fi
printf 'psql:%s\\n' "$*" >> "$PINVI_TEST_LOG"
""",
    )
    _write_executable(
        fake_bin / "pg_restore",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'pg_restore:%s\\n' "$*" >> "$PINVI_TEST_LOG"
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "PINVI_RESTORE_DATABASE_URL": "postgresql://pinvi:fixture@db:5432/pinvi",
            "PINVI_RESTORE_APP_ROLE": "pinvi_app",
            "PINVI_TEST_LOG": str(invocation_log),
        }
    )

    result = subprocess.run(  # noqa: S603
        [BASH_BIN, str(_repo_root() / "scripts" / "restore-db.sh"), str(snapshot)],
        cwd=_repo_root(),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout == f"RESTORED_FILE={snapshot}\n"
    calls = invocation_log.read_text(encoding="utf-8").splitlines()
    assert calls[0].startswith("psql:")
    assert "FROM pg_roles" in calls[0]
    assert calls[1].startswith("psql:")
    assert 'CREATE SCHEMA IF NOT EXISTS "app"' in calls[1]
    assert calls[2].startswith("pg_restore:")
    assert "--no-owner" in calls[2]
    assert "--no-privileges" in calls[2]
    assert calls[3].startswith("psql:")
    assert 'GRANT USAGE ON SCHEMA "app" TO "pinvi_app"' in calls[3]


def test_restore_db_rejects_invalid_runtime_role_before_schema_mutation(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    invocation_log = tmp_path / "invocations.log"
    snapshot = tmp_path / "m05.dump"
    snapshot.write_bytes(b"custom-format-fixture")
    _write_executable(
        fake_bin / "psql",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'psql:%s\\n' "$*" >> "$PINVI_TEST_LOG"
printf 'f\\n'
""",
    )
    _write_executable(
        fake_bin / "pg_restore",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'pg_restore:%s\\n' "$*" >> "$PINVI_TEST_LOG"
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "PINVI_RESTORE_DATABASE_URL": "postgresql://pinvi:fixture@db:5432/pinvi",
            "PINVI_RESTORE_APP_ROLE": "pinvi_app",
            "PINVI_TEST_LOG": str(invocation_log),
        }
    )

    result = subprocess.run(  # noqa: S603
        [BASH_BIN, str(_repo_root() / "scripts" / "restore-db.sh"), str(snapshot)],
        cwd=_repo_root(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert "PINVI_RESTORE_APP_ROLE" in result.stderr
    calls = invocation_log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert calls[0].startswith("psql:")
    assert "FROM pg_roles" in calls[0]
