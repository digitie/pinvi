"""M05 schema-swap preflight를 실제 PostgreSQL 권한 상태에서 검증한다."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
HOTSWAP_SCRIPT = ROOT / "scripts/restore-hotswap.sh"
TEST_PASSWORD = "m05-test-only-password"
AUDIT_FIXTURE_OCCURRED_AT = "2026-08-24T03:00:00+00:00"


def _audit_content_hash(
    prev_hash: str,
    *,
    action: str,
    ip_hash: str,
    request_id: str,
    occurred_at: str,
) -> str:
    payload = {
        "actor_user_id": "40000000-0000-4000-8000-000000000001",
        "action": action,
        "resource_type": "restore",
        "resource_id": None,
        "before_state": None,
        "after_state": None,
        "access_reason": None,
        "target_pii_fields": None,
        "ip_hash": ip_hash,
        "user_agent": None,
        "request_id": request_id,
        "occurred_at": occurred_at,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + serialized).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _Case:
    database: str
    fence_role: str
    hotswap_role: str
    app_role: str
    app_url: str
    fence_url: str
    hotswap_url: str
    expected_failure: str
    expected_delete: bool
    requires_definer_proof: bool = False


def _require_tools() -> dict[str, str]:
    names = ("bash", "pg_dump", "pg_restore", "psql")
    resolved = {name: shutil.which(name) for name in names}
    if any(path is None for path in resolved.values()):
        pytest.skip("PostgreSQL client tool이 없어 M05 실제 권한 검증을 건너뜁니다.")
    return {name: str(path) for name, path in resolved.items()}


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _require_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr


def _psql(tools: dict[str, str], database_url: str, sql: str) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            tools["psql"],
            "--no-psqlrc",
            "--set=ON_ERROR_STOP=1",
            "--tuples-only",
            "--no-align",
            f"--dbname={database_url}",
            "--file=-",
        ],
        input_text=sql,
    )


def _quoted(identifier: str) -> str:
    assert identifier.replace("_", "").isalnum()
    return f'"{identifier}"'


def _database_url(*, host: str, port: str, role: str, database: str) -> str:
    return f"postgresql://{role}:{TEST_PASSWORD}@{host}:{port}/{database}"


def _create_case(
    *,
    tools: dict[str, str],
    root_url: str,
    host: str,
    port: str,
    suffix: str,
    kind: str,
) -> _Case:
    database = f"m05_{kind}_{suffix}"
    fence_role = f"m05_fence_{kind}_{suffix}"
    hotswap_role = f"m05_swap_{kind}_{suffix}"
    app_role = f"m05_app_{kind}_{suffix}"
    extra_role = f"m05_extra_{kind}_{suffix}"
    roles = [fence_role, hotswap_role, app_role]
    if kind == "extra":
        roles.append(extra_role)

    create_roles = "\n".join(
        "CREATE ROLE "
        f"{_quoted(role)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
        f"NOBYPASSRLS {'NOINHERIT' if role in {app_role, fence_role} else 'INHERIT'} "
        f"PASSWORD '{TEST_PASSWORD}';"
        for role in roles
    )
    _require_success(
        _psql(
            tools,
            root_url,
            f"""
{create_roles}
GRANT pg_signal_backend TO {_quoted(hotswap_role)};
CREATE DATABASE {_quoted(database)} OWNER {_quoted(fence_role)};
GRANT CONNECT, CREATE ON DATABASE {_quoted(database)} TO {_quoted(hotswap_role)};
GRANT CONNECT ON DATABASE {_quoted(database)} TO {_quoted(app_role)};
{"GRANT CONNECT ON DATABASE " + _quoted(database) + " TO " + _quoted(extra_role) + ";" if kind == "extra" else ""}
""",
        )
    )

    hotswap_url = _database_url(host=host, port=port, role=hotswap_role, database=database)
    fence_url = _database_url(host=host, port=port, role=fence_role, database=database)
    app_url = _database_url(host=host, port=port, role=app_role, database=database)
    root_target_url = _database_url(host=host, port=port, role="m05_root", database=database)
    _require_success(
        _psql(
            tools,
            root_target_url,
            f"""
CREATE SCHEMA x_extension AUTHORIZATION m05_root;
CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA x_extension;
REVOKE ALL ON SCHEMA x_extension FROM PUBLIC;
GRANT USAGE ON SCHEMA x_extension TO {_quoted(hotswap_role)}, {_quoted(app_role)};
""",
        )
    )

    table_grants = (
        f"GRANT INSERT ON TABLE app.widgets TO {_quoted(app_role)};"
        if kind == "acl"
        else (
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO {_quoted(app_role)};\n"
            f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA app TO {_quoted(app_role)};"
        )
    )
    extra_grant = (
        f"GRANT USAGE ON SCHEMA app TO {_quoted(extra_role)};\n"
        f"GRANT INSERT ON TABLE app.widgets TO {_quoted(extra_role)};"
        if kind == "extra"
        else ""
    )
    default_acl = (
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {_quoted(hotswap_role)} "
        f"GRANT SELECT ON TABLES TO {_quoted(extra_role)};"
        if kind == "global_default"
        else ""
    )
    if kind == "global_default":
        roles.append(extra_role)
        _require_success(
            _psql(
                tools,
                root_url,
                f"CREATE ROLE {_quoted(extra_role)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                f"NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD '{TEST_PASSWORD}';",
            )
        )

    reconciliation_schema = ""
    if kind in {
        "canonical",
        "trigger_noop",
        "trigger_truncate_noop",
        "audit_trigger_noop",
        "audit_content_noop",
        "missing_audit",
    }:
        # The executing hotswap validates the M05 reconciliation safeguards after
        # restore.  Keep this fixture structurally small, but include the exact
        # protected objects so this is a genuine happy-path exercise rather than
        # an ACL-only preflight probe.
        audit_guard_body = (
            """BEGIN
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
        USING ERRCODE = '55000';
