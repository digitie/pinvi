"""현재 main과 M05 계약을 새 Alembic 기준선 위에 한 번에 적용한다.

Revision ID: 20260824_0101
Revises: 20260824_0100
Create Date: 2026-08-24

N150의 `0061` 기준선 뒤에 합류한 location-audit·동의 이력·좌표 출처 변경과 M05의
옛 `0062`~`0065` DDL을 모두 이 revision에 통합한다. 이 revision은 새 설치와
ADR-065의 명시적 `0061` rebaseline 뒤에만 실행된다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0101"
down_revision: str | None = "20260824_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_M05_SCHEMA_FILE = "20260824_0101_m05_activation.sql"
_M05_SCHEMA_SHA256 = "128e2b374842ca2e9755041815457625a8c2212c013c1bafd6adb93db42128cb"
_M05_SCHEMA_STATEMENT_COUNT = 21
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")
_ROLE_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")
_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0101'"
)
_LOCATION_ACCESS_LOG_PURPOSE_CONSTRAINT = "ck_location_access_log_ck_location_access_log_purpose"
_LOCATION_ACCESS_LOG_PURPOSES = (
    "'viewport_query', 'nearby_attractions', 'weather_at_coord', "
    "'feature_request', 'region_covering', 'region_radius', 'third_party_place_search', "
    "'reverse_geocode'"
)
_LOCATION_AUDIT_COORD_SOURCE_CHECK = (
    "coord_source IS NULL OR coord_source IN ('device', 'map_pick')"
)
_LEGACY_REBASELINE_RECEIPT_PATH_ENV = "PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH"
_LEGACY_REBASELINE_RECEIPT_FIELDS = frozenset(
    {
        "action",
        "backup_manifest_sha256",
        "backup_sha256",
        "completed_at",
        "preflight",
        "state",
        "target_manifest_sha256",
        "version",
    }
)
_LEGACY_REBASELINE_PREFLIGHT_FIELDS = frozenset(
    {
        "app_data_content_sha256",
        "app_data_rows",
        "app_data_table_lines",
        "catalog_lines",
        "catalog_sha256",
        "current_user",
        "database_name",
        "database_oid",
        "expected_catalog_lines",
        "expected_catalog_sha256",
        "server_addr",
        "server_port",
        "server_version_num",
        "session_user",
        "system_identifier",
        "version_rows",
    }
)
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _split_postgres_statements(source: str) -> tuple[str, ...]:
    """dollar-quoted function body를 보존한 채 top-level SQL 문만 분리한다."""

    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    quote: str | None = None
    dollar_quote: str | None = None

    while index < len(source):
        if dollar_quote is not None:
            if source.startswith(dollar_quote, index):
                buffer.append(dollar_quote)
                index += len(dollar_quote)
                dollar_quote = None
            else:
                buffer.append(source[index])
                index += 1
            continue

        if quote is not None:
            character = source[index]
            buffer.append(character)
            index += 1
            if character == quote:
                if index < len(source) and source[index] == quote:
                    buffer.append(source[index])
                    index += 1
                else:
                    quote = None
            continue

        if source.startswith("--", index):
            newline = source.find("\n", index)
            index = len(source) if newline == -1 else newline + 1
            continue
        if source.startswith("/*", index):
            comment_end = source.find("*/", index + 2)
            if comment_end == -1:
                raise RuntimeError("0101 M05 schema artifact has an unterminated block comment")
            index = comment_end + 2
            continue

        character = source[index]
        if character in "'\"":
            quote = character
            buffer.append(character)
            index += 1
            continue
        if character == "$":
            match = _DOLLAR_QUOTE.match(source, index)
            if match is not None:
                dollar_quote = match.group(0)
                buffer.append(dollar_quote)
                index += len(dollar_quote)
                continue
        if character == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer.clear()
            index += 1
            continue
        buffer.append(character)
        index += 1

    if quote is not None or dollar_quote is not None:
        raise RuntimeError("0101 M05 schema artifact has an unterminated SQL literal")
    trailing = "".join(buffer).strip()
    if trailing:
        raise RuntimeError("0101 M05 schema artifact has a trailing SQL statement")
    if len(statements) != _M05_SCHEMA_STATEMENT_COUNT:
        raise RuntimeError("0101 M05 schema artifact statement count is invalid")
    return tuple(statements)


def _m05_schema_statements() -> tuple[str, ...]:
    path = Path(__file__).resolve().parents[1] / "baselines" / _M05_SCHEMA_FILE
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RuntimeError("0101 M05 schema artifact is unavailable") from exc
    if hashlib.sha256(payload).hexdigest() != _M05_SCHEMA_SHA256:
        raise RuntimeError("0101 M05 schema artifact digest is invalid")
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("0101 M05 schema artifact is not UTF-8") from exc
    return _split_postgres_statements(source)


def _reject_unsafe_m05_default_privileges(bind: sa.Connection) -> None:
    """M05 object에 권한이 전파될 default ACL이 있으면 DDL 전에 중단한다."""

    unsafe_default_acl = bind.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_default_acl default_acl
                WHERE default_acl.defaclrole = current_user::regrole
                  AND (
                    default_acl.defaclnamespace = 0
                    OR default_acl.defaclnamespace = (
                        SELECT namespace.oid
                        FROM pg_namespace namespace
                        WHERE namespace.nspname = 'ops'
                    )
                  )
            )
            """
        )
    )
    if unsafe_default_acl is True:
        raise RuntimeError("0101 rejects migration-owner default privileges for M05 objects")


