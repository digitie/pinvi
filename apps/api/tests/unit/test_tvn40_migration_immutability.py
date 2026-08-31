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


#: 봉인된 기준선 artifact와 그 sha256. **기존 파일의 불변**이 이 테스트가 지키는
#: 성질이고, 종전의 exact 파일 목록 비교는 그 성질에 더해 **신규 migration 추가까지**
#: 금지하고 있었다 — T-349(신규 migration이 필요한 태스크)가 이 한 줄 때문에 진행
#: 불가로 표시됐다(57cf93da). 목록 동등 대신 digest 불변 + 계보 무결로 바꾼다
#: (kor-travel-map `docs/reports/map-stall-root-cause-2026-08-31.md` §3 I-10,
#: 적대 검증 CONFIRMED — "국소 테스트 결함 수정"으로 분류).
_SEALED_BASELINE_SHA256 = {
    "20260824_0100_app_schema_baseline.py": (
        "8045687ffbb2d8a582ffb9e2121675328947e8514f5472e91a9f306573b32cb7"
    ),
    "20260824_0101_m05_activation_contract.py": (
        "7ab664705a9a25f11f615a35b34408c231c03a4c09ae38fff5f906ec2e220919"
    ),
}


def test_sealed_baseline_artifacts_are_immutable_and_lineage_is_linear() -> None:
    import hashlib

    versions_dir = API_DIR / "alembic" / "versions"
    present = {path.name: path for path in versions_dir.glob("*.py") if path.name != "__init__.py"}

    # ① 봉인 artifact는 존재해야 하고 바이트가 불변이어야 한다. 종전 테스트는 목록만
    #    보고 **내용은 보지 않았다** — 이름이 같으면 내용을 바꿔도 통과했다.
    #    (파일이 없으면 KeyError가 아니라 "missing"으로 보고한다 — R1-S8.)
    drifted = [
        f"{name}: observed="
        + (
            hashlib.sha256(present[name].read_bytes()).hexdigest()[:12] + "…"
            if name in present
            else "missing"
        )
        for name, sealed in _SEALED_BASELINE_SHA256.items()
        if name not in present or hashlib.sha256(present[name].read_bytes()).hexdigest() != sealed
    ]
    assert not drifted, (
        "봉인된 기준선 migration의 바이트가 변했다 — 기준선은 수정이 아니라 새 "
        f"migration으로만 진화한다: {drifted}"
    )

    # ② 신규 migration은 허용하되 계보는 단일 선형 체인이어야 한다.
    revisions: dict[str, str | None] = {}
    for name, path in sorted(present.items()):
        module = _load(path, f"pinvi_alembic_probe_{name.split('_', 1)[0]}")
        # 같은 revision을 가진 파일 두 개는 dict에서 조용히 덮인다 — 충돌은
        # 계보 검사가 아니라 여기서 즉시 잡는다(R1-S8).
        assert module.revision not in revisions, f"revision 충돌: {module.revision} ({name})"
        revisions[module.revision] = module.down_revision
    heads = set(revisions) - {d for d in revisions.values() if d is not None}
    roots = [r for r, d in revisions.items() if d is None]
    dangling = [f"{r} → {d}" for r, d in revisions.items() if d is not None and d not in revisions]

    assert roots == ["20260824_0100"], f"root는 봉인 기준선 하나여야 한다: {roots}"
    assert len(heads) == 1, f"migration 계보가 분기했다: {sorted(heads)}"
    assert not dangling, f"끊어진 down_revision: {dangling}"

    baseline = _load(
        versions_dir / "20260824_0100_app_schema_baseline.py",
        "pinvi_alembic_0100_test",
    )
    activation = _load(
        versions_dir / "20260824_0101_m05_activation_contract.py",
        "pinvi_alembic_0101_test",
    )
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
        migration = runner[
            runner.index("migrate_under_lifecycle_lock() {") : runner.index("migrate() {")
        ]
        wrapper = runner[
            runner.index("migrate() {") : runner.index("bootstrap_credential_file() {")
        ]
        assert migration.index("drain_runtime_writers") < migration.index("run_admin_bootstrap")
        assert (
            wrapper.index("acquire_migrator_lifecycle_lock")
            < wrapper.index("migrate_under_lifecycle_lock")
            < wrapper.index("release_migrator_lifecycle_lock")
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
