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
    # 2026-09-21: ADR-46/070의 공용 control-plane 이전이 M05의 4-role 분리를
    # 구조적으로 깨뜨렸다 — role-catalog reset이 "target role이 어떤 database도
    # 소유하면 안 된다"를 요구하는데, 공용 instance에서는 pinvi_dagster를 app
    # role이 정당하게 소유한다. Manager 쪽(kor-travel-docker-manager PR #382)은
    # M05를 통째로 폐기하고 geo/concierge/weather와 같은 단일 scoped app role
    # 패턴으로 접었다. 0101의 `_activate_m05_migration_owner`는 그 patternol에선
    # migration_owner/migrator_login 없이도 성공해야 하는데, production에서는
    # `_managed_deployment_requires_migration_owner()`가 무조건 거부했다 — 신선
    # 설치라도 벗어날 길이 없었다(제어흐름이 raise되면 뒤 migration은 아예 안
    # 돈다). "새 migration으로 진화" 원칙이 여기서는 적용되지 않는다 — 문제가
    # 뒤 migration이 손댈 수 없는 0101 자신의 제어흐름이다. 그래서 봉인을
    # 의도적으로 깬다: single_role(PINVI_APP_DB_USER)이 설정되고 legacy
    # rebaseline이 아니면 app_role을 그대로 반환해 통과시키되, migration_owner/
    # migrator_login이 하나라도 설정됐거나 legacy면 여전히 fail-closed다 — 기존
    # M05 배포를 위한 어느 경로도 약화하지 않았다.
    #
    # 2026-09-24: 위 봉인 이후 n150에서 fresh single-role install을 실제로
    # 돌려보니 0101이 자기 transaction 안에서 "permission denied for table
    # alembic_version"으로 롤백됐다 — `upgrade()`의 fresh 분기가
    # `_grant_fresh_runtime_app_privileges` 직후 `_revoke_runtime_alembic_version_privileges`를
    # 무조건 호출했기 때문이다. ADR-46/070 단일 scoped role 배포
    # (migration_owner/migrator_login 둘 다 미설정)에서는 그 대상 role이 이
    # migration을 실행 중인 connection 자신이라, 자기 접근 권한을 스스로
    # 거둬가면 alembic이 트랜잭션 끝에 내부적으로 찍는 head UPDATE까지 막힌다.
    # 반대로 managed-but-fresh(migration_owner/migrator_login은 설정했지만
    # legacy_rebaseline은 아닌 배포, `test_0101_can_use_a_separate_nonruntime_migration_owner`가
    # 검증하는 경로)에서는 그 role이 실행 connection과 분리돼 있어 거둬가는 쪽이
    # 맞다 — 이 호출을 완전히 지우면 그 테스트가 깨진다(실제로 한 번 그렇게
    # 깨졌다). 그래서 migration_owner/migrator_login 중 하나라도 설정된 경우에만
    # 호출하도록 좁혔다. 둘 다 이 역시 뒤 migration이 손댈 수 없는 0101 자신의
    # 제어흐름이라 같은 근거로 봉인을 다시 깬다. kor-travel-docker-manager 세션
    # n150 rebuild(pinset
    # 13ebca754f9f2139c4946c0a68c3565bc38bbd1098e6240f901b8738b454bc38)에서
    # 단일 role 경로가 0100→head(20260917_0102)까지 실제로 도달함을 확인.
    "20260824_0101_m05_activation_contract.py": (
        "7dcd388f562c4a3e72b00390e05d61f8c8859c9b77d01375f098a4f9feabb2a5"
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
