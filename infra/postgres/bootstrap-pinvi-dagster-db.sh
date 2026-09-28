#!/usr/bin/env sh
# Dagster instance storage: its own database, owned by its own login.
#
# apps/etl/dagster.yaml reads the instance storage DSN from PINVI_DAGSTER_PG_URL, and
# that DSN cannot name the PinVi app database: dagster-postgres keeps its schema
# history in a table called `alembic_version`, the same name PinVi's Alembic uses.
# Production gets this database from the Docker Manager
# (`kor-travel-shared-db-init-pinvi`). This one-shot is the same step for PinVi's own
# Compose stacks (smoke, the Manager's isolated M05 run, fresh deploy-node stacks).
#
# The login is not one of the M05 roles, and none of the M05 roles gains anything:
#   - LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT,
#     not a member of any role and no role is a member of it;
#   - it owns the Dagster database and nothing else, so Dagster's
#     `should_autocreate_tables` can create its tables on first start;
#   - PUBLIC has no privilege on the Dagster database, so the app runtime role cannot
#     connect to it;
#   - it has no CONNECT on the app database. app-db-runtime-role revokes PUBLIC
#     CONNECT there, and Compose runs this one-shot only after that one-shot succeeded.
#
# Idempotent. A re-run re-applies the role attributes and the password. A Dagster
# database that already exists but belongs to another role is refused before any
# change, not re-owned: its tables would still belong to the old owner.

set -eu

# Root bootstrap credentials must never inherit a caller-selected libpq target.
unset PGAPPNAME PGCONNECT_TIMEOUT PGDATABASE PGHOST PGHOSTADDR PGOPTIONS PGPASSFILE \
  PGPASSWORD PGPORT PGSERVICE PGSERVICEFILE PGSSLCERT PGSSLMODE PGSSLKEY \
  PGSSLROOTCERT PGTARGETSESSIONATTRS PGUSER PSQLRC

# Only the ordinary PinVi Compose network endpoint. The Manager provisions the
# production database itself and never runs this script.
PINVI_DB_HOST="app-postgres"
PINVI_DB_PORT="5432"

input_error() {
  echo "$1" >&2
  exit 2
}

require_value() {
  if [ -z "$2" ]; then
    input_error "$1 is required"
  fi
}

require_value "POSTGRES_USER" "${POSTGRES_USER:-}"
require_value "POSTGRES_PASSWORD" "${POSTGRES_PASSWORD:-}"
require_value "POSTGRES_DB" "${POSTGRES_DB:-}"
require_value "PINVI_APP_DB_USER" "${PINVI_APP_DB_USER:-}"
require_value "PINVI_APP_SCHEMA_OWNER" "${PINVI_APP_SCHEMA_OWNER:-}"
require_value "PINVI_MIGRATION_OWNER" "${PINVI_MIGRATION_OWNER:-}"
require_value "PINVI_MIGRATOR_DB_USER" "${PINVI_MIGRATOR_DB_USER:-}"
require_value "PINVI_DAGSTER_DB" "${PINVI_DAGSTER_DB:-}"
require_value "PINVI_DAGSTER_DB_USER" "${PINVI_DAGSTER_DB_USER:-}"
require_value "PINVI_DAGSTER_DB_PASSWORD" "${PINVI_DAGSTER_DB_PASSWORD:-}"

for identifier in \
  "${POSTGRES_USER}" \
  "${POSTGRES_DB}" \
  "${PINVI_APP_DB_USER}" \
  "${PINVI_APP_SCHEMA_OWNER}" \
  "${PINVI_MIGRATION_OWNER}" \
  "${PINVI_MIGRATOR_DB_USER}" \
  "${PINVI_DAGSTER_DB}" \
  "${PINVI_DAGSTER_DB_USER}"; do
  case "${identifier}" in
    ''|[!a-z_]*|*[!a-z0-9_]* ) input_error "invalid PostgreSQL identifier" ;;
  esac
done

# The Dagster login must be a new principal. Naming an M05 role or the bootstrap owner
# here would hand that role a new password and ownership of the Dagster database.
for reserved_role in \
  "${POSTGRES_USER}" \
  "${PINVI_APP_DB_USER}" \
  "${PINVI_APP_SCHEMA_OWNER}" \
  "${PINVI_MIGRATION_OWNER}" \
  "${PINVI_MIGRATOR_DB_USER}"; do
  if [ "${PINVI_DAGSTER_DB_USER}" = "${reserved_role}" ]; then
    input_error "PINVI_DAGSTER_DB_USER must differ from the bootstrap and M05 roles"
  fi
done
case "${PINVI_DAGSTER_DB}" in
  "${POSTGRES_DB}"|postgres|template0|template1 )
    input_error "PINVI_DAGSTER_DB must name a database of its own"
    ;;
esac