END;"""
            if kind != "audit_trigger_noop"
            else """BEGIN
    RETURN NEW;
END;"""
        )
        audit_content_hash_sql = (
            "repeat('2', 64)"
            if kind == "audit_content_noop"
            else repr(
                _audit_content_hash(
                    "0" * 64,
                    action="m05.fixture",
                    ip_hash="1" * 64,
                    request_id="40000000-0000-4000-8000-000000000002",
                    occurred_at=AUDIT_FIXTURE_OCCURRED_AT,
                )
            )
        )
        audit_table = (
            ""
            if kind == "missing_audit"
            else """CREATE TABLE app.admin_audit_log (
  log_id bigserial PRIMARY KEY,
  actor_user_id uuid NOT NULL REFERENCES app.users(user_id) ON DELETE RESTRICT,
  action varchar(64) NOT NULL,
  resource_type varchar(64) NOT NULL,
  resource_id varchar(128),
  before_state jsonb,
  after_state jsonb,
  access_reason text,
  target_pii_fields varchar(64)[],
  ip_hash varchar(64) NOT NULL,
  user_agent varchar(512),
  request_id uuid NOT NULL,
  prev_hash varchar(64) NOT NULL,
  content_hash varchar(64) NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_admin_audit_log_prev_hash UNIQUE (prev_hash)
);
CREATE FUNCTION app.guard_admin_audit_log_append_only()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $audit_guard__BODY__$audit_guard$;
CREATE TRIGGER trg_admin_audit_log_append_only
  BEFORE INSERT OR UPDATE OR DELETE ON app.admin_audit_log
  FOR EACH ROW EXECUTE FUNCTION app.guard_admin_audit_log_append_only();
ALTER TABLE app.admin_audit_log
  ENABLE ALWAYS TRIGGER trg_admin_audit_log_append_only;
CREATE TRIGGER trg_admin_audit_log_truncate_append_only
  BEFORE TRUNCATE ON app.admin_audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION app.guard_admin_audit_log_append_only();
ALTER TABLE app.admin_audit_log
  ENABLE ALWAYS TRIGGER trg_admin_audit_log_truncate_append_only;
INSERT INTO app.users (user_id)
VALUES ('40000000-0000-4000-8000-000000000001');
INSERT INTO app.admin_audit_log (
  actor_user_id, action, resource_type, resource_id, before_state, after_state,
  access_reason, target_pii_fields, ip_hash, user_agent, request_id, prev_hash,
  content_hash, occurred_at
) VALUES (
  '40000000-0000-4000-8000-000000000001', 'm05.fixture', 'restore', NULL,
  NULL, NULL, NULL, NULL, repeat('1', 64), NULL,
  '40000000-0000-4000-8000-000000000002', repeat('0', 64), __AUDIT_CONTENT_HASH__,
  TIMESTAMPTZ '__AUDIT_OCCURRED_AT__'
);
""".replace("$audit_guard__BODY__$audit_guard$", f"$audit_guard${audit_guard_body}$audit_guard$")
            .replace("__AUDIT_CONTENT_HASH__", audit_content_hash_sql)
            .replace("__AUDIT_OCCURRED_AT__", AUDIT_FIXTURE_OCCURRED_AT.replace("T", " "))
        )
        trigger_body = (
            """
  IF TG_OP = 'INSERT' THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
    USING ERRCODE = '55000';
"""
            if kind not in {"trigger_noop", "trigger_truncate_noop"}
            else (
                """
  RETURN NEW;
"""
                if kind == "trigger_noop"
                else """
  IF TG_OP = 'INSERT' THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'TRUNCATE'
    AND TG_TABLE_NAME = 'ktm_feature_reference_reconciliation_delivery_attempts' THEN
    RETURN NULL;
  END IF;
  RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
    USING ERRCODE = '55000';
"""
            )
        )
        canonical_reconciliation_seed = (
            """
INSERT INTO app.ktm_feature_reference_reconciliation_applied_receipts (
  event_id, event_sequence, event_sha256, action, old_feature_id, old_feature_uuid,
  replacement_feature_id, replacement_feature_uuid, impact_root_sha256, impact_count,
  receipt_sha256
) VALUES (
  '40000000-0000-4000-8000-000000000010', 1, repeat('3', 64), 'detach',
  'preexisting-feature', '40000000-0000-4000-8000-000000000011', NULL, NULL,
  repeat('4', 64), 1, repeat('5', 64)
);
INSERT INTO app.ktm_feature_reference_reconciliation_impacts (
  event_id, impact_index, target_relation, target_id, old_feature_id, old_feature_uuid,
  replacement_feature_id, replacement_feature_uuid, outcome
) VALUES (
  '40000000-0000-4000-8000-000000000010', 0, 'trip_day_pois',
  '40000000-0000-4000-8000-000000000012', 'preexisting-feature',
  '40000000-0000-4000-8000-000000000011', NULL, NULL, 'detach'
);
"""
            if kind == "canonical"
            else ""
        )
        reconciliation_schema = f"""
