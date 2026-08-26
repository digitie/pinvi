"""Compose-level lifecycle proof for the sealed M05 one-shot migrator login."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[4]
COMPOSE_FILE = ROOT / "infra" / "docker-compose.app.yml"


def _docker_compose_binary() -> str | None:
    docker = shutil.which("docker")
    if docker is None:
        return None
    if (
        subprocess.run(  # noqa: S603 - resolved local Docker binary with fixed arguments
            [docker, "info"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        ).returncode
        != 0
    ):
        return None
    return docker


def test_migrator_login_is_opened_only_for_migration_and_sealed_with_sessions(
    tmp_path: Path,
) -> None:
    docker = _docker_compose_binary()
    if docker is None:
        pytest.skip("Docker daemon is required for the Compose role lifecycle proof")

    suffix = uuid4().hex[:10]
    project = f"pinvi-m05-role-{suffix}"
    root_role = f"m05_root_{suffix}"
    runtime_role = f"m05_runtime_{suffix}"
    schema_owner = f"m05_app_owner_{suffix}"
    migration_owner = f"m05_migration_owner_{suffix}"
    migrator_role = f"m05_migrator_{suffix}"
    password = "m05-compose-test-password"
    ephemeral_password = "m05-one-shot-ephemeral-password"
    rotated_password = "m05-one-shot-rotated-password"
    environment_file = tmp_path / "compose.env"
    environment_file.write_text(
        "\n".join(
            (
                f"PINVI_DB_OWNER_USER={root_role}",
                f"PINVI_POSTGRES_PASSWORD={password}",
                f"PINVI_APP_DB_USER={runtime_role}",
                f"PINVI_APP_DB_PASSWORD={password}",
                f"PINVI_APP_SCHEMA_OWNER={schema_owner}",
                f"PINVI_MIGRATION_OWNER={migration_owner}",
                f"PINVI_MIGRATOR_DB_USER={migrator_role}",
                f"PINVI_MIGRATOR_DB_PASSWORD={password}",
                f"PINVI_API_IMAGE=pinvi-m05-api-{suffix}:test",
                "",
            )
        ),
        encoding="utf-8",
    )
    compose_environment = os.environ.copy()
    for name in (
        "PINVI_DB_OWNER_USER",
        "PINVI_POSTGRES_PASSWORD",
        "PINVI_APP_DB_USER",
        "PINVI_APP_DB_PASSWORD",
        "PINVI_APP_SCHEMA_OWNER",
        "PINVI_MIGRATION_OWNER",
        "PINVI_MIGRATOR_DB_USER",
        "PINVI_MIGRATOR_DB_PASSWORD",
        "PINVI_M05_LEGACY_REBASELINE",
        "PINVI_MIGRATOR_DISABLE_LOGIN",
    ):
        compose_environment.pop(name, None)

    def compose(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(  # noqa: S603 - fixed Compose invocation in an isolated project
            (
                docker,
                "compose",
                "--project-name",
                project,
                "--file",
                str(COMPOSE_FILE),
                "--env-file",
                str(environment_file),
                *arguments,
            ),
            check=False,
            cwd=ROOT,
            env=compose_environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if check:
            assert result.returncode == 0, result.stderr
        return result

    def role_state() -> tuple[str, str, str, str, str]:
        query = (
            "SELECT "  # noqa: S608 - role names use a fixed prefix plus UUID hex only
            f"(SELECT rolcanlogin::text FROM pg_roles WHERE rolname = '{migrator_role}'), "
            f"has_database_privilege('{migrator_role}', current_database(), 'CONNECT')::text, "
            f"(SELECT count(*)::text FROM pg_stat_activity WHERE usename = '{migrator_role}'), "
            f"has_function_privilege('{migrator_role}', "
            "'x_extension.digest(bytea,text)'::regprocedure, 'EXECUTE')::text, "
            f"has_function_privilege('{migration_owner}', "
            "'x_extension.digest(bytea,text)'::regprocedure, 'EXECUTE')::text"
        )
        result = compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            f"--username={root_role}",
            "--dbname=pinvi",
            f"--command={query}",
        )
        state = result.stdout.strip().split("|")
        assert len(state) == 5
        return state[0], state[1], state[2], state[3], state[4]

    def managed_schema_state() -> tuple[str, str, str, str, str, str, str]:
        query = (
            "SELECT "  # noqa: S608 - role names use a fixed prefix plus UUID hex only
            "(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'app'), "
            "(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'ops'), "
            "(SELECT pg_get_userbyid(nspowner) FROM pg_namespace "
            "WHERE nspname = 'pinvi_internal'), "
            f"has_database_privilege('{migration_owner}', current_database(), 'CREATE'), "
            f"has_schema_privilege('{migration_owner}', 'ops', 'CREATE'), "
            f"has_schema_privilege('{migration_owner}', 'pinvi_internal', 'USAGE'), "
            "(SELECT version_num FROM app.alembic_version)"
        )
        result = compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            f"--username={root_role}",
            "--dbname=pinvi",
            f"--command={query}",
        )
        state = result.stdout.strip().split("|")
        assert len(state) == 7
        return tuple(state)  # type: ignore[return-value]

    def role_catalog_fingerprint() -> str:
        query = (
            "WITH catalog_rows(value) AS ("  # noqa: S608 - role names use a fixed prefix plus UUID hex only
            "SELECT 'role|' || rolname || '|' || rolcanlogin::text || '|' || rolsuper::text "
            "|| '|' || rolcreaterole::text || '|' || rolcreatedb::text || '|' "
            "|| rolreplication::text || '|' || rolbypassrls::text || '|' || rolinherit::text "
            "FROM pg_roles "
            f"WHERE rolname IN ('{root_role}', '{runtime_role}', '{schema_owner}', "
            f"'{migration_owner}', '{migrator_role}') "
            "UNION ALL "
            "SELECT 'membership|' || roleid::text || '|' || member::text || '|' "
            "|| admin_option::text || '|' || inherit_option::text || '|' || set_option::text "
            "FROM pg_auth_members "
            "UNION ALL "
            "SELECT 'setting|' || setdatabase::text || '|' || setrole::text || '|' "
            "|| array_to_string(setconfig, ',') "
            "FROM pg_db_role_setting "
            "UNION ALL "
            "SELECT 'database|' || datname || '|' || datdba::text || '|' || COALESCE(datacl::text, '') "
            "FROM pg_database WHERE datname = current_database() "
            "UNION ALL "
            "SELECT 'schema|' || nspname || '|' || nspowner::text || '|' || COALESCE(nspacl::text, '') "
            "FROM pg_namespace "
            "WHERE nspname IN ('app', 'ops', 'pinvi_internal', 'x_extension') "
            "UNION ALL "
            "SELECT 'default_acl|' || defaclrole::text || '|' || defaclnamespace::text || '|' "
            "|| defaclobjtype::text || '|' || COALESCE(defaclacl::text, '') "
            "FROM pg_default_acl "
            "UNION ALL "
            "SELECT 'fence|' || procedure.proowner::text || '|' || COALESCE(procedure.proacl::text, '') "
            "FROM pg_proc procedure JOIN pg_namespace namespace "
            "ON namespace.oid = procedure.pronamespace "
            "WHERE namespace.nspname = 'pinvi_internal' "
            "AND procedure.proname = 'acquire_fresh_0101_database_fence' "
            "AND procedure.pronargs = 0 "
            "UNION ALL "
            "SELECT 'extension|' || extname || '|' || extowner::text "
            "FROM pg_extension "
            "WHERE extname IN ('pgcrypto', 'pg_trgm', 'citext')"
            ") "
            "SELECT md5(COALESCE(string_agg(value, E'\\n' ORDER BY value), '')) "
            "FROM catalog_rows"
        )
        result = compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            f"--username={root_role}",
            "--dbname=pinvi",
            f"--command={query}",
        )
        return result.stdout.strip()

    def sealed_role_topology_diagnostic() -> str:
        result = compose(
            "run",
            "--rm",
            "--no-deps",
            "--env",
            "PINVI_ROLE_TOPOLOGY_VERIFY_ONLY=1",
            "--env",
            "PINVI_MIGRATOR_DISABLE_LOGIN=1",
            "app-db-runtime-role",
        )
        return result.stdout.strip()

    def assert_sealed_noncanonical(reason: str) -> None:
        before = role_catalog_fingerprint()
        assert sealed_role_topology_diagnostic() == (
            '{"schema":"pinvi.role-topology-diagnostic.v1","status":"noncanonical",'
            f'"mode":"sealed","reasons":["{reason}"]}}'
        )
        assert role_catalog_fingerprint() == before

    def runtime_app_privilege_state() -> tuple[str, str, str, str, str]:
        query = (
            "SELECT "
            f"has_schema_privilege('{runtime_role}', 'app', 'USAGE'), "
            f"(has_table_privilege('{runtime_role}', 'app.users', 'SELECT') "
            f"AND has_table_privilege('{runtime_role}', 'app.users', 'INSERT') "
            f"AND has_table_privilege('{runtime_role}', 'app.users', 'UPDATE') "
            f"AND has_table_privilege('{runtime_role}', 'app.users', 'DELETE')), "
            f"(has_table_privilege('{runtime_role}', 'app.oauth_login_states', 'SELECT') "
            f"AND has_table_privilege('{runtime_role}', 'app.oauth_login_states', 'INSERT') "
            f"AND has_table_privilege('{runtime_role}', 'app.oauth_login_states', 'UPDATE') "
            f"AND has_table_privilege('{runtime_role}', 'app.oauth_login_states', 'DELETE')), "
            f"(has_table_privilege('{runtime_role}', 'app.oauth_mobile_exchanges', 'SELECT') "
            f"AND has_table_privilege('{runtime_role}', 'app.oauth_mobile_exchanges', 'INSERT') "
            f"AND has_table_privilege('{runtime_role}', 'app.oauth_mobile_exchanges', 'UPDATE') "
            f"AND has_table_privilege('{runtime_role}', 'app.oauth_mobile_exchanges', 'DELETE')), "
            f"(has_table_privilege('{runtime_role}', 'app.user_oauth_identities', 'SELECT') "
            f"AND has_table_privilege('{runtime_role}', 'app.user_oauth_identities', 'INSERT') "
            f"AND has_table_privilege('{runtime_role}', 'app.user_oauth_identities', 'UPDATE') "
            f"AND has_table_privilege('{runtime_role}', 'app.user_oauth_identities', 'DELETE'))"
        )
        result = compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            f"--username={root_role}",
            "--dbname=pinvi",
            f"--command={query}",
        )
        state = result.stdout.strip().split("|")
        assert len(state) == 5
        return tuple(state)  # type: ignore[return-value]

    def runtime_version_privilege_state() -> str:
        result = compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            f"--username={root_role}",
            "--dbname=pinvi",
            "--command="
            f"SELECT (has_table_privilege('{runtime_role}', 'app.alembic_version', 'SELECT') "
            f"AND NOT has_table_privilege('{runtime_role}', 'app.alembic_version', 'INSERT') "
            f"AND NOT has_table_privilege('{runtime_role}', 'app.alembic_version', 'UPDATE') "
            f"AND NOT has_table_privilege('{runtime_role}', 'app.alembic_version', 'DELETE'))::text;",
        )
        return result.stdout.strip()

    client_name = f"pinvi-m05-client-{suffix}"
    rotated_client_name = f"pinvi-m05-rotated-client-{suffix}"
    stale_role = f"m05_stale_{suffix}"
    try:
        compose("up", "--detach", "app-postgres")
        compose(
            "run",
            "--rm",
            "--no-deps",
            "--env",
            "PINVI_MIGRATOR_DISABLE_LOGIN=0",
            "app-db-runtime-role",
        )
        compose("build", "app-api")
        migration = compose(
            "run",
            "--rm",
            "--no-deps",
            "app-migrator",
            "alembic",
            "upgrade",
            "head",
        )
        assert migration.returncode == 0, migration.stderr
        compose("run", "--rm", "--no-deps", "app-db-runtime-role")
        assert role_state() == ("false", "false", "0", "false", "true")
        assert managed_schema_state() == (
            schema_owner,
            migration_owner,
            schema_owner,
            "f",
            "t",
            "t",
            "20260824_0101",
        )
        canonical_fingerprint = role_catalog_fingerprint()
        assert sealed_role_topology_diagnostic() == (
            '{"schema":"pinvi.role-topology-diagnostic.v1","status":"canonical",'
            '"mode":"sealed","reasons":[]}'
        )
        assert role_catalog_fingerprint() == canonical_fingerprint
        assert runtime_app_privilege_state() == ("t", "t", "t", "t", "t")

        # The evaluator is shared by the normal final gate and the sealed-only
        # diagnostic.  Each injected canonicality violation has one stable
        # typed reason; the diagnostic itself must not change the catalog.
        topology_cases = (
            (
                "bootstrap_catalog",
                f'ALTER SCHEMA ops OWNER TO "{root_role}";',
                f'ALTER SCHEMA ops OWNER TO "{migration_owner}";',
            ),
            (
                "fence_acl",
                "REVOKE EXECUTE ON FUNCTION pinvi_internal.acquire_fresh_0101_database_fence() "
                f'FROM "{schema_owner}";',
                "GRANT EXECUTE ON FUNCTION pinvi_internal.acquire_fresh_0101_database_fence() "
                f'TO "{schema_owner}";',
            ),
            (
                "runtime_role",
                f'ALTER ROLE "{runtime_role}" NOLOGIN;',
                f'ALTER ROLE "{runtime_role}" LOGIN;',
            ),
            (
                "migration_owner_policy",
                f'GRANT CONNECT ON DATABASE "pinvi" TO "{migration_owner}";',
                f'REVOKE CONNECT ON DATABASE "pinvi" FROM "{migration_owner}";',
            ),
            (
                "migrator_sealed",
                f'ALTER ROLE "{migrator_role}" LOGIN; '
                f'GRANT CONNECT ON DATABASE "pinvi" TO "{migrator_role}";',
                f'ALTER ROLE "{migrator_role}" NOLOGIN; '
                f'REVOKE CONNECT ON DATABASE "pinvi" FROM "{migrator_role}";',
            ),
            (
                "migrator_membership_setting",
                f'ALTER ROLE "{migrator_role}" IN DATABASE "pinvi" RESET ROLE;',
                f'ALTER ROLE "{migrator_role}" IN DATABASE "pinvi" SET ROLE TO "{schema_owner}";',
            ),
            (
                "app_ownership",
                f'ALTER SCHEMA app OWNER TO "{root_role}";',
                f'ALTER SCHEMA app OWNER TO "{schema_owner}";',
            ),
            (
                "extension_ownership",
                "DROP EXTENSION citext;",
                "CREATE EXTENSION citext SCHEMA x_extension;",
            ),
        )
        for reason, inject, restore in topology_cases:
            compose(
                "exec",
                "-T",
                "app-postgres",
                "psql",
                f"--username={root_role}",
                "--dbname=pinvi",
                f"--command={inject}",
            )
            assert_sealed_noncanonical(reason)
            compose(
                "exec",
                "-T",
                "app-postgres",
                "psql",
                f"--username={root_role}",
                "--dbname=pinvi",
                f"--command={restore}",
            )
            assert sealed_role_topology_diagnostic() == (
                '{"schema":"pinvi.role-topology-diagnostic.v1","status":"canonical",'
                '"mode":"sealed","reasons":[]}'
            )

        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            f'--command=ALTER DATABASE "pinvi" OWNER TO "{schema_owner}";',
        )
        database_owner_diagnostic_fingerprint = role_catalog_fingerprint()
        assert sealed_role_topology_diagnostic() == (
            '{"schema":"pinvi.role-topology-diagnostic.v1","status":"noncanonical",'
            '"mode":"sealed","reasons":["principal_identity","fence_acl","migrator_sealed"]}'
        )
        assert role_catalog_fingerprint() == database_owner_diagnostic_fingerprint
        database_owner_collision = compose(
            "run",
            "--rm",
            "--no-deps",
            "app-db-runtime-role",
            check=False,
        )
        assert database_owner_collision.returncode != 0
        assert "role topology is not canonical" in (
            database_owner_collision.stdout + database_owner_collision.stderr
        )
        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            f'--command=ALTER DATABASE "pinvi" OWNER TO "{root_role}";',
        )
        compose("run", "--rm", "--no-deps", "app-db-runtime-role")
        runtime_version_update = compose(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "/bin/sh",
            "app-db-runtime-role",
            "-ec",
            'PGPASSWORD="$PINVI_APP_DB_PASSWORD" exec psql --no-psqlrc '
            '--no-password --host=app-postgres --username="$PINVI_APP_DB_USER" '
            '--dbname="$POSTGRES_DB" '
            "--command=\"UPDATE app.alembic_version SET version_num = 'forged'\"",
            check=False,
        )
        assert runtime_version_update.returncode != 0
        assert "permission denied" in (
            runtime_version_update.stdout + runtime_version_update.stderr
        )

        # 이미 0101인 DB는 Alembic upgrade가 no-op이므로, 과거 0101 variant가 남긴
        # runtime/default ACL 누락을 app-db-runtime-role만으로 복구해야 한다.
        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            "--command="
            f'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA app FROM "{runtime_role}"; '
            f'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA app FROM "{runtime_role}"; '
            f'ALTER DEFAULT PRIVILEGES FOR ROLE "{schema_owner}" IN SCHEMA app '
            f'REVOKE ALL ON TABLES FROM "{runtime_role}"; '
            f'ALTER DEFAULT PRIVILEGES FOR ROLE "{schema_owner}" IN SCHEMA app '
            f'REVOKE ALL ON SEQUENCES FROM "{runtime_role}";',
        )
        assert runtime_app_privilege_state() == ("t", "f", "f", "f", "f")
        assert runtime_version_privilege_state() == "false"
        compose("run", "--rm", "--no-deps", "app-db-runtime-role")
        assert runtime_app_privilege_state() == ("t", "t", "t", "t", "t")
        assert runtime_version_privilege_state() == "true"
        runtime_version_select = compose(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "/bin/sh",
            "app-db-runtime-role",
            "-ec",
            'PGPASSWORD="$PINVI_APP_DB_PASSWORD" exec psql --no-psqlrc '
            "--no-password --tuples-only --no-align --host=app-postgres "
            '--username="$PINVI_APP_DB_USER" '
            '--dbname="$POSTGRES_DB" --command="SELECT version_num FROM app.alembic_version"',
        )
        assert runtime_version_select.stdout.strip() == "20260824_0101"
        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            "--command="
            f'SET ROLE "{schema_owner}"; '
            "CREATE TABLE app.runtime_repair_default_acl_probe (id bigserial PRIMARY KEY); "
            "RESET ROLE;",
        )
        repaired_default_acl_probe = compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            f"--username={root_role}",
            "--dbname=pinvi",
            "--command="
            f"SELECT has_table_privilege('{runtime_role}', 'app.runtime_repair_default_acl_probe', "
            "'SELECT, INSERT, UPDATE, DELETE')::text, "
            f"has_sequence_privilege('{runtime_role}', 'app.runtime_repair_default_acl_probe_id_seq', "
            "'USAGE, SELECT, UPDATE')::text;",
        )
        assert repaired_default_acl_probe.stdout.strip() == "true|true"

        # legacy bootstrap은 receipt fingerprint가 결박되기 전 app ACL/default ACL을
        # 바꾸지 않는다. 복원은 0101 handoff가 끝난 뒤 migration 안에서 수행한다.
        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            "--command="
            f'ALTER DEFAULT PRIVILEGES FOR ROLE "{schema_owner}" IN SCHEMA app '
            f'REVOKE ALL ON TABLES FROM "{runtime_role}"; '
            f'ALTER DEFAULT PRIVILEGES FOR ROLE "{schema_owner}" IN SCHEMA app '
            f'REVOKE ALL ON SEQUENCES FROM "{runtime_role}";',
        )
        compose(
            "run",
            "--rm",
            "--no-deps",
            "--env",
            "PINVI_M05_LEGACY_REBASELINE=1",
            "--env",
            "PINVI_MIGRATOR_DISABLE_LOGIN=1",
            "app-db-runtime-role",
        )
        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            "--command="
            f'SET ROLE "{schema_owner}"; '
            "CREATE TABLE app.legacy_default_acl_probe (id bigserial PRIMARY KEY); "
            "RESET ROLE;",
        )
        default_acl_probe = compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            f"--username={root_role}",
            "--dbname=pinvi",
            "--command="
            f"SELECT has_table_privilege('{runtime_role}', 'app.legacy_default_acl_probe', "
            "'SELECT, INSERT, UPDATE, DELETE')::text, "
            f"has_sequence_privilege('{runtime_role}', 'app.legacy_default_acl_probe_id_seq', "
            "'USAGE, SELECT, UPDATE')::text;",
        )
        assert default_acl_probe.stdout.strip() == "false|false"

        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            "--command="
            f'CREATE ROLE "{stale_role}" LOGIN NOINHERIT; '
            f'GRANT "{schema_owner}" TO "{stale_role}" WITH INHERIT FALSE, SET TRUE;',
        )
        stale_membership_fingerprint = role_catalog_fingerprint()
        assert sealed_role_topology_diagnostic() == (
            '{"schema":"pinvi.role-topology-diagnostic.v1","status":"noncanonical",'
            '"mode":"sealed","reasons":["schema_owner_membership"]}'
        )
        assert role_catalog_fingerprint() == stale_membership_fingerprint
        stale_membership = compose(
            "run",
            "--rm",
            "--no-deps",
            "--env",
            "PINVI_MIGRATOR_DISABLE_LOGIN=0",
            "app-db-runtime-role",
            check=False,
        )
        assert stale_membership.returncode != 0
        assert "role topology is not canonical" in stale_membership.stderr
        assert role_state()[:3] == ("false", "false", "0")
        sealed_membership = compose("run", "--rm", "--no-deps", "app-db-runtime-role", check=False)
        assert sealed_membership.returncode != 0
        assert "role topology is not canonical" in sealed_membership.stderr
        assert role_state()[:3] == ("false", "false", "0")
        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            f'--command=REVOKE "{schema_owner}" FROM "{stale_role}"; DROP ROLE "{stale_role}";',
        )
        compose("run", "--rm", "--no-deps", "app-db-runtime-role")

        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            "--command="
            f'CREATE ROLE "{stale_role}" LOGIN NOINHERIT; '
            f'GRANT "{runtime_role}" TO "{stale_role}" WITH INHERIT FALSE, SET TRUE;',
        )
        inbound_membership = compose("run", "--rm", "--no-deps", "app-db-runtime-role", check=False)
        assert inbound_membership.returncode != 0
        assert "role topology is not canonical" in inbound_membership.stderr
        assert role_state()[:3] == ("false", "false", "0")
        compose(
            "exec",
            "-T",
            "app-postgres",
            "psql",
            f"--username={root_role}",
            "--dbname=pinvi",
            f'--command=REVOKE "{runtime_role}" FROM "{stale_role}"; DROP ROLE "{stale_role}";',
        )
        compose("run", "--rm", "--no-deps", "app-db-runtime-role")

        compose(
            "run",
            "--rm",
            "--no-deps",
            "--env",
            "PINVI_MIGRATOR_DISABLE_LOGIN=0",
            "--env",
            f"PINVI_MIGRATOR_DB_PASSWORD={ephemeral_password}",
            "app-db-runtime-role",
        )
        assert role_state() == ("true", "true", "0", "false", "true")

        stale_password = compose(
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "/bin/sh",
            "app-db-runtime-role",
            "-ec",
            'PGPASSWORD="$PINVI_MIGRATOR_DB_PASSWORD" exec psql --no-psqlrc '
            '--no-password --host=app-postgres --username="$PINVI_MIGRATOR_DB_USER" '
            '--dbname="$POSTGRES_DB" --command="SELECT 1"',
            check=False,
        )
        assert stale_password.returncode != 0

        compose(
            "run",
            "--detach",
            "--name",
            client_name,
            "--no-deps",
            "--env",
            f"PINVI_MIGRATOR_DB_PASSWORD={ephemeral_password}",
            "--entrypoint",
            "/bin/sh",
            "app-db-runtime-role",
            "-ec",
            'PGPASSWORD="$PINVI_MIGRATOR_DB_PASSWORD" exec psql --no-psqlrc '
            '--no-password --host=app-postgres --username="$PINVI_MIGRATOR_DB_USER" '
            '--dbname="$POSTGRES_DB" --command="SELECT pg_sleep(60)"',
        )
        for _ in range(40):
            if role_state()[2] == "1":
                break
            time.sleep(0.25)
        assert role_state()[2] == "1"

        compose(
            "run",
            "--rm",
            "--no-deps",
            "--env",
            "PINVI_MIGRATOR_DISABLE_LOGIN=0",
            "--env",
            f"PINVI_MIGRATOR_DB_PASSWORD={rotated_password}",
            "app-db-runtime-role",
        )
        assert role_state() == ("true", "true", "0", "false", "true")
        terminated_client = subprocess.run(  # noqa: S603 - fixed Docker wait invocation
            [docker, "wait", client_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert terminated_client.returncode == 0
        assert terminated_client.stdout.strip() != "0"

        old_password = compose(
            "run",
            "--rm",
            "--no-deps",
            "--env",
            f"PINVI_MIGRATOR_DB_PASSWORD={ephemeral_password}",
            "--entrypoint",
            "/bin/sh",
            "app-db-runtime-role",
            "-ec",
            'PGPASSWORD="$PINVI_MIGRATOR_DB_PASSWORD" exec psql --no-psqlrc '
            '--no-password --host=app-postgres --username="$PINVI_MIGRATOR_DB_USER" '
            '--dbname="$POSTGRES_DB" --command="SELECT 1"',
            check=False,
        )
        assert old_password.returncode != 0

        compose(
            "run",
            "--detach",
            "--name",
            rotated_client_name,
            "--no-deps",
            "--env",
            f"PINVI_MIGRATOR_DB_PASSWORD={rotated_password}",
            "--entrypoint",
            "/bin/sh",
            "app-db-runtime-role",
            "-ec",
            'PGPASSWORD="$PINVI_MIGRATOR_DB_PASSWORD" exec psql --no-psqlrc '
            '--no-password --host=app-postgres --username="$PINVI_MIGRATOR_DB_USER" '
            '--dbname="$POSTGRES_DB" --command="SELECT pg_sleep(60)"',
        )
        for _ in range(40):
            if role_state()[2] == "1":
                break
            time.sleep(0.25)
        assert role_state()[2] == "1"

        compose(
            "run",
            "--rm",
            "--no-deps",
            "--env",
            "PINVI_MIGRATOR_DISABLE_LOGIN=1",
            "app-db-runtime-role",
        )
        assert role_state() == ("false", "false", "0", "false", "true")
    finally:
        compose("down", "--volumes", "--remove-orphans", check=False)
