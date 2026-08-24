"""M05 restore drill이 실제 backup/restore runner와 trigger proof를 사용한다."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


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


def test_m05_restore_drill_pins_single_canonical_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _restore_drill_module()

    def getaddrinfo(host: str, port: int, *, type: int) -> list[tuple[object, ...]]:
        assert host == "app-postgres"
        assert port == 5432
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", port, 0, 0))]

    monkeypatch.setattr(module.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setenv(
        "PINVI_TEST_RESTORE_URL",
        "postgresql+asyncpg://runtime@app-postgres:5432/pinvi?sslmode=require",
    )
    monkeypatch.delenv("PINVI_M05_RESTORE_TEST_MODE", raising=False)

    assert module._database_url("PINVI_TEST_RESTORE_URL") == (
        "postgresql://runtime@app-postgres:5432/pinvi?sslmode=require&hostaddr=::1"
    )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://runtime@app-postgres:5432/pinvi?host=other-postgres",
        "postgresql://runtime@app-postgres:5432/pinvi?hostaddr=127.0.0.1",
        "postgresql://runtime@app-postgres:5432/pinvi?port=6543",
        "postgresql://runtime@app-postgres:5432/pinvi?service=pinvi",
        "postgresql://runtime@app-postgres:5432/pinvi?servicefile=/tmp/pg_service.conf",
        "postgresql://runtime@app-postgres:5432/pinvi?sslmode=require&sslmode=verify-full",
        "postgresql://runtime@app-postgres:5432/pinvi?=value",
    ],
)
def test_m05_restore_drill_rejects_ambiguous_or_overridden_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    module = _restore_drill_module()
    monkeypatch.setenv("PINVI_TEST_RESTORE_URL", url)
    monkeypatch.delenv("PINVI_M05_RESTORE_TEST_MODE", raising=False)

    with pytest.raises(module.RestoreDrillError, match=r"ambiguous|endpoint override"):
        module._database_url("PINVI_TEST_RESTORE_URL")


def test_m05_restore_drill_rejects_multi_address_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _restore_drill_module()

    def getaddrinfo(host: str, port: int, *, type: int) -> list[tuple[object, ...]]:
        assert host == "app-postgres"
        assert port == 5432
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.0.9", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.0.10", port)),
        ]

    monkeypatch.setattr(module.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setenv(
        "PINVI_TEST_RESTORE_URL",
        "postgresql://runtime@app-postgres:5432/pinvi",
    )
    monkeypatch.delenv("PINVI_M05_RESTORE_TEST_MODE", raising=False)

    with pytest.raises(module.RestoreDrillError, match="exactly one address"):
        module._database_url("PINVI_TEST_RESTORE_URL")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://runtime@app-postgres:5432/",
        "mysql://runtime@app-postgres:5432/pinvi",
        "postgresql://runtime@app-postgres:5432/pinvi#fragment",
    ],
)
def test_m05_restore_drill_rejects_noncanonical_database_url(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    module = _restore_drill_module()
    monkeypatch.setenv("PINVI_TEST_RESTORE_URL", url)
    monkeypatch.delenv("PINVI_M05_RESTORE_TEST_MODE", raising=False)

    with pytest.raises(module.RestoreDrillError, match="PostgreSQL URL"):
        module._database_url("PINVI_TEST_RESTORE_URL")


def test_m05_restore_drill_serializes_target_recreation_and_preflights_staging_role() -> None:
    module = _restore_drill_module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "_staging_role_check(" in source
    assert "PINVI_RESTORE_PROVISION_DATABASE_URL" in source
    assert "PINVI_RESTORE_PROVISIONER_ROLE" in source
    assert "PINVI_BACKUP_CATALOG_PATH" in source
    assert 'ALTER ROLE "{provisioner_role}" NOLOGIN;' in source
    assert "restore provisioner login must be disabled" in source
    assert "SELECT pg_advisory_lock(1414679892, 1213421392);" in source
    assert "SELECT pg_advisory_unlock(1414679892, 1213421392);" in source
    assert "_ProvisioningLock" not in source
    assert "PINVI_RESTORE_COORDINATION_DATABASE_URL" not in source
    assert "m05_operation_lease.py" in source
    assert "staging/production restore drill requires a root-owned target lease" in source
    assert "with _acquire_root_target_lease(target_url) as lease:" in source
    assert "return _run_drill(args, _lease_held=True, _operation_lease=lease)" in source
    run = source[source.index("def _run_drill(") :]
    assert run.index("with _acquire_root_target_lease(target_url) as lease:") < run.index(
        "        _staging_role_check("
    )
    recreate = source[
        source.index("def _recreate_disposable_target(") : source.index("def _identity_key(")
    ]
    assert recreate.index("{disable_provisioner_sql}") < recreate.index("DROP DATABASE IF EXISTS")
    assert "REVOKE ALL ON FUNCTION x_extension.digest(bytea, text) FROM PUBLIC;" in recreate
    assert "GRANT EXECUTE ON FUNCTION x_extension.digest(bytea, text)" in recreate
    assert "restore hotswap digest ACL is not canonical" in recreate
    assert "NOT m.admin_option" in recreate
    assert "m.inherit_option" in recreate
    assert "m.set_option" in recreate
    assert 'PINVI_RESTORE_HOTSWAP_EXECUTE": "1"' not in source
    assert '"PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL": "precheck"' in source
    assert 'restore_env["PINVI_M05_OPERATION_LEASE_FD"]' in source
    assert 'restore_env["PINVI_M05_OPERATION_LEASE_TOKEN"]' in source
    assert "pass_fds=restore_pass_fds" in source


def test_m05_restore_drill_requires_root_owned_target_lease_in_managed_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _restore_drill_module()
    monkeypatch.setenv("PINVI_ENVIRONMENT", "staging")
    monkeypatch.delenv("PINVI_M05_RESTORE_TEST_MODE", raising=False)

    with pytest.raises(module.RestoreDrillError, match="root-owned target lease"):
        module._run_drill(
            SimpleNamespace(
                output=tmp_path / "restore-evidence.json",
                require_root_owned=False,
            )
        )


def test_m05_operation_lease_binds_only_pinned_target_identity() -> None:
    script = Path(__file__).resolve().parents[4] / "scripts/m05_operation_lease.py"
    spec = importlib.util.spec_from_file_location("m05_operation_lease", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    first = module.operation_lease_token(
        "postgresql://first:secret@db:5432/pinvi_m05_restore_one?hostaddr=192.0.2.10"
    )
    same_target = module.operation_lease_token(
        "postgresql://second:other@db:5432/pinvi_m05_restore_one?hostaddr=192.0.2.10"
    )
    other_target = module.operation_lease_token(
        "postgresql://second:other@db:5432/pinvi_m05_restore_two?hostaddr=192.0.2.10"
    )

    assert first == same_target
    assert first != other_target
    with pytest.raises(module.M05OperationLeaseError, match="database URL"):
        module.operation_lease_token("postgresql://role@db:5432/pinvi_m05_restore_one")


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
for arg in "$@"; do
  if [[ "$arg" == --file=* ]]; then
    : >"${arg#--file=}"
  fi
done
exit 0
""",
    )
    _write_executable(
        fake_bin / "psql",
        """#!/usr/bin/env bash
set -euo pipefail
sql="$*"
if [[ "$sql" == *"-Atq"* && "$sql" != *"m05_hotswap_topology.sql"* ]]; then
  while IFS= read -r line; do
    if [[ "$line" == *"M05_LOCK_ACQUIRED"* ]]; then
      echo 'M05_LOCK_ACQUIRED|123'
    elif [[ "$line" == *"M05_SCALAR|"* ]]; then
      scalar="$(printf '%s\\n' "$line" | sed -n 's/.*M05_SCALAR|\\([0-9][0-9]*\\)|.*/\\1/p')"
      echo "M05_SCALAR|${scalar}|12345"
    elif [[ "$line" == *"M05_SQL_DONE|"* ]]; then
      marker="$(printf '%s\\n' "$line" | sed -n 's/.*M05_SQL_DONE|\\([0-9][0-9]*\\).*/\\1/p')"
      echo "M05_SQL_DONE|${marker}"
    fi
  done
elif [[ "$sql" == *"SET LOCAL session_replication_role"* ]]; then
  echo 'app.ktm_feature_reference_reconciliation_delivery_attempts is append-only' >&2
  exit 1
elif [[ "$sql" == *"json_build_object"* ]]; then
  if [[ "$sql" == *"/source"* ]]; then
          echo '{"database":"fixture-source","user":"fixture","database_oid":"100","system_identifier":"1","schema_exists":true,"server_version_num":"160000"}'
  else
          echo '{"database":"pinvi_m05_restore_target","user":"fixture","database_oid":"200","system_identifier":"1","schema_exists":false,"server_version_num":"160000"}'
  fi
elif [[ "$sql" == *"to_regnamespace"* && "$sql" == *"IS NOT NULL"* && "$sql" == *"x_extension"* ]]; then
  echo t
elif [[ "$sql" == *"to_regnamespace"* && "$sql" == *"IS NOT NULL"* ]]; then
  echo f
elif [[ "$sql" == *"to_regnamespace"* && "$sql" == *"IS NULL"* ]]; then
  echo t
elif [[ "$sql" == *"SELECT COALESCE((SELECT oid::text FROM pg_namespace"* ]]; then
  echo 12345
elif [[ "$sql" == *"m05_hotswap_topology.sql"* ]]; then
  echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    elif [[ "$sql" == *"has_schema_privilege"* || "$sql" == *"count(*) = 6"* || "$sql" == *"FROM pg_roles"* || "$sql" == *"fresh disposable target"* || "$sql" == *"pg_namespace"* ]]; then
  echo t
elif [[ "$sql" == *"lag(content_hash)"* ]]; then
  echo valid
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
    output.parent.chmod(0o700)
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
    assert evidence["hotswap_success"] is False
    assert evidence["hotswap_success_marker"] == ""
    assert evidence["hotswap_success_output_sha256"] == ""
