"""M05 schema-swap preflight를 실제 PostgreSQL 권한 상태에서 검증한다."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
HOTSWAP_SCRIPT = ROOT / "scripts/restore-hotswap.sh"
TEST_PASSWORD = "m05-test-only-password"


@dataclass(frozen=True)
class _Case:
    database: str
    fence_role: str
    hotswap_role: str
    app_role: str
    app_url: str
    fence_url: str
    hotswap_url: str
    expected_failure: str
    expected_delete: bool
    requires_definer_proof: bool = False


def _require_tools() -> dict[str, str]:
    names = ("bash", "pg_dump", "pg_restore", "psql")
    resolved = {name: shutil.which(name) for name in names}
    if any(path is None for path in resolved.values()):
        pytest.skip("PostgreSQL client tool이 없어 M05 실제 권한 검증을 건너뜁니다.")
    return {name: str(path) for name, path in resolved.items()}


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _require_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr


def _psql(tools: dict[str, str], database_url: str, sql: str) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            tools["psql"],
            "--no-psqlrc",
            "--set=ON_ERROR_STOP=1",
            "--tuples-only",
            "--no-align",
            f"--dbname={database_url}",
            "--file=-",
        ],
        input_text=sql,
    )


def _quoted(identifier: str) -> str:
    assert identifier.replace("_", "").isalnum()
    return f'"{identifier}"'


def _database_url(*, host: str, port: str, role: str, database: str) -> str:
    return f"postgresql://{role}:{TEST_PASSWORD}@{host}:{port}/{database}"


def _create_case(
    *,
    tools: dict[str, str],
    root_url: str,
    host: str,
    port: str,
    suffix: str,
    kind: str,
) -> _Case:
    database = f"m05_{kind}_{suffix}"
    fence_role = f"m05_fence_{kind}_{suffix}"
    hotswap_role = f"m05_swap_{kind}_{suffix}"
    app_role = f"m05_app_{kind}_{suffix}"
    extra_role = f"m05_extra_{kind}_{suffix}"
    roles = [fence_role, hotswap_role, app_role]
    if kind == "extra":
        roles.append(extra_role)

    create_roles = "\n".join(
        "CREATE ROLE "
        f"{_quoted(role)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
        f"NOBYPASSRLS {'NOINHERIT' if role in {app_role, fence_role} else 'INHERIT'} "
        f"PASSWORD '{TEST_PASSWORD}';"
        for role in roles
    )
    _require_success(
        _psql(
            tools,
            root_url,
            f"""
{create_roles}
GRANT pg_signal_backend TO {_quoted(hotswap_role)};
CREATE DATABASE {_quoted(database)} OWNER {_quoted(fence_role)};
GRANT CONNECT, CREATE ON DATABASE {_quoted(database)} TO {_quoted(hotswap_role)};
GRANT CONNECT ON DATABASE {_quoted(database)} TO {_quoted(app_role)};
{"GRANT CONNECT ON DATABASE " + _quoted(database) + " TO " + _quoted(extra_role) + ";" if kind == "extra" else ""}
""",
        )
    )

    hotswap_url = _database_url(host=host, port=port, role=hotswap_role, database=database)
    fence_url = _database_url(host=host, port=port, role=fence_role, database=database)
    app_url = _database_url(host=host, port=port, role=app_role, database=database)
    _require_success(
        _psql(
            tools,
            _database_url(host=host, port=port, role="m05_root", database=database),
            f"""
CREATE SCHEMA x_extension AUTHORIZATION m05_root;
REVOKE ALL ON SCHEMA x_extension FROM PUBLIC;
GRANT USAGE ON SCHEMA x_extension TO {_quoted(hotswap_role)}, {_quoted(app_role)};
""",
        )
    )

    table_grants = (
        f"GRANT INSERT ON TABLE app.widgets TO {_quoted(app_role)};"
        if kind == "acl"
        else (
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO {_quoted(app_role)};\n"
            f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA app TO {_quoted(app_role)};"
        )
    )
    extra_grant = (
        f"GRANT USAGE ON SCHEMA app TO {_quoted(extra_role)};\n"
        f"GRANT INSERT ON TABLE app.widgets TO {_quoted(extra_role)};"
        if kind == "extra"
        else ""
    )
    default_acl = (
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {_quoted(hotswap_role)} "
        f"GRANT SELECT ON TABLES TO {_quoted(extra_role)};"
        if kind == "global_default"
        else ""
    )
    if kind == "global_default":
        roles.append(extra_role)
        _require_success(
            _psql(
                tools,
                root_url,
                f"CREATE ROLE {_quoted(extra_role)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                f"NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD '{TEST_PASSWORD}';",
            )
        )

    setup_sql = f"""
