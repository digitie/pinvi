#!/usr/bin/env sh
# Runtime DB login and one-shot Alembic role topology bootstrap.
#
# app-api/app-dagster only receive PINVI_APP_DB_USER. The root bootstrap login
# creates (or temporarily re-enables) the non-inheriting migrator login, while
# 0101 itself switches just its M05 receipt DDL to PINVI_MIGRATION_OWNER.

set -eu

# Root bootstrap credentials must never inherit a caller-selected libpq target.
# Every connection below supplies the one validated endpoint explicitly.
unset PGAPPNAME PGCONNECT_TIMEOUT PGDATABASE PGHOST PGHOSTADDR PGOPTIONS PGPASSFILE \
  PGPASSWORD PGPORT PGSERVICE PGSERVICEFILE PGSSLCERT PGSSLMODE PGSSLKEY \
  PGSSLROOTCERT PGTARGETSESSIONATTRS PGUSER PSQLRC

PINVI_ROLE_TOPOLOGY_VERIFY_ONLY="${PINVI_ROLE_TOPOLOGY_VERIFY_ONLY:-0}"
PINVI_ROLE_CATALOG_RESET_ONLY="${PINVI_ROLE_CATALOG_RESET_ONLY:-0}"
PINVI_ROLE_CATALOG_RESET_PERMIT_FILE="${PINVI_ROLE_CATALOG_RESET_PERMIT_FILE:-}"
PINVI_ROLE_CATALOG_RESET_RESULT_FILE="${PINVI_ROLE_CATALOG_RESET_RESULT_FILE:-}"
PINVI_M05_LEGACY_REBASELINE="${PINVI_M05_LEGACY_REBASELINE:-0}"
PINVI_MIGRATOR_DISABLE_LOGIN="${PINVI_MIGRATOR_DISABLE_LOGIN:-1}"
# The ordinary PinVi Compose network reaches PostgreSQL as ``app-postgres:5432``.
# The Docker Manager's host-network one-shot is the only other supported
# topology, and it must use the dedicated loopback endpoint exactly.
PINVI_DB_HOST="${PINVI_DB_HOST:-app-postgres}"
PINVI_DB_PORT="${PINVI_DB_PORT:-5432}"

emit_role_topology_diagnostic() {
  status="$1"
  reason="$2"
  printf '%s\n' \
    "{\"schema\":\"pinvi.role-topology-diagnostic.v1\",\"status\":\"${status}\",\"mode\":\"sealed\",\"reasons\":[\"${reason}\"]}"
  exit 0
}

input_error() {
  message="$1"
  if [ "${PINVI_ROLE_TOPOLOGY_VERIFY_ONLY}" = "1" ]; then
    emit_role_topology_diagnostic "invalid" "input_invalid"
  fi
  echo "${message}" >&2
  exit 2
}

require_value() {
  name="$1"
  value="$2"
  if [ -z "${value}" ]; then
    input_error "${name} is required"
  fi
}

case "${PINVI_ROLE_TOPOLOGY_VERIFY_ONLY}" in
  0|1 ) ;;
  * ) input_error "PINVI_ROLE_TOPOLOGY_VERIFY_ONLY must be 0 or 1" ;;
esac
case "${PINVI_ROLE_CATALOG_RESET_ONLY}" in
  0|1 ) ;;
  * ) input_error "PINVI_ROLE_CATALOG_RESET_ONLY must be 0 or 1" ;;
esac
if [ "${PINVI_ROLE_TOPOLOGY_VERIFY_ONLY}" = "1" ] \
  && [ "${PINVI_ROLE_CATALOG_RESET_ONLY}" = "1" ]; then
  input_error "role topology verification and catalog reset cannot run together"
fi

require_value "POSTGRES_USER" "${POSTGRES_USER:-}"
require_value "POSTGRES_PASSWORD" "${POSTGRES_PASSWORD:-}"
require_value "POSTGRES_DB" "${POSTGRES_DB:-}"
require_value "PINVI_APP_DB_USER" "${PINVI_APP_DB_USER:-}"
require_value "PINVI_APP_DB_PASSWORD" "${PINVI_APP_DB_PASSWORD:-}"
require_value "PINVI_APP_SCHEMA_OWNER" "${PINVI_APP_SCHEMA_OWNER:-}"
require_value "PINVI_MIGRATION_OWNER" "${PINVI_MIGRATION_OWNER:-}"
require_value "PINVI_MIGRATOR_DB_USER" "${PINVI_MIGRATOR_DB_USER:-}"
require_value "PINVI_MIGRATOR_DB_PASSWORD" "${PINVI_MIGRATOR_DB_PASSWORD:-}"

for role_name in \
  "${POSTGRES_USER}" \
  "${PINVI_APP_DB_USER}" \
  "${PINVI_APP_SCHEMA_OWNER}" \
  "${PINVI_MIGRATION_OWNER}" \
  "${PINVI_MIGRATOR_DB_USER}"; do
  case "${role_name}" in
    ''|[!a-z_]*|*[!a-z0-9_]* ) input_error "invalid PostgreSQL role name" ;;
  esac
done
case "${POSTGRES_DB}" in
  ''|[!a-z_]*|*[!a-z0-9_]* ) input_error "invalid POSTGRES_DB" ;;
esac
case "${PINVI_M05_LEGACY_REBASELINE}" in
  0|1 ) ;;
  * ) input_error "PINVI_M05_LEGACY_REBASELINE must be 0 or 1" ;;
esac
case "${PINVI_MIGRATOR_DISABLE_LOGIN}" in
  0|1 ) ;;
  * ) input_error "PINVI_MIGRATOR_DISABLE_LOGIN must be 0 or 1" ;;
esac
case "${PINVI_DB_HOST}:${PINVI_DB_PORT}" in
  app-postgres:5432|127.0.0.1:12800 ) ;;
  * )
    input_error "PINVI_DB_HOST and PINVI_DB_PORT must name an approved PostgreSQL endpoint"
    ;;
esac

if [ "${POSTGRES_USER}" = "${PINVI_APP_DB_USER}" ] \
  || [ "${POSTGRES_USER}" = "${PINVI_APP_SCHEMA_OWNER}" ] \
  || [ "${POSTGRES_USER}" = "${PINVI_MIGRATION_OWNER}" ] \
  || [ "${POSTGRES_USER}" = "${PINVI_MIGRATOR_DB_USER}" ] \
  || [ "${PINVI_APP_DB_USER}" = "${PINVI_APP_SCHEMA_OWNER}" ] \
  || [ "${PINVI_APP_DB_USER}" = "${PINVI_MIGRATION_OWNER}" ] \
  || [ "${PINVI_APP_DB_USER}" = "${PINVI_MIGRATOR_DB_USER}" ] \
  || [ "${PINVI_APP_SCHEMA_OWNER}" = "${PINVI_MIGRATION_OWNER}" ] \
  || [ "${PINVI_APP_SCHEMA_OWNER}" = "${PINVI_MIGRATOR_DB_USER}" ] \
  || [ "${PINVI_MIGRATION_OWNER}" = "${PINVI_MIGRATOR_DB_USER}" ]; then
  input_error "runtime, schema owner, migration owner, migrator, and bootstrap roles must differ"