CREATE TABLE app.users (user_id uuid PRIMARY KEY);
{audit_table}
CREATE TABLE app.ktm_feature_reference_reconciliation_delivery_attempts (
  event_id uuid NOT NULL,
  attempt_sequence bigint NOT NULL CHECK (attempt_sequence > 0),
  event_sequence bigint NOT NULL CHECK (event_sequence > 0),
  event_sha256 varchar(64) NOT NULL CHECK (event_sha256 ~ '^[0-9a-f]{{64}}$'),
  status varchar(16) NOT NULL,
  block_fingerprint_sha256 varchar(64),
  observation_root_sha256 varchar(64) NOT NULL
    CHECK (observation_root_sha256 ~ '^[0-9a-f]{{64}}$'),
  PRIMARY KEY (event_id, attempt_sequence),
  CHECK (
    (status = 'blocked' AND block_fingerprint_sha256 IS NOT NULL) OR
    (status = 'applied' AND block_fingerprint_sha256 IS NULL)
  )
);
CREATE TABLE app.ktm_feature_reference_reconciliation_applied_receipts (
  event_id uuid PRIMARY KEY,
  event_sequence bigint NOT NULL UNIQUE CHECK (event_sequence > 0),
  event_sha256 varchar(64) NOT NULL UNIQUE CHECK (event_sha256 ~ '^[0-9a-f]{{64}}$'),
  action varchar(16) NOT NULL,
  old_feature_id text NOT NULL,
  old_feature_uuid uuid NOT NULL,
  replacement_feature_id text,
  replacement_feature_uuid uuid,
  impact_root_sha256 varchar(64) NOT NULL CHECK (impact_root_sha256 ~ '^[0-9a-f]{{64}}$'),
  impact_count bigint NOT NULL CHECK (impact_count >= 0),
  receipt_sha256 varchar(64) NOT NULL UNIQUE CHECK (receipt_sha256 ~ '^[0-9a-f]{{64}}$'),
  CHECK (
    (replacement_feature_id IS NULL AND replacement_feature_uuid IS NULL) OR
    (replacement_feature_id IS NOT NULL AND replacement_feature_uuid IS NOT NULL)
  ),
  CHECK (
    (action = 'rebind' AND replacement_feature_id IS NOT NULL) OR
    (action = 'detach' AND replacement_feature_id IS NULL)
  )
);
CREATE TABLE app.ktm_feature_reference_reconciliation_impacts (
  event_id uuid NOT NULL,
  impact_index integer NOT NULL CHECK (impact_index >= 0),
  target_relation varchar(32) NOT NULL
    CHECK (target_relation IN ('trip_day_pois', 'curated_plan_pois', 'feature_suggestions')),
  target_id uuid NOT NULL,
  old_feature_id text NOT NULL,
  old_feature_uuid uuid NOT NULL,
  replacement_feature_id text,
  replacement_feature_uuid uuid,
  outcome varchar(24) NOT NULL,
  PRIMARY KEY (event_id, impact_index),
  UNIQUE (event_id, target_relation, target_id),
  FOREIGN KEY (event_id)
    REFERENCES app.ktm_feature_reference_reconciliation_applied_receipts(event_id)
    ON DELETE RESTRICT,
  CHECK (
    (replacement_feature_id IS NULL AND replacement_feature_uuid IS NULL) OR
    (replacement_feature_id IS NOT NULL AND replacement_feature_uuid IS NOT NULL)
  ),
  CHECK (
    (outcome = 'rebind' AND replacement_feature_id IS NOT NULL) OR
    (outcome = 'detach' AND replacement_feature_id IS NULL) OR
    outcome = 'already_reconciled'
  )
);
CREATE FUNCTION app.guard_ktm_feature_reference_reconciliation_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
{trigger_body}
END;
$$;
CREATE TRIGGER trg_ktm_feature_reference_reconciliation_delivery_attempts_append_only
  BEFORE INSERT OR UPDATE OR DELETE
  ON app.ktm_feature_reference_reconciliation_delivery_attempts
  FOR EACH ROW EXECUTE FUNCTION app.guard_ktm_feature_reference_reconciliation_append_only();
ALTER TABLE app.ktm_feature_reference_reconciliation_delivery_attempts
  ENABLE ALWAYS TRIGGER trg_ktm_feature_reference_reconciliation_delivery_attempts_append_only;
CREATE TRIGGER trg_ktm_feature_reference_reconciliation_delivery_attempts_truncate_append_only
  BEFORE TRUNCATE
  ON app.ktm_feature_reference_reconciliation_delivery_attempts
  FOR EACH STATEMENT EXECUTE FUNCTION app.guard_ktm_feature_reference_reconciliation_append_only();
ALTER TABLE app.ktm_feature_reference_reconciliation_delivery_attempts
  ENABLE ALWAYS TRIGGER trg_ktm_feature_reference_reconciliation_delivery_attempts_truncate_append_only;
CREATE TRIGGER trg_ktm_feature_reference_reconciliation_applied_receipts_append_only
  BEFORE INSERT OR UPDATE OR DELETE
  ON app.ktm_feature_reference_reconciliation_applied_receipts
  FOR EACH ROW EXECUTE FUNCTION app.guard_ktm_feature_reference_reconciliation_append_only();
ALTER TABLE app.ktm_feature_reference_reconciliation_applied_receipts
  ENABLE ALWAYS TRIGGER trg_ktm_feature_reference_reconciliation_applied_receipts_append_only;
