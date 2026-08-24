from __future__ import annotations

import hashlib
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


def test_restore_hotswap_rejects_noncanonical_acl_before_write_fence_mutation() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "assert_supported_acl_topology()" in source
    assert "PINVI_RESTORE_WRITE_ROLES is not supported" in source
    assert "schema-swap requires canonical single-runtime-role ACLs" in source
    assert "aclexplode(COALESCE(c.relacl" in source
    assert "a.attacl IS NOT NULL" in source
    assert "OR p.prosecdef" in source
    assert "d.defaclnamespace = 0" in source
    assert "NOT owner_role.rolcreatedb" in source
    assert "AND NOT owner_role.rolinherit" in source
    assert "WHERE m.roleid = r.oid" in source
    assert "WHERE membership.member = owner_role.oid" in source
    assert "OR membership.roleid = owner_role.oid" in source
    assert "has_schema_privilege((SELECT oid FROM app_role), n.oid, 'USAGE')" in source
    assert "NOT has_schema_privilege((SELECT oid FROM app_role), n.oid, 'CREATE')" in source
    assert "PINVI_RESTORE_TRUSTED_BACKUP_DIR" in source
    assert "trusted snapshot archive inventory failed" in source
    enter = source.index("enter_write_fence()")
    assert source.index("  assert_supported_acl_topology\n", enter) < source.index(
        "  local writer_logins", enter
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
    unsafe_sql = (
        "SELECT 1;\nCOMMIT;\n\\! true\n",
        "\\copy app.users FROM PROGRAM 'id'\n",
        "\\i /tmp/restore.sql\n",
        "\\connect other_database\n",
        "SELECT 'DELETE FROM app.users' AS sql \\gexec\n",
        "\\.\n",
    )
    awk = shutil.which("awk")
    assert awk is not None

    safe = subprocess.run(  # noqa: S603
        [awk, awk_program, "-"],
        input=safe_sql,
        text=True,
        capture_output=True,
        check=False,
    )
    assert safe.returncode == 1, safe.stderr
    for sample in unsafe_sql:
        unsafe = subprocess.run(  # noqa: S603
            [awk, awk_program, "-"],
            input=sample,
            text=True,
            capture_output=True,
            check=False,
        )
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


def test_restore_hotswap_rejects_api_writable_snapshot_before_pg_restore(tmp_path: Path) -> None:
    marker = tmp_path / "pg-restore-called"
    snapshot = tmp_path / "untrusted.dump"
    snapshot.write_bytes(b"malicious-custom-archive")
    snapshot.with_name(f"{snapshot.name}.sha256").write_text(
        f"{hashlib.sha256(snapshot.read_bytes()).hexdigest()}  {snapshot.name}\n",
        encoding="utf-8",
    )
    fake_tool = tmp_path / "pg_restore"
    _write_executable(
        fake_tool,
        "#!/usr/bin/env bash\nset -euo pipefail\ntouch \"$PINVI_TEST_TOOL_MARKER\"\n",
    )
    env = os.environ.copy()
    env.update(
        {
            "PINVI_ENVIRONMENT": "production",
            "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
            "PINVI_RESTORE_DATABASE_URL": "postgresql://restore-owner@db:5432/pinvi",
            "PINVI_RESTORE_FENCE_DATABASE_URL": "postgresql://fence-owner@db:5432/pinvi",
            "PINVI_RESTORE_PG_RESTORE_BIN": str(fake_tool),
            "PINVI_TEST_TOOL_MARKER": str(marker),
        }
    )
    env.pop("PINVI_M05_RESTORE_TEST_MODE", None)

    result = subprocess.run(  # noqa: S603
        [BASH_BIN, str(SCRIPT), "run", str(snapshot), "app_restore", "app_previous"],
        cwd=SCRIPT.parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert "strict restore requires a root-owned trusted backup directory" in result.stdout
    assert not marker.exists()


def test_restore_hotswap_rejects_wrong_fence_target_before_mutation(tmp_path: Path) -> None:
    marker = tmp_path / "mutation-called"
    snapshot = tmp_path / "m05.dump"
    snapshot.write_bytes(b"custom-format-fixture")
    snapshot.with_name(f"{snapshot.name}.sha256").write_text(
        f"{hashlib.sha256(snapshot.read_bytes()).hexdigest()}  {snapshot.name}\n",
        encoding="utf-8",
    )
    pg_restore = tmp_path / "pg_restore"
    psql = tmp_path / "psql"
    _write_executable(
        pg_restore,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" != *"--list"* ]]; then
  touch "$PINVI_TEST_MUTATION_MARKER"
fi
""",
    )
    _write_executable(
        psql,
        """#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  *"--dbname=postgresql://restore-owner@db:5432/pinvi"*)
    printf 'pinvi|100|200|127.0.0.1|5432\\n'
    ;;
  *"--dbname=postgresql://fence-owner@db:5432/other"*)
    printf 'other|101|200|127.0.0.1|5432\\n'
    ;;
  *)
    touch "$PINVI_TEST_MUTATION_MARKER"
    exit 99
    ;;
esac
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "PINVI_ENVIRONMENT": "development",
            "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
            "PINVI_RESTORE_PRIVATE_TOOL_COPY": "1",
            "PINVI_RESTORE_DATABASE_URL": "postgresql://restore-owner@db:5432/pinvi",
            "PINVI_RESTORE_FENCE_DATABASE_URL": "postgresql://fence-owner@db:5432/other",
            "PINVI_RESTORE_PG_RESTORE_BIN": str(pg_restore),
            "PINVI_RESTORE_PG_RESTORE_SHA256": hashlib.sha256(pg_restore.read_bytes()).hexdigest(),
            "PINVI_RESTORE_PSQL_BIN": str(psql),
            "PINVI_RESTORE_PSQL_SHA256": hashlib.sha256(psql.read_bytes()).hexdigest(),
            "PINVI_RESTORE_BASH_BIN": BASH_BIN,
            "PINVI_RESTORE_BASH_SHA256": hashlib.sha256(Path(BASH_BIN).read_bytes()).hexdigest(),
            "PINVI_RESTORE_EXPECTED_DATABASE_NAME": "pinvi",
            "PINVI_RESTORE_EXPECTED_DATABASE_OID": "100",
            "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER": "200",
            "PINVI_RESTORE_EXPECTED_HOSTADDR": "127.0.0.1",
            "PINVI_RESTORE_EXPECTED_PORT": "5432",
            "PINVI_TEST_MUTATION_MARKER": str(marker),
        }
    )
    env.pop("PINVI_M05_RESTORE_TEST_MODE", None)

    result = subprocess.run(  # noqa: S603
        [BASH_BIN, str(SCRIPT), "run", str(snapshot), "app_restore", "app_previous"],
        cwd=SCRIPT.parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert "database fence target does not match the restore target" in result.stdout
    assert not marker.exists()