fi

export PGPASSWORD="${POSTGRES_PASSWORD}"
if [ "${PINVI_ROLE_TOPOLOGY_VERIFY_ONLY}" = "1" ]; then
  if ! psql --no-psqlrc --no-password --tuples-only --no-align --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" --command='SELECT 1' >/dev/null 2>&1; then
    unset PGPASSWORD
    emit_role_topology_diagnostic "unavailable" "endpoint_unavailable"
  fi
else
  attempt=0
  until psql --no-psqlrc --no-password --tuples-only --no-align --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" --command='SELECT 1' >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    # postgis' first-run entrypoint can briefly report a healthy bootstrap server,
    # shut it down, and then start the final server. Keep the role bootstrap alive
    # across that restart instead of treating the transient window as a deploy failure.
    if [ "$attempt" -ge 90 ]; then
      unset PGPASSWORD
      echo "Postgres TCP endpoint did not become ready for DB role bootstrap" >&2
      exit 1
    fi
    sleep 1
  done
fi

evaluate_role_topology() {
  topology_output="${1}"
  PGPASSWORD="${POSTGRES_PASSWORD}" psql --no-psqlrc --no-password --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 \
      --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
      --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
      --set="bootstrap_owner=${POSTGRES_USER}" \
      --set="app_role=${PINVI_APP_DB_USER}" \
      --set="schema_owner=${PINVI_APP_SCHEMA_OWNER}" \
      --set="migration_owner=${PINVI_MIGRATION_OWNER}" \
      --set="migrator_role=${PINVI_MIGRATOR_DB_USER}" \
      --set="legacy_rebaseline=${PINVI_M05_LEGACY_REBASELINE}" \
      --set="migrator_disabled=${PINVI_MIGRATOR_DISABLE_LOGIN}" \
      --set="topology_output=${topology_output}" 2>/dev/null <<'SQL'
BEGIN READ ONLY;
WITH runtime_role AS (
    SELECT * FROM pg_roles WHERE rolname = :'app_role'
),
schema_owner AS (
    SELECT * FROM pg_roles WHERE rolname = :'schema_owner'
),
migration_owner AS (
    SELECT * FROM pg_roles WHERE rolname = :'migration_owner'
),
migrator_role AS (
    SELECT * FROM pg_roles WHERE rolname = :'migrator_role'
),
database_owner AS (
    SELECT database_row.datdba AS oid, database_row.oid AS database_oid
    FROM pg_database database_row
    WHERE database_row.datname = current_database()
),
app_schema AS (
    SELECT namespace.oid, namespace.nspowner
    FROM pg_namespace namespace
    WHERE namespace.nspname = 'app'
),
x_extension_schema AS (
    SELECT namespace.oid, namespace.nspowner
    FROM pg_namespace namespace
    WHERE namespace.nspname = 'x_extension'
),
pinvi_internal_schema AS (
    SELECT namespace.oid, namespace.nspowner
    FROM pg_namespace namespace
    WHERE namespace.nspname = 'pinvi_internal'
),
ops_schema AS (
    SELECT namespace.oid, namespace.nspowner
    FROM pg_namespace namespace
    WHERE namespace.nspname = 'ops'
),
fresh_admission_fence AS (
    SELECT procedure.oid, procedure.proowner, procedure.proacl
    FROM pg_proc procedure
    JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
    WHERE namespace.nspname = 'pinvi_internal'
      AND procedure.proname = 'acquire_fresh_0101_database_fence'
      AND procedure.pronargs = 0
),
app_objects AS (
    SELECT relation.relowner AS owner_oid
    FROM pg_class relation
    JOIN app_schema schema ON schema.oid = relation.relnamespace
    UNION ALL
    SELECT procedure.proowner
    FROM pg_proc procedure
    JOIN app_schema schema ON schema.oid = procedure.pronamespace
    UNION ALL
    SELECT type_row.typowner
    FROM pg_type type_row
    JOIN app_schema schema ON schema.oid = type_row.typnamespace
    UNION ALL
    SELECT operator_row.oprowner
    FROM pg_operator operator_row
    JOIN app_schema schema ON schema.oid = operator_row.oprnamespace
    UNION ALL
    SELECT collation_row.collowner
    FROM pg_collation collation_row
    JOIN app_schema schema ON schema.oid = collation_row.collnamespace
    UNION ALL
    SELECT conversion_row.conowner
    FROM pg_conversion conversion_row
    JOIN app_schema schema ON schema.oid = conversion_row.connamespace
    UNION ALL
    SELECT opclass_row.opcowner
    FROM pg_opclass opclass_row
    JOIN app_schema schema ON schema.oid = opclass_row.opcnamespace
    UNION ALL
    SELECT opfamily_row.opfowner
    FROM pg_opfamily opfamily_row
    JOIN app_schema schema ON schema.oid = opfamily_row.opfnamespace
    UNION ALL
    SELECT config_row.cfgowner
    FROM pg_ts_config config_row
    JOIN app_schema schema ON schema.oid = config_row.cfgnamespace
    UNION ALL
    SELECT dictionary_row.dictowner
    FROM pg_ts_dict dictionary_row
    JOIN app_schema schema ON schema.oid = dictionary_row.dictnamespace
    UNION ALL
    SELECT statistic_row.stxowner
    FROM pg_statistic_ext statistic_row
    JOIN app_schema schema ON schema.oid = statistic_row.stxnamespace
    UNION ALL
    SELECT extension_row.extowner
    FROM pg_extension extension_row
    JOIN app_schema schema ON schema.oid = extension_row.extnamespace
),
diagnostic_checks(position, reason, passed) AS (
    VALUES
        (
            1,
            'principal_identity',
            (SELECT count(*) FROM runtime_role) = 1
                AND (SELECT count(*) FROM schema_owner) = 1
                AND (SELECT count(*) FROM migration_owner) = 1
                AND (SELECT count(*) FROM migrator_role) = 1
                AND (SELECT count(*) FROM database_owner) = 1
                AND COALESCE(
                    (SELECT oid FROM schema_owner) <> (SELECT oid FROM database_owner),
                    false
                )
        ),
        (
            2,
            'bootstrap_catalog',
            (SELECT count(*) FROM app_schema) = 1
                AND (SELECT count(*) FROM x_extension_schema) = 1
                AND (SELECT count(*) FROM pinvi_internal_schema) = 1
                AND (SELECT count(*) FROM ops_schema) = 1
                AND COALESCE(
                    (SELECT nspowner FROM ops_schema) = (SELECT oid FROM migration_owner),
                    false
                )
                AND COALESCE(
                    (SELECT nspowner FROM pinvi_internal_schema) = (SELECT oid FROM schema_owner),
                    false
                )
                AND COALESCE(
                    (SELECT nspowner FROM x_extension_schema) = :'bootstrap_owner'::regrole,
                    false
                )
        ),
        (
            3,
            'fence_acl',
            (SELECT count(*) FROM fresh_admission_fence) = 1
                AND COALESCE(
                    (SELECT proowner FROM fresh_admission_fence) = (SELECT oid FROM database_owner),
                    false
                )
                AND EXISTS (
                    SELECT 1
                    FROM fresh_admission_fence fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(fence.proacl, acldefault('f', fence.proowner))
                    ) AS acl
                    WHERE acl.grantee = (SELECT oid FROM schema_owner)
                      AND acl.privilege_type = 'EXECUTE'
                      AND NOT acl.is_grantable
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM fresh_admission_fence fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(fence.proacl, acldefault('f', fence.proowner))
                    ) AS acl
                    WHERE NOT (
                        acl.grantee = fence.proowner
                        OR (acl.grantee = (SELECT oid FROM schema_owner)
                            AND acl.privilege_type = 'EXECUTE'
                            AND NOT acl.is_grantable)
                    )
                )
        ),
        (
            4,
            'runtime_role',
            EXISTS (
                SELECT 1 FROM runtime_role runtime
                WHERE runtime.rolcanlogin
                  AND NOT runtime.rolsuper
                  AND NOT runtime.rolcreaterole
                  AND NOT runtime.rolcreatedb
                  AND NOT runtime.rolreplication
                  AND NOT runtime.rolbypassrls
                  AND NOT runtime.rolinherit
                  AND runtime.oid <> (SELECT oid FROM database_owner)
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_auth_members membership
                      WHERE membership.member = runtime.oid
                         OR membership.roleid = runtime.oid
                  )
                  AND NOT has_database_privilege(runtime.oid, current_database(), 'CREATE')
                  AND has_schema_privilege(runtime.oid, 'x_extension', 'USAGE')
                  AND NOT has_schema_privilege(runtime.oid, 'app', 'CREATE')
                  AND NOT has_schema_privilege(runtime.oid, 'x_extension', 'CREATE')
            )
        ),
        (
            5,
            'schema_owner_membership',
            EXISTS (
                SELECT 1 FROM schema_owner owner
                WHERE NOT owner.rolcanlogin
                  AND NOT owner.rolsuper
                  AND NOT owner.rolcreaterole
                  AND NOT owner.rolcreatedb
                  AND NOT owner.rolreplication
                  AND NOT owner.rolbypassrls
                  AND NOT owner.rolinherit
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_auth_members membership
                      WHERE membership.member = owner.oid
                  )
                  AND (
                      SELECT count(*)
                      FROM pg_auth_members membership
                      WHERE membership.roleid = owner.oid
                        AND membership.member IN (
                            (SELECT oid FROM migration_owner),
                            (SELECT oid FROM migrator_role)
                        )
                        AND NOT membership.admin_option
                        AND NOT membership.inherit_option
                        AND membership.set_option
                  ) = 2
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_auth_members membership
                      WHERE membership.roleid = owner.oid
                        AND (
                            membership.member NOT IN (
                                (SELECT oid FROM migration_owner),
                                (SELECT oid FROM migrator_role)
                            )
                            OR membership.admin_option
                            OR membership.inherit_option
                            OR NOT membership.set_option
                        )
                  )
            )
        ),
        (
            6,
            'migration_owner_policy',
            EXISTS (
                SELECT 1 FROM migration_owner owner
                WHERE NOT owner.rolcanlogin
                  AND NOT owner.rolsuper
                  AND NOT owner.rolcreaterole
                  AND NOT owner.rolcreatedb
                  AND NOT owner.rolreplication
                  AND NOT owner.rolbypassrls
                  AND NOT owner.rolinherit
                  AND owner.oid <> (SELECT oid FROM database_owner)
                  AND NOT has_database_privilege(owner.oid, current_database(), 'CONNECT')
                  AND has_schema_privilege(owner.oid, 'x_extension', 'USAGE')
                  AND NOT has_schema_privilege(owner.oid, 'x_extension', 'CREATE')
                  AND has_schema_privilege(owner.oid, 'pinvi_internal', 'USAGE')
                  AND NOT EXISTS (
                      SELECT 1
                      FROM pg_namespace app_namespace
                      CROSS JOIN LATERAL aclexplode(
                          COALESCE(
                              app_namespace.nspacl,
                              acldefault('n', app_namespace.nspowner)
                          )
                      ) AS app_acl
                      WHERE app_namespace.nspname = 'app'
                        AND app_acl.grantee IN (owner.oid, 0)
                        AND app_acl.privilege_type = 'CREATE'
                  )
                  AND EXISTS (
                      SELECT 1 FROM pg_auth_members membership
                      WHERE membership.member = owner.oid
                        AND membership.roleid = (SELECT oid FROM schema_owner)
                        AND NOT membership.admin_option
                        AND NOT membership.inherit_option
                        AND membership.set_option
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_auth_members membership
                      WHERE membership.member = owner.oid
                        AND membership.roleid <> (SELECT oid FROM schema_owner)
                  )
                  AND (
                      SELECT count(*)
                      FROM pg_auth_members membership
                      WHERE membership.member = (SELECT oid FROM migrator_role)
                        AND membership.roleid = owner.oid
                        AND NOT membership.admin_option
                        AND NOT membership.inherit_option
                        AND membership.set_option
                  ) = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_auth_members membership
                      WHERE membership.roleid = owner.oid
                        AND (
                            membership.member <> (SELECT oid FROM migrator_role)
                            OR membership.admin_option
                            OR membership.inherit_option
                            OR NOT membership.set_option
                        )
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_default_acl default_acl
                      WHERE default_acl.defaclrole = owner.oid
                        AND default_acl.defaclnamespace = 0
                  )
            )
        ),
        (
            7,
            'migrator_sealed',
            EXISTS (
                SELECT 1 FROM migrator_role migrator
                WHERE (:'migrator_disabled' = '1') = NOT migrator.rolcanlogin
                  AND NOT migrator.rolsuper
                  AND NOT migrator.rolcreaterole
                  AND NOT migrator.rolcreatedb
                  AND NOT migrator.rolreplication
                  AND NOT migrator.rolbypassrls
                  AND NOT migrator.rolinherit
                  AND migrator.oid <> (SELECT oid FROM database_owner)
                  AND (
                      (:'migrator_disabled' = '0'
                        AND has_database_privilege(migrator.oid, current_database(), 'CONNECT'))
                      OR (
                          :'migrator_disabled' = '1'
                          AND NOT has_database_privilege(migrator.oid, current_database(), 'CONNECT')
                          AND NOT EXISTS (
                              SELECT 1
                              FROM pg_stat_activity activity
                              WHERE activity.usesysid = migrator.oid
                                AND activity.pid <> pg_backend_pid()
                          )
                      )
                  )
                  AND NOT has_database_privilege(migrator.oid, current_database(), 'CREATE')
                  AND NOT pg_has_role(migrator.oid, (SELECT oid FROM database_owner), 'MEMBER')
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_auth_members membership
                      WHERE membership.roleid = migrator.oid
                  )
            )
        ),
        (
            8,
            'migrator_membership_setting',
            EXISTS (
                SELECT 1 FROM migrator_role migrator
                WHERE (
                    SELECT count(*)
                    FROM pg_auth_members membership
                    WHERE membership.member = migrator.oid
                      AND membership.roleid IN (
                          (SELECT oid FROM schema_owner),
                          (SELECT oid FROM migration_owner)
                      )
                      AND NOT membership.admin_option
                      AND NOT membership.inherit_option
                      AND membership.set_option
                ) = 2
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_auth_members membership
                      WHERE membership.member = migrator.oid
                        AND membership.roleid NOT IN (
                            (SELECT oid FROM schema_owner),
                            (SELECT oid FROM migration_owner)
                        )
                  )
                  AND EXISTS (
                      SELECT 1
                      FROM pg_db_role_setting setting_row
                      WHERE setting_row.setrole = migrator.oid
                        AND setting_row.setdatabase = (SELECT database_oid FROM database_owner)
                        AND ('role=' || :'schema_owner') = ANY(setting_row.setconfig)
                  )
            )
        ),
        (
            9,
            'app_ownership',
            :'legacy_rebaseline' = '1'
                OR (
                    (SELECT count(*) FROM app_schema) = 1
                    AND COALESCE(
                        (SELECT nspowner FROM app_schema) = :'schema_owner'::regrole,
                        false
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM app_objects
                        WHERE owner_oid <> :'schema_owner'::regrole
                    )
                )
        ),
        (
            10,
            'extension_ownership',
            (
                SELECT count(*)
                FROM pg_extension extension_row
                JOIN x_extension_schema schema ON schema.oid = extension_row.extnamespace
                WHERE extension_row.extname IN ('pgcrypto', 'pg_trgm', 'citext')
                  AND extension_row.extowner = :'bootstrap_owner'::regrole
            ) = 3
        )
)
SELECT CASE
    WHEN :'topology_output' = 'diagnostic' THEN format(
        '%s|%s',
        CASE WHEN bool_and(passed) THEN 'canonical' ELSE 'noncanonical' END,
        COALESCE(string_agg(reason, ',' ORDER BY position) FILTER (WHERE NOT passed), '')
    )
    ELSE CASE WHEN bool_and(passed) THEN 't' ELSE 'f' END
