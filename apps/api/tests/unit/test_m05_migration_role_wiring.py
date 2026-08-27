"""M05 receipt migration의 one-shot 역할 경계를 정적으로 고정한다."""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_compose_keeps_runtime_and_migrator_role_inputs_separate() -> None:
    compose = (ROOT / "infra" / "docker-compose.app.yml").read_text(encoding="utf-8")
    postgres_block = compose.split("  app-postgres:", maxsplit=1)[1].split(
        "  # Root bootstrap", maxsplit=1
    )[0]
    assert "app-postgres:/var/lib/postgresql/data" in postgres_block
    assert "\n  app-postgres:\n" in compose.rsplit("volumes:", maxsplit=1)[1]
    rustfs_init_block = compose.split("  app-rustfs-init:", maxsplit=1)[1].split(
        "  app-api:", maxsplit=1
    )[0]
    assert "set -eu" in rustfs_init_block
    assert "mc ls local/pinvi-media" in rustfs_init_block
    assert "mc mb -p local/pinvi-media" in rustfs_init_block
    assert "|| true" not in rustfs_init_block
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
    assert "postgresql+asyncpg://${PINVI_MIGRATOR_DB_USER:-pinvi_migrator}:" in migrator_block
    assert "PINVI_MIGRATOR_DATABASE_URL" not in migrator_block
    assert "PINVI_APP_DB_USER: ${PINVI_APP_DB_USER:-pinvi_app}" in migrator_block
    assert "PINVI_MIGRATION_OWNER" in migrator_block
    assert "PINVI_MIGRATOR_DB_USER" in migrator_block
    assert "PINVI_ENVIRONMENT: ${PINVI_ENVIRONMENT:-smoke}" in migrator_block
    legacy_migrator_block = compose.split("  app-legacy-rebaseline-migrator:", maxsplit=1)[1].split(
        "  app-web:", maxsplit=1
    )[0]
    assert "profiles: [legacy-rebaseline]" in legacy_migrator_block
    assert (
        "PINVI_DATABASE_URL: postgresql+asyncpg://invalid:invalid@app-postgres:5432/pinvi"
        in legacy_migrator_block
    )
    assert "PINVI_LEGACY_REBASELINE_DATABASE_URL" not in legacy_migrator_block
    assert "PINVI_APP_DB_USER" in legacy_migrator_block
    assert "PINVI_MIGRATOR_DB_USER" in legacy_migrator_block
    assert 'PINVI_M05_LEGACY_REBASELINE: "1"' in legacy_migrator_block
    assert 'user: "0:0"' in legacy_migrator_block
    assert "PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH" in legacy_migrator_block


def test_bootstrap_requires_noninheriting_set_role_and_seals_login() -> None:
    bootstrap = (ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh").read_text(
        encoding="utf-8"
    )

    assert "PINVI_MIGRATOR_DISABLE_LOGIN" in bootstrap
    assert "PINVI_ROLE_TOPOLOGY_VERIFY_ONLY" in bootstrap
    assert "evaluate_role_topology()" in bootstrap
    assert "run_sealed_role_topology_verifier()" in bootstrap
    assert "BEGIN READ ONLY;" in bootstrap
    assert '"schema":"pinvi.role-topology-diagnostic.v1"' in bootstrap
    assert "migrator_sealed" in bootstrap
    assert "migrator_membership_setting" in bootstrap
    verifier = bootstrap[
        bootstrap.index("evaluate_role_topology()") : bootstrap.index("reset_fresh_role_catalog()")
    ]
    for mutation in (
        "ALTER ",
        "CREATE ",
        "GRANT ",
        "REVOKE ",
        "DROP ",
        "pg_terminate_backend",
        "\\gexec",
    ):
        assert mutation not in verifier
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
    assert "이전 backend는 계속 살아 있을 수 있다" in bootstrap
    assert "세션 종료까지 확인해" in bootstrap
    assert "seal_migrator_on_failure()" in bootstrap
    assert "trap 'seal_migrator_on_failure' EXIT" in bootstrap
    assert "OR membership.roleid = runtime.oid" in bootstrap
    assert "FROM pg_operator operator_row" in bootstrap
    assert "FROM pg_collation collation" in bootstrap
    assert "FROM pg_extension extension" in bootstrap
    assert 'role_topology_safe="$(evaluate_role_topology normal)"' in bootstrap
    assert '--set="topology_output=${topology_output}"' in bootstrap
    assert "grep -E" not in verifier
    assert "REVOKE ALL ON FUNCTION x_extension.digest(bytea, text) FROM PUBLIC;" in bootstrap
    assert "GRANT EXECUTE ON FUNCTION x_extension.digest(bytea, text)" in bootstrap
    assert "WHERE membership.roleid = owner.oid" in bootstrap
    assert "WHERE membership.roleid = migrator.oid" in bootstrap
    assert "CREATE SCHEMA IF NOT EXISTS ops AUTHORIZATION" in bootstrap
    assert (
        'GRANT USAGE ON SCHEMA pinvi_internal TO :"schema_owner", :"migration_owner"' in bootstrap
    )
    assert "0101이 catalog fingerprint·handoff를 완료한 뒤 app runtime 권한" in bootstrap
    assert "이미 적용된 0101을 재실행하지 않는다" in bootstrap
    assert "SELECT (to_regclass('app.alembic_version') IS NOT NULL)::text;" in bootstrap
    assert 'if [ "${alembic_version_table_exists}" = "true" ]; then' in bootstrap
    assert 'if [ "${applied_revision}" = "20260824_0101" ]; then' in bootstrap
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app" in bootstrap
    assert 'REVOKE ALL PRIVILEGES ON TABLE app.alembic_version FROM :"app_role";' in bootstrap
    assert 'GRANT SELECT ON TABLE app.alembic_version TO :"app_role";' in bootstrap
    assert 'ALTER DEFAULT PRIVILEGES FOR ROLE :"schema_owner" IN SCHEMA app' in bootstrap
    m05_acl_repair = bootstrap[
        bootstrap.index("# Alembic은 이미 적용된 0101을 재실행하지 않는다") :
    ]
    assert 'SET LOCAL ROLE :"schema_owner";' not in m05_acl_repair
    assert "pinvi_internal.acquire_fresh_0101_database_fence()" in bootstrap
    assert 'GRANT CREATE ON DATABASE :"database_name" TO :"schema_owner";' in bootstrap
    assert (
        'GRANT CREATE ON DATABASE :"database_name" TO :"schema_owner", :"migration_owner";'
        not in bootstrap
    )


