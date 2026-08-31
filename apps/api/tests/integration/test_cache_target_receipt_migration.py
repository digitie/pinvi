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
async def test_active_graph_has_the_sealed_baseline_prefix(session_factory) -> None:  # type: ignore[no-untyped-def]
    """legacy history를 로드하지 않고, 봉인 기준선 0100→0101이 계보의 prefix다."""

    versions = sorted(
        path.name
        for path in (API_DIR / "alembic" / "versions").glob("*.py")
        if path.name != "__init__.py"
    )
    # exact 목록 비교는 신규 migration 추가까지 금지한다(I-10과 같은 결함의 두 번째
    # 사본 — 적대 리뷰 R1-S8). 봉인 기준선 2개가 계보의 **prefix**임은 유지하되,
    # 그 뒤의 추가는 unit 게이트(test_tvn40_migration_immutability)가 digest 불변·
    # 단일 선형 체인으로 지킨다.
    assert versions[:2] == [
        "20260824_0100_app_schema_baseline.py",
        "20260824_0101_m05_activation_contract.py",
    ]

    heads = _alembic("heads")
    assert heads.returncode == 0, heads.stderr
    head_lines = heads.stdout.strip().splitlines()
    assert len(head_lines) == 1, heads.stdout
    assert head_lines[0].endswith("(head)")
    head_revision = head_lines[0].removesuffix("(head)").strip()

    # fresh install DB는 exact 문자열이 아니라 **현재 단일 head**에 있어야 한다 —
    # 신규 migration이 추가되면 head가 전진하고, 이 대조는 그대로 유효하다.
    async with session_factory() as session:
        assert await session.scalar(
            text("SELECT version_num FROM app.alembic_version")
        ) == head_revision