END
FROM diagnostic_checks;
ROLLBACK;
SQL
}

run_sealed_role_topology_verifier() {
  if [ "${PINVI_M05_LEGACY_REBASELINE}" != "0" ] \
    || [ "${PINVI_MIGRATOR_DISABLE_LOGIN}" != "1" ]; then
    unset PGPASSWORD
    emit_role_topology_diagnostic "invalid" "input_invalid"
  fi

  if ! verification_result="$(evaluate_role_topology diagnostic)"; then
    unset PGPASSWORD
    emit_role_topology_diagnostic "unavailable" "verification_unavailable"
  fi
  unset PGPASSWORD

  case "${verification_result}" in
    *'
'*) emit_role_topology_diagnostic "unavailable" "verification_unavailable" ;;
  esac

  case "${verification_result}" in
    'canonical|')
      printf '%s\n' '{"schema":"pinvi.role-topology-diagnostic.v1","status":"canonical","mode":"sealed","reasons":[]}'
      exit 0
      ;;
    'noncanonical|'*)
      verification_reasons="${verification_result#noncanonical|}"
      if [ -z "${verification_reasons}" ]; then
        emit_role_topology_diagnostic "unavailable" "verification_unavailable"
      fi
      previous_position=0
      json_reasons=""
      while [ -n "${verification_reasons}" ]; do
        case "${verification_reasons}" in
          *,*)
            verification_reason="${verification_reasons%%,*}"
            verification_reasons="${verification_reasons#*,}"
            ;;
          *)
            verification_reason="${verification_reasons}"
            verification_reasons=""
            ;;
        esac
        case "${verification_reason}" in
          principal_identity) reason_position=1 ;;
          bootstrap_catalog) reason_position=2 ;;
          fence_acl) reason_position=3 ;;
          runtime_role) reason_position=4 ;;
          schema_owner_membership) reason_position=5 ;;
          migration_owner_policy) reason_position=6 ;;
          migrator_sealed) reason_position=7 ;;
          migrator_membership_setting) reason_position=8 ;;
          app_ownership) reason_position=9 ;;
          extension_ownership) reason_position=10 ;;
          *) emit_role_topology_diagnostic "unavailable" "verification_unavailable" ;;
        esac
        if [ "${reason_position}" -le "${previous_position}" ]; then
          emit_role_topology_diagnostic "unavailable" "verification_unavailable"
        fi
        previous_position="${reason_position}"
        if [ -n "${json_reasons}" ]; then
          json_reasons="${json_reasons},"
        fi
        json_reasons="${json_reasons}\"${verification_reason}\""
      done
      printf '%s\n' "{\"schema\":\"pinvi.role-topology-diagnostic.v1\",\"status\":\"noncanonical\",\"mode\":\"sealed\",\"reasons\":[${json_reasons}]}"
      exit 0
      ;;
    *) emit_role_topology_diagnostic "unavailable" "verification_unavailable" ;;
  esac
}