export PGPASSWORD="${POSTGRES_PASSWORD}"
attempt=0
until psql --no-psqlrc --no-password --tuples-only --no-align --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
  --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" --command='SELECT 1' >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  # Same first-run restart window as bootstrap-pinvi-runtime-role.sh.
  if [ "$attempt" -ge 90 ]; then
    unset PGPASSWORD
    echo "Postgres TCP endpoint did not become ready for the Dagster database bootstrap" >&2
    exit 1
  fi
  sleep 1
done

# Refuse before any mutation: a Dagster database that exists but belongs to another
# role is not ours to re-own or to change the ACL of.
existing_database="$(
  psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --quiet --tuples-only --no-align \
    --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --set="dagster_role=${PINVI_DAGSTER_DB_USER}" \
    --set="dagster_db=${PINVI_DAGSTER_DB}" <<'SQL'
SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'dagster_db') THEN 'absent'
    WHEN (SELECT datdba FROM pg_database WHERE datname = :'dagster_db')
        = (SELECT oid FROM pg_roles WHERE rolname = :'dagster_role') THEN 'owned'
    ELSE 'foreign'
END;
SQL
)"
case "${existing_database}" in
  absent|owned ) ;;
  foreign )
    unset PGPASSWORD
    echo "the Dagster storage database already exists and belongs to another role; refusing to adopt it" >&2
    exit 3
    ;;
  * )
    unset PGPASSWORD
    echo "could not determine the Dagster storage database owner" >&2
    exit 1
    ;;
esac

# No explicit transaction: CREATE DATABASE cannot run inside one. Every statement is
# its own autocommit step and ON_ERROR_STOP ends the script at the first failure.
psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
  --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
  --set="dagster_role=${PINVI_DAGSTER_DB_USER}" \
  --set="dagster_password=${PINVI_DAGSTER_DB_PASSWORD}" \
  --set="dagster_db=${PINVI_DAGSTER_DB}" \
  >/dev/null <<'SQL'
SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L',
    :'dagster_role',
    :'dagster_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'dagster_role')
\gexec
SELECT format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L',
    :'dagster_role',
    :'dagster_password'
)
\gexec
-- template0: template1 may carry extensions or objects that the Dagster login would
-- then find in a database it owns but did not create.
SELECT format('CREATE DATABASE %I OWNER %I TEMPLATE template0', :'dagster_db', :'dagster_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'dagster_db')
\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'dagster_db')
\gexec
SQL

storage_isolated="$(
  psql --no-psqlrc --no-password --set=ON_ERROR_STOP=1 --quiet --tuples-only --no-align \
    --host="${PINVI_DB_HOST}" --port="${PINVI_DB_PORT}" \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --set="dagster_role=${PINVI_DAGSTER_DB_USER}" \
    --set="dagster_db=${PINVI_DAGSTER_DB}" \
    --set="app_db=${POSTGRES_DB}" <<'SQL'
WITH dagster_role AS (
    SELECT * FROM pg_roles WHERE rolname = :'dagster_role'
),
dagster_database AS (
    SELECT * FROM pg_database WHERE datname = :'dagster_db'
)
SELECT (
    (SELECT count(*) FROM dagster_role) = 1
    AND (SELECT count(*) FROM dagster_database) = 1
    AND EXISTS (
        SELECT 1 FROM dagster_role role_row
        WHERE role_row.rolcanlogin
          AND NOT role_row.rolsuper
          AND NOT role_row.rolcreaterole
          AND NOT role_row.rolcreatedb
          AND NOT role_row.rolreplication
          AND NOT role_row.rolbypassrls
          AND NOT role_row.rolinherit
    )
    AND NOT EXISTS (
        SELECT 1 FROM pg_auth_members membership
        WHERE membership.member = (SELECT oid FROM dagster_role)
           OR membership.roleid = (SELECT oid FROM dagster_role)
    )
    -- It owns the Dagster database, and no other database.
    AND (SELECT datdba FROM dagster_database) = (SELECT oid FROM dagster_role)
    AND NOT EXISTS (
        SELECT 1 FROM pg_database database_row
        WHERE database_row.datdba = (SELECT oid FROM dagster_role)
          AND database_row.datname <> :'dagster_db'
    )
    -- Nobody but the owner holds a privilege on the Dagster database.
    AND NOT EXISTS (
        SELECT 1
        FROM dagster_database database_row
        CROSS JOIN LATERAL aclexplode(
            COALESCE(database_row.datacl, acldefault('d', database_row.datdba))
        ) AS acl
        WHERE acl.grantee <> database_row.datdba
    )
    -- It cannot reach the app database.
    AND NOT has_database_privilege((SELECT oid FROM dagster_role), :'app_db', 'CONNECT')
)::text;
SQL
)"
unset PGPASSWORD

if [ "${storage_isolated}" != "true" ]; then
  echo "the Dagster login is not isolated (role attributes, a membership, another owned database, a non-owner privilege on the Dagster database, or CONNECT on the app database)" >&2
  exit 3
fi
