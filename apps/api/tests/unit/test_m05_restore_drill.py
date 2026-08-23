"""M05 restore drill이 실제 backup/restore runner와 trigger proof를 사용한다."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def _restore_drill_module():
    script = Path(__file__).resolve().parents[4] / "scripts/m05_restore_drill.py"
    spec = importlib.util.spec_from_file_location("m05_restore_drill", script)
    if spec is None or spec.loader is None:
        raise AssertionError("restore drill module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m05_restore_drill_normalizes_asyncpg_url_for_psql() -> None:
    module = _restore_drill_module()
    os.environ["PINVI_M05_RESTORE_TEST_MODE"] = "1"
    os.environ["PINVI_TEST_RESTORE_URL"] = "postgresql+asyncpg://runtime:secret@db:5432/pinvi"
    try:
        assert module._database_url("PINVI_TEST_RESTORE_URL") == (
            "postgresql://runtime:secret@db:5432/pinvi"
        )
    finally:
        os.environ.pop("PINVI_TEST_RESTORE_URL", None)
        os.environ.pop("PINVI_M05_RESTORE_TEST_MODE", None)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def test_m05_restore_drill_seals_actual_runner_evidence(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "git",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"rev-parse HEAD"* ]]; then
  echo "ffffffffffffffffffffffffffffffffffffffff"
elif [[ "$*" == *"status --porcelain"* ]]; then
  exit 0
else
  exec /usr/bin/git "$@"
fi
""",
    )
    _write_executable(
        fake_bin / "pg_dump",
        """#!/usr/bin/env bash
set -euo pipefail
for arg in "$@"; do
  if [[ "$arg" == --file=* ]]; then
    printf 'custom-format-fixture' > "${arg#--file=}"
  fi
done
""",
    )
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
sql="$*"
if [[ "$sql" == *"SET LOCAL session_replication_role"* ]]; then
  echo 'app.ktm_feature_reference_reconciliation_delivery_attempts is append-only' >&2
  exit 1
elif [[ "$sql" == *"json_build_object"* ]]; then
  if [[ "$sql" == *"/source"* ]]; then
    echo '{"database":"fixture-source","user":"fixture","database_oid":"100","system_identifier":"1","schema_exists":true,"server_version_num":"160000"}'
  else
    echo '{"database":"pinvi_m05_restore_target","user":"fixture","database_oid":"200","system_identifier":"1","schema_exists":false,"server_version_num":"160000"}'
  fi
elif [[ "$sql" == *"has_schema_privilege"* || "$sql" == *"count(*) = 6"* || "$sql" == *"FROM pg_roles"* ]]; then
  echo t
elif [[ "$sql" == *"lag(content_hash)"* ]]; then
  echo valid
elif [[ "$sql" == *"to_regnamespace"* && "$sql" == *"IS NOT NULL"* ]]; then
  echo f
elif [[ "$sql" == *"to_regnamespace"* ]]; then
  echo 12345
elif [[ "$sql" == *"to_regclass"* ]]; then
  echo t
elif [[ "$sql" == *"count(*)::text"* ]]; then
  echo 1
else
  echo 1
fi
""",
    )
    output = tmp_path / "evidence" / "restore.json"
    output.parent.mkdir(mode=0o700)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "PINVI_M05_RESTORE_TEST_MODE": "1",
            "PINVI_ENVIRONMENT": "test",
            "PINVI_RESTORE_SOURCE_DATABASE_URL": "postgresql://source:secret@db/source",
            "PINVI_RESTORE_STAGING_DATABASE_URL": "postgresql://owner:secret@db/target",
            "PINVI_RESTORE_RUNTIME_DATABASE_URL": "postgresql://runtime:secret@db/target",
            "PINVI_RESTORE_RUNTIME_ROLE": "pinvi_app",
            "PINVI_RESTORE_STAGING_ROLE": "pinvi_owner",
            "PINVI_SOURCE_REVISION": "f" * 40,
        }
    )
    script = Path(__file__).resolve().parents[4] / "scripts/m05_restore_drill.py"
    result = subprocess.run(  # noqa: S603 - invokes the repository-pinned helper
        [sys.executable, str(script), "run", "--output", str(output)],
        cwd=script.parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "secret" not in result.stdout
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["no_owner_restore"] is True
    assert evidence["runtime_role_verified"] is True
    assert evidence["trigger_guard_verified"] is True
    assert evidence["restore_command"] == (
        "pg_restore --clean --if-exists --exit-on-error --no-owner --no-privileges"
    )
