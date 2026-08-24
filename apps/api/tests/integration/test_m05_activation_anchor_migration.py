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
