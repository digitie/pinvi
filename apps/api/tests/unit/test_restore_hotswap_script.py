from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts/restore-hotswap.sh"


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
    assert 'exec "${SETSID_BIN}" "${PSQL_BIN}"' in source
    assert "trap terminate_restore TERM INT" in source
    assert "SET session_replication_role = replica" not in source


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
COPY app.users (id) FROM stdin;
COMMIT;
\\.
SELECT 1;
"""
    unsafe_sql = "SELECT 1;\nCOMMIT;\n"
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
