"""공유 통합 cluster가 실제로 비내구로 도는지 서버에서 확인한다 (n150 디스크 I/O 보호)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def test_shared_cluster_data_directory_is_on_tmpfs(_database_url: str) -> None:
    """설정이 빠지면 데이터가 조용히 SSD로 돌아간다 — 서버의 mount 표에서 확인한다(superuser)."""
    engine = create_async_engine(_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            data_directory = str(await connection.scalar(text("SHOW data_directory")))
            mounts = str(await connection.scalar(text("SELECT pg_read_file('/proc/mounts')")))
    finally:
        await engine.dispose()
    tmpfs_roots = [
        fields[1]
        for fields in (line.split() for line in mounts.splitlines())
        if len(fields) > 2 and fields[2] == "tmpfs"
    ]
    assert any(
        data_directory == root or data_directory.startswith(root.rstrip("/") + "/")
        for root in tmpfs_roots
        if root.startswith("/var/lib/postgresql")
    ), (data_directory, tmpfs_roots)


@pytest.mark.parametrize("knob", ["fsync", "synchronous_commit", "full_page_writes"])
async def test_shared_cluster_runs_without_durability(_database_url: str, knob: str) -> None:
    engine = create_async_engine(_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text(f"SHOW {knob}")) == "off"
    finally:
        await engine.dispose()
