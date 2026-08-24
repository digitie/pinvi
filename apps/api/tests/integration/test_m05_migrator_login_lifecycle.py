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

    client_name = f"pinvi-m05-client-{suffix}"
    stale_role = f"m05_stale_{suffix}"
    try:
        compose("up", "--detach", "app-postgres")
        compose("run", "--rm", "--no-deps", "app-db-runtime-role")
        assert role_state() == ("false", "false", "0", "false", "true")

        # legacy 0101이 app catalog을 schema owner로 넘긴 뒤에도 다음 DDL에 runtime
        # grant가 남아야 한다. canonical owner의 default ACL을 일부러 비운 뒤 legacy
        # bootstrap으로 다시 고정하고, 그 owner가 만든 table/sequence를 직접 확인한다.
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
        assert default_acl_probe.stdout.strip() == "true|true"

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
            "PINVI_MIGRATOR_DISABLE_LOGIN=1",
            "app-db-runtime-role",
        )
        assert role_state() == ("false", "false", "0", "false", "true")
    finally:
        compose("down", "--volumes", "--remove-orphans", check=False)
