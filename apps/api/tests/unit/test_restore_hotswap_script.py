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
    assert "PINVI_M05_OPERATION_LEASE_FD" in source
    assert "PINVI_M05_OPERATION_LEASE_TOKEN" in source
    assert "assert_operation_lease" in source
    assert source.rindex("assert_operation_lease") < source.rindex(
        "assert_trusted_snapshot_provenance"
    )
    assert "database fence URL must be a dedicated non-superuser target owner" in source
    assert "FENCE_EXECUTOR_ROLE" in source
    assert "login.rolname <> '${FENCE_EXECUTOR_ROLE}'" in source
    assert source.count("login.rolname <> current_user") >= 2
    assert "SET session_replication_role = replica" not in source


def test_restore_hotswap_failure_path_never_mutates_database_topology() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    cleanup = source[source.index("cleanup() {") : source.index("trap cleanup EXIT")]

    assert "rollback_schema_switch" not in source
    assert "SCHEMA_SWITCH_ACTIVE" not in source
    assert "DROP SCHEMA IF EXISTS ${RESTORE_SCHEMA}" not in source
    assert "CREATE SCHEMA IF NOT EXISTS" not in source
    assert "rollback will be attempted" not in source
    assert "release_write_fence" not in cleanup
    assert "ALTER SCHEMA" not in cleanup
    assert "DROP SCHEMA" not in cleanup
    assert "REVOKE CONNECT" not in cleanup
    assert "GRANT CONNECT" not in cleanup
    assert "record_forensics_failure" in cleanup
    assert "database write fence remains active" in cleanup


def test_restore_hotswap_binds_forensics_to_actual_mutation_boundaries() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    main = source[source.rindex('phase draining running "write fence"') :]

    assert source.rindex("assert_forensics_inactive") < source.rindex("start_advisory_lock")
    assert main.index("assert_restore_schema_absent") < main.index("prepare_write_fence_inventory")
    assert main.index("prepare_write_fence_inventory") < main.index("forensics_begin")
    assert main.index("forensics_begin") < main.index("enter_write_fence")
    assert main.index("forensics_transition fence_intent") < main.index("enter_write_fence")
    assert main.index("enter_write_fence") < main.index("forensics_transition fence_applied")
    assert main.index("assert_restore_schema_absent") < main.index(
        'run_guarded_command "CREATE SCHEMA ${RESTORE_SCHEMA}"'
    )
    assert "CREATE SCHEMA IF NOT EXISTS" not in main
    assert main.index("phase validating success") < main.index("forensics_transition restore_ready")
    assert main.index("forensics_transition switched") < main.index(
        "forensics_transition fence_release_intent"
    )
    assert main.index("forensics_transition fence_release_intent") < main.index(
        "release_write_fence"
    )
    assert main.index("release_write_fence") < main.index("persist_post_release_forensics")
    post_release_forensics = source[
        source.index("persist_post_release_forensics() {") : source.index(
            "reapply_write_fence_after_post_release_forensic_failure()"
        )
    ]
    assert "forensics_seal_release_receipt" in post_release_forensics
    assert "forensics_transition fence_released" not in source
    release = source[
        source.index("release_write_fence() {") : source.index("persist_post_release_forensics()")
    ]
    assert (
        release.index("read_release_receipt_after_commit")
        < release.index("assert_database_fence_restored")
        < release.index("assert_supported_acl_topology")
    )
    cleanup = source[source.index("cleanup() {") : source.index("trap cleanup EXIT")]
    assert "release_receipt_seal_is_exact" in cleanup
    assert "PINVI_RESTORE_TEST_SIGKILL_AFTER_RELEASE_RECEIPT_COMMIT_ONCE" in release
    assert "PINVI_RESTORE_TEST_SIGKILL_AFTER_RELEASE_RECEIPT_SEAL_ONCE" in main
    assert '"${PINVI_ENVIRONMENT:-}" == "test"' in source


def test_restore_hotswap_receipt_gate_accepts_canonical_uuid_and_uses_owner_verifier() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    release = source[
        source.index("release_receipt_sql() {") : source.index(
            "read_release_receipt_after_commit()"
        )
    ]
    receipt_read = source[
        source.index("read_release_receipt_after_commit() {") : source.index(
            "release_write_fence()"
        )
    ]

    assert "[89ab][0-9a-f]{3}-[0-9a-f]{12}" in release
    assert "[89ab][0-9a-f]{12}" not in release
    assert "ops.verify_m05_hotswap_release_receipt" in receipt_read
    assert "x_extension.digest" not in receipt_read


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
    inventory = source.index("prepare_write_fence_inventory()")
    assert source.index("  assert_supported_acl_topology\n", inventory) < source.index(
        "  writer_logins", inventory
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
        '#!/usr/bin/env bash\nset -euo pipefail\ntouch "$PINVI_TEST_TOOL_MARKER"\n',
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
    assert "strict hotswap requires a trusted target operation lease" in result.stdout
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
