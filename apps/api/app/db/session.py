from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    return create_engine(url, pool_pre_ping=True)


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