CREATE TRIGGER trg_ktm_feature_reference_reconciliation_applied_receipts_truncate_append_only
  BEFORE TRUNCATE
  ON app.ktm_feature_reference_reconciliation_applied_receipts
  FOR EACH STATEMENT EXECUTE FUNCTION app.guard_ktm_feature_reference_reconciliation_append_only();
ALTER TABLE app.ktm_feature_reference_reconciliation_applied_receipts
  ENABLE ALWAYS TRIGGER trg_ktm_feature_reference_reconciliation_applied_receipts_truncate_append_only;
CREATE TRIGGER trg_ktm_feature_reference_reconciliation_impacts_append_only
  BEFORE INSERT OR UPDATE OR DELETE
  ON app.ktm_feature_reference_reconciliation_impacts
  FOR EACH ROW EXECUTE FUNCTION app.guard_ktm_feature_reference_reconciliation_append_only();
ALTER TABLE app.ktm_feature_reference_reconciliation_impacts
  ENABLE ALWAYS TRIGGER trg_ktm_feature_reference_reconciliation_impacts_append_only;
CREATE TRIGGER trg_ktm_feature_reference_reconciliation_impacts_truncate_append_only
  BEFORE TRUNCATE
  ON app.ktm_feature_reference_reconciliation_impacts
  FOR EACH STATEMENT EXECUTE FUNCTION app.guard_ktm_feature_reference_reconciliation_append_only();
ALTER TABLE app.ktm_feature_reference_reconciliation_impacts
  ENABLE ALWAYS TRIGGER trg_ktm_feature_reference_reconciliation_impacts_truncate_append_only;
{canonical_reconciliation_seed}
"""

    setup_sql = f"""
CREATE SCHEMA app AUTHORIZATION {_quoted(hotswap_role)};
REVOKE ALL ON SCHEMA app FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO {_quoted(app_role)};
CREATE TABLE app.widgets (
  id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  value integer NOT NULL DEFAULT 0
);
INSERT INTO app.widgets (value) VALUES (0);
CREATE TABLE app.ktm_cache_target_boundary_audits (
  transaction_id uuid PRIMARY KEY,
  contract_version text NOT NULL,
  status text NOT NULL,
  schema_revision text NOT NULL,
  CONSTRAINT ck_ktm_ct_boundary_contract CHECK (
    contract_version = 'pinvi-cache-target-final-boundary/v1'
    AND status = 'succeeded'
    AND schema_revision = '20260824_0063'
  )
);
{reconciliation_schema}
{table_grants}
{extra_grant}
{default_acl}
"""  # noqa: S608 - 역할명은 내부 생성값을 quoted로 제한한다.
    _require_success(_psql(tools, hotswap_url, setup_sql))

    requires_definer_proof = kind in {"security_definer", "cross_schema_security_definer"}
    if requires_definer_proof:
        function_schema = "app" if kind == "security_definer" else "public"
        definer_sql = f"""
CREATE FUNCTION {function_schema}.definer_write() RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_catalog
AS $$
BEGIN
  UPDATE app.widgets SET value = value + 1 WHERE id = 1;
END;
$$;
REVOKE INSERT, UPDATE, DELETE ON TABLE app.widgets FROM {_quoted(app_role)};
"""  # noqa: S608 - 역할명은 내부 생성값을 quoted로 제한한다.
        _require_success(
            _psql(
                tools,
                root_target_url if kind == "cross_schema_security_definer" else hotswap_url,
                definer_sql,
            )
        )
        _require_success(_psql(tools, app_url, f"SELECT {function_schema}.definer_write();"))
        proof = _psql(tools, hotswap_url, "SELECT value FROM app.widgets WHERE id = 1;")
        _require_success(proof)
        assert proof.stdout.strip() == "1"
        _require_success(
            _psql(
                tools,
                hotswap_url,
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO {_quoted(app_role)};",
            )
        )

    expected_failure = {
        "canonical": "",
        "trigger_noop": "M05 append-only trigger unexpectedly allowed",
        "trigger_truncate_noop": "M05 append-only trigger unexpectedly allowed TRUNCATE on delivery attempts",
        "audit_trigger_noop": "restored admin audit log is missing a canonical ENABLE ALWAYS append-only guard",
        "audit_content_noop": "restored admin audit hash chain or content hash is invalid",
        "missing_audit": "schema-swap requires canonical single-runtime-role ACLs",
        "acl": "schema-swap requires canonical single-runtime-role ACLs",
        "extra": "schema-swap requires exactly one canonical runtime writer role",
        "global_default": "schema-swap requires canonical single-runtime-role ACLs",
        "security_definer": "schema-swap requires canonical single-runtime-role ACLs",
        "cross_schema_security_definer": "schema-swap requires canonical single-runtime-role ACLs",
    }[kind]
    return _Case(
        database=database,
        fence_role=fence_role,
        hotswap_role=hotswap_role,
        app_role=app_role,
        app_url=app_url,
        fence_url=fence_url,
        hotswap_url=hotswap_url,
        expected_failure=expected_failure,
        expected_delete=kind != "acl",
        requires_definer_proof=requires_definer_proof,
    )


def _snapshot(tools: dict[str, str], hotswap_url: str, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = directory / "m05-preflight.dump"
    result = _run(
        [
            tools["pg_dump"],
            "--format=custom",
            "--schema=app",
            f"--file={snapshot}",
            hotswap_url,
        ]
    )
    _require_success(result)
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    snapshot.with_name(f"{snapshot.name}.sha256").write_text(
        f"{digest}  {snapshot.name}\n", encoding="utf-8"
    )
    return snapshot


def _identity(tools: dict[str, str], hotswap_url: str) -> tuple[str, str, str, str, str]:
    result = _psql(
        tools,
        hotswap_url,
        "SELECT current_database(), d.oid::text, (pg_control_system()).system_identifier::text, "
        "COALESCE(host(inet_server_addr()), ''), inet_server_port()::text "
        "FROM pg_database d WHERE d.datname = current_database();",
    )
    _require_success(result)
    values = tuple(result.stdout.strip().split("|"))
    assert len(values) == 5
    return values[0], values[1], values[2], values[3], values[4]


def _assert_source_unchanged(tools: dict[str, str], case: _Case, restore_schema: str) -> None:
    result = _psql(
        tools,
        case.hotswap_url,
        f"""