CREATE SCHEMA app AUTHORIZATION {_quoted(hotswap_role)};
REVOKE ALL ON SCHEMA app FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO {_quoted(app_role)};
CREATE TABLE app.widgets (
  id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  value integer NOT NULL DEFAULT 0
);
INSERT INTO app.widgets (value) VALUES (0);
{table_grants}
{extra_grant}
{default_acl}
"""  # noqa: S608 - 역할명은 내부 생성값을 quoted로 제한한다.
    _require_success(_psql(tools, hotswap_url, setup_sql))

    requires_definer_proof = kind == "security_definer"
    if requires_definer_proof:
        definer_sql = f"""
CREATE FUNCTION app.definer_write() RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_catalog
AS $$
BEGIN
  UPDATE app.widgets SET value = value + 1 WHERE id = 1;
END;
$$;
REVOKE INSERT, UPDATE, DELETE ON TABLE app.widgets FROM {_quoted(app_role)};
"""  # noqa: S608 - 역할명은 내부 생성값을 quoted로 제한한다.
        _require_success(
            _psql(
                tools,
                hotswap_url,
                definer_sql,
            )
        )
        _require_success(_psql(tools, app_url, "SELECT app.definer_write();"))
        proof = _psql(tools, hotswap_url, "SELECT value FROM app.widgets WHERE id = 1;")
        _require_success(proof)
        assert proof.stdout.strip() == "1"
        _require_success(
            _psql(
                tools,
                hotswap_url,
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO {_quoted(app_role)};",
            )
        )

    expected_failure = {
        "acl": "schema-swap requires canonical single-runtime-role ACLs",
        "extra": "schema-swap requires exactly one canonical runtime writer role",
        "global_default": "schema-swap requires canonical single-runtime-role ACLs",
        "security_definer": "schema-swap requires canonical single-runtime-role ACLs",
    }[kind]
    return _Case(
        database=database,
        fence_role=fence_role,
        hotswap_role=hotswap_role,
        app_role=app_role,
        app_url=app_url,
        fence_url=fence_url,
        hotswap_url=hotswap_url,
        expected_failure=expected_failure,
        expected_delete=kind != "acl",
        requires_definer_proof=requires_definer_proof,
    )


def _snapshot(tools: dict[str, str], hotswap_url: str, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = directory / "m05-preflight.dump"
    result = _run(
        [
            tools["pg_dump"],
            "--format=custom",
            "--schema=app",
            f"--file={snapshot}",
            hotswap_url,
        ]
    )
    _require_success(result)
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    snapshot.with_name(f"{snapshot.name}.sha256").write_text(
        f"{digest}  {snapshot.name}\n", encoding="utf-8"
    )
    return snapshot


def _identity(tools: dict[str, str], hotswap_url: str) -> tuple[str, str, str, str, str]:
    result = _psql(
        tools,
        hotswap_url,
        "SELECT current_database(), d.oid::text, (pg_control_system()).system_identifier::text, "
        "COALESCE(host(inet_server_addr()), ''), inet_server_port()::text "
        "FROM pg_database d WHERE d.datname = current_database();",
    )
    _require_success(result)
    values = tuple(result.stdout.strip().split("|"))
    assert len(values) == 5
    return values[0], values[1], values[2], values[3], values[4]


def _assert_source_unchanged(tools: dict[str, str], case: _Case, restore_schema: str) -> None:
    result = _psql(
        tools,
        case.hotswap_url,
        f"""