def test_fresh_role_catalog_reset_is_narrow_and_preflighted() -> None:
    bootstrap = (ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh").read_text(
        encoding="utf-8"
    )
    reset = bootstrap[
        bootstrap.index("reset_fresh_role_catalog()") : bootstrap.index("seal_migrator_login()")
    ]

    assert 'PINVI_ROLE_CATALOG_RESET_ONLY="${PINVI_ROLE_CATALOG_RESET_ONLY:-0}"' in bootstrap
    assert "role topology verification and catalog reset cannot run together" in bootstrap
    assert "fresh PinVi role catalog reset has invalid lifecycle input" in reset
    assert "fresh PinVi role catalog reset could not prove an isolated target" in reset
    assert "BEGIN;" in reset
    assert "foreign_membership" in reset
    assert "foreign_database_owner" in reset
    assert "foreign_role_setting" in reset
    assert "foreign_shared_dependency" in reset
    assert "foreign_user_namespace_object" in reset
    assert "pg_shdepend" in reset
    assert "LOCK TABLE pg_catalog.pg_authid, pg_catalog.pg_auth_members" in reset
    assert "pg_db_role_setting" in reset
    assert "pg_namespace" in reset
    assert "pg_depend" in reset
    assert "complete namespace-scoped object inventory" in reset
    assert "PINVI_ROLE_CATALOG_RESET_PERMIT_FILE" in reset
    assert "pinvi-role-catalog-reset-v1" in reset
    assert "0:0:600" in reset
    assert "pg_control_system" in reset
    assert "membership.grantor" not in reset
    assert "target 네 role 내부" in reset
    assert "target_identity_invalid" in reset
    assert "foreign_namespace_object" in reset
    assert "\\gset" in reset
    assert "\\echo :reset_class" in reset
    assert "DROP ROLE IF EXISTS" in reset
    assert "DROP OWNED" not in reset
    assert "REASSIGN OWNED" not in reset
    assert "2>/dev/null" in reset
    assert ">/dev/null 2>&1" not in reset