if [ "${PINVI_ROLE_TOPOLOGY_VERIFY_ONLY}" = "1" ]; then
  run_sealed_role_topology_verifier
fi

reset_fresh_role_catalog() {
  # This is deliberately narrower than normal reconciliation: it is only for a
  # just-recreated PinVi database.  A database drop does not remove cluster-wide
  # role memberships or per-role settings, so a prior failed candidate can make
  # the otherwise fresh target fail the strict normal topology gate.  Refuse any
  # dependency outside the four generated non-root roles and this target DB
  # before issuing a single role mutation.  The Manager must create this target
  # from template0: template1 may carry extension/type/namespace residue and is
  # therefore deliberately rejected by the isolation proof below.
  # A fresh-reset refusal is deliberately diagnosable only by a fixed enum.
  # Never expose catalog names, OIDs, ACLs, or psql stderr through the
  # root-owned receipt: the Manager persists that receipt in its durable
  # journal.  Keeping the classification inside this one transaction also
  # preserves the proof-to-mutation lock boundary.
  reset_fresh_role_catalog_diagnostic="unclassified"
  reset_fresh_role_catalog_diagnostic="$(PGPASSWORD="${POSTGRES_PASSWORD}" psql --quiet --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --tuples-only --no-align \
    --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --set="database_name=${POSTGRES_DB}" \
    --set="app_role=${PINVI_APP_DB_USER}" \
    --set="schema_owner=${PINVI_APP_SCHEMA_OWNER}" \
    --set="migration_owner=${PINVI_MIGRATION_OWNER}" \
    --set="migrator_role=${PINVI_MIGRATOR_DB_USER}" \
    --set="expected_system_identifier=${reset_expected_system_identifier}" \
    --set="expected_database_oid=${reset_expected_database_oid}" \
    --set="expected_database_owner=${reset_expected_database_owner}" \
    2>/dev/null <<'SQL'
BEGIN;
LOCK TABLE pg_catalog.pg_authid, pg_catalog.pg_auth_members,
           pg_catalog.pg_db_role_setting, pg_catalog.pg_database,
           pg_catalog.pg_shdepend, pg_catalog.pg_namespace,
           pg_catalog.pg_depend IN ACCESS EXCLUSIVE MODE;
WITH target_database AS (
    SELECT database_row.oid, database_row.datdba
    FROM pg_database database_row
    WHERE database_row.datname = :'database_name'
),
bootstrap_owner AS (
    SELECT role_row.oid
    FROM pg_roles role_row
    WHERE role_row.rolname = current_user
),
target_roles AS (
    SELECT role_row.oid
    FROM pg_roles role_row
    WHERE role_row.rolname IN (
        :'app_role',
        :'schema_owner',
        :'migration_owner',
        :'migrator_role'
    )
),
foreign_membership AS (
    SELECT 1
    FROM pg_auth_members membership
    WHERE (
        membership.roleid IN (SELECT oid FROM target_roles)
        OR membership.member IN (SELECT oid FROM target_roles)
    )
      AND NOT (
        membership.roleid IN (SELECT oid FROM target_roles)
        AND membership.member IN (SELECT oid FROM target_roles)
        AND membership.grantor IN (SELECT oid FROM bootstrap_owner)
      )
),
foreign_database_owner AS (
    SELECT 1
    FROM pg_database database_row
    WHERE database_row.datdba IN (SELECT oid FROM target_roles)
),
foreign_role_setting AS (
    SELECT 1
    FROM pg_db_role_setting setting_row
    WHERE setting_row.setrole IN (SELECT oid FROM target_roles)
      AND setting_row.setdatabase NOT IN (0, (SELECT oid FROM target_database))
),
foreign_shared_dependency AS (
    SELECT 1
    FROM pg_shdepend dependency
    WHERE dependency.refobjid IN (SELECT oid FROM target_roles)
      AND (
        NOT (
            dependency.dbid = 0
            AND dependency.classid = 'pg_auth_members'::regclass
        )
        AND NOT (
            dependency.dbid IN (0, (SELECT oid FROM target_database))
            AND dependency.classid = 'pg_db_role_setting'::regclass
        )
      )
),
foreign_user_namespace_object AS (
    -- pg_depend is the complete namespace-scoped object inventory.  Looking
    -- only at relations and procedures misses a public enum/domain/type and
    -- several other object kinds that can survive a failed prior candidate.
    SELECT 1
    FROM pg_depend dependency
    JOIN pg_namespace namespace
      ON dependency.refclassid = 'pg_namespace'::regclass
     AND dependency.refobjid = namespace.oid
    WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND namespace.nspname NOT LIKE 'pg_temp_%'
      AND namespace.nspname NOT LIKE 'pg_toast_temp_%'
),
isolation AS (
    SELECT
        (SELECT count(*) FROM target_database) = 1
            AND COALESCE(
                (SELECT system_identifier::text FROM pg_control_system())
                    = :'expected_system_identifier',
                false
            )
            AND COALESCE(
                (SELECT oid::text FROM target_database) = :'expected_database_oid',
                false
            )
            AND COALESCE(
                (SELECT datdba::regrole::text FROM target_database)
                    = :'expected_database_owner',
                false
            ) AS target_identity_valid,
        to_regnamespace('app') IS NULL
            AND to_regnamespace('ops') IS NULL
            AND to_regnamespace('pinvi_internal') IS NULL
            AND to_regnamespace('x_extension') IS NULL AS protected_namespace_absent,
        NOT EXISTS (
            SELECT 1 FROM pg_namespace namespace
            WHERE namespace.nspname NOT IN (
                'pg_catalog', 'information_schema', 'pg_toast', 'public'
            )
              AND namespace.nspname NOT LIKE 'pg_temp_%'
              AND namespace.nspname NOT LIKE 'pg_toast_temp_%'
        ) AS extra_namespace_absent,
        NOT EXISTS (
            SELECT 1 FROM pg_extension extension_row
            WHERE extension_row.extname <> 'plpgsql'
        ) AS extension_absent,
        NOT EXISTS (
            SELECT 1 FROM pg_class relation
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
              AND namespace.nspname NOT LIKE 'pg_temp_%'
              AND namespace.nspname NOT LIKE 'pg_toast_temp_%'
        ) AS relation_absent,
        NOT EXISTS (
            SELECT 1 FROM pg_proc procedure
            JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
            WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        ) AS routine_absent,
        NOT EXISTS (SELECT 1 FROM foreign_membership) AS foreign_membership_absent,
        NOT EXISTS (SELECT 1 FROM foreign_database_owner) AS foreign_database_owner_absent,
        NOT EXISTS (SELECT 1 FROM foreign_role_setting) AS foreign_role_setting_absent,
        NOT EXISTS (SELECT 1 FROM foreign_shared_dependency) AS foreign_shared_dependency_absent,
        NOT EXISTS (SELECT 1 FROM foreign_user_namespace_object)
            AS foreign_user_namespace_object_absent
),
reset_classification AS (
    SELECT
        CASE
            WHEN NOT target_identity_valid THEN 'target_identity_invalid'
            WHEN NOT protected_namespace_absent THEN 'protected_namespace_present'
            WHEN NOT extra_namespace_absent THEN 'extra_namespace_present'
            WHEN NOT extension_absent THEN 'extension_present'
            WHEN NOT relation_absent THEN 'relation_present'
            WHEN NOT routine_absent THEN 'routine_present'
            WHEN NOT foreign_membership_absent THEN 'foreign_membership'
            WHEN NOT foreign_database_owner_absent THEN 'foreign_database_owner'
            WHEN NOT foreign_role_setting_absent THEN 'foreign_role_setting'
            WHEN NOT foreign_shared_dependency_absent THEN 'foreign_shared_dependency'
            WHEN NOT foreign_user_namespace_object_absent THEN 'foreign_namespace_object'
            ELSE 'completed'
        END AS reset_class,
        target_identity_valid
            AND protected_namespace_absent
            AND extra_namespace_absent
            AND extension_absent
            AND relation_absent
            AND routine_absent
            AND foreign_membership_absent
            AND foreign_database_owner_absent
            AND foreign_role_setting_absent
            AND foreign_shared_dependency_absent
            AND foreign_user_namespace_object_absent AS reset_isolated
    FROM isolation
)
SELECT reset_class, reset_isolated FROM reset_classification
\gset
\echo :reset_class
\if :reset_isolated
SELECT format('DROP ROLE IF EXISTS %I', :'migrator_role')
\gexec
SELECT format('DROP ROLE IF EXISTS %I', :'migration_owner')
\gexec
SELECT format('DROP ROLE IF EXISTS %I', :'schema_owner')
\gexec
SELECT format('DROP ROLE IF EXISTS %I', :'app_role')
\gexec
COMMIT;
\else
ROLLBACK;
\endif
SQL
  )" || return 1
  case "${reset_fresh_role_catalog_diagnostic}" in
    completed|target_identity_invalid|protected_namespace_present|extra_namespace_present|extension_present|relation_present|routine_present|foreign_membership|foreign_database_owner|foreign_role_setting|foreign_shared_dependency|foreign_namespace_object)
      ;;
    *)
      reset_fresh_role_catalog_diagnostic="unclassified"
      return 1
      ;;
  esac
  [ "${reset_fresh_role_catalog_diagnostic}" = "completed" ]
}