SELECT to_regnamespace('app') IS NOT NULL,
       to_regnamespace('{restore_schema}') IS NULL,
       has_table_privilege('{case.app_role}', 'app.widgets', 'INSERT'),
       has_table_privilege('{case.app_role}', 'app.widgets', 'DELETE');
""",
    )
    _require_success(result)
    app_exists, restore_missing, can_insert, can_delete = result.stdout.strip().split("|")
    assert app_exists == "t"
    assert restore_missing == "t"
    assert can_insert == "t"
    assert (can_delete == "t") is case.expected_delete


def _assert_source_not_swapped(tools: dict[str, str], case: _Case, previous_schema: str) -> None:
    result = _psql(
        tools,
        case.hotswap_url,
        f"""
SELECT to_regnamespace('app') IS NOT NULL,
       to_regnamespace('{previous_schema}') IS NULL,
       has_table_privilege('{case.app_role}', 'app.widgets', 'INSERT'),
       has_table_privilege('{case.app_role}', 'app.widgets', 'DELETE');
""",
    )
    _require_success(result)
    app_exists, previous_missing, can_insert, can_delete = result.stdout.strip().split("|")
    assert app_exists == "t"
    assert previous_missing == "t"
    assert can_insert == "t"
    assert (can_delete == "t") is case.expected_delete


def test_restore_hotswap_preflight_rejects_real_noncanonical_topologies_before_mutation(
    tmp_path: Path,
) -> None:
    """ACL/default-ACL/definer 우회는 write fence나 restore 전에 막힌다."""
    tools = _require_tools()
    try:
        import docker  # noqa: F401
        from testcontainers.postgres import PostgresContainer
    except Exception:
        pytest.skip("docker SDK 미설치 — M05 실제 권한 검증을 건너뜁니다.")

    suffix = uuid.uuid4().hex[:8]
    container = PostgresContainer(
        "postgres:16-alpine",
        username="m05_root",
        password=TEST_PASSWORD,
        dbname="m05_root",
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        root_url = _database_url(host=host, port=port, role="m05_root", database="m05_root")
        cases = [
            _create_case(
                tools=tools,
                root_url=root_url,
                host=host,
                port=port,
                suffix=suffix,
                kind=kind,
            )
            for kind in (
                "acl",
                "extra",
                "global_default",
                "security_definer",
                "cross_schema_security_definer",
                "audit_content_noop",
                "missing_audit",
            )
        ]

        # 복원 실행 중 writer inventory에 root superuser가 섞이지 않도록, 모든 fixture를
        # 만든 뒤 container lifecycle로만 정리하는 root login을 닫는다.
        _require_success(_psql(tools, root_url, "ALTER ROLE m05_root NOLOGIN;"))

        for index, case in enumerate(cases):
            snapshot = _snapshot(tools, case.hotswap_url, tmp_path / f"snapshot-{index}")
            identity = _identity(tools, case.hotswap_url)
            restore_schema = f"app_restore_{index}_{suffix}"
            previous_schema = f"app_previous_{index}_{suffix}"
            env = os.environ.copy()
            env.update(
                {
                    # This fixture exercises ACL preflight only. Production/staging
                    # provenance is covered by the root-owned M05 drill evidence gate.
                    "PINVI_ENVIRONMENT": "development",
                    "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
                    "PINVI_RESTORE_PRIVATE_TOOL_COPY": "1",
                    "PINVI_RESTORE_DATABASE_URL": case.hotswap_url,
                    "PINVI_RESTORE_FENCE_DATABASE_URL": case.fence_url,
                    "PINVI_RESTORE_APP_ROLE": case.app_role,
                    "PINVI_RESTORE_PG_RESTORE_BIN": tools["pg_restore"],
                    "PINVI_RESTORE_PG_RESTORE_SHA256": hashlib.sha256(
                        Path(tools["pg_restore"]).read_bytes()
                    ).hexdigest(),
                    "PINVI_RESTORE_PSQL_BIN": tools["psql"],
                    "PINVI_RESTORE_PSQL_SHA256": hashlib.sha256(
                        Path(tools["psql"]).read_bytes()
                    ).hexdigest(),
                    "PINVI_RESTORE_BASH_BIN": tools["bash"],
                    "PINVI_RESTORE_BASH_SHA256": hashlib.sha256(
                        Path(tools["bash"]).read_bytes()
                    ).hexdigest(),
                    "PINVI_RESTORE_EXPECTED_DATABASE_NAME": identity[0],
                    "PINVI_RESTORE_EXPECTED_DATABASE_OID": identity[1],
                    "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER": identity[2],
                    "PINVI_RESTORE_EXPECTED_HOSTADDR": identity[3],
                    "PINVI_RESTORE_EXPECTED_PORT": identity[4],
                }
            )
            env.pop("PINVI_M05_RESTORE_TEST_MODE", None)
            result = _run(
                [
                    tools["bash"],
                    str(HOTSWAP_SCRIPT),
                    "run",
                    str(snapshot),
                    restore_schema,
                    previous_schema,
                ],
                env=env,
            )

            assert result.returncode == 3, result.stdout + result.stderr
            assert case.expected_failure in result.stdout + result.stderr
            _assert_source_unchanged(tools, case, restore_schema)
    finally:
        container.stop()


@pytest.mark.parametrize(
    ("kind", "expected_failure"),
    [
        ("trigger_noop", "M05 append-only trigger unexpectedly allowed"),
        (
            "trigger_truncate_noop",
            "M05 append-only trigger unexpectedly allowed TRUNCATE on delivery attempts",
        ),
        (
            "audit_trigger_noop",
            "restored admin audit log is missing a canonical ENABLE ALWAYS append-only guard",
        ),
    ],
)
def test_restore_hotswap_rejects_real_append_only_trigger_drift_before_schema_switch(
    tmp_path: Path, kind: str, expected_failure: str
) -> None:
    """Catalog-shaped DML/TRUNCATE drift must not reach the schema rename."""

    tools = _require_tools()
    try:
        import docker  # noqa: F401
        from testcontainers.postgres import PostgresContainer
    except Exception:
        pytest.skip("docker SDK 미설치 — M05 실제 trigger 의미 검증을 건너뜁니다.")

    suffix = uuid.uuid4().hex[:8]
    container = PostgresContainer(
        "postgres:16-alpine",
        username="m05_root",
        password=TEST_PASSWORD,
        dbname="m05_root",
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        root_url = _database_url(host=host, port=port, role="m05_root", database="m05_root")
        case = _create_case(
            tools=tools,
            root_url=root_url,
            host=host,
            port=port,
            suffix=suffix,
            kind=kind,
        )
        identity = _identity(tools, case.hotswap_url)
        snapshot = _snapshot(tools, case.hotswap_url, tmp_path / f"{kind}-snapshot")
        _require_success(_psql(tools, root_url, "ALTER ROLE m05_root NOLOGIN;"))

        restore_schema = f"app_restore_{suffix}"
        previous_schema = f"app_previous_{suffix}"
        env = os.environ.copy()
        env.update(
            {
                "PINVI_ENVIRONMENT": "development",
                "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
                "PINVI_RESTORE_PRIVATE_TOOL_COPY": "1",
                "PINVI_RESTORE_DATABASE_URL": case.hotswap_url,
                "PINVI_RESTORE_FENCE_DATABASE_URL": case.fence_url,
                "PINVI_RESTORE_APP_ROLE": case.app_role,
                "PINVI_RESTORE_ALLOW_NO_DRAIN": "1",
                "PINVI_RESTORE_DRAIN_VERIFIED": "1",
                "PINVI_RESTORE_PG_RESTORE_BIN": tools["pg_restore"],
                "PINVI_RESTORE_PG_RESTORE_SHA256": hashlib.sha256(
                    Path(tools["pg_restore"]).read_bytes()
                ).hexdigest(),
                "PINVI_RESTORE_PSQL_BIN": tools["psql"],
                "PINVI_RESTORE_PSQL_SHA256": hashlib.sha256(
                    Path(tools["psql"]).read_bytes()
                ).hexdigest(),
                "PINVI_RESTORE_BASH_BIN": tools["bash"],
                "PINVI_RESTORE_BASH_SHA256": hashlib.sha256(
                    Path(tools["bash"]).read_bytes()
                ).hexdigest(),
                "PINVI_RESTORE_EXPECTED_DATABASE_NAME": identity[0],
                "PINVI_RESTORE_EXPECTED_DATABASE_OID": identity[1],
                "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER": identity[2],
                "PINVI_RESTORE_EXPECTED_HOSTADDR": identity[3],
                "PINVI_RESTORE_EXPECTED_PORT": identity[4],
            }
        )
        env.pop("PINVI_M05_RESTORE_TEST_MODE", None)
        result = _run(
            [
                tools["bash"],
                str(HOTSWAP_SCRIPT),
                "run",
                str(snapshot),
                restore_schema,
                previous_schema,
            ],
            env=env,
        )

        assert result.returncode == 3, result.stdout + result.stderr
        assert expected_failure in result.stderr
        _assert_source_not_swapped(tools, case, previous_schema)
    finally:
        container.stop()


def test_restore_hotswap_real_canonical_topology_completes_and_releases_fence(
    tmp_path: Path,
) -> None:
    """Dedicated fence owner와 direct pg_signal executor가 실제 schema swap을 완주한다."""

    tools = _require_tools()
    try:
        import docker  # noqa: F401
        from testcontainers.postgres import PostgresContainer
    except Exception:
        pytest.skip("docker SDK 미설치 — M05 실제 hotswap 검증을 건너뜁니다.")

    suffix = uuid.uuid4().hex[:8]
    container = PostgresContainer(
        "postgres:16-alpine",
        username="m05_root",
        password=TEST_PASSWORD,
        dbname="m05_root",
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        root_url = _database_url(host=host, port=port, role="m05_root", database="m05_root")
        case = _create_case(
            tools=tools,
            root_url=root_url,
            host=host,
            port=port,
            suffix=suffix,
            kind="canonical",
        )
        before_identity = _identity(tools, case.hotswap_url)
        fence_topology = _psql(
            tools,
            case.fence_url,
            """