def test_bootstrap_only_accepts_the_declared_postgres_endpoints(tmp_path: Path) -> None:
    bootstrap = (ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh").read_text(
        encoding="utf-8"
    )

    assert 'PINVI_DB_HOST="${PINVI_DB_HOST:-app-postgres}"' in bootstrap
    assert 'PINVI_DB_PORT="${PINVI_DB_PORT:-5432}"' in bootstrap
    assert "app-postgres:5432|127.0.0.1:12800" in bootstrap
    assert "must name an approved PostgreSQL endpoint" in bootstrap
    assert "PGHOSTADDR" in bootstrap
    assert '--host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}"' in bootstrap
    assert "--host=app-postgres" not in bootstrap

    required_environment = {
        **os.environ,
        "POSTGRES_USER": "pinvi_owner",
        "POSTGRES_PASSWORD": "test-root-password",
        "POSTGRES_DB": "pinvi",
        "PINVI_APP_DB_USER": "pinvi_app",
        "PINVI_APP_DB_PASSWORD": "test-app-password",
        "PINVI_APP_SCHEMA_OWNER": "pinvi_app_owner",
        "PINVI_MIGRATION_OWNER": "pinvi_migration_owner",
        "PINVI_MIGRATOR_DB_USER": "pinvi_migrator",
        "PINVI_MIGRATOR_DB_PASSWORD": "test-migrator-password",
    }
    shell = shutil.which("sh")
    assert shell is not None
    for override in (
        {"PINVI_DB_HOST": "db.example.test"},
        {"PINVI_DB_HOST": "127.0.0.1", "PINVI_DB_PORT": "5432"},
        {"PINVI_DB_HOST": "app-postgres", "PINVI_DB_PORT": "12800"},
        {"PINVI_DB_PORT": "0"},
        {"PINVI_DB_PORT": "9" * 128},
    ):
        result = subprocess.run(  # noqa: S603 -- fixed repository script under test
            [shell, str(ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh")],
            check=False,
            capture_output=True,
            text=True,
            env={**required_environment, **override},
        )
        assert result.returncode == 2
        assert "must name an approved PostgreSQL endpoint" in result.stderr

    fake_psql = tmp_path / "psql"
    fake_psql.write_text(
        "#!/bin/sh\n"
        'if [ -n "${PGHOSTADDR:-}" ]; then\n'
        "  exit 96\n"
        "fi\n"
        'case " $* " in\n'
        "  *topology_output=diagnostic*) printf '%s\\n' \"${PINVI_TEST_TOPOLOGY_RESULT:-canonical|}\" ;;\n"
        "  *topology_output=normal*) printf 't\\n' ;;\n"
        "  *\" --tuples-only \"*) printf 't\\n' ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_psql.chmod(0o700)
    for host, port in (("app-postgres", "5432"), ("127.0.0.1", "12800")):
        result = subprocess.run(  # noqa: S603 -- fixed repository script under test
            [shell, str(ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh")],
            check=False,
            capture_output=True,
            text=True,
            env={
                **required_environment,
                "PATH": f"{tmp_path}:{required_environment['PATH']}",
                "PGHOSTADDR": "127.0.0.2",
                "PINVI_DB_HOST": host,
                "PINVI_DB_PORT": port,
            },
        )
        assert result.returncode == 0, result.stderr

    verifier = subprocess.run(  # noqa: S603 -- fixed repository script under test
        [shell, str(ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh")],
        check=False,
        capture_output=True,
        text=True,
        env={
            **required_environment,
            "PATH": f"{tmp_path}:{required_environment['PATH']}",
            "PGHOSTADDR": "127.0.0.2",
            "PINVI_ROLE_TOPOLOGY_VERIFY_ONLY": "1",
        },
    )
    assert verifier.returncode == 0
    assert verifier.stderr == ""
    assert verifier.stdout.strip() == (
        '{"schema":"pinvi.role-topology-diagnostic.v1","status":"canonical",'
        '"mode":"sealed","reasons":[]}'
    )

    accepted_noncanonical = subprocess.run(  # noqa: S603 -- fixed repository script under test
        [shell, str(ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh")],
        check=False,
        capture_output=True,
        text=True,
        env={
            **required_environment,
            "PATH": f"{tmp_path}:{required_environment['PATH']}",
            "PINVI_ROLE_TOPOLOGY_VERIFY_ONLY": "1",
            "PINVI_TEST_TOPOLOGY_RESULT": "noncanonical|bootstrap_catalog,migrator_membership_setting",
        },
    )
    assert accepted_noncanonical.returncode == 0
    assert accepted_noncanonical.stderr == ""
    assert accepted_noncanonical.stdout.strip() == (
        '{"schema":"pinvi.role-topology-diagnostic.v1","status":"noncanonical",'
        '"mode":"sealed","reasons":["bootstrap_catalog","migrator_membership_setting"]}'
    )

    for malformed_result in (
        "noncanonical|",
        "noncanonical|unknown_reason",
        "noncanonical|runtime_role,runtime_role",
        "noncanonical|runtime_role,bootstrap_catalog",
        "canonical|\nnoncanonical|runtime_role",
        "canonical|unexpected",
    ):
        malformed_verifier = subprocess.run(  # noqa: S603 -- fixed repository script under test
            [shell, str(ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh")],
            check=False,
            capture_output=True,
            text=True,
            env={
                **required_environment,
                "PATH": f"{tmp_path}:{required_environment['PATH']}",
                "PINVI_ROLE_TOPOLOGY_VERIFY_ONLY": "1",
                "PINVI_TEST_TOPOLOGY_RESULT": malformed_result,
            },
        )
        assert malformed_verifier.returncode == 0
        assert malformed_verifier.stderr == ""
        assert malformed_verifier.stdout.strip() == (
            '{"schema":"pinvi.role-topology-diagnostic.v1","status":"unavailable",'
            '"mode":"sealed","reasons":["verification_unavailable"]}'
        )

    invalid_verifier = subprocess.run(  # noqa: S603 -- fixed repository script under test
        [shell, str(ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh")],
        check=False,
        capture_output=True,
        text=True,
        env={
            **required_environment,
            "PATH": f"{tmp_path}:{required_environment['PATH']}",
            "PINVI_ROLE_TOPOLOGY_VERIFY_ONLY": "1",
            "PINVI_DB_HOST": "db.example.test",
        },
    )
    assert invalid_verifier.returncode == 0
    assert invalid_verifier.stderr == ""
    assert invalid_verifier.stdout.strip() == (
        '{"schema":"pinvi.role-topology-diagnostic.v1","status":"invalid",'
        '"mode":"sealed","reasons":["input_invalid"]}'
    )


def test_0101_switches_only_m05_objects_and_restores_app_owner_for_versioning() -> None:
    migration = (
        ROOT / "apps" / "api" / "alembic" / "versions" / "20260824_0101_m05_activation_contract.py"
    ).read_text(encoding="utf-8")

    activation = migration.index("app_owner = _activate_m05_migration_owner(bind)")
    ops_schema = migration.index("statement.strip() == 'CREATE SCHEMA IF NOT EXISTS \"ops\"'")
    assertion = migration.index("_assert_m05_acl(bind)")
    restore = migration.index("_restore_app_owner(app_owner)")

    assert "SET LOCAL ROLE" in migration
    assert activation < ops_schema < assertion < restore
    assert migration.index("_advance_boundary_contract()") < activation
    assert migration.index("_replace_admin_audit_guard()") < activation
    assert "_managed_deployment_requires_migration_owner" in migration
    assert "_configured_migrator_login" in migration
    assert "_configured_app_runtime_role" in migration
    assert "0101 managed migration requires migration and migrator roles" in migration
    assert "membership.roleid = (SELECT oid FROM migration_role)" in migration
    assert "_assert_legacy_rebaseline_handoff(bind)" in migration
    assert "PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH" in migration
    assert "_LEGACY_REBASELINE_SERIALIZATION_LOCK_SQL" in migration
    assert "_assert_legacy_rebaseline_ddl_quiescence" in migration
    assert "FROM pg_operator operator_row" in migration
    assert "ALTER OPERATOR app." in migration
    upgrade = migration[migration.index("def upgrade()") :]
    assert upgrade.index("_assert_legacy_rebaseline_handoff(bind)") < upgrade.index(
        "_advance_boundary_contract()"
    )
    handoff = migration[
        migration.index("def _assert_legacy_rebaseline_handoff") : migration.index(
            "def _activate_m05_migration_owner"
        )
    ]
    assert handoff.index("_LEGACY_REBASELINE_SERIALIZATION_LOCK_SQL") < handoff.index(
        "SELECT json_build_object"
    )
    assert handoff.index("_LEGACY_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_SQL") < handoff.index(
        "SELECT json_build_object"
    )
    assert handoff.index("SELECT json_build_object") < handoff.index(
        "_acquire_legacy_rebaseline_database_connection_fence(bind)"
    )
    assert "_grant_legacy_runtime_app_privileges(bind, canonical_app_owner)" in upgrade


def test_rebaseline_fence_blocks_new_backends_and_catches_inherited_catalog_owners() -> None:
    helper = (ROOT / "scripts" / "alembic_rebaseline.py").read_text(encoding="utf-8")
    migration = (
        ROOT / "apps" / "api" / "alembic" / "versions" / "20260824_0101_m05_activation_contract.py"
    ).read_text(encoding="utf-8")

    for source in (helper, migration):
        assert "LOCK TABLE pg_catalog.pg_database IN ACCESS EXCLUSIVE MODE" in source
        assert "SET LOCAL lock_timeout = '5s'" in source
        assert "could not acquire database connection fence within 5s" in source
        assert "requires superuser connection fence authority" in source
        assert "SELECT current_role_row.rolsuper" in source
        authority_start = source.index("SELECT current_role_row.rolsuper")
        authority_sql = source[authority_start : source.index('"""', authority_start)]
        assert "database_row.datdba" not in authority_sql
        assert "SELECT pg_stat_clear_snapshot()" in source
        assert "pre-existing DDL-capable sessions to be stopped" in source
        assert "SELECT pg_terminate_backend(:pid, 5000)" not in source
        assert "pg_catalog.pg_authid" in source
        assert "role_row.rolcreaterole" in source
        assert "has_schema_privilege(activity.usesysid, 'x_extension', 'CREATE')" in source
        for fragment in ("relation_acl", "function_acl", "type_acl", "default_acl"):
            assert fragment in source
        assert "pg_has_role(activity.usesysid, owner_row.owner_oid, 'USAGE')" in source
        assert "pg_has_role(activity.usesysid, owner_row.owner_oid, 'SET')" in source
        assert "ALLOW_CONNECTIONS false" not in source

    helper_fence = helper[
        helper.index("async def _acquire_rebaseline_database_connection_fence") : helper.index(
            "async def _app_data_fingerprint"
        )
    ]
    migration_fence = migration[
        migration.index(
            "def _acquire_legacy_rebaseline_database_connection_fence"
        ) : migration.index("def _legacy_rebaseline_catalog_fingerprint")
    ]
    assert helper_fence.index("_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_SQL") < helper_fence.index(
        "_REBASELINE_DATABASE_FENCE_AUTHORITY_SQL"
    )
    assert migration_fence.index(
        "_LEGACY_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_SQL"
    ) < migration_fence.index("_LEGACY_REBASELINE_DATABASE_FENCE_AUTHORITY_SQL")

    env = (ROOT / "apps" / "api" / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "_MIGRATION_SERIALIZATION_LOCK_SQL" in env
    assert env.index("_MIGRATION_SERIALIZATION_LOCK_SQL") < env.index("context.run_migrations()")


def test_migration_wrappers_open_only_for_the_one_shot_and_seal_afterward() -> None:
    for path in (ROOT / "scripts" / "docker-app.sh", ROOT / "scripts" / "deploy-node.sh"):
        source = path.read_text(encoding="utf-8")
        migration = source[source.index("migrate_under_lifecycle_lock() {") :]
        wrapper = source[source.index("migrate() {") :]
        assert "m05_legacy_rebaseline_profile()" in source
        assert "validate_bootstrap_admin_credential_file" in source
        assert "pinvi-admin-bootstrap validate-credential" in source
        assert "PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_SHA256" in source
        assert 'source "$ROOT_DIR/scripts/migrator-lifecycle-lock.sh"' in source
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
        assert "MIGRATOR_ONE_SHOT_PASSWORD" in source
        assert "od -An -N32 -tx1 /dev/urandom" in source
        assert 'PINVI_MIGRATOR_DB_PASSWORD="$MIGRATOR_ONE_SHOT_PASSWORD" compose run' in source
        assert "compose_with_one_shot_migrator_password" in source
        assert 'MIGRATOR_ONE_SHOT_PASSWORD=""' in source
        assert "reject_explicit_migrator_database_url()" in source
        assert "PINVI_MIGRATOR_DATABASE_URL is unsupported" in source
        assert "MIGRATOR_LOGIN_NEEDS_SEAL" in source
        assert "for attempt in 1 2 3; do" in source
        assert (
            wrapper.index("acquire_migrator_lifecycle_lock")
            < wrapper.index("migrate_under_lifecycle_lock")
            < wrapper.index("release_migrator_lifecycle_lock")
        )
        assert "if ! migrate_under_lifecycle_lock; then" not in wrapper
        assert 'if ! prepare_migrator_login "$legacy_rebaseline"; then' in migration
        assert "migrator preparation failed; sealing the one-shot login" in migration
        assert (
            migration.index("prepare_migrator_login")
            < migration.index("run_admin_bootstrap")
            < migration.rindex("seal_migrator_login")
        )
        assert migration.index("validate_bootstrap_admin_credential_file") < migration.index(
            "drain_runtime_writers"
        )


def test_runtime_writer_recovery_is_fail_closed_and_database_ready() -> None:
    for name in ("scripts/docker-app.sh", "scripts/deploy-node.sh"):
        source = (ROOT / name).read_text(encoding="utf-8")
        recovery_name = (
            "restore_runtime_writers_without_rollback()"
            if "restore_runtime_writers_without_rollback()" in source
            else "restore_runtime_writers()"
        )
        recovery = source[
            source.index(recovery_name) : source.index("m05_legacy_rebaseline_profile() {")
        ]
        assert 'local restore_failed="0"' in recovery
        assert 'docker start "$RUNTIME_API_CONTAINER_ID"' in recovery
        assert 'docker start "$RUNTIME_DAGSTER_CONTAINER_ID"' in recovery
        assert "RUNTIME_API_IMAGE_ID" in recovery
        assert "RUNTIME_DAGSTER_IMAGE_ID" in recovery
        assert "pinvi_verify_or_remove_running_dagster" not in recovery
        assert 'wait_for_url "http://127.0.0.1:${API_PORT}/health" "API restore"' in recovery
        assert "feature-reference-reconciliation" in recovery
        assert "wait_for_container_health" in source
        assert 'if [[ "$restore_failed" != "0" ]]; then' in recovery
        assert "release_migrator_lifecycle_lock || true" in source
        assert "runtime_snapshot_preflight()" in source
        assert "remove_new_runtime_writers()" in source
        assert "RUNTIME_NEW_WRITERS_STARTED" in source
        assert 'elif [[ "$RUNTIME_NEW_WRITERS_STARTED" == "1" ]]' in source
        assert '|| "$RUNTIME_DAGSTER_WAS_RUNNING" == "1"' in source
        assert "runtime_dagster_is_running()" in source
        assert "dagster_rollout_enabled()" in source
        assert "runtime_capture_predeploy_container_ids()" in source
        assert "runtime_record_new_container_ids()" in source
        assert "runtime_new_container_ids()" in source
        assert "pinvi_runtime_container_ids_into_array" in source
        assert "RUNTIME_CONTAINER_DISCOVERY_FAILED" in source
        assert "containing managed writers before rollback" in source
        assert "remove_recorded_new_runtime_writers()" in source
        assert "contain_unverified_runtime_writers()" in source
        assert "RUNTIME_NEW_API_CONTAINER_IDS" in source
        assert "RUNTIME_NEW_WEB_CONTAINER_IDS" in source
        assert "RUNTIME_NEW_DAGSTER_CONTAINER_IDS" in source
        assert "RUNTIME_API_SNAPSHOT_RENAMED" in source
        assert "RUNTIME_WEB_SNAPSHOT_RENAMED" in source
        assert "RUNTIME_DAGSTER_SNAPSHOT_RENAMED" in source
        preserve = source[
            source.index("preserve_runtime_writers()") : source.index(
                "rollback_preserved_runtime_writers()"
            )
        ]
        assert "restore_runtime_snapshot_names" in preserve
        assert "|| true" not in preserve
        assert "pinvi_verify_running_app" in source
        assert "pinvi_verify_running_dagster" in source
        assert "pinvi_verify_or_remove_running_app" not in source
        assert "pinvi_verify_or_remove_running_dagster" not in source
        assert "disarm_preserved_runtime_writers_after_rollout()" in source
        assert "keeping healthy new writers and remaining snapshots" in source
        if name == "scripts/deploy-node.sh":
            assert "prepare_standalone_dagster_writer()" in source
            assert "finalize_preserved_runtime_writers" in source[source.index("dagster_up() {") :]
    docker_app = (ROOT / "scripts" / "docker-app.sh").read_text(encoding="utf-8")
    assert "PINVI_DEV_FORCE_KILL" in docker_app
    assert "refusing to terminate it" in docker_app
    assert "configured_environment()" in docker_app
    assert "staging|production)" in docker_app
    assert "smoke_on_exit()" in docker_app
    assert 'restore_runtime_writers_on_exit "$exit_code"' in docker_app
    assert "assert_host_ports_available_before_migration()" in docker_app
    assert '"$CADVISOR_PORT"' in docker_app
    assert '"$PROMETHEUS_PORT"' in docker_app
    assert '"$GRAFANA_PORT"' in docker_app
    assert "host-port preflight failed at the migration boundary" in docker_app
    assert "host-port preflight failed immediately before migration" in docker_app
    assert 'ss -H -ltn "sport = :${port}" 2>/dev/null || true' not in docker_app
    assert "require_isolated_database_endpoint" in docker_app
    assert "isolated app-postgres service" in docker_app
    assert (
        "assert_host_ports_available_before_migration"
        in docker_app[docker_app.index("migrate() {") :]
    )
    deploy_node = (ROOT / "scripts" / "deploy-node.sh").read_text(encoding="utf-8")
    assert "assert_host_ports_available_before_migration()" in deploy_node
    assert (
        "assert_host_ports_available_before_migration"
        in deploy_node[deploy_node.index("migrate() {") :]
    )
    assert (
        'RUSTFS_CONSOLE_PORT="$(compose_env_value PINVI_RUSTFS_CONSOLE_PORT 12105)"' in deploy_node
    )
    assert 'CADVISOR_PORT="$(compose_env_value PINVI_CADVISOR_PORT 12301)"' in deploy_node
    assert 'PROMETHEUS_PORT="$(compose_env_value PINVI_PROMETHEUS_PORT 12401)"' in deploy_node
    assert 'GRAFANA_PORT="$(compose_env_value PINVI_GRAFANA_PORT 12205)"' in deploy_node
    assert "host-port preflight failed at the migration boundary" in deploy_node
    assert "host-port preflight failed immediately before migration" in deploy_node
    assert 'ss -H -ltn "sport = :${port}" 2>/dev/null || true' not in deploy_node
    assert (
        '"$RUSTFS_CONSOLE_PORT"'
        in deploy_node[deploy_node.index("assert_host_ports_available_before_migration()") :]
    )
    dagster_start = deploy_node.index("dagster_up() {")
    assert "assert_host_ports_available_before_migration" in deploy_node[dagster_start:]
    standalone_start = deploy_node.index("prepare_standalone_dagster_writer()")
    standalone_end = deploy_node.index("\n}\n", standalone_start) + 3
    standalone = deploy_node[standalone_start:standalone_end]
    assert "runtime_snapshot_preflight" in standalone
    assert standalone.index("runtime_snapshot_preflight") < standalone.index(
        "runtime_writer_container_id"
    )
    for cleanup in ("down() {", "reset() {"):
        cleanup_start = docker_app.index(cleanup)
        cleanup_end = docker_app.find("\n}\n", cleanup_start) + 3
        assert "runtime_snapshot_preflight" in docker_app[cleanup_start:cleanup_end]
        assert "acquire_migrator_lifecycle_lock" in docker_app[cleanup_start:cleanup_end]
        assert "release_migrator_lifecycle_lock" in docker_app[cleanup_start:cleanup_end]


def test_discovery_failure_stops_managed_writers_and_removes_only_recorded_ids(
    tmp_path: Path,
) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for dependency in ("api-image-provenance.sh", "migrator-lifecycle-lock.sh"):
        shutil.copy2(ROOT / "scripts" / dependency, scripts_dir / dependency)

    for name in ("docker-app.sh", "deploy-node.sh"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        isolated_script = scripts_dir / name
        isolated_script.write_text(
            source.rsplit('\nmain "$@"', maxsplit=1)[0] + "\n", encoding="utf-8"
        )
        event_log = tmp_path / f"{name}.events"
        driver = r"""
set -euo pipefail
source "$1"
log() { :; }
compose() {
  printf 'compose:%s\n' "$*" >> "$FAKE_EVENT_LOG"
  [[ "${FAKE_STOP_APP_API_FAIL:-0}" != "1" || "$*" != "stop app-api" ]]
}
runtime_new_container_ids() {
  case "$1" in
    app-api) printf '%s\n' recorded-api ;;
    app-web) printf '%s\n' recorded-web ;;
    app-dagster) printf '%s\n' recorded-dagster ;;
  esac
}
docker() { printf 'docker:%s\n' "$*" >> "$FAKE_EVENT_LOG"; }
RUNTIME_CONTAINER_DISCOVERY_FAILED=1
if remove_new_runtime_writers; then
  exit 1
fi
"""
        expected_events = [
            "compose:stop app-web",
            "compose:stop app-api",
            "compose:--profile etl stop app-dagster",
            "docker:rm -f recorded-api",
            "docker:rm -f recorded-web",
            "docker:rm -f recorded-dagster",
        ]
        for stop_failure in ("0", "1"):
            event_log.unlink(missing_ok=True)
            subprocess.run(  # noqa: S603 -- fixed test-only bash driver
                ["bash", "-c", driver, "--", str(isolated_script)],  # noqa: S607 -- fixture script
                check=True,
                input="",
                text=True,
                env={
                    "FAKE_EVENT_LOG": str(event_log),
                    "FAKE_STOP_APP_API_FAIL": stop_failure,
                    "PINVI_ROOT_DIR": str(tmp_path),
                },
            )
            assert event_log.read_text(encoding="utf-8").splitlines() == expected_events


def test_snapshot_identity_drift_refuses_name_restoration(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for dependency in ("api-image-provenance.sh", "migrator-lifecycle-lock.sh"):
        shutil.copy2(ROOT / "scripts" / dependency, scripts_dir / dependency)

    for name in ("docker-app.sh", "deploy-node.sh"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        isolated_script = scripts_dir / name
        isolated_script.write_text(
            source.rsplit('\nmain "$@"', maxsplit=1)[0] + "\n", encoding="utf-8"
        )
        event_log = tmp_path / f"{name}.snapshot-events"
        driver = r"""
set -euo pipefail
source "$1"
RUNTIME_API_SNAPSHOT_RENAMED=1
RUNTIME_API_BACKUP_NAME=app-api.pinvi-predeploy
RUNTIME_API_CONTAINER_NAME=app-api
RUNTIME_API_CONTAINER_ID=expected-api
RUNTIME_API_IMAGE_ID=expected-image
docker() {
  case "$*" in
    "container inspect app-api.pinvi-predeploy") return 0 ;;
    container\ inspect\ --format\ *\ app-api.pinvi-predeploy)
      printf '%s\n' 'impostor-api|expected-image|pinvi-app|app-api'
      ;;
    rename*) printf 'unexpected-rename:%s\n' "$*" >> "$FAKE_EVENT_LOG"; return 99 ;;
    *) return 98 ;;
  esac
}
if restore_runtime_snapshot_name app-api; then
  exit 1
fi
"""
        subprocess.run(  # noqa: S603 -- fixed test-only bash driver
            ["bash", "-c", driver, "--", str(isolated_script)],  # noqa: S607 -- fixture script
            check=True,
            input="",
            text=True,
            env={"FAKE_EVENT_LOG": str(event_log), "PINVI_ROOT_DIR": str(tmp_path)},
        )
        assert not event_log.exists()


def test_existing_runtime_refuses_in_place_snapshot_preflight(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for dependency in ("api-image-provenance.sh", "migrator-lifecycle-lock.sh"):
        shutil.copy2(ROOT / "scripts" / dependency, scripts_dir / dependency)

    for name in ("scripts/docker-app.sh", "scripts/deploy-node.sh"):
        source = (ROOT / name).read_text(encoding="utf-8")
        isolated_script = scripts_dir / Path(name).name
        isolated_script.write_text(
            source.rsplit('\nmain "$@"', maxsplit=1)[0] + "\n", encoding="utf-8"
        )
        driver = r"""
set -euo pipefail
source "$1"
pinvi_runtime_predeploy_snapshot_ids() { return 0; }
RUNTIME_DEPLOY_PRESERVE=1
RUNTIME_PREDEPLOY_API_CONTAINER_IDS=(existing-api)
if runtime_snapshot_preflight; then
  exit 1
fi
"""
        result = subprocess.run(  # noqa: S603 -- fixed test-only bash driver
            ["bash", "-c", driver, "--", str(isolated_script)],  # noqa: S607 -- fixture script
            check=False,
            capture_output=True,
            text=True,
            env={"PINVI_ROOT_DIR": str(tmp_path)},
        )
        assert result.returncode == 0
        assert "in-place runtime snapshot is disabled" in result.stderr


def test_stale_predeploy_snapshot_refuses_runtime_mutation(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for dependency in ("api-image-provenance.sh", "migrator-lifecycle-lock.sh"):
        shutil.copy2(ROOT / "scripts" / dependency, scripts_dir / dependency)

    for name in ("scripts/docker-app.sh", "scripts/deploy-node.sh"):
        source = (ROOT / name).read_text(encoding="utf-8")
        isolated_script = scripts_dir / Path(name).name
        isolated_script.write_text(
            source.rsplit('\nmain "$@"', maxsplit=1)[0] + "\n", encoding="utf-8"
        )
        driver_template = r"""
set -euo pipefail
source "$1"
pinvi_runtime_predeploy_snapshot_ids() {{ printf '%s\n' stale-snapshot; }}
RUNTIME_DEPLOY_PRESERVE={preserve}
if runtime_snapshot_preflight; then
  exit 1
fi
"""
        for preserve in ("0", "1"):
            result = subprocess.run(  # noqa: S603 -- fixed test-only bash driver
                [
                    "/usr/bin/bash",
                    "-c",
                    driver_template.format(preserve=preserve),
                    "--",
                    str(isolated_script),
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"PINVI_ROOT_DIR": str(tmp_path)},
            )
            assert result.returncode == 0
            assert "stale rollback artifact" in result.stderr


def test_direct_reset_and_down_require_isolated_runtime_identity(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    event_log = tmp_path / "compose-events.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == "context show" ]]; then
  printf '%s\n' default
  exit 0
fi
if [[ "$1 $2" == "context inspect" ]]; then
  printf '%s\n' unix:///var/run/docker.sock
  exit 0
fi
if [[ "$1 $2" == "compose version" ]]; then
  exit 0
fi
if [[ "${PINVI_TEST_STALE_SNAPSHOT:-0}" == "1" \
  && "$*" == *Names* ]]; then
  case "$*" in
    *"service=app-api"*) printf '%s\n' 'stale-api app-api.pinvi-predeploy' ;;
    *"service=app-web"*) printf '%s\n' 'stale-web app-web.pinvi-predeploy' ;;
    *"service=app-dagster"*) printf '%s\n' 'stale-dagster app-dagster.pinvi-predeploy' ;;
  esac
  exit 0
fi
if [[ "${PINVI_TEST_DB_IDENTITY_FAIL:-0}" == "1" \
  && "$1 $2" == "container ls" && "$*" != *"service="* ]]; then
  printf '%s\n' db-container
  exit 0
fi
if [[ "${PINVI_TEST_DB_IDENTITY_FAIL:-0}" == "1" \
  && "$1 $2" == "volume ls" ]]; then
  printf '%s\n' app-postgres-volume
  exit 0
fi
if [[ "${PINVI_TEST_DB_IDENTITY_FAIL:-0}" == "1" \
  && "$1 $2" == "volume inspect" ]]; then
  exit 1
fi
if [[ "$1 $2" == "container ls" || "$1 $2" == "volume ls" ]]; then
  exit 0
fi
if [[ "$1" == "compose" ]]; then
  printf '%s\\n' "$*" >> "$PINVI_TEST_EVENT_LOG"
fi
""",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    isolated_env_file = tmp_path / "smoke.env"
    isolated_env_file.write_text("PINVI_ENVIRONMENT=smoke\n", encoding="utf-8")

    base_env = {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "PINVI_ENV_FILE": str(isolated_env_file),
        "PINVI_ENVIRONMENT": "smoke",
        "PINVI_ROOT_DIR": str(ROOT),
        "PINVI_TEST_EVENT_LOG": str(event_log),
    }
    isolated = dict(base_env, PINVI_DOCKER_PROJECT="pinvi-app-smoke")
    reset = subprocess.run(  # noqa: S603 -- fixed test-only shell driver
        [str(ROOT / "scripts" / "docker-app.sh"), "reset"],
        check=False,
        capture_output=True,
        text=True,
        env=isolated,
    )
    assert reset.returncode == 0
    assert not event_log.exists()

    identity_reset = subprocess.run(  # noqa: S603 -- fixed test-only shell driver
        [str(ROOT / "scripts" / "docker-app.sh"), "reset"],
        check=False,
        capture_output=True,
        text=True,
        env=dict(isolated, PINVI_TEST_DB_IDENTITY_FAIL="1"),
    )
    assert identity_reset.returncode != 0
    assert "database identity" in identity_reset.stderr
    assert not event_log.exists()

    external_db_reset = subprocess.run(  # noqa: S603 -- fixed test-only shell driver
        [str(ROOT / "scripts" / "docker-app.sh"), "reset"],
        check=False,
        capture_output=True,
        text=True,
        env=dict(
            isolated,
            PINVI_DATABASE_URL="postgresql+asyncpg://pinvi:secret@prod-db:5432/pinvi",
        ),
    )
    assert external_db_reset.returncode != 0
    assert "isolated app-postgres service" in external_db_reset.stderr
    assert not event_log.exists()

    external_legacy_db_reset = subprocess.run(  # noqa: S603 -- fixed test-only shell driver
        [str(ROOT / "scripts" / "docker-app.sh"), "reset"],
        check=False,
        capture_output=True,
        text=True,
        env=dict(
            isolated,
            PINVI_LEGACY_REBASELINE_DATABASE_URL=(
                "postgresql+asyncpg://pinvi:secret@prod-db:5432/pinvi"
            ),
        ),
    )
    assert external_legacy_db_reset.returncode != 0
    assert "PINVI_LEGACY_REBASELINE_DATABASE_URL" in external_legacy_db_reset.stderr
    assert not event_log.exists()

    stale_reset = subprocess.run(  # noqa: S603 -- fixed test-only shell driver
        [str(ROOT / "scripts" / "docker-app.sh"), "reset"],
        check=False,
        capture_output=True,
        text=True,
        env=dict(isolated, PINVI_TEST_STALE_SNAPSHOT="1"),
    )
    assert stale_reset.returncode != 0
    assert "stale pre-deploy snapshot" in stale_reset.stderr
    assert not event_log.exists()

    arbitrary = dict(base_env, PINVI_DOCKER_PROJECT="pinvi-app-prod")
    down = subprocess.run(  # noqa: S603 -- fixed test-only shell driver
        [str(ROOT / "scripts" / "docker-app.sh"), "down"],
        check=False,
        capture_output=True,
        text=True,
        env=arbitrary,
    )
    assert down.returncode != 0
    assert not event_log.exists()

    stale_down = subprocess.run(  # noqa: S603 -- fixed test-only shell driver
        [str(ROOT / "scripts" / "docker-app.sh"), "down"],
        check=False,
        capture_output=True,
        text=True,
        env=dict(isolated, PINVI_TEST_STALE_SNAPSHOT="1"),
    )
    assert stale_down.returncode != 0
    assert "stale pre-deploy snapshot" in stale_down.stderr
    assert not event_log.exists()


def test_compose_preflight_uses_effective_env_file_and_root_dotenv_fallback(
    tmp_path: Path,
) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for dependency in ("api-image-provenance.sh", "migrator-lifecycle-lock.sh"):
        shutil.copy2(ROOT / "scripts" / dependency, scripts_dir / dependency)

    env_file = tmp_path / "stage.env"
    env_file.write_text(
        "export PINVI_API_PORT=13801\n"
        "export PINVI_WEB_PORT=13805\n"
        "export PINVI_RUSTFS_PORT=13101\n"
        "export PINVI_RUSTFS_CONSOLE_PORT=13105\n"
        "export PINVI_DAGSTER_DEV_PORT=13802\n"
        "export PINVI_CADVISOR_PORT=13301\n"
        "export PINVI_PROMETHEUS_PORT=13401\n"
        "export PINVI_GRAFANA_PORT=13205\n",
        encoding="utf-8",
    )
    root_dotenv = tmp_path / ".env"
    root_dotenv.write_text(
        "export PINVI_ENVIRONMENT=production\n"
        "export PINVI_DATABASE_URL=postgresql+asyncpg://pinvi:secret@production-db:5432/pinvi\n"
        "export PINVI_API_PORT=13901\n",
        encoding="utf-8",
    )

    for name in ("docker-app.sh", "deploy-node.sh"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        isolated_script = scripts_dir / name
        isolated_script.write_text(
            source.rsplit('\nmain "$@"', maxsplit=1)[0] + "\n", encoding="utf-8"
        )
        result = subprocess.run(  # noqa: S603 -- fixed test-only shell driver
            [
                "/usr/bin/bash",
                "-c",
                """
set -euo pipefail
source "$1"
[[ "$API_PORT" == "13801" ]]
[[ "$WEB_PORT" == "13805" ]]
[[ "$RUSTFS_PORT" == "13101" ]]
[[ "$RUSTFS_CONSOLE_PORT" == "13105" ]]
[[ "$DAGSTER_PORT" == "13802" ]]
[[ "$CADVISOR_PORT" == "13301" ]]
[[ "$PROMETHEUS_PORT" == "13401" ]]
[[ "$GRAFANA_PORT" == "13205" ]]
""",
                "bash",
                str(isolated_script),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                "PATH": "/usr/bin:/bin",
                "PINVI_ROOT_DIR": str(tmp_path),
                "PINVI_ENV_FILE": str(env_file),
            },
        )
        assert result.returncode == 0, result.stderr

    source = (ROOT / "scripts" / "docker-app.sh").read_text(encoding="utf-8")
    isolated_script = scripts_dir / "docker-app-dotenv.sh"
    isolated_script.write_text(source.rsplit('\nmain "$@"', maxsplit=1)[0] + "\n", encoding="utf-8")
    result = subprocess.run(  # noqa: S603 -- fixed test-only shell driver
        [
            "/usr/bin/bash",
            "-c",
            """
set -euo pipefail
source "$1"
[[ "$API_PORT" == "13901" ]]
[[ "$(configured_environment)" == "production" ]]
if require_isolated_database_endpoint; then
  exit 1
fi
""",
            "bash",
            str(isolated_script),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PINVI_ROOT_DIR": str(tmp_path),
            "PINVI_ENV_FILE": str(tmp_path / "missing.env"),
        },
    )
    assert result.returncode == 0, result.stderr
    assert "isolated app-postgres service" in result.stderr


def test_live_ui_gates_pin_the_exact_checkout_revision() -> None:
    runner = (ROOT / "scripts" / "n150-playwright-runner.sh").read_text(encoding="utf-8")
    gate = (ROOT / "scripts" / "verify-v100-live-gate.sh").read_text(encoding="utf-8")
    for source in (runner, gate):
        assert "PINVI_LIVE_EXPECTED_REVISION" in source
        assert "git rev-parse --verify HEAD^{commit}" in source
        assert "does not match expected" in source
    assert "assert_exact_live_checkout" in runner
    assert "require_exact_live_revision" in gate
    assert "live Playwright phases require PINVI_V100_GATE_N150_RUNNER=1" in gate
    assert "git status --porcelain=v1 --untracked-files=all" in runner
    assert "git status --porcelain=v1 --untracked-files=all" in gate
    assert "PINVI_LIVE_UI_E2E" in runner
    assert "PINVI_M05_LIVE_E2E" in runner
    assert "sha256:[0-9a-f]{64}" in runner
    for phase in (
        "admin-live-list",
        "admin-live-smoke",
        "admin-live-full",
        "live-mutating-list",
        "trip-realtime-mutating",
        "backup-mutating",
    ):
        phase_start = gate.index(f"    {phase})")
        phase_end = gate.index("      ;;", phase_start)
        assert "run_live_playwright" in gate[phase_start:phase_end]

    for runbook in ("admin-live-e2e.md", "v100-live-gate.md"):
        documentation = (ROOT / "docs" / "runbooks" / runbook).read_text(encoding="utf-8")
        assert "$(git rev-parse --verify HEAD^{commit})" not in documentation
        assert "<trusted release candidate SHA>" in documentation

    attestation = (ROOT / "scripts" / "m05_activation_attestation.py").read_text(encoding="utf-8")
    m05_runner = attestation[
        attestation.index('child_env["PINVI_M05_LIVE_EVENT_ID"]') : attestation.index(
            "completed = subprocess.run(command, check=False, env=child_env)",
            attestation.index('child_env["PINVI_M05_LIVE_EVENT_ID"]'),
        )
    ]
    assert 'child_env["PINVI_SOURCE_REVISION"] = source_revision' in m05_runner
    assert 'child_env["PINVI_LIVE_EXPECTED_REVISION"] = source_revision' in m05_runner
    for name in (
        "PINVI_M05_LIVE_OLD_FEATURE_ID",
        "PINVI_M05_LIVE_REPLACEMENT_FEATURE_ID",
        "PINVI_M05_LIVE_IMPACT_COUNT",
        "PINVI_M05_LIVE_EMAIL",
        "PINVI_M05_LIVE_PASSWORD",
    ):
        assert f'child_env["{name}"]' in m05_runner
    for binding in (
        "args.map_docker_project",
        "args.map_admin_service",
        "args.map_api_service",
        "args.map_frontend_service",
        "args.pinvi_docker_project",
        'expected_compose_service="app-api"',
        'expected_compose_service="app-web"',
        'expected_compose_service="app-dagster"',
    ):
        assert binding in attestation
    live_e2e = (
        ROOT / "apps/web/e2e/admin-feature-reference-reconciliations-live-mutating.live.ts"
    ).read_text(encoding="utf-8")
    assert "unexpectedApiMutations" in live_e2e
    assert "requestUrl.pathname === '/auth/login'" in live_e2e
    assert "isReadOnlyRequest" in live_e2e
    assert "method === 'OPTIONS'" in live_e2e


def test_runtime_discovery_failure_is_detected_without_caller_pipefail() -> None:
    provenance = ROOT / "scripts" / "api-image-provenance.sh"
    command = """\
set -eu
ROOT_DIR="$2"
COMPOSE_FILE="$2/infra/docker-compose.app.yml"
source "$1"
docker() { return 73; }
declare -a container_ids=()
if pinvi_runtime_container_ids_into_array container_ids app-api; then
  exit 81
fi
[[ "$RUNTIME_CONTAINER_DISCOVERY_FAILED" == "1" ]]
"""
    result = subprocess.run(  # noqa: S603 -- fixed test-only bash driver
        ["bash", "-c", command, "bash", str(provenance), str(ROOT)],  # noqa: S607 -- fixture script
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    for name in ("scripts/docker-app.sh", "scripts/deploy-node.sh"):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert "remove_recorded_new_runtime_writers()" in source
        assert "contain_unverified_runtime_writers()" in source
        assert "containing managed writers before rollback" in source
        assert "compose stop app-web" in source
        assert "compose stop app-api" in source
        assert "compose --profile etl stop app-dagster" in source
        assert (
            "remove_recorded_new_runtime_writers"
            in source[source.index("remove_new_runtime_writers()") :]
        )


def test_fresh_0101_and_role_bootstrap_fence_direct_app_schema_create() -> None:
    migration = (
        ROOT / "apps" / "api" / "alembic" / "versions" / "20260824_0101_m05_activation_contract.py"
    ).read_text(encoding="utf-8")
    bootstrap = (ROOT / "infra" / "postgres" / "bootstrap-pinvi-runtime-role.sh").read_text(
        encoding="utf-8"
    )

    assert "_acquire_fresh_0101_writer_fence(bind)" in migration
    assert "_FRESH_0101_DATABASE_FENCE_FUNCTION" in migration
    assert "LOCK TABLE pinvi_internal.baseline_origin" in migration
    assert "canonical fresh 0100 catalog fingerprint" in migration
    assert "app_namespace.nspname = 'app'" in migration
    assert "app_acl.privilege_type = 'CREATE'" in migration
    assert "app_acl.privilege_type = 'CREATE'" in bootstrap
    assert "(SELECT oid FROM app_owner) <> (SELECT oid FROM database_owner)" in migration
    assert ":legacy_rebaseline" in migration
    assert "legacy_rebaseline\n                    OR (SELECT oid FROM app_owner)" in migration
    assert "(SELECT oid FROM schema_owner) <> (SELECT oid FROM database_owner)" in bootstrap
    assert "relation.relkind = 'r'" in migration
    assert "relation.relpersistence = 'p'" in migration


def test_fresh_deploy_waits_for_a_successful_rustfs_bucket_initializer() -> None:
    source = (ROOT / "scripts" / "deploy-node.sh").read_text(encoding="utf-8")
    assert "wait_for_fresh_stack_one_shot()" in source
    assert "wait_for_fresh_stack_one_shot app-rustfs-init" in source
    assert 'timeout --foreground 120s docker container wait "$container_id"' in source
    assert '"$state" == "exited 0"' in source


def test_docker_app_up_uses_the_explicit_legacy_role_profile_before_migration() -> None:
    source = (ROOT / "scripts" / "docker-app.sh").read_text(encoding="utf-8")
    up_deps = source[source.index("up_deps() {") : source.index("drain_runtime_writers() {")]
    up = source[source.index("up() {") : source.index("down() {")]

    assert "app-db-runtime-role" not in up_deps
    assert 'local legacy_rebaseline="${1:-0}"' not in up_deps
    assert "legacy_rebaseline_receipt_file >/dev/null" in up
    assert up.index("acquire_migrator_lifecycle_lock") < up.index("free_app_ports")
    assert up.index("drain_runtime_writers") < up.index("free_app_ports")
    assert (
        up.index("free_app_ports")
        < up.index("up_deps")
        < up.index("migrate_under_lifecycle_lock")
        < up.index("release_migrator_lifecycle_lock")
    )
