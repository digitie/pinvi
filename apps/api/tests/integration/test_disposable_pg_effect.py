"""공유 통합 cluster가 실제로 비내구로 도는지 서버에서 확인한다 (n150 디스크 I/O 보호)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


@pytest.mark.parametrize("knob", ["fsync", "synchronous_commit", "full_page_writes"])
async def test_shared_cluster_runs_without_durability(_database_url: str, knob: str) -> None:
    engine = create_async_engine(_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text(f"SHOW {knob}")) == "off"
    finally:
        await engine.dispose()
