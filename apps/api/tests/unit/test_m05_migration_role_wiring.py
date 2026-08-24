"""M05 receipt migration의 one-shot 역할 경계를 정적으로 고정한다."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_compose_keeps_runtime_and_migrator_role_inputs_separate() -> None:
    compose = (ROOT / "infra" / "docker-compose.app.yml").read_text(encoding="utf-8")
    runtime_block = compose.split("  app-api:", maxsplit=1)[1].split(
        "  # Explicit one-shot only:", maxsplit=1
    )[0]
    role_bootstrap_block = compose.split("  app-db-runtime-role:", maxsplit=1)[1].split(
        "  app-rustfs:", maxsplit=1
    )[0]
    migrator_block = compose.split("  app-migrator:", maxsplit=1)[1].split(
        "  app-web:", maxsplit=1
    )[0]

    assert "\n      PINVI_MIGRATOR_DATABASE_URL:" not in runtime_block
    assert "\n      PINVI_MIGRATION_OWNER:" not in runtime_block
    for value in (
        "PINVI_APP_SCHEMA_OWNER",
        "PINVI_MIGRATION_OWNER",
        "PINVI_MIGRATOR_DB_USER",
        "PINVI_MIGRATOR_DB_PASSWORD",
        "PINVI_M05_LEGACY_REBASELINE",
    ):
        assert value in role_bootstrap_block
    assert 'PINVI_MIGRATOR_DISABLE_LOGIN: "1"' in role_bootstrap_block
    assert 'PINVI_M05_LEGACY_REBASELINE: "0"' in role_bootstrap_block
    assert "postgresql+asyncpg://pinvi_migrator:" in migrator_block
    assert "PINVI_MIGRATION_OWNER" in migrator_block
    assert "PINVI_MIGRATOR_DB_USER" in migrator_block
    assert "PINVI_ENVIRONMENT: ${PINVI_ENVIRONMENT:-smoke}" in migrator_block
    legacy_migrator_block = compose.split("  app-legacy-rebaseline-migrator:", maxsplit=1)[1].split(
        "  app-web:", maxsplit=1
    )[0]
    assert "profiles: [legacy-rebaseline]" in legacy_migrator_block
    assert "PINVI_LEGACY_REBASELINE_DATABASE_URL" in legacy_migrator_block
    assert "PINVI_MIGRATOR_DB_USER" in legacy_migrator_block
    assert 'PINVI_M05_LEGACY_REBASELINE: "1"' in legacy_migrator_block
    assert 'user: "0:0"' in legacy_migrator_block
    assert "PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH" in legacy_migrator_block


def test_bootstrap_requires_noninheriting_set_role_and_seals_login() -> None:
    bootstrap = (ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh").read_text(
        encoding="utf-8"
    )

    assert "PINVI_MIGRATOR_DISABLE_LOGIN" in bootstrap
    assert "WITH INHERIT FALSE, SET TRUE" in bootstrap
    assert "REVOKE CONNECT ON DATABASE" in bootstrap
    assert "NOT has_database_privilege(owner.oid, current_database(), 'CONNECT')" in bootstrap
    assert "NOT membership.admin_option" in bootstrap
    assert "NOT membership.inherit_option" in bootstrap
    assert "membership.set_option" in bootstrap
    assert "PINVI_M05_LEGACY_REBASELINE=1 root-only one-shot" in bootstrap
    assert 'PINVI_MIGRATOR_DISABLE_LOGIN="${PINVI_MIGRATOR_DISABLE_LOGIN:-1}"' in bootstrap
    assert "REVOKE CONNECT ON DATABASE" in bootstrap
    assert "pg_terminate_backend(activity.pid, 5000)" in bootstrap
    assert "FROM pg_stat_activity activity" in bootstrap
    assert "close the one-shot credential before any" in bootstrap
    assert "OR membership.roleid = runtime.oid" in bootstrap
    assert "REVOKE ALL ON FUNCTION x_extension.digest(bytea, text) FROM PUBLIC;" in bootstrap
    assert "GRANT EXECUTE ON FUNCTION x_extension.digest(bytea, text)" in bootstrap
    assert "WHERE membership.roleid = owner.oid" in bootstrap
    assert "WHERE membership.roleid = migrator.oid" in bootstrap


def test_0101_switches_only_m05_objects_and_restores_app_owner_for_versioning() -> None:
    migration = (
        ROOT / "apps" / "api" / "alembic" / "versions" / "20260824_0101_m05_activation_contract.py"
    ).read_text(encoding="utf-8")

    activation = migration.index("app_owner = _activate_m05_migration_owner(bind)")
    ops_schema = migration.index('op.execute("CREATE SCHEMA IF NOT EXISTS ops")')
    assertion = migration.index("_assert_m05_acl(bind)")
    restore = migration.index("_restore_app_owner(app_owner)")

    assert "SET LOCAL ROLE" in migration
    assert activation < ops_schema < assertion < restore
    assert migration.index("_advance_boundary_contract()") < activation
    assert migration.index("_replace_admin_audit_guard()") < activation
    assert "_managed_deployment_requires_migration_owner" in migration
    assert "_configured_migrator_login" in migration
    assert "0101 managed migration requires migration and migrator roles" in migration
    assert "membership.roleid = (SELECT oid FROM migration_role)" in migration
    assert "_assert_legacy_rebaseline_handoff(bind)" in migration
    assert "PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH" in migration
    upgrade = migration[migration.index("def upgrade()") :]
    assert upgrade.index("_assert_legacy_rebaseline_handoff(bind)") < upgrade.index(
        "_advance_boundary_contract()"
    )


def test_migration_wrappers_open_only_for_the_one_shot_and_seal_afterward() -> None:
    for path in (ROOT / "scripts" / "docker-app.sh", ROOT / "scripts" / "deploy-node.sh"):
        source = path.read_text(encoding="utf-8")
        migration = source[source.index("migrate() {") :]
        assert "m05_legacy_rebaseline_profile()" in source
        assert "prepare_migrator_login()" in source
        assert "seal_migrator_login()" in source
        assert "PINVI_MIGRATOR_DISABLE_LOGIN=1" in source
        assert "app-legacy-rebaseline-migrator" in source
        assert "--profile legacy-rebaseline" in source
        assert "legacy_rebaseline_receipt_file()" in source
        assert "PINVI_M05_LEGACY_REBASELINE_RECEIPT_HOST_PATH" in source
        assert "legacy rebaseline receipt must be root-owned mode 0600" in source
        assert 'runner_user="0:0"' in source
        assert "legacy-rebaseline-receipt.json:ro" in source
        assert "run --rm --no-deps" in source
        assert 'if ! prepare_migrator_login "$legacy_rebaseline"; then' in migration
        assert "migrator preparation failed; sealing the one-shot login" in migration
        assert (
            migration.index("prepare_migrator_login")
            < migration.index("run_admin_bootstrap")
            < migration.rindex("seal_migrator_login")
        )
