"""활성 Alembic 기준선 artifact의 무결성을 검증한다."""

from __future__ import annotations

import importlib.util
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2]


def _load(path: Path, name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_active_migration_artifacts_are_complete_and_digest_guarded() -> None:
    versions_dir = API_DIR / "alembic" / "versions"
    assert sorted(path.name for path in versions_dir.glob("*.py")) == [
        "20260824_0100_app_schema_baseline.py",
        "20260824_0101_m05_activation_contract.py",
    ]

    baseline = _load(
        versions_dir / "20260824_0100_app_schema_baseline.py",
        "pinvi_alembic_0100_test",
    )
    activation = _load(
        versions_dir / "20260824_0101_m05_activation_contract.py",
        "pinvi_alembic_0101_test",
    )
    assert baseline.revision == "20260824_0100"
    assert baseline.down_revision is None
    assert activation.revision == "20260824_0101"
    assert activation.down_revision == baseline.revision
    assert len(baseline._baseline_statements()) == baseline._BASELINE_STATEMENT_COUNT
    assert len(activation._m05_schema_statements()) == activation._M05_SCHEMA_STATEMENT_COUNT
