"""0101 M05 통합 migration의 실제 PostgreSQL 계약을 검증한다."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

API_DIR = Path(__file__).resolve().parents[2]
_ROLE_PASSWORD = "m05-role-owner-test-only"


def _alembic(database_url: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PINVI_DATABASE_URL"] = database_url
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env=env,
        check=check,
        capture_output=True,
        text=True,
    )


async def _execute_autocommit(database_url: str, sql: str) -> None:
    engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(sql))
    finally:
        await engine.dispose()


async def _new_database(_database_url: str, prefix: str) -> tuple[str, str]:
    database_name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    parsed = make_url(_database_url)
    target_url = parsed.set(database=database_name).render_as_string(hide_password=False)
    maintenance_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    await _execute_autocommit(maintenance_url, f'CREATE DATABASE "{database_name}"')
    return target_url, maintenance_url


async def _drop_database(maintenance_url: str, database_url: str) -> None:
    database_name = make_url(database_url).database
    assert database_name is not None
    await _execute_autocommit(
        maintenance_url,
        f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)',
    )


def _role_database_url(database_url: str, *, role: str, password: str, database: str) -> str:
    return make_url(database_url).set(
        username=role,
        password=password,
        database=database,
    ).render_as_string(hide_password=False)


@pytest.mark.asyncio
async def test_0101_installs_m05_final_contract_with_minimal_public_surface(
    _database_url: str,
) -> None:
    """새 DB는 0100→0101만 거쳐 anchor, receipt, audit guard를 함께 얻는다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_0101")
    try:
        upgraded = _alembic(target_url, "upgrade", "head")
        assert upgraded.returncode == 0, upgraded.stderr

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                    == "20260824_0101"
                )
                boundary_definition = await connection.scalar(
                    text(
                        "SELECT pg_get_constraintdef(constraint_row.oid) "
                        "FROM pg_constraint constraint_row "
                        "JOIN pg_class relation ON relation.oid = constraint_row.conrelid "
                        "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
                        "WHERE namespace.nspname = 'app' "
                        "AND relation.relname = 'ktm_cache_target_boundary_audits' "
                        "AND pg_get_constraintdef(constraint_row.oid) "
                        "LIKE '%pinvi-cache-target-final-boundary/v1%'"
                    )
                )
                assert "schema_revision = '20260824_0101'::text" in boundary_definition

                trigger_rows = await connection.execute(
                    text(
                        "SELECT namespace.nspname, relation.relname, trigger_row.tgname, "
                        "trigger_row.tgenabled::text "
                        "FROM pg_trigger trigger_row "
                        "JOIN pg_class relation ON relation.oid = trigger_row.tgrelid "
                        "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
                        "WHERE (namespace.nspname, relation.relname) IN ("
                        "('app', 'admin_audit_log'), "
                        "('ops', 'm05_activation_database_anchor'), "
                        "('ops', 'm05_hotswap_release_receipts')) "
                        "AND trigger_row.tgname LIKE 'trg_%append_only%' "
                        "AND NOT trigger_row.tgisinternal"
                    )
                )
                assert {
                    (row[0], row[1], row[2], row[3]) for row in trigger_rows
                } >= {
                    ("app", "admin_audit_log", "trg_admin_audit_log_append_only", "A"),
                    ("app", "admin_audit_log", "trg_admin_audit_log_truncate_append_only", "A"),
                    (
                        "ops",
                        "m05_activation_database_anchor",
                        "trg_m05_activation_database_anchor_append_only",
                        "A",
                    ),
                    (
                        "ops",
                        "m05_activation_database_anchor",
                        "trg_m05_activation_database_anchor_truncate_append_only",
                        "A",
                    ),
                    (
                        "ops",
                        "m05_hotswap_release_receipts",
                        "trg_m05_hotswap_release_receipts_append_only",
                        "A",
                    ),
                    (
                        "ops",
                        "m05_hotswap_release_receipts",
                        "trg_m05_hotswap_release_receipts_truncate_append_only",
                        "A",
                    ),
                }

                public_anchor_read = await connection.scalar(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM pg_class relation "
                        "CROSS JOIN LATERAL aclexplode(COALESCE(relation.relacl, "
                        "acldefault('r', relation.relowner))) acl "
                        "WHERE relation.oid = 'ops.m05_activation_database_anchor'::regclass "
                        "AND acl.grantee = 0 AND acl.privilege_type = 'SELECT' "
                        "AND NOT acl.is_grantable)"
                    )
                )
                assert public_anchor_read is True
                public_receipt_capability = await connection.scalar(
                    text(
                        "WITH objects AS ("
                        "SELECT relation.relacl AS acl, acldefault('r', relation.relowner) "
                        "AS default_acl FROM pg_class relation "
                        "WHERE relation.oid = 'ops.m05_hotswap_release_receipts'::regclass "
                        "UNION ALL "
                        "SELECT procedure.proacl, acldefault('f', procedure.proowner) "
                        "FROM pg_proc procedure WHERE procedure.oid IN ("
                        "'ops.m05_hotswap_release_topology_sha256("
                        "name,name,name,name,name,name)'::regprocedure, "
                        "'ops.record_m05_hotswap_release_receipt("
                        "uuid,text,text,text,text,text,text,text,name,name,name,name,name,name,"
                        "oid,oid,oid,oid,jsonb,jsonb,boolean,text)'::regprocedure, "
                        "'ops.verify_m05_hotswap_release_receipt(uuid,text)'::regprocedure)"
                        ") SELECT EXISTS (SELECT 1 FROM objects "
                        "CROSS JOIN LATERAL aclexplode(COALESCE(acl, default_acl)) privilege "
                        "WHERE privilege.grantee = 0)"
                    )
                )
                assert public_receipt_capability is False

                await connection.execute(
                    text(
                        "INSERT INTO ops.m05_activation_database_anchor "
                        "(generation, receipt_sha256, record_sha256) "
                        "VALUES (1, repeat('1', 64), repeat('2', 64))"
                    )
                )
                with pytest.raises(DBAPIError, match="append-only"):
                    await connection.execute(
                        text(
                            "UPDATE ops.m05_activation_database_anchor "
                            "SET generation = 2 WHERE generation = 1"
                        )
                    )
                await connection.rollback()
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup_sql", "expected_message"),
    (
        (
            "CREATE SCHEMA ops; "
            "ALTER DEFAULT PRIVILEGES IN SCHEMA ops GRANT EXECUTE ON FUNCTIONS TO PUBLIC",
            "rejects migration-owner default privileges",
        ),
        (
            "CREATE SCHEMA ops; "
            "CREATE TABLE ops.m05_activation_database_anchor (generation bigint)",
            "refuses to replace pre-existing M05 objects",
        ),
    ),
)
async def test_0101_rejects_unsafe_existing_ops_state(
    _database_url: str,
    setup_sql: str,
    expected_message: str,
) -> None:
    """0101은 default ACL·부분 M05 object를 덮어쓰지 않고 0100에 남긴다."""

    target_url, maintenance_url = await _new_database(_database_url, "pinvi_m05_0101_reject")
    try:
        baseline = _alembic(target_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr
        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                for statement in setup_sql.split("; "):
                    await connection.execute(text(statement))
        finally:
            await engine.dispose()

        failed = _alembic(target_url, "upgrade", "20260824_0101", check=False)
        assert failed.returncode != 0
        assert expected_message in (failed.stdout + failed.stderr)

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                    == "20260824_0100"
                )
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)


