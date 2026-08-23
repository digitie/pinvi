#!/usr/bin/env sh
# App runtime DB login bootstrap.  The migration/restore owner never reaches API/Dagster.

set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${PINVI_APP_DB_USER:?PINVI_APP_DB_USER is required}"
: "${PINVI_APP_DB_PASSWORD:?PINVI_APP_DB_PASSWORD is required}"

case "${POSTGRES_USER}" in
  ''|[!a-z_]*|*[!a-z0-9_]* ) echo "invalid POSTGRES_USER" >&2; exit 2 ;;
esac
case "${PINVI_APP_DB_USER}" in
  ''|[!a-z_]*|*[!a-z0-9_]* ) echo "invalid PINVI_APP_DB_USER" >&2; exit 2 ;;
esac
if [ "${POSTGRES_USER}" = "${PINVI_APP_DB_USER}" ]; then
  echo "runtime DB role must differ from the migration owner" >&2
  exit 2
fi

export PGPASSWORD="${POSTGRES_PASSWORD}"
attempt=0
until psql --no-password --tuples-only --no-align --host=app-postgres \
  --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" --command='SELECT 1' >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 15 ]; then
    unset PGPASSWORD
    echo "Postgres TCP endpoint did not become ready for runtime role bootstrap" >&2
    exit 1
  fi
  sleep 1
done
psql --no-password --set=ON_ERROR_STOP=1 --host=app-postgres --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" --set="owner=${POSTGRES_USER}" \
  --set="app_role=${PINVI_APP_DB_USER}" --set="app_password=${PINVI_APP_DB_PASSWORD}" \
  >/dev/null <<'SQL'
SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT PASSWORD %L',
    :'app_role',
    :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec
SELECT format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT PASSWORD %L',
    :'app_role',
    :'app_password'
)
\gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION %I', :'owner')
\gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS x_extension AUTHORIZATION %I', :'owner')
\gexec
SELECT format('ALTER SCHEMA x_extension OWNER TO %I', :'owner')
\gexec
REVOKE ALL ON SCHEMA app FROM PUBLIC;
REVOKE ALL ON SCHEMA x_extension FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO :"app_role";
GRANT USAGE ON SCHEMA x_extension TO :"app_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO :"app_role";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA app TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA app
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"app_role";
SQL

runtime_role_safe="$(
  psql --no-password --tuples-only --no-align --host=app-postgres \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --set="app_role=${PINVI_APP_DB_USER}" <<'SQL'
SELECT
  r.rolcanlogin
  AND NOT r.rolsuper
  AND NOT r.rolcreaterole
  AND NOT r.rolcreatedb
  AND NOT r.rolreplication
  AND NOT pg_has_role(r.oid, current_user, 'member')
  AND r.oid <> current_user::regrole
  AND NOT EXISTS (
    SELECT 1
    FROM pg_auth_members m
    WHERE m.member = r.oid
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_namespace n
    WHERE n.nspname IN ('app', 'x_extension')
      AND (
        n.nspowner = r.oid
        OR pg_has_role(r.oid, n.nspowner, 'member')
        OR has_schema_privilege(r.oid, n.oid, 'CREATE')
      )
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('app', 'x_extension')
      AND (c.relowner = r.oid OR pg_has_role(r.oid, c.relowner, 'member'))
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname IN ('app', 'x_extension')
      AND (p.proowner = r.oid OR pg_has_role(r.oid, p.proowner, 'member'))
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname IN ('app', 'x_extension')
      AND (t.typowner = r.oid OR pg_has_role(r.oid, t.typowner, 'member'))
  )
  AND NOT EXISTS (
    SELECT 1
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE n.nspname = 'x_extension'
      AND (e.extowner = r.oid OR pg_has_role(r.oid, e.extowner, 'member'))
  )
FROM pg_roles r
WHERE r.rolname = :'app_role';
SQL
)"
unset PGPASSWORD

if [ "${runtime_role_safe}" != "t" ]; then
  echo "runtime DB role is privileged, has a role membership, owns protected objects, can CREATE there, or inherits the migration owner" >&2
  exit 3
fi
