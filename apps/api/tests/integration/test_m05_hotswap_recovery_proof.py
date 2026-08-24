"""M05 trusted recovery proof를 실제 PostgreSQL 16 catalog에서 검증한다."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
TOPOLOGY_SQL = ROOT / "scripts/m05_hotswap_topology.sql"
TEST_PASSWORD = "m05-recovery-proof-test-only"


def _hotswap_module():
    spec = importlib.util.spec_from_file_location(
        "m05_hotswap_recovery_proof_entrypoint",
        ROOT / "scripts/trusted-hotswap-entrypoint.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _require_psql() -> str:
    path = shutil.which("psql")
    if path is None:
        pytest.skip("psql이 없어 M05 PostgreSQL 16 recovery proof를 건너뜁니다.")
    return path


def _run(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _psql(psql: str, database_url: str, sql: str) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            psql,
            "--no-psqlrc",
            "--set=ON_ERROR_STOP=1",
            "--tuples-only",
            "--no-align",
            f"--dbname={database_url}",
            "--file=-",
        ],
        input_text=sql,
    )


def _require_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def _url(*, host: str, port: str, role: str, database: str) -> str:
    return f"postgresql://{role}:{TEST_PASSWORD}@{host}:{port}/{database}"


def _topology_sha256(
    psql: str,
    database_url: str,
    *,
    app_role: str,
    fence_role: str,
) -> str:
    result = _run(
        [
            psql,
            "--no-psqlrc",
            "-X",
            "-Atq",
            "--set=ON_ERROR_STOP=1",
            f"--dbname={database_url}",
            "--set=source_schema=app",
            "--set=previous_schema=app_previous",
            "--set=restore_schema=app_restore",
            f"--set=app_role={app_role}",
            f"--set=fence_role={fence_role}",
            f"--file={TOPOLOGY_SQL}",
        ]
    )
    _require_success(result)
    digest = result.stdout.strip()
    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)
    return digest


def _prepared_marker(
    *,
    app_role: str,
    fence_role: str,
    target_identity_sha256: str,
    topology_sha256: str,
    source_oid: int,
) -> dict[str, object]:
    return {
        "acl_topology_sha256": topology_sha256,
        "app_role": app_role,
        "connect_restore_grants": [],
        "fence_executor_role": fence_role,
        "operation_id": "123e4567-e89b-42d3-a456-426614174000",
        "previous_schema": "app_previous",
        "public_connect_was_granted": False,
        "recovery_required": False,
        "restore_schema": "app_restore",
        "source_schema": "app",
        "source_schema_oid_before": source_oid,
        "state": "prepared",
        "target_identity_sha256": target_identity_sha256,
    }


def test_trusted_recovery_rejects_authority_surface_drift() -> None:
    """PG16 catalog의 모든 M05 writer escape drift는 root recovery를 막는다."""

    psql = _require_psql()
    try:
        import docker  # noqa: F401
        from testcontainers.postgres import PostgresContainer
    except Exception:
        pytest.skip("docker SDK가 없어 M05 PostgreSQL 16 recovery proof를 건너뜁니다.")

    suffix = uuid.uuid4().hex[:8]
    database = f"m05_proof_{suffix}"
    restore_role = f"m05_restore_{suffix}"
    app_role = f"m05_app_{suffix}"
    fence_role = f"m05_fence_{suffix}"
    secdef_owner = f"m05_secdef_{suffix}"
    helper_schema = f"m05_helper_{suffix}"
    container = PostgresContainer(
        "postgres:16-alpine",
        username="m05_root",
        password=TEST_PASSWORD,
        dbname="m05_root",
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        root_url = _url(host=host, port=port, role="m05_root", database="m05_root")
        _require_success(
            _psql(
                psql,
                root_url,
                f"""
CREATE ROLE "{restore_role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS INHERIT PASSWORD '{TEST_PASSWORD}';
CREATE ROLE "{app_role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD '{TEST_PASSWORD}';
CREATE ROLE "{fence_role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD '{TEST_PASSWORD}';
CREATE ROLE "{secdef_owner}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD '{TEST_PASSWORD}';
CREATE DATABASE "{database}" OWNER "{restore_role}";
""",
            )
        )
        restore_url = _url(host=host, port=port, role=restore_role, database=database)
        root_target_url = _url(host=host, port=port, role="m05_root", database=database)
        _require_success(
            _psql(
                psql,
                root_target_url,
                f"""
CREATE SCHEMA x_extension AUTHORIZATION "{restore_role}";
CREATE EXTENSION pgcrypto SCHEMA x_extension;
GRANT USAGE ON SCHEMA x_extension TO "{restore_role}", "{app_role}";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE "{database}" TO "{app_role}";
""",
            )
        )
        _require_success(
            _psql(
                psql,
                restore_url,
                f"""
