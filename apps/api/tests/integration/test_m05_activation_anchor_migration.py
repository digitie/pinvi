"""M05 database activation anchor migration의 실제 ACL 경계를 검증한다."""

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
TEST_PASSWORD = "m05-anchor-test-only-password"


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


@pytest.mark.asyncio
async def test_0062_rejects_global_default_acl_and_keeps_anchor_writer_root_only(
    _database_url: str,
) -> None:
    """migration-owner default ACL은 rollback하고 정상 anchor는 공개 read만 허용한다."""
    suffix = uuid.uuid4().hex[:12]
    database_name = f"pinvi_m05_anchor_{suffix}"
    reader_role = f"m05_anchor_reader_{suffix}"
    parsed = make_url(_database_url)
    target_url = parsed.set(database=database_name).render_as_string(hide_password=False)
    maintenance_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    quoted_database = f'"{database_name}"'
    quoted_reader = f'"{reader_role}"'
    reader_url = parsed.set(
        username=reader_role,
        password=TEST_PASSWORD,
        database=database_name,
    ).render_as_string(hide_password=False)

    await _execute_autocommit(
        maintenance_url,
        f"CREATE DATABASE {quoted_database}",
    )
    try:
        prior = _alembic(target_url, "upgrade", "20260821_0061")
        assert prior.returncode == 0, prior.stderr

        target_engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with target_engine.begin() as connection:
                await connection.execute(
                    text("ALTER DEFAULT PRIVILEGES FOR ROLE pinvi GRANT INSERT ON TABLES TO PUBLIC")
                )
        finally:
            await target_engine.dispose()

        failed = _alembic(target_url, "upgrade", "head", check=False)
        assert failed.returncode != 0
        assert "rejects migration-owner default privileges" in failed.stderr

        target_engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with target_engine.connect() as connection:
                version = await connection.scalar(
                    text("SELECT version_num FROM app.alembic_version")
                )
                assert version == "20260821_0061"
                assert (
                    await connection.scalar(
                        text("SELECT to_regclass('ops.m05_activation_database_anchor')")
                    )
                    is None
                )
            async with target_engine.begin() as connection:
                await connection.execute(
                    text("ALTER DEFAULT PRIVILEGES FOR ROLE pinvi REVOKE ALL ON TABLES FROM PUBLIC")
                )
        finally:
            await target_engine.dispose()

        repaired = _alembic(target_url, "upgrade", "head")
        assert repaired.returncode == 0, repaired.stderr

        await _execute_autocommit(
            maintenance_url,
            f"CREATE ROLE {quoted_reader} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            f"NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD '{TEST_PASSWORD}'",
        )
        reader_engine = create_async_engine(reader_url, poolclass=NullPool)
        target_engine = create_async_engine(target_url, poolclass=NullPool)
        try:
            async with target_engine.begin() as connection:
                assert (
                    await connection.scalar(
                        text(
                            "SELECT has_table_privilege(:role, "
                            "'ops.m05_activation_database_anchor', 'SELECT')"
                        ),
                        {"role": reader_role},
                    )
                    is True
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT has_table_privilege(:role, "
                            "'ops.m05_activation_database_anchor', 'INSERT')"
                        ),
                        {"role": reader_role},
                    )
                    is False
                )
                await connection.execute(
                    text(
                        "INSERT INTO ops.m05_activation_database_anchor "
                        "(generation, receipt_sha256, record_sha256) "
                        "VALUES (1, :receipt_sha256, :record_sha256)"
                    ),
                    {"receipt_sha256": "a" * 64, "record_sha256": "b" * 64},
                )

            async with reader_engine.connect() as connection:
                assert (
                    await connection.scalar(
                        text("SELECT count(*) FROM ops.m05_activation_database_anchor")
                    )
                    == 1
                )
                with pytest.raises(DBAPIError, match="permission denied"):
                    await connection.execute(
                        text(
                            "INSERT INTO ops.m05_activation_database_anchor "
                            "(generation, receipt_sha256, record_sha256) "
                            "VALUES (2, :receipt_sha256, :record_sha256)"
                        ),
                        {"receipt_sha256": "c" * 64, "record_sha256": "d" * 64},
                    )
                await connection.rollback()

            async with target_engine.connect() as connection:
                for statement in (
                    "UPDATE ops.m05_activation_database_anchor SET generation = 2 WHERE generation = 1",
                    "DELETE FROM ops.m05_activation_database_anchor WHERE generation = 1",
                    "TRUNCATE ops.m05_activation_database_anchor",
                ):
                    with pytest.raises(DBAPIError, match="append-only"):
                        await connection.execute(text(statement))
                    await connection.rollback()
        finally:
            await reader_engine.dispose()
            await target_engine.dispose()
    finally:
        await _execute_autocommit(
            maintenance_url,
            f"DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE)",
        )
        await _execute_autocommit(
            maintenance_url,
            f"DROP ROLE IF EXISTS {quoted_reader}",
        )


@pytest.mark.asyncio
async def test_0063_installs_the_boundary_and_admin_audit_contract_on_real_head(
    _database_url: str,
) -> None:
    """실제 Alembic head가 hotswap runner의 0063 계약을 설치했는지 확인한다."""

    engine = create_async_engine(_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM app.alembic_version"))
                == "20260824_0063"
            )
            boundary_definition = await connection.scalar(
                text(
                    "SELECT pg_get_constraintdef(constraint_row.oid) "
                    "FROM pg_constraint constraint_row "
                    "WHERE constraint_row.conrelid = "
                    "'app.ktm_cache_target_boundary_audits'::regclass "
                    "AND constraint_row.conname = 'ck_ktm_ct_boundary_contract'"
                )
            )
            assert isinstance(boundary_definition, str)
            assert "pinvi-cache-target-final-boundary/v1" in boundary_definition
            assert "status = 'succeeded'::text" in boundary_definition
            assert "schema_revision = '20260824_0063'::text" in boundary_definition

            trigger_rows = await connection.execute(
                text(
                    "SELECT trigger_row.tgname, trigger_row.tgenabled::text "
                    "FROM pg_trigger trigger_row "
                    "JOIN pg_class relation ON relation.oid = trigger_row.tgrelid "
                    "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
                    "WHERE namespace.nspname = 'app' "
                    "AND relation.relname = 'admin_audit_log' "
                    "AND trigger_row.tgname IN ("
                    "'trg_admin_audit_log_append_only', "
                    "'trg_admin_audit_log_truncate_append_only') "
                    "AND NOT trigger_row.tgisinternal"
                )
            )
            assert {(row[0], row[1]) for row in trigger_rows} == {
                ("trg_admin_audit_log_append_only", "A"),
                ("trg_admin_audit_log_truncate_append_only", "A"),
            }

            function_body = await connection.scalar(
                text(
                    "SELECT regexp_replace(btrim(procedure.prosrc), "
                    "'[[:space:]]+', ' ', 'g') "
                    "FROM pg_proc procedure "
                    "JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace "
                    "WHERE namespace.nspname = 'app' "
                    "AND procedure.proname = 'guard_admin_audit_log_append_only'"
                )
            )
            assert function_body == (
                "BEGIN IF TG_OP = 'INSERT' THEN RETURN NEW; END IF; "
                "RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || "
                "TG_TABLE_NAME USING ERRCODE = '55000'; END;"
            )
    finally:
        await engine.dispose()
