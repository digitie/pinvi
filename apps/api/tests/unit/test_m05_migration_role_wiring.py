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
    assert "postgresql+asyncpg://pinvi_migrator:" in migrator_block
    assert "PINVI_MIGRATION_OWNER" in migrator_block


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


def test_migration_wrappers_seal_the_one_shot_login_after_success() -> None:
    for path in (ROOT / "scripts" / "docker-app.sh", ROOT / "scripts" / "deploy-node.sh"):
        source = path.read_text(encoding="utf-8")
        assert "seal_migrator_login()" in source
        assert "PINVI_MIGRATOR_DISABLE_LOGIN=1" in source
        assert source.index("app-migrator pinvi-admin-bootstrap") < source.rindex(
            "seal_migrator_login"
        )
