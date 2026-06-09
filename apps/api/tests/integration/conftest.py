"""통합 테스트 harness — PostGIS testcontainer + 실제 Alembic 마이그레이션.

`docs/conventions/testing.md`. Sprint 2 DoD: `pytest tests/integration -q`.

전략:
- PostGIS 컨테이너 1개 (session scope) — 실제 `app` schema 를 alembic upgrade head
  로 구성. metadata.create_all 이 아니라 마이그레이션을 돌려야 COLLATE "C" UNIQUE
  인덱스 + num_nonnulls CHECK + 트리거까지 검증된다.
- **engine/sessionmaker 는 함수 스코프**. pytest-asyncio 가 테스트마다 새 이벤트
  루프를 쓰므로(loop_scope=function), 엔진을 세션 스코프로 공유하면
  "Future attached to a different loop" 가 난다. 매 테스트에서 엔진을 새로 만들고
  app 의 module-global(engine / 미들웨어 factory)을 그 엔진으로 패치한다.
- 테스트마다 app schema 테이블 TRUNCATE 로 격리.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

API_DIR = Path(__file__).resolve().parents[2]


def _require_docker() -> None:
    try:
        import docker  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("docker SDK 미설치 — 통합 테스트 skip")


@pytest.fixture(autouse=True)
def _clear_feature_cache() -> Iterator[None]:
    """프로세스 로컬 feature 캐시(T-146/D-26)를 테스트 간 격리."""
    from app.services.feature_cache import feature_cache

    feature_cache.clear()
    yield
    feature_cache.clear()


@pytest.fixture(scope="session")
def _database_url() -> Iterator[str]:
    """PostGIS 컨테이너 기동 + alembic upgrade head (1회) → asyncpg URL 반환."""
    _require_docker()
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer(
        "postgis/postgis:16-3.5-alpine",
        username="tripmate",
        password="tripmate_test",
        dbname="tripmate_test",
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        url = f"postgresql+asyncpg://tripmate:tripmate_test@{host}:{port}/tripmate_test"

        # 마이그레이션은 subprocess 로 (자체 이벤트 루프, CI 쉘 스텝과 동일 경로).
        env = dict(os.environ)
        env["TRIPMATE_DATABASE_URL"] = url
        result = subprocess.run(
            ["alembic", "upgrade", "head"],  # noqa: S607 — venv PATH 의 alembic (테스트 전용)
            cwd=str(API_DIR),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"alembic upgrade 실패:\n{result.stdout}\n{result.stderr}")

        yield url
    finally:
        container.stop()


@pytest_asyncio.fixture
async def session_factory(_database_url: str):  # type: ignore[no-untyped-def]
    """테스트별 엔진/세션팩토리 — 현재 이벤트 루프에 바인딩 + app 글로벌 패치."""
    from app.core.config import settings

    settings.tripmate_database_url = _database_url

    # NullPool: 연결을 풀에 재사용하지 않는다. 테스트에서 미들웨어 세션 + 라우트
    # 세션이 같은 풀 커넥션을 공유하다 "another operation is in progress" 가 나는
    # 것을 방지(매 세션 새 커넥션).
    engine = create_async_engine(_database_url, poolclass=NullPool, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # app 의 module-global 들을 이 엔진으로 교체 (deps.get_db + 미들웨어가 사용)
    import app.db.session as db_session
    import app.middleware.location_audit as loc_audit

    db_session.engine = engine
    db_session.async_session_factory = factory
    loc_audit.async_session_factory = factory

    # 테스트 시작 전 app schema 비우기 (alembic_version 제외)
    async with engine.begin() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'app' AND tablename <> 'alembic_version'"
            )
        )
        tables = [r[0] for r in rows]
        if tables:
            joined = ", ".join(f'app."{t}"' for t in tables)
            await conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    """session_factory 에 의존 → app 글로벌이 패치된 뒤 app import."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def verified_user(session_factory):  # type: ignore[no-untyped-def]
    """이메일 인증 완료된 사용자 생성 → (user_id, email) 반환."""
    from app.models.user import User

    email = f"user_{uuid.uuid4().hex[:8]}@tripmate.test"
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash=None,
            nickname="테스트",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.user_id), email


@pytest.fixture
def auth_cookies():  # type: ignore[no-untyped-def]
    """user_id → access cookie dict 생성 helper."""
    from app.core.security import create_access_token

    def _make(user_id: str) -> dict[str, str]:
        return {"tripmate_access": create_access_token(subject=user_id)}

    return _make
