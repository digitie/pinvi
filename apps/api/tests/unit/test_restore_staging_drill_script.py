"""restore-staging-drill.sh contract tests."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "restore-staging-drill.sh"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def _write_snapshot(path: Path, *, absolute_sidecar_path: bool = False) -> None:
    content = b"pinvi dump fixture"
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    sidecar_path = path if absolute_sidecar_path else path.name
    path.with_suffix(".dump.sha256").write_text(
        f"{digest}  {sidecar_path}\n",
        encoding="utf-8",
    )


def _fake_tool_env(tmp_path: Path) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "pg_restore",
        """#!/usr/bin/env bash
set -euo pipefail
exit 0
""",
    )
    _write_executable(
        fake_bin / "psql",
        """#!/usr/bin/env bash
set -euo pipefail
sql="${*: -1}"
if [[ "$*" == *"DROP SCHEMA"* ]]; then
  exit 0
elif [[ "$sql" == *"lag(content_hash)"* ]]; then
  echo valid
elif [[ "$sql" == *"to_regnamespace"* ]]; then
  echo 12345
elif [[ "$sql" == *"to_regclass('app.users')"* ]]; then
  echo t
elif [[ "$sql" == *"count(*)::text FROM app.users"* ]]; then
  echo 3
elif [[ "$sql" == *"to_regclass('app.trips')"* ]]; then
  echo t
elif [[ "$sql" == *"count(*)::text FROM app.trips"* ]]; then
  echo 2
elif [[ "$sql" == *"to_regclass('app.admin_audit_log')"* ]]; then
  echo t
elif [[ "$sql" == *"count(*)::text FROM app.admin_audit_log"* ]]; then
  echo 4
else
  echo 1
fi
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    for key in (
        "PINVI_DATABASE_URL",
        "PINVI_RESTORE_DATABASE_URL",
        "PINVI_RESTORE_STAGING_DATABASE_URL",
        "PINVI_RESTORE_DRILL_ALLOW_NON_STAGING",
    ):
        env.pop(key, None)
    return env


def test_restore_staging_drill_requires_staging_url(tmp_path: Path) -> None:
    snapshot = tmp_path / "pinvi-app-test.dump"
    _write_snapshot(snapshot)
    env = _fake_tool_env(tmp_path)

    result = subprocess.run(  # noqa: S603
        [str(SCRIPT), "run", str(snapshot)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "PINVI_RESTORE_STAGING_DATABASE_URL is required" in result.stdout


def test_restore_staging_drill_masks_path_and_rehearses_guard(tmp_path: Path) -> None:
    snapshot = tmp_path / "pinvi-app-test.dump"
    _write_snapshot(snapshot)
    env = _fake_tool_env(tmp_path)
    env["PINVI_RESTORE_STAGING_DATABASE_URL"] = (
        "postgresql://pinvi:pinvi@localhost:5432/pinvi_staging"
    )
    env["PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL"] = "precheck"

    result = subprocess.run(  # noqa: S603
        [str(SCRIPT), "run", str(snapshot)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "DRILL_EVIDENCE=snapshot=backup://pinvi-app-test.dump" in result.stdout
    assert "DRILL_EVIDENCE=admin_audit_chain_links=valid" in result.stdout
    assert "DRILL_EVIDENCE=rollback_rehearsal=precheck_guard_schema_unchanged" in result.stdout
    assert "DRILL_PHASE=complete:success:staging restore drill completed" in result.stdout
    assert str(snapshot) not in result.stdout


def test_restore_staging_drill_accepts_legacy_absolute_sidecar(tmp_path: Path) -> None:
    snapshot = tmp_path / "pinvi-app-legacy.dump"
    _write_snapshot(snapshot, absolute_sidecar_path=True)
    env = _fake_tool_env(tmp_path)
    env["PINVI_RESTORE_STAGING_DATABASE_URL"] = (
        "postgresql://pinvi:pinvi@localhost:5432/pinvi_staging"
    )
    env["PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL"] = "precheck"

    result = subprocess.run(  # noqa: S603
        [str(SCRIPT), "run", str(snapshot)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "DRILL_EVIDENCE=checksum=verified" in result.stdout
    assert "DRILL_PHASE=complete:success:staging restore drill completed" in result.stdout