SELECT current_user,
       (SELECT role.rolname
        FROM pg_database database
        JOIN pg_roles role ON role.oid = database.datdba
        WHERE database.datname = current_database()),
       (SELECT NOT rolinherit FROM pg_roles WHERE rolname = current_user),
       NOT EXISTS (
         SELECT 1
         FROM pg_auth_members membership
         JOIN pg_roles role ON role.oid = membership.member OR role.oid = membership.roleid
         WHERE role.rolname = current_user
       );
""",
        )
        _require_success(fence_topology)
        assert fence_topology.stdout.strip().split("|")[2:] == ["t", "t"]
        before_schema = _psql(
            tools,
            case.hotswap_url,
            "SELECT oid::text FROM pg_namespace WHERE nspname = 'app';",
        )
        _require_success(before_schema)
        before_schema_oid = before_schema.stdout.strip()
        assert before_schema_oid
        snapshot = _snapshot(tools, case.hotswap_url, tmp_path / "canonical-snapshot")
        _require_success(_psql(tools, root_url, "ALTER ROLE m05_root NOLOGIN;"))

        restore_schema = f"app_restore_{suffix}"
        previous_schema = f"app_previous_{suffix}"
        env = os.environ.copy()
        env.update(
            {
                "PINVI_ENVIRONMENT": "development",
                "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
                "PINVI_RESTORE_PRIVATE_TOOL_COPY": "1",
                "PINVI_RESTORE_DATABASE_URL": case.hotswap_url,
                "PINVI_RESTORE_FENCE_DATABASE_URL": case.fence_url,
                "PINVI_RESTORE_APP_ROLE": case.app_role,
                "PINVI_RESTORE_ALLOW_NO_DRAIN": "1",
                "PINVI_RESTORE_DRAIN_VERIFIED": "1",
                "PINVI_RESTORE_PG_RESTORE_BIN": tools["pg_restore"],
                "PINVI_RESTORE_PG_RESTORE_SHA256": hashlib.sha256(
                    Path(tools["pg_restore"]).read_bytes()
                ).hexdigest(),
                "PINVI_RESTORE_PSQL_BIN": tools["psql"],
                "PINVI_RESTORE_PSQL_SHA256": hashlib.sha256(
                    Path(tools["psql"]).read_bytes()
                ).hexdigest(),
                "PINVI_RESTORE_BASH_BIN": tools["bash"],
                "PINVI_RESTORE_BASH_SHA256": hashlib.sha256(
                    Path(tools["bash"]).read_bytes()
                ).hexdigest(),
                "PINVI_RESTORE_EXPECTED_DATABASE_NAME": before_identity[0],
                "PINVI_RESTORE_EXPECTED_DATABASE_OID": before_identity[1],
                "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER": before_identity[2],
                "PINVI_RESTORE_EXPECTED_HOSTADDR": before_identity[3],
                "PINVI_RESTORE_EXPECTED_PORT": before_identity[4],
            }
        )
        env.pop("PINVI_M05_RESTORE_TEST_MODE", None)

        result = _run(
            [
                tools["bash"],
                str(HOTSWAP_SCRIPT),
                "run",
                str(snapshot),
                restore_schema,
                previous_schema,
            ],
            env=env,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "RESTORE_PHASE=switching:success:schema-swap completed" in result.stdout
        reflection_insert = _psql(
            tools,
            case.hotswap_url,
            f"""
