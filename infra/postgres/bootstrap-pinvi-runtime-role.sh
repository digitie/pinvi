#!/usr/bin/env sh
# Runtime DB login and one-shot Alembic role topology bootstrap.
#
# app-api/app-dagster only receive PINVI_APP_DB_USER. The root bootstrap login
# creates (or temporarily re-enables) the non-inheriting migrator login, while
# 0101 itself switches just its M05 receipt DDL to PINVI_MIGRATION_OWNER.

set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${PINVI_APP_DB_USER:?PINVI_APP_DB_USER is required}"
: "${PINVI_APP_DB_PASSWORD:?PINVI_APP_DB_PASSWORD is required}"
: "${PINVI_APP_SCHEMA_OWNER:?PINVI_APP_SCHEMA_OWNER is required}"
: "${PINVI_MIGRATION_OWNER:?PINVI_MIGRATION_OWNER is required}"
: "${PINVI_MIGRATOR_DB_USER:?PINVI_MIGRATOR_DB_USER is required}"
: "${PINVI_MIGRATOR_DB_PASSWORD:?PINVI_MIGRATOR_DB_PASSWORD is required}"

PINVI_M05_LEGACY_REBASELINE="${PINVI_M05_LEGACY_REBASELINE:-0}"
PINVI_MIGRATOR_DISABLE_LOGIN="${PINVI_MIGRATOR_DISABLE_LOGIN:-1}"

for role_name in \
  "${POSTGRES_USER}" \
  "${PINVI_APP_DB_USER}" \
  "${PINVI_APP_SCHEMA_OWNER}" \
  "${PINVI_MIGRATION_OWNER}" \
  "${PINVI_MIGRATOR_DB_USER}"; do
  case "${role_name}" in
    ''|[!a-z_]*|*[!a-z0-9_]* ) echo "invalid PostgreSQL role name" >&2; exit 2 ;;
  esac
done
case "${POSTGRES_DB}" in
  ''|[!a-z_]*|*[!a-z0-9_]* ) echo "invalid POSTGRES_DB" >&2; exit 2 ;;
esac
case "${PINVI_M05_LEGACY_REBASELINE}" in
  0|1 ) ;;
  * ) echo "PINVI_M05_LEGACY_REBASELINE must be 0 or 1" >&2; exit 2 ;;
esac
case "${PINVI_MIGRATOR_DISABLE_LOGIN}" in
  0|1 ) ;;
  * ) echo "PINVI_MIGRATOR_DISABLE_LOGIN must be 0 or 1" >&2; exit 2 ;;
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
  echo "runtime, schema owner, migration owner, migrator, and bootstrap roles must differ" >&2
  exit 2
fi

export PGPASSWORD="${POSTGRES_PASSWORD}"
attempt=0
until psql --no-psqlrc --no-password --tuples-only --no-align --host=app-postgres \
  --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" --command='SELECT 1' >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 15 ]; then
    unset PGPASSWORD
    echo "Postgres TCP endpoint did not become ready for DB role bootstrap" >&2
    exit 1
  fi
  sleep 1
done

