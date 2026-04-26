from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

POSTGRES_SESSION_TIMEZONE = "Asia/Seoul"


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    db_engine = create_engine(url, pool_pre_ping=True)
    configure_engine_timezone(db_engine)
    return db_engine


def configure_engine_timezone(db_engine: Engine) -> None:
    if db_engine.dialect.name != "postgresql":
        return

    @event.listens_for(db_engine, "connect")
    def set_postgres_session_timezone(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET TIME ZONE '{POSTGRES_SESSION_TIMEZONE}'")
        finally:
            cursor.close()


def build_session_factory(
    *,
    database_url: str | None = None,
    engine: Engine | None = None,
) -> sessionmaker[Session]:
    db_engine = engine or build_engine(database_url)
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


engine = build_engine()
SessionLocal = build_session_factory(engine=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
