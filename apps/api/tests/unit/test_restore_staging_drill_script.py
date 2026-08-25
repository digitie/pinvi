"""restore-staging-drill.sh contract tests."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

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
if [[ -n "${PINVI_TEST_TOOL_MARKER:-}" ]]; then
  touch "$PINVI_TEST_TOOL_MARKER"
fi
exit 0
""",
    )
    _write_executable(
        fake_bin / "psql",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${PINVI_TEST_TOOL_MARKER:-}" ]]; then
  touch "$PINVI_TEST_TOOL_MARKER"
fi
sql="${*: -1}"
if [[ "$*" == *"DROP SCHEMA"* ]]; then
  exit 0
elif [[ "$sql" == *"FROM pg_roles"* ]]; then
  echo t
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
    env["PINVI_M05_RESTORE_TEST_MODE"] = "1"
    env["PINVI_ENVIRONMENT"] = "test"
    for key in (
        "PINVI_DATABASE_URL",
        "PINVI_RESTORE_DATABASE_URL",
        "PINVI_RESTORE_HOTSWAP_DATABASE_URL",
        "PINVI_RESTORE_STAGING_DATABASE_URL",
        "PINVI_RESTORE_DRILL_ALLOW_NON_STAGING",
        "PINVI_RESTORE_APP_ROLE",
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


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_restore_staging_drill_rejects_test_mode_before_restore_tools(
    tmp_path: Path,
    environment: str,
) -> None:
    snapshot = tmp_path / "pinvi-app-test.dump"
    _write_snapshot(snapshot)
    marker = tmp_path / "restore-tool-called"
    env = _fake_tool_env(tmp_path)
    env.update(
        {
            "PINVI_ENVIRONMENT": environment,
            "PINVI_DATABASE_URL": "postgresql://pinvi:fixture@db:5432/pinvi",
            "PINVI_RESTORE_DRILL_ALLOW_NON_STAGING": "1",
            "PINVI_TEST_TOOL_MARKER": str(marker),
        }
    )

    result = subprocess.run(  # noqa: S603
        [str(SCRIPT), "run", str(snapshot)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert "M05 restore test mode requires PINVI_ENVIRONMENT=test" in result.stdout
    assert not marker.exists()


def test_restore_staging_drill_forwards_target_binding_marker() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert (
        "RESTORE_TARGET_BINDING=*|RESTORE_SOURCE_BINDING=*) printf '%s\\n' \"${restore_line}\" ;;"
        in script
    )
    assert (
        'FENCE_DATABASE_URL="${PINVI_RESTORE_FENCE_DATABASE_URL:-${STAGING_DATABASE_URL}}"'
        in script
    )
    assert 'TRUSTED_SNAPSHOT="${SNAPSHOT}"' in script
    assert 'restore-db.sh" "${TRUSTED_SNAPSHOT}"' in script
    assert 'PINVI_RESTORE_FENCE_DATABASE_URL="${FENCE_DATABASE_URL}"' in script
    assert "PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME" in script
    assert "PINVI_RESTORE_FENCE_DATABASE_URL is required for a non-test staging drill" in script
    assert "PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL=none|precheck" in script
    assert "DROP SCHEMA" not in script
    assert "rollback_database_fence" not in script
    assert "m05_advisory_lock_present" not in script
    assert "drain rollback rehearsal is unavailable" in script
    assert "PINVI_M05_OPERATION_LEASE_FD" in script
    assert "PINVI_M05_OPERATION_LEASE_TOKEN" in script
    assert "assert_operation_lease" in script
    assert "strict staging drill requires a trusted target operation lease" in script


def test_restore_staging_drill_rejects_managed_run_without_lease_before_tools(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "pinvi-app-staging.dump"
    _write_snapshot(snapshot)
    marker = tmp_path / "restore-tool-called"
    env = _fake_tool_env(tmp_path)
    env.update(
        {
            "PINVI_M05_RESTORE_TEST_MODE": "0",
            "PINVI_ENVIRONMENT": "staging",
            "PINVI_RESTORE_STAGING_DATABASE_URL": "postgresql://pinvi:pinvi@localhost:5432/pinvi_staging",
            "PINVI_RESTORE_FENCE_DATABASE_URL": "postgresql://fence:fence@localhost:5432/pinvi_staging",
            "PINVI_TEST_TOOL_MARKER": str(marker),
        }
    )

    result = subprocess.run(  # noqa: S603
        [str(SCRIPT), "run", str(snapshot)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert "strict staging drill requires a trusted target operation lease" in result.stdout
    assert not marker.exists()


def test_restore_staging_drill_rejects_legacy_drain_before_any_database_tool(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "pinvi-app-test.dump"
    _write_snapshot(snapshot)
    marker = tmp_path / "restore-tool-called"
    env = _fake_tool_env(tmp_path)
    env.update(
        {
            "PINVI_RESTORE_STAGING_DATABASE_URL": (
                "postgresql://pinvi:pinvi@localhost:5432/pinvi_staging"
            ),
            "PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL": "drain",
            "PINVI_TEST_TOOL_MARKER": str(marker),
        }
    )

    result = subprocess.run(  # noqa: S603
        [str(SCRIPT), "run", str(snapshot)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert "drain rollback rehearsal is unavailable" in result.stdout
    assert not marker.exists()


def test_restore_staging_drill_masks_path_and_rehearses_guard(tmp_path: Path) -> None:
    snapshot = tmp_path / "pinvi-app-test.dump"
    _write_snapshot(snapshot)
    env = _fake_tool_env(tmp_path)
    env["PINVI_RESTORE_STAGING_DATABASE_URL"] = (
        "postgresql://pinvi:pinvi@localhost:5432/pinvi_staging"
    )
    env["PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL"] = "precheck"
    env["PINVI_RESTORE_APP_ROLE"] = "pinvi_app"

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
    env["PINVI_RESTORE_APP_ROLE"] = "pinvi_app"

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