CREATE SCHEMA app AUTHORIZATION "{restore_role}";
GRANT USAGE ON SCHEMA app TO "{app_role}";
CREATE TABLE app.admin_audit_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  action text NOT NULL
);
CREATE FUNCTION app.admin_audit_append_only_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'append only';
END;
$$;
CREATE TRIGGER m05_admin_audit_append_only
BEFORE INSERT OR UPDATE OR DELETE ON app.admin_audit_log
FOR EACH ROW EXECUTE FUNCTION app.admin_audit_append_only_guard();
ALTER TABLE app.admin_audit_log
  ENABLE ALWAYS TRIGGER m05_admin_audit_append_only;
""",
            )
        )
        _require_success(
            _psql(
                psql,
                root_target_url,
                f"""
CREATE SCHEMA "{helper_schema}" AUTHORIZATION "{secdef_owner}";
SET ROLE "{secdef_owner}";
CREATE FUNCTION "{helper_schema}".m05_external_secdef()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
  RETURN 1;
END;
$$;
RESET ROLE;
GRANT USAGE ON SCHEMA "{helper_schema}" TO "{app_role}";
GRANT EXECUTE ON FUNCTION "{helper_schema}".m05_external_secdef() TO "{app_role}";
""",
            )
        )

        hotswap = _hotswap_module()
        topology_sha256 = _topology_sha256(
            psql, restore_url, app_role=app_role, fence_role=fence_role
        )
        source_oid_result = _psql(
            psql,
            restore_url,
            "SELECT oid::text FROM pg_namespace WHERE nspname = 'app';",
        )
        _require_success(source_oid_result)
        source_oid = int(source_oid_result.stdout.strip())
        target_identity_sha256, _ = hotswap._identity_sha256_from_psql(restore_url)
        marker = _prepared_marker(
            app_role=app_role,
            fence_role=fence_role,
            target_identity_sha256=target_identity_sha256,
            topology_sha256=topology_sha256,
            source_oid=source_oid,
        )

        assert hotswap._safe_recovery_observation(marker, restore_url, TOPOLOGY_SQL)

        _require_success(
            _psql(
                psql,
                root_target_url,
                f'GRANT CREATE ON SCHEMA public TO "{app_role}";',
            )
        )
        assert (
            _topology_sha256(psql, restore_url, app_role=app_role, fence_role=fence_role)
            != topology_sha256
        )
        with pytest.raises(hotswap.TrustedHotswapError, match="safe writer release"):
            hotswap._safe_recovery_observation(marker, restore_url, TOPOLOGY_SQL)

        _require_success(
            _psql(
                psql,
                root_target_url,
                f'REVOKE CREATE ON SCHEMA public FROM "{app_role}";',
            )
        )
        assert (
            _topology_sha256(psql, restore_url, app_role=app_role, fence_role=fence_role)
            == topology_sha256
        )
        _require_success(
            _psql(
                psql,
                restore_url,
                "ALTER TABLE app.admin_audit_log DISABLE TRIGGER m05_admin_audit_append_only;",
            )
        )
        with pytest.raises(hotswap.TrustedHotswapError, match="ACL topology"):
            hotswap._safe_recovery_observation(marker, restore_url, TOPOLOGY_SQL)

        _require_success(
            _psql(
                psql,
                root_target_url,
                f"""
ALTER TABLE app.admin_audit_log
  ENABLE ALWAYS TRIGGER m05_admin_audit_append_only;
SET ROLE "{secdef_owner}";
CREATE OR REPLACE FUNCTION "{helper_schema}".m05_external_secdef()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
  RETURN 2;
END;
$$;
RESET ROLE;
""",
            )
        )
        with pytest.raises(hotswap.TrustedHotswapError, match="ACL topology"):
            hotswap._safe_recovery_observation(marker, restore_url, TOPOLOGY_SQL)

        body_topology_sha256 = _topology_sha256(
            psql, restore_url, app_role=app_role, fence_role=fence_role
        )
        assert body_topology_sha256 != topology_sha256
        marker["acl_topology_sha256"] = body_topology_sha256
        assert hotswap._safe_recovery_observation(marker, restore_url, TOPOLOGY_SQL)

        _require_success(
            _psql(
                psql,
                root_target_url,
                f'GRANT EXECUTE ON FUNCTION "{helper_schema}".m05_external_secdef() '
                f'TO "{app_role}" WITH GRANT OPTION;',
            )
        )
        with pytest.raises(hotswap.TrustedHotswapError, match="ACL topology"):
            hotswap._safe_recovery_observation(marker, restore_url, TOPOLOGY_SQL)

        grant_option_topology_sha256 = _topology_sha256(
            psql, restore_url, app_role=app_role, fence_role=fence_role
        )
        assert grant_option_topology_sha256 != body_topology_sha256
        marker["acl_topology_sha256"] = grant_option_topology_sha256
        assert hotswap._safe_recovery_observation(marker, restore_url, TOPOLOGY_SQL)

        _require_success(
            _psql(
                psql,
                root_target_url,
                f'GRANT pg_read_all_data TO "{secdef_owner}";',
            )
        )
        with pytest.raises(hotswap.TrustedHotswapError, match="ACL topology"):
            hotswap._safe_recovery_observation(marker, restore_url, TOPOLOGY_SQL)
    finally:
        container.stop()