SELECT to_regnamespace('app') IS NOT NULL,
       to_regnamespace('{restore_schema}') IS NULL,
       has_table_privilege('{case.app_role}', 'app.widgets', 'INSERT'),
       has_table_privilege('{case.app_role}', 'app.widgets', 'DELETE');
""",
    )
    _require_success(result)
    app_exists, restore_missing, can_insert, can_delete = result.stdout.strip().split("|")
    assert app_exists == "t"
    assert restore_missing == "t"
    assert can_insert == "t"
    assert (can_delete == "t") is case.expected_delete


def test_restore_hotswap_preflight_rejects_real_noncanonical_topologies_before_mutation(
    tmp_path: Path,
) -> None:
    """ACL/default-ACL/definer 우회는 write fence나 restore 전에 막힌다."""
    tools = _require_tools()
    try:
        import docker  # noqa: F401
        from testcontainers.postgres import PostgresContainer
    except Exception:
        pytest.skip("docker SDK 미설치 — M05 실제 권한 검증을 건너뜁니다.")

    suffix = uuid.uuid4().hex[:8]
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
        root_url = _database_url(host=host, port=port, role="m05_root", database="m05_root")
        cases = [
            _create_case(
                tools=tools,
                root_url=root_url,
                host=host,
                port=port,
                suffix=suffix,
                kind=kind,
            )
            for kind in ("acl", "extra", "global_default", "security_definer")
        ]

        # 복원 실행 중 writer inventory에 root superuser가 섞이지 않도록, 모든 fixture를
        # 만든 뒤 container lifecycle로만 정리하는 root login을 닫는다.
        _require_success(_psql(tools, root_url, "ALTER ROLE m05_root NOLOGIN;"))

        for index, case in enumerate(cases):
            snapshot = _snapshot(tools, case.hotswap_url, tmp_path / f"snapshot-{index}")
            identity = _identity(tools, case.hotswap_url)
            restore_schema = f"app_restore_{index}_{suffix}"
            previous_schema = f"app_previous_{index}_{suffix}"
            env = os.environ.copy()
            env.update(
                {
                    # This fixture exercises ACL preflight only. Production/staging
                    # provenance is covered by the root-owned M05 drill evidence gate.
                    "PINVI_ENVIRONMENT": "development",
                    "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
                    "PINVI_RESTORE_PRIVATE_TOOL_COPY": "1",
                    "PINVI_RESTORE_DATABASE_URL": case.hotswap_url,
                    "PINVI_RESTORE_FENCE_DATABASE_URL": case.fence_url,
                    "PINVI_RESTORE_APP_ROLE": case.app_role,
                    "PINVI_RESTORE_PG_RESTORE_BIN": tools["pg_restore"],
                    "PINVI_RESTORE_PG_RESTORE_SHA256": hashlib.sha256(
                        Path(tools["pg_restore"]).read_bytes()
                    ).hexdigest(),
                    "PINVI_RESTORE_PSQL_BIN": tools["psql"],
                    "PINVI_RESTORE_PSQL_SHA256": hashlib.sha256(
                        Path(tools["psql"]).read_bytes()
                    ).hexdigest(),
                    "PINVI_RESTORE_BASH_BIN": tools["bash"],
                    "PINVI_RESTORE_BASH_SHA256": hashlib.sha256(
                        Path(tools["bash"]).read_bytes()
                    ).hexdigest(),
                    "PINVI_RESTORE_EXPECTED_DATABASE_NAME": identity[0],
                    "PINVI_RESTORE_EXPECTED_DATABASE_OID": identity[1],
                    "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER": identity[2],
                    "PINVI_RESTORE_EXPECTED_HOSTADDR": identity[3],
                    "PINVI_RESTORE_EXPECTED_PORT": identity[4],
                }
            )
            env.pop("PINVI_M05_RESTORE_TEST_MODE", None)
            result = _run(
                [
                    tools["bash"],
                    str(HOTSWAP_SCRIPT),
                    "run",
                    str(snapshot),
                    restore_schema,
                    previous_schema,
                ],
                env=env,
            )

            assert result.returncode == 3, result.stdout + result.stderr
            assert case.expected_failure in result.stdout
            _assert_source_unchanged(tools, case, restore_schema)
    finally:
        container.stop()
