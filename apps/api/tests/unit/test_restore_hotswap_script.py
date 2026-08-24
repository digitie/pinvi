from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "scripts/restore-hotswap.sh"
BASH_BIN = "/usr/bin/bash"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def test_restore_hotswap_rejects_session_and_lock_control_in_dump_sql() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "pg_advisory_(lock|unlock)" in source
    assert "pg_(cancel|terminate)_backend" in source
    assert "discard[[:space:]]+all" in source
    assert "end|rollback|abort" in source
    assert "block_comment_depth" in source
    assert "dollar_delimiter" in source
    assert "advisory_lock_sql_guard" in source
    assert source.count("advisory_lock_sql_guard") >= 6
    assert 'exec "${PSQL_BIN}" --no-psqlrc -v ON_ERROR_STOP=1 -Atq "${DATABASE_URL}"' in source
    assert "trap terminate_restore TERM INT" in source
    assert "execute_fence_sql_file" in source
    assert "PINVI_RESTORE_FENCE_DATABASE_URL" in source
    assert "database fence URL must be a dedicated non-superuser target owner" in source
    assert "FENCE_EXECUTOR_ROLE" in source
    assert "login.rolname <> '${FENCE_EXECUTOR_ROLE}'" in source
    assert source.count("login.rolname <> current_user") >= 2
    assert "SET session_replication_role = replica" not in source


def test_restore_hotswap_validates_all_m05_always_triggers_before_switch() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "restored schema is missing an ENABLE ALWAYS M05 append-only trigger" in source
    assert "t.tgenabled = 'A'" in source
    assert "NOT t.tgisinternal" in source
    assert "guard_ktm_feature_reference_reconciliation_append_only" in source
    assert (
        "left('trg_ktm_feature_reference_reconciliation_delivery_attempts_append_only', 63)"
        in source
    )
    assert (
        "left('trg_ktm_feature_reference_reconciliation_impacts_truncate_append_only', 63)"
        in source
    )


def test_restore_hotswap_sql_guard_executes_and_ignores_literal_controls() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    start_marker = "  if awk '\n"
    end_marker = '\n  \' "${sql_file}"; then'
    start = source.index(start_marker) + len(start_marker)
    end = source.index(end_marker, start)
    awk_program = source[start:end]
    safe_sql = """/* COMMIT; */
CREATE FUNCTION app.users_guard() RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
  RAISE NOTICE 'COMMIT; pg_advisory_lock(1, 2)';
  RETURN NEW;
END;
$fn$;
\\restrict trusted_dump_token
\\unrestrict trusted_dump_token
COPY app.users (id) FROM stdin;
COMMIT;
\\.
SELECT 1;
"""
    unsafe_sql = "SELECT 1;\nCOMMIT;\n\\! true\n"
    awk = shutil.which("awk")
    assert awk is not None

    safe = subprocess.run(  # noqa: S603
        [awk, awk_program, "-"],
        input=safe_sql,
        text=True,
        capture_output=True,
        check=False,
    )
    unsafe = subprocess.run(  # noqa: S603
        [awk, awk_program, "-"],
        input=unsafe_sql,
        text=True,
        capture_output=True,
        check=False,
    )

    assert safe.returncode == 1, safe.stderr
    assert unsafe.returncode == 0, unsafe.stderr


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_restore_hotswap_rejects_test_mode_outside_test_before_db_tool(
    tmp_path: Path,
    environment: str,
) -> None:
    marker = tmp_path / "db-tool-called"
    fake_tool = tmp_path / "fake-db-tool"
    _write_executable(
        fake_tool,
        """#!/usr/bin/env bash
set -euo pipefail
touch "$PINVI_TEST_TOOL_MARKER"
exit 99
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "PINVI_M05_RESTORE_TEST_MODE": "1",
            "PINVI_ENVIRONMENT": environment,
            "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
            "PINVI_DATABASE_URL": "postgresql://fixture@db:5432/pinvi",
            "PINVI_RESTORE_PG_RESTORE_BIN": str(fake_tool),
            "PINVI_RESTORE_PSQL_BIN": str(fake_tool),
            "PINVI_TEST_TOOL_MARKER": str(marker),
        }
    )

    result = subprocess.run(  # noqa: S603
        [
            BASH_BIN,
            str(SCRIPT),
            "run",
            str(tmp_path / "never.dump"),
            "app_restore",
            "app_previous",
        ],
        cwd=SCRIPT.parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert "M05 restore test mode requires PINVI_ENVIRONMENT=test" in result.stdout
    assert not marker.exists()


def test_restore_hotswap_requires_explicit_fence_url_before_db_tool(tmp_path: Path) -> None:
    marker = tmp_path / "db-tool-called"
    fake_tool = tmp_path / "fake-db-tool"
    _write_executable(
        fake_tool,
        """#!/usr/bin/env bash
set -euo pipefail
touch "$PINVI_TEST_TOOL_MARKER"
exit 99
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "PINVI_ENVIRONMENT": "staging",
            "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
            "PINVI_DATABASE_URL": "postgresql://fixture@db:5432/pinvi",
            "PINVI_RESTORE_PG_RESTORE_BIN": str(fake_tool),
            "PINVI_RESTORE_PSQL_BIN": str(fake_tool),
            "PINVI_TEST_TOOL_MARKER": str(marker),
        }
    )
    env.pop("PINVI_M05_RESTORE_TEST_MODE", None)
    env.pop("PINVI_RESTORE_FENCE_DATABASE_URL", None)

    result = subprocess.run(  # noqa: S603
        [
            BASH_BIN,
            str(SCRIPT),
            "run",
            str(tmp_path / "never.dump"),
            "app_restore",
            "app_previous",
        ],
        cwd=SCRIPT.parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert "PINVI_RESTORE_FENCE_DATABASE_URL is required" in result.stdout
    assert not marker.exists()
