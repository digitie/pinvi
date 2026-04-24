from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from alembic import command
from app.db.base import Base
from app.db.session import build_engine

DEFAULT_DOCKER_ADMIN_DATABASE_URL = (
    "postgresql+psycopg://tripmate:tripmate_dev_password@localhost:55432/postgres"
)


def _get_admin_database_url() -> str:
    return os.environ.get("TRIPMATE_TEST_ADMIN_DATABASE_URL", DEFAULT_DOCKER_ADMIN_DATABASE_URL)


def _create_database(admin_engine: Engine, database_name: str) -> None:
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))


def _drop_database(admin_engine: Engine, database_name: str) -> None:
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))


@pytest.fixture(scope="session")
def postgres_test_database_url() -> Generator[str, None, None]:
    admin_database_url = _get_admin_database_url()
    database_name = f"tripmate_test_{uuid4().hex[:8]}"
    admin_engine = create_engine(admin_database_url, pool_pre_ping=True)

    try:
        _create_database(admin_engine, database_name)
    except OperationalError as exc:
        admin_engine.dispose()
        raise RuntimeError(
            "Docker Postgres is not reachable. Start the WSL2 Docker stack first with "
            "`docker compose -f infra/docker-compose.yml up -d`."
        ) from exc

    test_database_url = make_url(admin_database_url).set(database=database_name).render_as_string(
        hide_password=False
    )

    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_config.attributes["database_url"] = test_database_url
    alembic_config.set_main_option("sqlalchemy.url", test_database_url)
    command.upgrade(alembic_config, "head")

    try:
        yield test_database_url
    finally:
        _drop_database(admin_engine, database_name)
        admin_engine.dispose()


@pytest.fixture(scope="session")
def postgres_test_engine(postgres_test_database_url: str) -> Generator[Engine, None, None]:
    engine = build_engine(postgres_test_database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def db_session(postgres_test_engine: Engine) -> Generator[Session, None, None]:
    session_factory = sessionmaker(bind=postgres_test_engine, autoflush=False, autocommit=False)
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        table_names = [table.name for table in reversed(Base.metadata.sorted_tables)]
        if table_names:
            joined_table_names = ", ".join(table_names)
            with postgres_test_engine.begin() as connection:
                connection.execute(
                    text(f"TRUNCATE TABLE {joined_table_names} RESTART IDENTITY CASCADE")
                )