def _reject_existing_m05_objects(bind: sa.Connection) -> None:
    """부분 적용된 과거 M05 object 위로 덮어쓰지 않는다."""

    existing = bind.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_class relation
                JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = 'ops'
                  AND relation.relname IN (
                    'm05_activation_database_anchor',
                    'm05_hotswap_release_receipts'
                  )
                UNION ALL
                SELECT 1
                FROM pg_proc procedure
                JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
                WHERE namespace.nspname = 'ops'
                  AND procedure.proname IN (
                    'guard_m05_activation_database_anchor_append_only',
                    'guard_m05_hotswap_release_receipts_append_only',
                    'm05_hotswap_release_topology_sha256',
                    'record_m05_hotswap_release_receipt',
                    'verify_m05_hotswap_release_receipt'
                  )
            )
            """
        )
    )
    if existing is True:
        raise RuntimeError("0101 refuses to replace pre-existing M05 objects")


def _configured_migration_owner() -> str | None:
    """Return the explicitly configured M05 receipt owner, if this is a managed run."""

    configured = os.environ.get("PINVI_MIGRATION_OWNER")
    if configured is None or not configured.strip():
        return None
    if configured != configured.strip() or _ROLE_IDENTIFIER.fullmatch(configured) is None:
        raise RuntimeError("0101 migration owner configuration is invalid")
    return configured


def _configured_migrator_login() -> str | None:
    """Return the explicitly configured one-shot login that may activate owner roles."""

    configured = os.environ.get("PINVI_MIGRATOR_DB_USER")
    if configured is None or not configured.strip():
        return None
    if configured != configured.strip() or _ROLE_IDENTIFIER.fullmatch(configured) is None:
        raise RuntimeError("0101 migrator login configuration is invalid")
    return configured


def _managed_deployment_requires_migration_owner() -> bool:
    """Keep staging/production M05 receipt ownership fail-closed."""

    environment = os.environ.get("PINVI_ENVIRONMENT", "").strip().lower()
    return environment in {"staging", "production"}


def _legacy_rebaseline_profile() -> bool:
    """Allow the one approved 0061 owner path without broadening normal migrator authority."""

    configured = os.environ.get("PINVI_M05_LEGACY_REBASELINE", "0")
    if configured == "0":
        return False
    if configured == "1":
        return True
    raise RuntimeError("0101 legacy rebaseline profile configuration is invalid")


def _read_legacy_rebaseline_receipt() -> dict[str, object]:
    """Read the root-only applied 0061→0100 receipt without a pathname race."""

    configured = os.environ.get(_LEGACY_REBASELINE_RECEIPT_PATH_ENV, "")
    if not configured:
        raise RuntimeError("0101 legacy rebaseline requires an applied root-owned receipt")
    path = Path(configured)
    if not path.is_absolute():
        raise RuntimeError("0101 legacy rebaseline receipt path must be absolute")
    if os.geteuid() != 0:
        raise RuntimeError("0101 legacy rebaseline requires a root OS account")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise RuntimeError("0101 legacy rebaseline receipt must be root-owned mode 0600")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            payload = stream.read(64 * 1024 + 1)
    except OSError as exc:
        raise RuntimeError("0101 legacy rebaseline receipt is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > 64 * 1024:
        raise RuntimeError("0101 legacy rebaseline receipt is too large")

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise RuntimeError("0101 legacy rebaseline receipt has duplicate JSON keys")
            value[key] = item
        return value

    try:
        receipt = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("0101 legacy rebaseline receipt is not valid JSON") from exc
    if not isinstance(receipt, dict) or frozenset(receipt) != _LEGACY_REBASELINE_RECEIPT_FIELDS:
        raise RuntimeError("0101 legacy rebaseline receipt fields are invalid")
    if (
        receipt["action"] != "0061_to_0100_rebaseline"
        or receipt["version"] != 1
        or receipt["state"] != "applied"
        or not isinstance(receipt["completed_at"], str)
        or not receipt["completed_at"]
        or not isinstance(receipt["preflight"], dict)
        or any(
            not isinstance(receipt[field], str) or _SHA256.fullmatch(receipt[field]) is None
            for field in (
                "backup_manifest_sha256",
                "backup_sha256",
                "target_manifest_sha256",
            )
        )
    ):
        raise RuntimeError("0101 legacy rebaseline receipt values are invalid")
    preflight = receipt["preflight"]
    if frozenset(preflight) != _LEGACY_REBASELINE_PREFLIGHT_FIELDS:
        raise RuntimeError("0101 legacy rebaseline receipt preflight is invalid")
    if (
        preflight["version_rows"] != ["20260821_0061"]
        or any(
            not isinstance(preflight[field], str) or not preflight[field]
            for field in (
                "database_name",
                "system_identifier",
                "server_addr",
            )
        )
        or any(
            not isinstance(preflight[field], int) or isinstance(preflight[field], bool)
            for field in ("database_oid", "server_port")
        )
        or preflight["database_oid"] <= 0
        or not 1 <= preflight["server_port"] <= 65535
    ):
        raise RuntimeError("0101 legacy rebaseline receipt preflight is invalid")
    return receipt


def _assert_legacy_rebaseline_handoff(bind: sa.Connection) -> None:
    """Bind the privileged 0101 legacy path to its completed 0061→0100 receipt."""

    if not _legacy_rebaseline_profile():
        return
    receipt = _read_legacy_rebaseline_receipt()
    preflight = receipt["preflight"]
    assert isinstance(preflight, dict)
    expected_identity = {
        key: preflight[key]
        for key in (
            "database_name",
            "database_oid",
            "system_identifier",
            "server_addr",
            "server_port",
        )
    }
    identity_payload = bind.scalar(
        sa.text(
            """
            SELECT json_build_object(
                'database_name', current_database(),
                'database_oid', (
                    SELECT database_row.oid
                    FROM pg_database database_row
                    WHERE database_row.datname = current_database()
                )::bigint,
                'system_identifier', (pg_control_system()).system_identifier::text,
                'server_addr', COALESCE(inet_server_addr()::text, ''),
                'server_port', COALESCE(inet_server_port(), 0)::integer
            )::text
            """
        )
    )
    version_rows_payload = bind.scalar(
        sa.text(
            """
            SELECT COALESCE(
                json_agg(version_num ORDER BY version_num)::text,
                '[]'
            )
            FROM app.alembic_version
            """
        )
    )
    try:
        identity = json.loads(identity_payload)
        version_rows = json.loads(version_rows_payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("0101 legacy rebaseline database proof is invalid") from exc
    if identity != expected_identity:
        raise RuntimeError("0101 legacy rebaseline receipt does not match this database")
    if version_rows != ["20260824_0100"]:
        raise RuntimeError("0101 legacy rebaseline requires the 0100 handoff row")


def _activate_m05_migration_owner(bind: sa.Connection) -> str | None:
    """Switch only the M05 portion to its non-login receipt owner.

    The pre-existing app tables are still changed by their owner.  This matters for the
    one supported 0061 rebaseline: ADR-063 deliberately does not rewrite old object
    ownership while stamping 0100.  Fresh installs instead arrive here through the
    non-inheriting one-shot migrator login whose database default role is the app owner.
    """

    migration_owner = _configured_migration_owner()
    migrator_login = _configured_migrator_login()
    legacy_rebaseline = _legacy_rebaseline_profile()
    if migration_owner is None or migrator_login is None:
        if (
            legacy_rebaseline
            or _managed_deployment_requires_migration_owner()
            or migration_owner is not None
            or migrator_login is not None
        ):
            raise RuntimeError("0101 managed migration requires migration and migrator roles")
        return None

    role_contract_valid = bind.scalar(
        sa.text(
            """
            WITH migration_role AS (
                SELECT role_row.oid, role_row.rolcanlogin, role_row.rolsuper,
                       role_row.rolcreaterole, role_row.rolcreatedb,
                       role_row.rolreplication, role_row.rolbypassrls,
                       role_row.rolinherit
                FROM pg_roles role_row
                WHERE role_row.rolname = :migration_owner
            ),
            migrator_role AS (
                SELECT role_row.oid, role_row.rolcanlogin, role_row.rolsuper,
                       role_row.rolcreaterole, role_row.rolcreatedb,
                       role_row.rolreplication, role_row.rolbypassrls,
                       role_row.rolinherit
                FROM pg_roles role_row
                WHERE role_row.rolname = :migrator_login
            ),
            app_owner AS (
                SELECT namespace.nspowner AS oid
                FROM pg_namespace namespace
                WHERE namespace.nspname = 'app'
            ),
            database_owner AS (
                SELECT database_row.datdba AS oid
                FROM pg_database database_row
                WHERE database_row.datname = current_database()
            ),
            session_role AS (
                SELECT role_row.oid, role_row.rolcanlogin, role_row.rolsuper,
                       role_row.rolcreaterole, role_row.rolcreatedb,
                       role_row.rolreplication, role_row.rolbypassrls,
                       role_row.rolinherit
                FROM pg_roles role_row
                WHERE role_row.rolname = session_user
            )
            SELECT
                (SELECT count(*) FROM migration_role) = 1
                AND (SELECT count(*) FROM migrator_role) = 1
                AND (SELECT count(*) FROM app_owner) = 1
                AND (SELECT count(*) FROM database_owner) = 1
                AND (SELECT count(*) FROM session_role) = 1
                AND EXISTS (
                    SELECT 1
                    FROM migration_role migration
                    WHERE NOT migration.rolcanlogin
                      AND NOT migration.rolsuper
                      AND NOT migration.rolcreaterole
                      AND NOT migration.rolcreatedb
                      AND NOT migration.rolreplication
                      AND NOT migration.rolbypassrls
                      AND NOT migration.rolinherit
                      AND migration.oid <> (SELECT oid FROM app_owner)
                      AND migration.oid <> (SELECT oid FROM database_owner)
                )
                AND EXISTS (
                    SELECT 1
                    FROM migrator_role migrator
                    WHERE NOT migrator.rolsuper
                      AND NOT migrator.rolcreaterole
                      AND NOT migrator.rolcreatedb
                      AND NOT migrator.rolreplication
                      AND NOT migrator.rolbypassrls
                      AND NOT migrator.rolinherit
                      AND migrator.oid <> (SELECT oid FROM migration_role)
                      AND migrator.oid <> (SELECT oid FROM app_owner)
                      AND migrator.oid <> (SELECT oid FROM database_owner)
                      AND CASE WHEN :legacy_rebaseline THEN NOT migrator.rolcanlogin
                               ELSE migrator.rolcanlogin
                          END
                      AND NOT EXISTS (
                          SELECT 1
                          FROM pg_auth_members membership
                          WHERE membership.roleid = migrator.oid
                      )
                )
                AND has_schema_privilege(
                    (SELECT oid FROM migration_role), 'x_extension', 'USAGE'
                )
                AND NOT has_schema_privilege(
                    (SELECT oid FROM migration_role), 'x_extension', 'CREATE'
                )
                AND has_function_privilege(
                    (SELECT oid FROM migration_role),
                    'x_extension.digest(bytea,text)'::regprocedure,
                    'EXECUTE'
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_default_acl default_acl
                    WHERE default_acl.defaclrole = (SELECT oid FROM migration_role)
                      AND default_acl.defaclnamespace = 0
                )
                AND (
                    CASE WHEN :legacy_rebaseline THEN
                        session_user = current_user
                        AND current_user::regrole = (SELECT oid FROM app_owner)
                        AND current_user::regrole = (SELECT oid FROM database_owner)
                        AND (SELECT count(*) FROM app.alembic_version) = 1
                        AND (SELECT version_num FROM app.alembic_version) = '20260824_0100'
                        AND pg_has_role(
                            session_user::regrole,
                            (SELECT oid FROM migration_role),
                            'SET'
                        )
                        AND NOT EXISTS (
                            SELECT 1
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM app_owner)
                        )
                        AND (
                            SELECT count(*)
                            FROM pg_auth_members membership
                            WHERE membership.member = (SELECT oid FROM migrator_role)
                              AND membership.roleid = (SELECT oid FROM migration_role)
                              AND NOT membership.admin_option
                              AND NOT membership.inherit_option
                              AND membership.set_option
                        ) = 1
                        AND NOT EXISTS (
                            SELECT 1
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM migration_role)
                              AND (
                                  membership.member <> (SELECT oid FROM migrator_role)
                                  OR membership.admin_option
                                  OR membership.inherit_option
                                  OR NOT membership.set_option
                              )
                        )
                    ELSE
                        session_user <> current_user
                        AND current_user::regrole = (SELECT oid FROM app_owner)
                        AND EXISTS (
                            SELECT 1
                            FROM session_role session_login
                            WHERE session_login.rolcanlogin
                              AND NOT session_login.rolsuper
                              AND NOT session_login.rolcreaterole
                              AND NOT session_login.rolcreatedb
                              AND NOT session_login.rolreplication
                              AND NOT session_login.rolbypassrls
                              AND NOT session_login.rolinherit
                              AND session_login.oid <> (SELECT oid FROM database_owner)
                              AND session_login.oid = (SELECT oid FROM migrator_role)
                        )
                        AND (
                            SELECT count(*)
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM app_owner)
                              AND membership.member IN (
                                  (SELECT oid FROM migration_role),
                                  (SELECT oid FROM migrator_role)
                              )
                              AND NOT membership.admin_option
                              AND NOT membership.inherit_option
                              AND membership.set_option
                        ) = 2
                        AND NOT EXISTS (
                            SELECT 1
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM app_owner)
                              AND (
                                  membership.member NOT IN (
                                      (SELECT oid FROM migration_role),
                                      (SELECT oid FROM migrator_role)
                                  )
                                  OR membership.admin_option
                                  OR membership.inherit_option
                                  OR NOT membership.set_option
                              )
                        )
                        AND (
                            SELECT count(*)
                            FROM pg_auth_members membership
                            WHERE membership.member = (SELECT oid FROM migrator_role)
                              AND membership.roleid = (SELECT oid FROM migration_role)
                              AND NOT membership.admin_option
                              AND NOT membership.inherit_option
                              AND membership.set_option
                        ) = 1
                        AND NOT EXISTS (
                            SELECT 1
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM migration_role)
                              AND (
                                  membership.member <> (SELECT oid FROM migrator_role)
                                  OR membership.admin_option
                                  OR membership.inherit_option
                                  OR NOT membership.set_option
                              )
                        )
                        AND NOT pg_has_role(
                            (SELECT oid FROM session_role),
                            (SELECT oid FROM database_owner),
                            'MEMBER'
                        )
                    END
                )
            """
        ),
        {
            "migration_owner": migration_owner,
            "migrator_login": migrator_login,
            "legacy_rebaseline": legacy_rebaseline,
        },
    )
    if role_contract_valid is not True:
        raise RuntimeError("0101 migration owner role contract is not satisfied")

    # The identifier has already been constrained to a portable PostgreSQL role name.
    op.execute(f'SET LOCAL ROLE "{migration_owner}"')
    if (
        bind.scalar(
            sa.text("SELECT current_user = :migration_owner"), {"migration_owner": migration_owner}
        )
        is not True
    ):
        raise RuntimeError("0101 could not activate the migration owner")
    return bind.scalar(
        sa.text(
            """
            SELECT namespace.nspowner::regrole::text
            FROM pg_namespace namespace
            WHERE namespace.nspname = 'app'
            """
        )
    )


def _restore_app_owner(app_owner: str | None) -> None:
    """Let Alembic write its version row with the pre-existing app owner again."""

    if app_owner is None:
        return
    if _ROLE_IDENTIFIER.fullmatch(app_owner) is None:
        raise RuntimeError("0101 app schema owner is invalid")
    op.execute(f'SET LOCAL ROLE "{app_owner}"')
    if (
        op.get_bind().scalar(sa.text("SELECT current_user = :app_owner"), {"app_owner": app_owner})
        is not True
    ):
        raise RuntimeError("0101 could not restore the app schema owner")


def _advance_boundary_contract() -> None:
    """finalize가 기준선 이후 M05 계약만 수용하도록 revision pin을 전진시킨다."""

    op.drop_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        _BOUNDARY_CONTRACT_CHECK,
        schema="app",
    )


def _install_location_audit_purpose_contract() -> None:
    """현재 main의 `/search` 감사 purpose를 0061 기준선 위에 반영한다."""

    op.execute(
        f"ALTER TABLE app.location_access_log DROP CONSTRAINT "
        f"{_LOCATION_ACCESS_LOG_PURPOSE_CONSTRAINT}"
    )
    op.execute(
        f"ALTER TABLE app.location_access_log ADD CONSTRAINT "
        f"{_LOCATION_ACCESS_LOG_PURPOSE_CONSTRAINT} "
        f"CHECK (purpose IN ({_LOCATION_ACCESS_LOG_PURPOSES}))"
    )


def _install_location_audit_coord_source_contract() -> None:
    """좌표 출처를 기록해 device 동의 게이트와 audit ledger를 같은 계약으로 묶는다."""

    for table in ("location_access_log", "location_audit_outbox"):
        op.add_column(
            table,
            sa.Column("coord_source", sa.Text(), nullable=True),
            schema="app",
        )
        op.create_check_constraint(
            f"ck_{table}_coord_source",
            table,
            _LOCATION_AUDIT_COORD_SOURCE_CHECK,
            schema="app",
        )


def _install_user_consent_event_history() -> None:
    """T-326의 현재 상태 이력 테이블과 정직한 0061 data backfill을 적용한다."""

    # 구 runtime은 user_consents만 in-place로 갱신한다. source table의 DML을 이
    # migration transaction 끝까지 막아야 backfill snapshot 뒤에 commit된 동의/철회가
    # event ledger에서 누락되지 않는다. deploy runner도 API/Dagster writer를 먼저 stop한다.
    op.execute("LOCK TABLE app.user_consents IN SHARE ROW EXCLUSIVE MODE")
    op.create_table(
        "user_consent_events",
        sa.Column(
            "event_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_user_consent_events")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name=op.f("fk_user_consent_events_user_id"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "consent_type IN ('tos', 'privacy', 'lbs_tos', 'location_collection', "
            "'demographic_use', 'marketing')",
            name=op.f("ck_user_consent_events_consent_type"),
        ),
        sa.CheckConstraint(
            "event IN ('agreed', 'withdrawn')",
            name=op.f("ck_user_consent_events_event"),
        ),
        sa.CheckConstraint(
            "source IN ('register', 'profile_complete', 'settings', 'backfill')",
            name=op.f("ck_user_consent_events_source"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_user_consent_events_user_type_time",
        "user_consent_events",
        ["user_id", "consent_type", "occurred_at"],
        schema="app",
    )
    # `0101`은 M05 object용 별도 migration owner로도 실행한다. app schema의 새 table은
    # 그 owner가 아니라 app schema owner가 소유해야 runtime privilege 경계가 기존 table과 같다.
    op.execute(
        sa.text(
            """
            DO $app_owner$
            DECLARE
                app_owner name;
            BEGIN
                SELECT namespace.nspowner::regrole::text::name
                  INTO app_owner
                  FROM pg_namespace namespace
                 WHERE namespace.nspname = 'app';
                IF app_owner IS NULL THEN
                    RAISE EXCEPTION 'app schema owner is unavailable';
                END IF;
                EXECUTE format('ALTER TABLE app.user_consent_events OWNER TO %I', app_owner);
            END
            $app_owner$
            """
        )
    )
    # 현재 상태만 남은 0061 행에서 정확히 복원할 수 있는 agreement/withdrawal만 기록한다.
    # 재동의로 사라진 과거 cycle은 추정해 만들지 않는다.
    op.execute(
        sa.text(
            """
            INSERT INTO app.user_consent_events
                (user_id, consent_type, version, event, source, occurred_at)
            SELECT user_id, consent_type, version, event, 'backfill', occurred_at
            FROM (
                SELECT c.user_id, c.consent_type, c.version, 'agreed' AS event, c.agreed_at AS occurred_at
                FROM app.user_consents c
                UNION ALL
                SELECT c.user_id, c.consent_type, c.version, 'withdrawn', c.withdrawn_at
                FROM app.user_consents c
                WHERE c.withdrawn_at IS NOT NULL
            ) AS restored
            WHERE NOT EXISTS (
                SELECT 1 FROM app.user_consent_events e
                WHERE e.user_id = restored.user_id
                  AND e.consent_type = restored.consent_type
                  AND e.event = restored.event
                  AND e.source = 'backfill'
            )
            """
        )
    )


def _replace_admin_audit_guard() -> None:
    """restore 뒤 admin reflection도 기존 원장에 append만 하도록 고정한다."""

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION app.guard_admin_audit_log_append_only()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY INVOKER
            SET search_path = pg_catalog
            AS $function$BEGIN
                IF TG_OP = 'INSERT' THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
                    USING ERRCODE = '55000';
            END;$function$
            """
        )
    )
    op.execute("DROP TRIGGER IF EXISTS trg_admin_audit_log_append_only ON app.admin_audit_log")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_admin_audit_log_truncate_append_only ON app.admin_audit_log"
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_admin_audit_log_append_only
            BEFORE INSERT OR UPDATE OR DELETE ON app.admin_audit_log
            FOR EACH ROW EXECUTE FUNCTION app.guard_admin_audit_log_append_only()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_admin_audit_log_truncate_append_only
            BEFORE TRUNCATE ON app.admin_audit_log
            FOR EACH STATEMENT EXECUTE FUNCTION app.guard_admin_audit_log_append_only()
            """
        )
    )
    for trigger_name in (
        "trg_admin_audit_log_append_only",
        "trg_admin_audit_log_truncate_append_only",
    ):
        op.execute(sa.text(f"ALTER TABLE app.admin_audit_log ENABLE ALWAYS TRIGGER {trigger_name}"))


def _grant_receipt_fence_access(bind: sa.Connection) -> None:
    """database owner fence에 receipt read와 세 security-definer execute만 허용한다."""

    bind.execute(
        sa.text(
            """
            DO $m05$
            DECLARE
                fence_role name;
            BEGIN
                SELECT database_row.datdba::regrole::text::name
                  INTO fence_role
                  FROM pg_database database_row
                 WHERE database_row.datname = current_database();
                EXECUTE format(
                    'GRANT SELECT ON TABLE ops.m05_hotswap_release_receipts TO %I',
                    fence_role
                );
                EXECUTE format(
                    'GRANT EXECUTE ON FUNCTION '
                    || 'ops.m05_hotswap_release_topology_sha256(name, name, name, name, name, name) '
                    || 'TO %I',
                    fence_role
                );
                EXECUTE format(
                    'GRANT EXECUTE ON FUNCTION '
                    || 'ops.record_m05_hotswap_release_receipt('
                    || 'uuid, text, text, text, text, text, text, text, name, name, name, '
                    || 'name, name, name, oid, oid, oid, oid, jsonb, jsonb, boolean, text) '
                    || 'TO %I',
                    fence_role
                );
                EXECUTE format(
                    'GRANT EXECUTE ON FUNCTION '
                    || 'ops.verify_m05_hotswap_release_receipt(uuid, text) '
                    || 'TO %I',
                    fence_role
                );
            END
            $m05$
            """
        )
    )


def _harden_m05_acl(bind: sa.Connection) -> None:
    """public verification 범위와 fence capability를 최소 권한으로 확정한다."""

    op.execute("REVOKE ALL ON SCHEMA ops FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA ops TO PUBLIC")
    op.execute("REVOKE ALL PRIVILEGES ON TABLE ops.m05_activation_database_anchor FROM PUBLIC")
    op.execute("GRANT SELECT ON TABLE ops.m05_activation_database_anchor TO PUBLIC")
    op.execute("REVOKE ALL PRIVILEGES ON TABLE ops.m05_hotswap_release_receipts FROM PUBLIC")
    for signature in (
        "ops.guard_m05_activation_database_anchor_append_only()",
        "ops.guard_m05_hotswap_release_receipts_append_only()",
        "ops.m05_hotswap_release_topology_sha256(name, name, name, name, name, name)",
        "ops.record_m05_hotswap_release_receipt("
        "uuid, text, text, text, text, text, text, text, name, name, name, name, name, "
        "name, oid, oid, oid, oid, jsonb, jsonb, boolean, text)",
        "ops.verify_m05_hotswap_release_receipt(uuid, text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    _grant_receipt_fence_access(bind)


def _assert_m05_acl(bind: sa.Connection) -> None:
    """M05 object owner와 공개/fence ACL이 정확히 기대한 surface인지 검사한다."""

    acl_is_exact = bind.scalar(
        sa.text(
            """
            WITH fence_role AS (
                SELECT database_row.datdba AS oid
                FROM pg_database database_row
                WHERE database_row.datname = current_database()
            ),
            m05_schema AS (
                SELECT namespace.oid, namespace.nspowner, namespace.nspacl
                FROM pg_namespace namespace
                WHERE namespace.nspname = 'ops'
            ),
            anchor_table AS (
                SELECT relation.oid, relation.relowner, relation.relacl
                FROM pg_class relation
                JOIN m05_schema schema ON schema.oid = relation.relnamespace
                WHERE relation.relname = 'm05_activation_database_anchor'
                  AND relation.relkind = 'r'
            ),
            receipt_table AS (
                SELECT relation.oid, relation.relowner, relation.relacl
                FROM pg_class relation
                JOIN m05_schema schema ON schema.oid = relation.relnamespace
                WHERE relation.relname = 'm05_hotswap_release_receipts'
                  AND relation.relkind = 'r'
            ),
            guard_functions AS (
                SELECT procedure.oid, procedure.proowner, procedure.proacl, procedure.prosecdef
                FROM pg_proc procedure
                JOIN m05_schema schema ON schema.oid = procedure.pronamespace
                WHERE procedure.oid IN (
                    'ops.guard_m05_activation_database_anchor_append_only()'::regprocedure,
                    'ops.guard_m05_hotswap_release_receipts_append_only()'::regprocedure
                )
            ),
            receipt_functions AS (
                SELECT procedure.oid, procedure.proowner, procedure.proacl, procedure.prosecdef
                FROM pg_proc procedure
                JOIN m05_schema schema ON schema.oid = procedure.pronamespace
                WHERE procedure.oid IN (
                    'ops.m05_hotswap_release_topology_sha256(name, name, name, name, name, name)'::regprocedure,
                    'ops.record_m05_hotswap_release_receipt(uuid, text, text, text, text, text, text, text, name, name, name, name, name, name, oid, oid, oid, oid, jsonb, jsonb, boolean, text)'::regprocedure,
                    'ops.verify_m05_hotswap_release_receipt(uuid, text)'::regprocedure
                )
            )
            SELECT
                (SELECT count(*) FROM fence_role) = 1
                AND (SELECT count(*) FROM m05_schema) = 1
                AND (SELECT count(*) FROM anchor_table) = 1
                AND (SELECT count(*) FROM receipt_table) = 1
                AND (SELECT count(*) FROM guard_functions) = 2
                AND (SELECT count(*) FROM receipt_functions) = 3
                AND NOT EXISTS (
                    SELECT 1 FROM m05_schema schema
                    WHERE schema.nspowner <> current_user::regrole
                )
                AND NOT EXISTS (
                    SELECT 1 FROM anchor_table relation
                    WHERE relation.relowner <> current_user::regrole
                )
                AND NOT EXISTS (
                    SELECT 1 FROM receipt_table relation
                    WHERE relation.relowner <> current_user::regrole
                )
                AND NOT EXISTS (
                    SELECT 1 FROM guard_functions procedure
                    WHERE procedure.proowner <> current_user::regrole OR procedure.prosecdef
                )
                AND NOT EXISTS (
                    SELECT 1 FROM receipt_functions procedure
                    WHERE procedure.proowner <> current_user::regrole OR NOT procedure.prosecdef
                )
                AND EXISTS (
                    SELECT 1
                    FROM m05_schema schema
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(schema.nspacl, acldefault('n', schema.nspowner))
                    ) acl
                    WHERE acl.grantee = 0 AND acl.privilege_type = 'USAGE'
                      AND NOT acl.is_grantable
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM m05_schema schema
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(schema.nspacl, acldefault('n', schema.nspowner))
                    ) acl
                    WHERE NOT (
                        acl.grantee = schema.nspowner
                        OR (acl.grantee = 0 AND acl.privilege_type = 'USAGE'
                            AND NOT acl.is_grantable)
                    )
                )
                AND EXISTS (
                    SELECT 1
                    FROM anchor_table relation
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(relation.relacl, acldefault('r', relation.relowner))
                    ) acl
                    WHERE acl.grantee = 0 AND acl.privilege_type = 'SELECT'
                      AND NOT acl.is_grantable
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM anchor_table relation
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(relation.relacl, acldefault('r', relation.relowner))
                    ) acl
                    WHERE NOT (
                        acl.grantee = relation.relowner
                        OR (acl.grantee = 0 AND acl.privilege_type = 'SELECT'
                            AND NOT acl.is_grantable)
                    )
                )
                AND EXISTS (
                    SELECT 1
                    FROM receipt_table relation
                    CROSS JOIN fence_role fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(relation.relacl, acldefault('r', relation.relowner))
                    ) acl
                    WHERE acl.grantee = fence.oid AND acl.privilege_type = 'SELECT'
                      AND NOT acl.is_grantable
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM receipt_table relation
                    CROSS JOIN fence_role fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(relation.relacl, acldefault('r', relation.relowner))
                    ) acl
                    WHERE NOT (
                        acl.grantee = relation.relowner
                        OR (acl.grantee = fence.oid AND acl.privilege_type = 'SELECT'
                            AND NOT acl.is_grantable)
                    )
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM guard_functions procedure
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(procedure.proacl, acldefault('f', procedure.proowner))
                    ) acl
                    WHERE acl.grantee <> procedure.proowner
                )
                AND (
                    SELECT count(*)
                    FROM receipt_functions procedure
                    CROSS JOIN fence_role fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(procedure.proacl, acldefault('f', procedure.proowner))
                    ) acl
                    WHERE acl.grantee = fence.oid AND acl.privilege_type = 'EXECUTE'
                      AND NOT acl.is_grantable
                ) = 3
                AND NOT EXISTS (
                    SELECT 1
                    FROM receipt_functions procedure
                    CROSS JOIN fence_role fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(procedure.proacl, acldefault('f', procedure.proowner))
                    ) acl
                    WHERE NOT (
                        acl.grantee = procedure.proowner
                        OR (acl.grantee = fence.oid AND acl.privilege_type = 'EXECUTE'
                            AND NOT acl.is_grantable)
                    )
                )
            """
        )
    )
    if acl_is_exact is not True:
        raise RuntimeError("0101 M05 ACL is not canonical")


def upgrade() -> None:
    bind = op.get_bind()
    _assert_legacy_rebaseline_handoff(bind)
    _install_location_audit_purpose_contract()
    _install_location_audit_coord_source_contract()
    _install_user_consent_event_history()
    _advance_boundary_contract()
    _replace_admin_audit_guard()
    app_owner = _activate_m05_migration_owner(bind)
    # named ops default ACL까지 검사하려면 schema를 먼저 확보해야 한다. 이 revision은
    # partial legacy M05 object를 덮어쓰지 않고 transaction 전체를 fail-close한다.
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    _reject_unsafe_m05_default_privileges(bind)
    _reject_existing_m05_objects(bind)
    op.execute("SET LOCAL check_function_bodies = false")
    for statement in _m05_schema_statements():
        op.execute(sa.text(statement))
    _harden_m05_acl(bind)
    _assert_m05_acl(bind)
    _restore_app_owner(app_owner)


def downgrade() -> None:
    raise RuntimeError("0101 M05 activation contract migration is forward-only")