@pytest.mark.asyncio
async def test_0101_can_use_a_separate_nonruntime_migration_owner(
    _database_url: str,
) -> None:
    """0101 owner는 runtime/fence와 분리하면서도 app owner 권한으로 DDL을 수행한다."""

    suffix = uuid.uuid4().hex[:12]
    database_name = f"pinvi_m05_owner_{suffix}"
    app_owner = f"m05_app_owner_{suffix}"
    fence_role = f"m05_fence_{suffix}"
    migration_owner = f"m05_migration_{suffix}"
    parsed = make_url(_database_url)
    maintenance_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    app_url = _role_database_url(
        _database_url,
        role=app_owner,
        password=_ROLE_PASSWORD,
        database=database_name,
    )
    migration_url = _role_database_url(
        _database_url,
        role=migration_owner,
        password=_ROLE_PASSWORD,
        database=database_name,
    )
    target_url = parsed.set(database=database_name).render_as_string(hide_password=False)

    try:
        for statement in (
            f'CREATE ROLE "{fence_role}" LOGIN NOINHERIT PASSWORD \'{_ROLE_PASSWORD}\';',
            f'CREATE ROLE "{app_owner}" LOGIN INHERIT PASSWORD \'{_ROLE_PASSWORD}\';',
            f'CREATE ROLE "{migration_owner}" LOGIN INHERIT PASSWORD \'{_ROLE_PASSWORD}\' '
            f'IN ROLE "{app_owner}";',
        ):
            await _execute_autocommit(maintenance_url, statement)
        await _execute_autocommit(
            maintenance_url,
            f'CREATE DATABASE "{database_name}" OWNER "{fence_role}";',
        )
        await _execute_autocommit(
            maintenance_url,
            f'GRANT CONNECT, CREATE ON DATABASE "{database_name}" '
            f'TO "{app_owner}", "{migration_owner}";',
        )

        baseline = _alembic(app_url, "upgrade", "20260824_0100")
        assert baseline.returncode == 0, baseline.stderr
        await _execute_autocommit(
            app_url,
            f'GRANT USAGE ON SCHEMA x_extension TO "{migration_owner}";',
        )
        activation = _alembic(migration_url, "upgrade", "20260824_0101")
        assert activation.returncode == 0, activation.stderr

        engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                owners = await connection.execute(
                    text(
                        "SELECT namespace.nspowner::regrole::text, "
                        "relation.relowner::regrole::text "
                        "FROM pg_namespace namespace "
                        "JOIN pg_class relation ON relation.relnamespace = namespace.oid "
                        "WHERE namespace.nspname = 'ops' "
                        "AND relation.relname = 'm05_hotswap_release_receipts'"
                    )
                )
                assert owners.one() == (migration_owner, migration_owner)
                extension_access = await connection.scalar(
                    text(
                        "SELECT has_schema_privilege(:migration_owner, 'x_extension', 'USAGE') "
                        "AND NOT has_schema_privilege(:fence_role, 'x_extension', 'USAGE')"
                    ),
                    {"migration_owner": migration_owner, "fence_role": fence_role},
                )
                assert extension_access is True
        finally:
            await engine.dispose()
    finally:
        await _drop_database(maintenance_url, target_url)
        await _execute_autocommit(
            maintenance_url,
            f'DROP ROLE IF EXISTS "{migration_owner}", "{app_owner}", "{fence_role}";',
        )