INSERT INTO app.admin_audit_log (
  actor_user_id, action, resource_type, resource_id, before_state, after_state,
  access_reason, target_pii_fields, ip_hash, user_agent, request_id, prev_hash,
  content_hash, occurred_at
) VALUES (
  '40000000-0000-4000-8000-000000000001', 'm05.reflection', 'restore', NULL,
  NULL, NULL, NULL, NULL, repeat('6', 64), NULL,
  '40000000-0000-4000-8000-000000000003',
  {_audit_content_hash("0" * 64, action="m05.fixture", ip_hash="1" * 64, request_id="40000000-0000-4000-8000-000000000002", occurred_at=AUDIT_FIXTURE_OCCURRED_AT)!r},
  {_audit_content_hash(_audit_content_hash("0" * 64, action="m05.fixture", ip_hash="1" * 64, request_id="40000000-0000-4000-8000-000000000002", occurred_at=AUDIT_FIXTURE_OCCURRED_AT), action="m05.reflection", ip_hash="6" * 64, request_id="40000000-0000-4000-8000-000000000003", occurred_at="2026-08-24T03:01:00+00:00")!r},
  TIMESTAMPTZ '2026-08-24 03:01:00+00'
);
""",  # noqa: S608 - test fixture identifiers are generated locally.
        )
        _require_success(reflection_insert)
        after = _psql(
            tools,
            case.hotswap_url,
            f"""
