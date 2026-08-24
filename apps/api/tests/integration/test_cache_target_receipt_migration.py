"""새 Alembic 기준선 graph의 최소 형태를 검증한다."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

API_DIR = Path(__file__).resolve().parents[2]


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env=dict(os.environ),
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.asyncio
async def test_active_graph_is_the_two_revision_baseline(session_factory) -> None:  # type: ignore[no-untyped-def]
    """legacy history를 로드하지 않고 0100→0101만 fresh install head가 된다."""

    versions = sorted(
        path.name
        for path in (API_DIR / "alembic" / "versions").glob("*.py")
        if path.name != "__init__.py"
    )
    assert versions == [
        "20260824_0100_app_schema_baseline.py",
        "20260824_0101_m05_activation_contract.py",
    ]

    heads = _alembic("heads")
    assert heads.returncode == 0, heads.stderr
    assert heads.stdout.strip() == "20260824_0101 (head)"

    async with session_factory() as session:
        assert await session.scalar(text("SELECT version_num FROM app.alembic_version")) == (
            "20260824_0101"
        )