load_fresh_role_catalog_reset_permit() {
  if [ -z "${PINVI_ROLE_CATALOG_RESET_PERMIT_FILE}" ] \
    || [ ! -f "${PINVI_ROLE_CATALOG_RESET_PERMIT_FILE}" ] \
    || [ -L "${PINVI_ROLE_CATALOG_RESET_PERMIT_FILE}" ]; then
    return 1
  fi
  permit_mode="$(stat -c '%u:%g:%a' "${PINVI_ROLE_CATALOG_RESET_PERMIT_FILE}" 2>/dev/null)" || return 1
  if [ "${permit_mode}" != "0:0:600" ]; then
    return 1
  fi
  IFS='|' read -r permit_version permit_transaction permit_pinset \
    reset_expected_system_identifier reset_expected_database_oid \
    reset_expected_database_name reset_expected_database_owner permit_extra \
    < "${PINVI_ROLE_CATALOG_RESET_PERMIT_FILE}" || return 1
  if [ -n "${permit_extra}" ] \
    || [ "${permit_version}" != "pinvi-role-catalog-reset-v1" ] \
    || [ "${reset_expected_database_name}" != "${POSTGRES_DB}" ] \
    || [ -z "${permit_transaction}" ] \
    || [ -z "${permit_pinset}" ] \
    || [ -z "${reset_expected_system_identifier}" ] \
    || [ -z "${reset_expected_database_oid}" ] \
    || [ -z "${reset_expected_database_owner}" ]; then
    return 1
  fi
}

