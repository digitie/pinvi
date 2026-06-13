"""Alembic env — Pinvi `app` schema 전용.

`feature` / `provider_sync` schema는 `kor-travel-map`이 별도 alembic으로 관리
(ADR-003). 본 env는 `app` + `x_extension` schema만 다룬다.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import context
from app.core.config import settings
from app.db.base import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def get_url() -> str:
    return settings.pinvi_database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="app",
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    connection.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
    connection.execute(text("CREATE SCHEMA IF NOT EXISTS x_extension"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="app",
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable: AsyncEngine = create_async_engine(
        get_url(),
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
        # SQLAlchemy 2.0 AsyncConnection 은 commit 없이 블록을 빠져나가면 DDL 을
        # 롤백한다 — context.begin_transaction() 만으로는 외부 async 트랜잭션이
        # 커밋되지 않아 테이블이 사라진다. 명시적 commit 필수.
        await connection.commit()
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
