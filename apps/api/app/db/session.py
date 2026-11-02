"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, SessionTransaction

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


async def release_read_connection(db: AsyncSession) -> None:
    """외부 HTTP 호출 전에 읽기 트랜잭션을 끝내 커넥션을 풀에 돌려준다.

    2026-11-02 점검: 요청 세션은 첫 쿼리(인증 조회)부터 요청이 끝날 때까지 트랜잭션을 연 채
    커넥션을 쥐었다. 그 사이 Map·weather 호출(수 초~수십 초)이 끼면 풀 커넥션이
    idle-in-transaction으로 묶여, 동시 요청이 늘면 다른 엔드포인트가 풀 대기(30s)에 걸린다.
    `expire_on_commit=False`라 이미 읽은 객체는 그대로 쓰고, 다음 쿼리는 새 트랜잭션을 연다.

    ORM에 반영 전 변경(new/dirty/deleted)이나 이 트랜잭션에서 이미 flush된 쓰기가 있으면 아무것도
    하지 않는다 — 호출자의 커밋 시점을 바꾸지 않는다(flush는 `_mark_flushed_writes`가 표시한다).
    ORM을 거치지 않은 쓰기(`db.execute(insert(...))`)는 보이지 않으므로 **읽기 경로에서만** 부른다.
    """
    if not db.in_transaction() or db.new or db.dirty or db.deleted:
        return
    if db.info.get(_FLUSHED_WRITES):
        return
    await db.commit()


_FLUSHED_WRITES = "pinvi_flushed_writes"


@event.listens_for(Session, "after_flush")
def _mark_flushed_writes(session: Session, _flush_context: object) -> None:
    session.info[_FLUSHED_WRITES] = True


@event.listens_for(Session, "after_transaction_end")
def _clear_flushed_writes(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        session.info.pop(_FLUSHED_WRITES, None)