load_fresh_role_catalog_reset_result_file() {
  if [ -z "${PINVI_ROLE_CATALOG_RESET_RESULT_FILE}" ] \
    || [ ! -f "${PINVI_ROLE_CATALOG_RESET_RESULT_FILE}" ] \
    || [ -L "${PINVI_ROLE_CATALOG_RESET_RESULT_FILE}" ]; then
    return 1
  fi
  result_mode="$(stat -c '%u:%g:%a' "${PINVI_ROLE_CATALOG_RESET_RESULT_FILE}" 2>/dev/null)" || return 1
  [ "${result_mode}" = "0:0:600" ]
}

write_fresh_role_catalog_reset_result() {
  result_status="$1"
  result_class="$2"
  printf '%s\n' \
    "{\"schema\":\"pinvi.role-catalog-reset-diagnostic.v1\",\"status\":\"${result_status}\",\"class\":\"${result_class}\",\"transaction\":\"${permit_transaction}\",\"pinset\":\"${permit_pinset}\"}" \
    > "${PINVI_ROLE_CATALOG_RESET_RESULT_FILE}"
}

if [ "${PINVI_ROLE_CATALOG_RESET_ONLY}" = "1" ]; then
  if ! load_fresh_role_catalog_reset_permit \
    || ! load_fresh_role_catalog_reset_result_file; then
    unset PGPASSWORD
    echo "fresh PinVi role catalog reset permit is invalid" >&2
    exit 2
  fi
  if [ "${PINVI_M05_LEGACY_REBASELINE}" != "0" ] \
    || [ "${PINVI_MIGRATOR_DISABLE_LOGIN}" != "1" ]; then
    write_fresh_role_catalog_reset_result "failed" "lifecycle_invalid"
    unset PGPASSWORD
    echo "fresh PinVi role catalog reset has invalid lifecycle input" >&2
    exit 2
  fi
  if ! reset_fresh_role_catalog; then
    write_fresh_role_catalog_reset_result "failed" "${reset_fresh_role_catalog_diagnostic}"
    unset PGPASSWORD
    echo "fresh PinVi role catalog reset could not prove an isolated target" >&2
    exit 3
  fi
  write_fresh_role_catalog_reset_result "completed" "completed"
  unset PGPASSWORD
  exit 0
fi

seal_migrator_login() {
  PGPASSWORD="${POSTGRES_PASSWORD}" psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 \
    --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --set="migrator_role=${PINVI_MIGRATOR_DB_USER}" \
    --set="database_name=${POSTGRES_DB}" \
    >/dev/null <<'SQL'
SELECT format('ALTER ROLE %I NOLOGIN', :'migrator_role')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator_role')
\gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM %I', :'database_name', :'migrator_role')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator_role')
\gexec
SELECT pg_terminate_backend(activity.pid, 5000)
FROM pg_stat_activity activity
JOIN pg_roles migrator ON migrator.oid = activity.usesysid
WHERE migrator.rolname = :'migrator_role'
  AND activity.pid <> pg_backend_pid();
SELECT 1 / CASE WHEN EXISTS (
    SELECT 1
    FROM pg_stat_activity activity
    JOIN pg_roles migrator ON migrator.oid = activity.usesysid
    WHERE migrator.rolname = :'migrator_role'
      AND activity.pid <> pg_backend_pid()
) THEN 0 ELSE 1 END;
SQL
}

