"""SQLAlchemy 2 declarative base + metadata.

`app` schema에만 한정. `feature` / `provider_sync`는 라이브러리 (ADR-003).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(schema="app", naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


# 모델 import — Alembic autogenerate에 필요.
# (각 모듈이 Base를 상속하면 metadata에 자동 등록됨)
from app.models import (  # noqa: E402,F401
    api_call_log,
    attachment,
    audit,
    comment,
    companion,
    curated_plan,
    email_queue,
    kasi,
    oauth_identity,
    poi,
    security,
    session,
    share_link,
    trip,
    trip_day,
    user,
    user_consent,
    user_email_verification,
)