seal_migrator_login() {
  PGPASSWORD="${POSTGRES_PASSWORD}" psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 \
    --host=app-postgres --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
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
    psql --no-psqlrc --no-password --tuples-only --no-align --host=app-postgres \
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

psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --host=app-postgres \
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
GRANT CREATE ON DATABASE :"database_name" TO :"schema_owner", :"migration_owner";
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
SQL

if [ "${PINVI_M05_LEGACY_REBASELINE}" = "0" ]; then
  psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --host=app-postgres \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --set="schema_owner=${PINVI_APP_SCHEMA_OWNER}" \
    >/dev/null <<'SQL'
SELECT format('CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION %I', :'schema_owner')
\gexec
SELECT format('ALTER SCHEMA app OWNER TO %I', :'schema_owner')
\gexec
SQL
fi

grant_app_runtime_privileges() {
  default_privilege_owner="$1"
  psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --host=app-postgres \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --set="app_role=${PINVI_APP_DB_USER}" \
    --set="default_privilege_owner=${default_privilege_owner}" \
    >/dev/null <<'SQL'
REVOKE ALL ON SCHEMA app FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO :"app_role";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA app TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"default_privilege_owner" IN SCHEMA app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"default_privilege_owner" IN SCHEMA app
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"app_role";
-- runtime은 application data만 갱신할 수 있다. migration provenance는
-- schema owner / one-shot migrator만 바꿀 수 있도록 broad table grant 뒤에 제외한다.
SELECT format('REVOKE ALL PRIVILEGES ON TABLE app.alembic_version FROM %I', :'app_role')
WHERE to_regclass('app.alembic_version') IS NOT NULL
\gexec
SQL
}

if [ "${PINVI_M05_LEGACY_REBASELINE}" = "0" ]; then
  grant_app_runtime_privileges "${PINVI_APP_SCHEMA_OWNER}"
fi

role_topology_safe="$(
  psql --no-psqlrc --no-password --tuples-only --no-align --host=app-postgres \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --set="bootstrap_owner=${POSTGRES_USER}" \
    --set="app_role=${PINVI_APP_DB_USER}" \
    --set="schema_owner=${PINVI_APP_SCHEMA_OWNER}" \
    --set="migration_owner=${PINVI_MIGRATION_OWNER}" \
    --set="migrator_role=${PINVI_MIGRATOR_DB_USER}" \
    --set="legacy_rebaseline=${PINVI_M05_LEGACY_REBASELINE}" \
    --set="migrator_disabled=${PINVI_MIGRATOR_DISABLE_LOGIN}" <<'SQL'
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
)
SELECT
    (SELECT count(*) FROM runtime_role) = 1
    AND (SELECT count(*) FROM schema_owner) = 1
    AND (SELECT count(*) FROM migration_owner) = 1
    AND (SELECT count(*) FROM migrator_role) = 1
    AND (SELECT count(*) FROM database_owner) = 1
    AND (SELECT count(*) FROM app_schema) = 1
    AND (SELECT count(*) FROM x_extension_schema) = 1
    AND EXISTS (
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
          AND (
              :'legacy_rebaseline' = '1'
              OR has_schema_privilege(runtime.oid, 'app', 'USAGE')
          )
          AND has_schema_privilege(runtime.oid, 'x_extension', 'USAGE')
          AND NOT has_schema_privilege(runtime.oid, 'app', 'CREATE')
          AND NOT has_schema_privilege(runtime.oid, 'x_extension', 'CREATE')
    )
    AND EXISTS (
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
    AND EXISTS (
        SELECT 1 FROM migration_owner owner
        WHERE NOT owner.rolcanlogin
          AND NOT owner.rolsuper
          AND NOT owner.rolcreaterole
          AND NOT owner.rolcreatedb
          AND NOT owner.rolreplication
          AND NOT owner.rolbypassrls
          AND NOT owner.rolinherit
          AND owner.oid <> (SELECT oid FROM database_owner)
          AND has_database_privilege(owner.oid, current_database(), 'CREATE')
          AND NOT has_database_privilege(owner.oid, current_database(), 'CONNECT')
          AND has_schema_privilege(owner.oid, 'x_extension', 'USAGE')
          AND NOT has_schema_privilege(owner.oid, 'x_extension', 'CREATE')
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
    AND EXISTS (
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
          AND (
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
    AND (SELECT nspowner FROM x_extension_schema) = :'bootstrap_owner'::regrole
    AND (
        :'legacy_rebaseline' = '1'
        OR (
            (SELECT nspowner FROM app_schema) = :'schema_owner'::regrole
            AND NOT EXISTS (
                SELECT 1 FROM app_objects
                WHERE owner_oid <> :'schema_owner'::regrole
            )
        )
    )
    AND (
        SELECT count(*)
        FROM pg_extension extension_row
        JOIN x_extension_schema schema ON schema.oid = extension_row.extnamespace
        WHERE extension_row.extname IN ('pgcrypto', 'pg_trgm', 'citext')
          AND extension_row.extowner = :'bootstrap_owner'::regrole
    ) = 3;
SQL
)"
unset PGPASSWORD

if [ "${role_topology_safe}" != "t" ]; then
  echo "runtime/migrator/migration-owner role topology is not canonical" >&2
  exit 3
fi