seal_migrator_on_failure() {
  status=$?
  if [ "${status}" -ne 0 ] && [ "${PINVI_MIGRATOR_DISABLE_LOGIN}" = "0" ]; then
    seal_migrator_login >/dev/null 2>&1 || true
  fi
  trap - EXIT
  exit "${status}"
}

# Explicit-open은 one-shot migration 전용이다. 이후 어떤 fail-closed 검증이 실패해도
# bootstrap 자체가 LOGIN/CONNECT를 즉시 회수한다. SIGKILL 이외의 종료도 같은 EXIT
# handler로 봉인한다.
trap 'seal_migrator_on_failure' EXIT
trap 'exit 1' HUP INT TERM

# 새 one-shot password를 열기 전에도 이전 backend는 계속 살아 있을 수 있다. 항상
# 먼저 LOGIN/CONNECT를 회수하고 세션 종료까지 확인해, 회전만으로 기존 migrator가
# 남는 경로를 없앤다. 이 효과는 뒤 topology 검증 실패와 분리되어 유지된다.
seal_migrator_login

# 기존 0061 owner를 바꾸는 것은 ADR-063의 rebaseline 범위를 넘는다. 일반 실행은
# 이미 새 app schema owner로 정착한 DB 또는 빈 DB만 받는다. 과거 0061 전환은
# PINVI_M05_LEGACY_REBASELINE=1 root-only one-shot으로만 아래 보호를 우회한다.
if [ "${PINVI_M05_LEGACY_REBASELINE}" = "0" ]; then
  canonical_app_ownership="$(
    psql --no-psqlrc --no-password --tuples-only --no-align --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
      --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
      --set="schema_owner=${PINVI_APP_SCHEMA_OWNER}" <<'SQL'
WITH app_schema AS (
    SELECT namespace.oid, namespace.nspowner::regrole::text AS owner_name
    FROM pg_namespace namespace
    WHERE namespace.nspname = 'app'
),
app_objects AS (
    SELECT relation.relowner::regrole::text AS owner_name
    FROM pg_class relation
    JOIN app_schema schema ON schema.oid = relation.relnamespace
    UNION ALL
    SELECT procedure.proowner::regrole::text
    FROM pg_proc procedure
    JOIN app_schema schema ON schema.oid = procedure.pronamespace
    UNION ALL
    SELECT type_row.typowner::regrole::text
    FROM pg_type type_row
    JOIN app_schema schema ON schema.oid = type_row.typnamespace
    UNION ALL
    SELECT operator_row.oprowner::regrole::text
    FROM pg_operator operator_row
    JOIN app_schema schema ON schema.oid = operator_row.oprnamespace
    UNION ALL
    SELECT collation_row.collowner::regrole::text
    FROM pg_collation collation_row
    JOIN app_schema schema ON schema.oid = collation_row.collnamespace
    UNION ALL
    SELECT conversion_row.conowner::regrole::text
    FROM pg_conversion conversion_row
    JOIN app_schema schema ON schema.oid = conversion_row.connamespace
    UNION ALL
    SELECT opclass_row.opcowner::regrole::text
    FROM pg_opclass opclass_row
    JOIN app_schema schema ON schema.oid = opclass_row.opcnamespace
    UNION ALL
    SELECT opfamily_row.opfowner::regrole::text
    FROM pg_opfamily opfamily_row
    JOIN app_schema schema ON schema.oid = opfamily_row.opfnamespace
    UNION ALL
    SELECT config_row.cfgowner::regrole::text
    FROM pg_ts_config config_row
    JOIN app_schema schema ON schema.oid = config_row.cfgnamespace
    UNION ALL
    SELECT dictionary_row.dictowner::regrole::text
    FROM pg_ts_dict dictionary_row
    JOIN app_schema schema ON schema.oid = dictionary_row.dictnamespace
    UNION ALL
    SELECT statistic_row.stxowner::regrole::text
    FROM pg_statistic_ext statistic_row
    JOIN app_schema schema ON schema.oid = statistic_row.stxnamespace
    UNION ALL
    SELECT extension_row.extowner::regrole::text
    FROM pg_extension extension_row
    JOIN app_schema schema ON schema.oid = extension_row.extnamespace
)
SELECT
    NOT EXISTS (SELECT 1 FROM app_objects)
    OR (
        (SELECT owner_name = :'schema_owner' FROM app_schema)
        AND NOT EXISTS (
            SELECT 1 FROM app_objects
            WHERE owner_name <> :'schema_owner'
        )
    );
SQL
  )"
  if [ "${canonical_app_ownership}" != "t" ]; then
    unset PGPASSWORD
    echo "existing app objects are not owned by PINVI_APP_SCHEMA_OWNER; use the approved root-only legacy rebaseline profile" >&2
    exit 3
  fi
fi

if [ "${PINVI_MIGRATOR_DISABLE_LOGIN}" = "1" ]; then
  migrator_login_attribute="NOLOGIN"
else
  migrator_login_attribute="LOGIN"
fi

psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
  --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
  --set="bootstrap_owner=${POSTGRES_USER}" \
  --set="app_role=${PINVI_APP_DB_USER}" --set="app_password=${PINVI_APP_DB_PASSWORD}" \
  --set="schema_owner=${PINVI_APP_SCHEMA_OWNER}" \
  --set="migration_owner=${PINVI_MIGRATION_OWNER}" \
  --set="migrator_role=${PINVI_MIGRATOR_DB_USER}" \
  --set="migrator_password=${PINVI_MIGRATOR_DB_PASSWORD}" \
  --set="migrator_login_attribute=${migrator_login_attribute}" \
  --set="migrator_disabled=${PINVI_MIGRATOR_DISABLE_LOGIN}" \
  --set="database_name=${POSTGRES_DB}" \
  >/dev/null <<'SQL'
SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L',
    :'app_role',
    :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec
SELECT format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L',
    :'app_role',
    :'app_password'
)
\gexec
SELECT format(
    'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT',
    :'schema_owner'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'schema_owner')
