"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

#: 세션 GUC 타임아웃(T-341). 요청 경로·백그라운드 워커·retention이 **단일 글로벌 엔진**을 공유하므로
#: (별도 커넥션 풀이 없다), 값은 "정상적인 배치 작업을 죽이지 않으면서 무한 대기를 막는" 쪽으로
#: 보수적으로 잡는다. 통합 테스트도 이 값을 그대로 써야 회귀를 잡을 수 있으므로
#: `tests/integration/conftest.py`가 이 상수를 가져다 쓴다 — 값을 여기서만 바꾸면 된다.
#:
#: - `lock_timeout`: 다른 트랜잭션이 쥔 락을 이 시간 넘게 기다리면 실패시킨다. T-339의 hang이
#:   여기 해당했다 — 이 값이 있었다면 그 hang은 30초 만에 에러로 끝나고 재시도할 수 있었을 것이다.
#: - `idle_in_transaction_session_timeout`: 트랜잭션을 연 채 아무것도 안 하는 세션을 끊는다.
#:   커넥션 누수나 미완결 요청이 풀을 영구히 점유하는 것을 막는다.
#: - `statement_timeout`: 개별 SQL 문 실행 시간의 상한. retention의 대량 archive/anonymize처럼
#:   합법적으로 오래 걸리는 배치가 있어 짧게 잡을 수 없다 — 폭주 쿼리만 잡는 넉넉한 backstop이다.
SESSION_TIMEOUT_SERVER_SETTINGS: dict[str, str] = {
    "lock_timeout": "30000",
    "idle_in_transaction_session_timeout": "60000",
    "statement_timeout": "600000",
}

engine = create_async_engine(
    settings.pinvi_database_url,
    pool_size=settings.pinvi_database_pool_size,
    pool_pre_ping=True,
    future=True,
    connect_args={"server_settings": SESSION_TIMEOUT_SERVER_SETTINGS},
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