SELECT (SELECT oid::text FROM pg_namespace WHERE nspname = 'app'),
       (SELECT oid::text FROM pg_namespace WHERE nspname = '{previous_schema}'),
       to_regnamespace('{restore_schema}') IS NULL,
       has_database_privilege('{case.app_role}', current_database(), 'CONNECT'),
       has_schema_privilege('{case.app_role}', 'app', 'USAGE'),
       has_table_privilege('{case.app_role}', 'app.widgets', 'SELECT, INSERT, UPDATE, DELETE'),
       has_database_privilege('{case.fence_role}', current_database(), 'CREATE'),
       (SELECT count(*)::text
        FROM app.ktm_feature_reference_reconciliation_applied_receipts),
       (SELECT event_sequence::text
        FROM app.ktm_feature_reference_reconciliation_applied_receipts
        WHERE event_id = '40000000-0000-4000-8000-000000000010'),
       (SELECT count(*)::text
        FROM app.ktm_feature_reference_reconciliation_impacts
        WHERE event_id = '40000000-0000-4000-8000-000000000010'),
       (SELECT count(*)::text FROM app.admin_audit_log),
       NOT EXISTS (
         WITH ordered AS (
           SELECT prev_hash, content_hash,
                  lag(content_hash) OVER (ORDER BY log_id) AS previous_content_hash
           FROM app.admin_audit_log
         )
         SELECT 1
         FROM ordered
         WHERE prev_hash <> COALESCE(previous_content_hash, repeat('0', 64))
       ),
       NOT EXISTS (
         SELECT 1 FROM pg_locks
         WHERE locktype = 'advisory'
           AND classid = 1414679892
           AND objid = 1213421392
           AND granted
       );
""",  # noqa: S608 - test fixture identifiers are generated locally.
        )
        _require_success(after)
        (
            app_oid,
            previous_oid,
            restore_missing,
            app_connect,
            app_usage,
            app_dml,
            fence_create,
            receipt_count,
            receipt_sequence,
            impact_count,
            audit_count,
            audit_chain_valid,
            lock_gone,
        ) = after.stdout.strip().split("|")
        assert app_oid and previous_oid and app_oid != before_schema_oid
        assert previous_oid == before_schema_oid
        assert restore_missing == "t"
        assert app_connect == "t"
        assert app_usage == "t"
        assert app_dml == "t"
        assert fence_create == "t"
        assert receipt_count == "1"
        assert receipt_sequence == "1"
        assert impact_count == "1"
        assert audit_count == "2"
        assert audit_chain_valid == "t"
        assert lock_gone == "t"

        failure_snapshot = _snapshot(tools, case.hotswap_url, tmp_path / "release-failure-snapshot")
        failure_identity = _identity(tools, case.hotswap_url)
        failure_restore_schema = f"app_restore_release_failure_{suffix}"
        failure_previous_schema = f"app_previous_release_failure_{suffix}"
        failure_env = os.environ.copy()
        failure_env.update(
            {
                "PINVI_ENVIRONMENT": "test",
                "PINVI_M05_RESTORE_TEST_MODE": "1",
                "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
                "PINVI_RESTORE_DATABASE_URL": case.hotswap_url,
                "PINVI_RESTORE_FENCE_DATABASE_URL": case.fence_url,
                "PINVI_RESTORE_APP_ROLE": case.app_role,
                "PINVI_RESTORE_ALLOW_NO_DRAIN": "1",
                "PINVI_RESTORE_DRAIN_VERIFIED": "1",
                "PINVI_RESTORE_TEST_FAIL_RELEASE_ONCE": "1",
                "PINVI_RESTORE_PG_RESTORE_BIN": tools["pg_restore"],
                "PINVI_RESTORE_PSQL_BIN": tools["psql"],
                "PINVI_RESTORE_BASH_BIN": tools["bash"],
                "PINVI_RESTORE_EXPECTED_DATABASE_NAME": failure_identity[0],
                "PINVI_RESTORE_EXPECTED_DATABASE_OID": failure_identity[1],
                "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER": failure_identity[2],
                "PINVI_RESTORE_EXPECTED_HOSTADDR": failure_identity[3],
                "PINVI_RESTORE_EXPECTED_PORT": failure_identity[4],
            }
        )
        failure_result = _run(
            [
                tools["bash"],
                str(HOTSWAP_SCRIPT),
                "run",
                str(failure_snapshot),
                failure_restore_schema,
                failure_previous_schema,
            ],
            env=failure_env,
        )
        assert failure_result.returncode == 3, failure_result.stdout + failure_result.stderr
        failure_output = failure_result.stdout + failure_result.stderr
        assert "schema-swap release failed; rollback will be attempted" in failure_output
        assert "schema-swap rolled back after fence release failure" in failure_output
        after_failure = _psql(
            tools,
            case.hotswap_url,
            f"""
SELECT (SELECT oid::text FROM pg_namespace WHERE nspname = 'app'),
       to_regnamespace('{failure_previous_schema}') IS NULL,
       to_regnamespace('{failure_restore_schema}') IS NULL,
       NOT EXISTS (
         SELECT 1 FROM pg_locks
         WHERE locktype = 'advisory'
           AND classid = 1414679892
           AND objid = 1213421392
           AND granted
       );
""",  # noqa: S608 - test fixture identifiers are generated locally.
        )
        _require_success(after_failure)
        failed_app_oid, failed_previous_missing, failed_restore_missing, failed_lock_gone = (
            after_failure.stdout.strip().split("|")
        )
        assert failed_app_oid == app_oid
        assert failed_previous_missing == "t"
        assert failed_restore_missing == "t"
        assert failed_lock_gone == "t"
    finally:
        container.stop()