\gexec
SELECT format(
    'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT',
    :'schema_owner'
)
\gexec
SELECT format(
    'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT',
    :'migration_owner'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migration_owner')
\gexec
SELECT format(
    'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT',
    :'migration_owner'
)
\gexec
SELECT format(
    'CREATE ROLE %I %s NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L',
    :'migrator_role',
    :'migrator_login_attribute',
    :'migrator_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator_role')
\gexec
SELECT format(
    'ALTER ROLE %I %s NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L',
    :'migrator_role',
    :'migrator_login_attribute',
    :'migrator_password'
)
\gexec
SELECT format('GRANT %I TO %I WITH INHERIT FALSE, SET TRUE', :'schema_owner', :'migration_owner')
\gexec
SELECT format('GRANT %I TO %I WITH INHERIT FALSE, SET TRUE', :'schema_owner', :'migrator_role')
\gexec
SELECT format('GRANT %I TO %I WITH INHERIT FALSE, SET TRUE', :'migration_owner', :'migrator_role')
\gexec
SELECT format('ALTER ROLE %I IN DATABASE %I SET ROLE TO %I',
              :'migrator_role', :'database_name', :'schema_owner')
\gexec
REVOKE CONNECT ON DATABASE :"database_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name" TO :"app_role";
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'migrator_role')
WHERE :'migrator_disabled' = '0'
\gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM %I', :'database_name', :'migrator_role')
WHERE :'migrator_disabled' = '1'
\gexec
SELECT pg_terminate_backend(activity.pid, 5000)
FROM pg_stat_activity activity
JOIN pg_roles migrator ON migrator.oid = activity.usesysid
WHERE :'migrator_disabled' = '1'
  AND migrator.rolname = :'migrator_role'
  AND activity.pid <> pg_backend_pid();
GRANT CREATE ON DATABASE :"database_name" TO :"schema_owner";
SELECT format('CREATE SCHEMA IF NOT EXISTS x_extension AUTHORIZATION %I', :'bootstrap_owner')
\gexec
SELECT format('ALTER SCHEMA x_extension OWNER TO %I', :'bootstrap_owner')
\gexec
CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS citext SCHEMA x_extension;
REVOKE ALL ON SCHEMA x_extension FROM PUBLIC;
GRANT USAGE ON SCHEMA x_extension TO :"app_role", :"schema_owner", :"migration_owner";
REVOKE ALL ON FUNCTION x_extension.digest(bytea, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION x_extension.digest(bytea, text)
  TO :"app_role", :"schema_owner", :"migration_owner";
SELECT format('CREATE SCHEMA IF NOT EXISTS ops AUTHORIZATION %I', :'migration_owner')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname = 'ops'
)
\gexec
SELECT format('ALTER SCHEMA ops OWNER TO %I', :'migration_owner')
WHERE EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname = 'ops'
)
\gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS pinvi_internal AUTHORIZATION %I', :'schema_owner')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname = 'pinvi_internal'
)
\gexec
SELECT format('ALTER SCHEMA pinvi_internal OWNER TO %I', :'schema_owner')
WHERE EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname = 'pinvi_internal'
)
\gexec
REVOKE ALL ON SCHEMA pinvi_internal FROM PUBLIC;
GRANT USAGE ON SCHEMA pinvi_internal TO :"schema_owner", :"migration_owner";
CREATE OR REPLACE FUNCTION pinvi_internal.acquire_fresh_0101_database_fence()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $pinvi_fresh_0101_fence$
BEGIN
    LOCK TABLE pg_catalog.pg_database IN ACCESS EXCLUSIVE MODE;
    LOCK TABLE pg_catalog.pg_authid, pg_catalog.pg_auth_members,
              pg_catalog.pg_db_role_setting IN ACCESS EXCLUSIVE MODE;
END
$pinvi_fresh_0101_fence$;
ALTER FUNCTION pinvi_internal.acquire_fresh_0101_database_fence() OWNER TO :"bootstrap_owner";
REVOKE ALL ON FUNCTION pinvi_internal.acquire_fresh_0101_database_fence() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pinvi_internal.acquire_fresh_0101_database_fence()
  TO :"schema_owner";
SQL

if [ "${PINVI_M05_LEGACY_REBASELINE}" = "0" ]; then
  psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --set="schema_owner=${PINVI_APP_SCHEMA_OWNER}" \
    >/dev/null <<'SQL'
SELECT format('CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION %I', :'schema_owner')
\gexec
SELECT format('ALTER SCHEMA app OWNER TO %I', :'schema_owner')
\gexec
SQL
fi

# fresh와 legacy 모두 0101이 catalog fingerprint·handoff를 완료한 뒤 app runtime 권한을
# 원자적으로 부여한다. legacy receipt가 결박되기 전에는 app ACL/default ACL을 바꾸지 않는다.
:

role_topology_safe="$(evaluate_role_topology normal)"
unset PGPASSWORD

if [ "${role_topology_safe}" != "t" ]; then
  echo "runtime/migrator/migration-owner role topology is not canonical" >&2
  exit 3
fi

# Alembic은 이미 적용된 0101을 재실행하지 않는다. 따라서 과거 0101 variant가 남긴
# runtime ACL 누락은 일반 role bootstrap에서 exact head일 때만 정본 app owner로 보정한다.
# 0100 이하와 legacy rebaseline은 migration handoff가 ACL을 결정해야 하므로 여기서
# 절대 수정하지 않는다.
if [ "${PINVI_M05_LEGACY_REBASELINE}" = "0" ]; then
  alembic_version_table_exists="$(
    PGPASSWORD="${POSTGRES_PASSWORD}" psql --no-psqlrc --no-password --tuples-only --no-align \
      --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
      --command="SELECT (to_regclass('app.alembic_version') IS NOT NULL)::text;"
  )"
  applied_revision=""
  if [ "${alembic_version_table_exists}" = "true" ]; then
    applied_revision="$(
      PGPASSWORD="${POSTGRES_PASSWORD}" psql --no-psqlrc --no-password --tuples-only --no-align \
        --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" <<'SQL'
SELECT CASE
    WHEN count(*) <> 1 THEN ''
    ELSE COALESCE((SELECT version_num FROM app.alembic_version), '')
END
FROM app.alembic_version;
SQL
    )"
  fi
  if [ "${applied_revision}" = "20260824_0101" ]; then
    PGPASSWORD="${POSTGRES_PASSWORD}" psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 \
      --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
      --set="app_role=${PINVI_APP_DB_USER}" \
      --set="schema_owner=${PINVI_APP_SCHEMA_OWNER}" \
      >/dev/null <<'SQL'
BEGIN;
REVOKE ALL ON SCHEMA app FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO :"app_role";
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA app FROM :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO :"app_role";
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA app FROM :"app_role";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA app TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"schema_owner" IN SCHEMA app
  REVOKE ALL ON TABLES FROM :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"schema_owner" IN SCHEMA app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"schema_owner" IN SCHEMA app
  REVOKE ALL ON SEQUENCES FROM :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"schema_owner" IN SCHEMA app
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"app_role";
REVOKE ALL PRIVILEGES ON TABLE app.alembic_version FROM :"app_role";
GRANT SELECT ON TABLE app.alembic_version TO :"app_role";
COMMIT;
SQL
  fi
fi
