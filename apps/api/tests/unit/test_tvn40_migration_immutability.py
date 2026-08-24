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


def test_0101_consent_backfill_and_deploy_runners_drain_legacy_writers() -> None:
    """구 runtime write가 backfill snapshot 뒤에 event ledger에서 빠지지 않게 막는다."""

    root = API_DIR.parents[1]
    migration = (
        API_DIR / "alembic" / "versions" / "20260824_0101_m05_activation_contract.py"
    ).read_text(encoding="utf-8")
    consent_history = migration[
        migration.index("def _install_user_consent_event_history()") : migration.index(
            "def _replace_admin_audit_guard()"
        )
    ]
    assert "LOCK TABLE app.user_consents IN SHARE ROW EXCLUSIVE MODE" in consent_history

    docker_app = (root / "scripts" / "docker-app.sh").read_text(encoding="utf-8")
    deploy = (root / "scripts" / "deploy-node.sh").read_text(encoding="utf-8")
    for runner in (docker_app, deploy):
        migrate = runner[
            runner.index("migrate() {") : runner.index("bootstrap_credential_file() {")
        ]
        assert migrate.index("drain_runtime_writers") < migrate.index(
            "app-migrator pinvi-admin-bootstrap"
        )
        assert "compose stop app-api" in runner

    assert "compose --profile etl stop app-dagster" in deploy


def test_strict_restore_accepts_legacy_manifest_without_created_at() -> None:
    """rebaseline 증명은 새 timestamp를 요구해도 기존 trusted restore는 깨지지 않는다."""

    root = API_DIR.parents[1]
    for name in ("restore-db.sh", "restore-hotswap.sh"):
        runner = (root / "scripts" / name).read_text(encoding="utf-8")
        assert "source_port; do" in runner
        assert "source_port created_at; do" not in runner
        assert 'if [[ -v "manifest[created_at]"' in runner
