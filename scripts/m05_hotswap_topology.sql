-- M05 hotswap 전·후 권한·역할 topology의 canonical SHA-256을 계산한다.
--
-- psql 변수는 모두 SQL literal로 치환한다. 호출자는 marker/schema validator를 통과한
-- 값만 전달한다. 이 파일은 한 줄 hash만 출력하며, catalog 원문을 operator log에 남기지
-- 않는다. source/previous/restore schema의 객체 표면은 전부 포함하되 x_extension은
-- schema ACL만 포함한다. 확장 객체 전체를 넣으면 PinVi hotswap과 무관한 extension churn이
-- recovery proof를 불필요하게 무효화하기 때문이다.
WITH parameters AS (
  SELECT
    :'source_schema'::name AS source_schema,
    :'previous_schema'::name AS previous_schema,
    :'restore_schema'::name AS restore_schema,
    :'app_role'::name AS app_role,
    :'fence_role'::name AS fence_role
),
schema_scope AS (
  SELECT namespace_row.oid, namespace_row.nspname, namespace_row.nspowner, namespace_row.nspacl
  FROM pg_namespace AS namespace_row
  CROSS JOIN parameters
  WHERE namespace_row.nspname IN (
    parameters.source_schema,
    parameters.previous_schema,
    parameters.restore_schema,
    'x_extension'::name
  )
),
active_schema_scope AS (
  SELECT schema_scope.*
  FROM schema_scope
  CROSS JOIN parameters
  WHERE schema_scope.nspname IN (
    parameters.source_schema,
    parameters.previous_schema,
    parameters.restore_schema
  )
),
source_owner_scope AS (
  SELECT schema_scope.nspowner AS role_oid
  FROM schema_scope
  CROSS JOIN parameters
  WHERE schema_scope.nspname = parameters.source_schema
),
restore_executor_scope AS (
  SELECT current_user::regrole::oid AS role_oid
),
role_scope AS (
  SELECT
    role_row.oid,
    role_row.rolname,
    role_row.rolcanlogin,
    role_row.rolsuper,
    role_row.rolinherit,
    role_row.rolcreaterole,
    role_row.rolcreatedb,
    role_row.rolreplication,
    role_row.rolbypassrls,
    role_row.rolconnlimit,
    role_row.rolvaliduntil,
    role_row.rolconfig
  FROM pg_roles AS role_row
  CROSS JOIN parameters
  WHERE role_row.rolname IN (parameters.app_role, parameters.fence_role)
     OR role_row.oid IN (SELECT role_oid FROM source_owner_scope)
     OR role_row.oid IN (SELECT role_oid FROM restore_executor_scope)
),
default_acl_owner_scope AS (
  SELECT role_oid FROM source_owner_scope
  UNION
  SELECT role_oid FROM restore_executor_scope
),
relation_scope AS (
  SELECT
    class_row.oid,
    class_row.relnamespace,
    class_row.relname,
    class_row.relkind,
    class_row.relowner,
    class_row.relacl
  FROM pg_class AS class_row
  JOIN active_schema_scope ON active_schema_scope.oid = class_row.relnamespace
  WHERE class_row.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
),
procedure_scope AS (
  SELECT
    procedure_row.oid,
    procedure_row.pronamespace,
    procedure_row.proname,
    procedure_row.proowner,
    procedure_row.proacl,
    procedure_row.prosecdef,
    pg_get_function_identity_arguments(procedure_row.oid) AS identity_arguments
  FROM pg_proc AS procedure_row
  JOIN schema_scope ON schema_scope.oid = procedure_row.pronamespace
  CROSS JOIN parameters
  WHERE schema_scope.nspname = parameters.source_schema
),
type_scope AS (
  SELECT
    type_row.oid,
    type_row.typnamespace,
    type_row.typname,
    type_row.typtype,
    type_row.typowner,
    type_row.typacl
  FROM pg_type AS type_row
  JOIN schema_scope ON schema_scope.oid = type_row.typnamespace
  CROSS JOIN parameters
  WHERE schema_scope.nspname = parameters.source_schema
),
column_scope AS (
  SELECT
    attribute_row.attrelid,
    attribute_row.attnum,
    attribute_row.attname,
    attribute_row.atttypid,
    attribute_row.attacl
  FROM pg_attribute AS attribute_row
  JOIN relation_scope ON relation_scope.oid = attribute_row.attrelid
  WHERE attribute_row.attnum > 0
    AND NOT attribute_row.attisdropped
),
default_acl_scope AS (
  SELECT default_acl.*
  FROM pg_default_acl AS default_acl
  WHERE default_acl.defaclnamespace IN (SELECT oid FROM active_schema_scope)
     OR (
       default_acl.defaclnamespace = 0
       AND default_acl.defaclrole IN (SELECT role_oid FROM default_acl_owner_scope)
     )
),
entries AS (
  SELECT jsonb_build_object(
    'kind', 'role',
    'oid', role_scope.oid,
    'name', role_scope.rolname,
    'can_login', role_scope.rolcanlogin,
    'superuser', role_scope.rolsuper,
    'inherit', role_scope.rolinherit,
    'create_role', role_scope.rolcreaterole,
    'create_database', role_scope.rolcreatedb,
    'replication', role_scope.rolreplication,
    'bypass_rls', role_scope.rolbypassrls,
    'connection_limit', role_scope.rolconnlimit,
    'valid_until', role_scope.rolvaliduntil,
    'configuration', role_scope.rolconfig
  ) AS entry
  FROM role_scope

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'role_membership',
    'member', membership.member,
    'role', membership.roleid,
    'grantor', membership.grantor,
    'admin_option', membership.admin_option,
    'inherit_option', membership.inherit_option,
    'set_option', membership.set_option
  )
  FROM pg_auth_members AS membership
  WHERE membership.member IN (SELECT oid FROM role_scope)
     OR membership.roleid IN (SELECT oid FROM role_scope)

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'database_acl_definition',
    'database_oid', database_row.oid,
    'acl_is_null', database_row.datacl IS NULL
  )
  FROM pg_database AS database_row
  WHERE database_row.datname = current_database()

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'database_acl',
    'grantor', acl.grantor,
    'grantee', acl.grantee,
    'privilege', acl.privilege_type,
    'grant_option', acl.is_grantable
  )
  FROM pg_database AS database_row
  CROSS JOIN LATERAL aclexplode(
    COALESCE(database_row.datacl, acldefault('d', database_row.datdba))
  ) AS acl
  WHERE database_row.datname = current_database()

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'schema',
    'oid', schema_scope.oid,
    'name', schema_scope.nspname,
    'owner', schema_scope.nspowner,
    'acl_is_null', schema_scope.nspacl IS NULL
  )
  FROM schema_scope

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'schema_acl',
    'schema_oid', schema_scope.oid,
    'grantor', acl.grantor,
    'grantee', acl.grantee,
    'privilege', acl.privilege_type,
    'grant_option', acl.is_grantable
  )
  FROM schema_scope
  CROSS JOIN LATERAL aclexplode(
    COALESCE(schema_scope.nspacl, acldefault('n', schema_scope.nspowner))
  ) AS acl

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'relation',
    'oid', relation_scope.oid,
    'schema_oid', relation_scope.relnamespace,
    'name', relation_scope.relname,
    'relation_kind', relation_scope.relkind,
    'owner', relation_scope.relowner,
    'acl_is_null', relation_scope.relacl IS NULL
  )
  FROM relation_scope

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'relation_acl',
    'relation_oid', relation_scope.oid,
    'grantor', acl.grantor,
    'grantee', acl.grantee,
    'privilege', acl.privilege_type,
    'grant_option', acl.is_grantable
  )
  FROM relation_scope
  CROSS JOIN LATERAL aclexplode(
    COALESCE(
      relation_scope.relacl,
      acldefault(
        CASE WHEN relation_scope.relkind = 'S' THEN 'S'::"char" ELSE 'r'::"char" END,
        relation_scope.relowner
      )
    )
  ) AS acl

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'column',
    'relation_oid', column_scope.attrelid,
    'number', column_scope.attnum,
    'name', column_scope.attname,
    'type_oid', column_scope.atttypid,
    'acl_is_null', column_scope.attacl IS NULL
  )
  FROM column_scope

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'column_acl',
    'relation_oid', column_scope.attrelid,
    'number', column_scope.attnum,
    'grantor', acl.grantor,
    'grantee', acl.grantee,
    'privilege', acl.privilege_type,
    'grant_option', acl.is_grantable
  )
  FROM column_scope
  CROSS JOIN LATERAL aclexplode(
    CASE
      WHEN array_ndims(column_scope.attacl) = 1 THEN column_scope.attacl
      ELSE NULL::aclitem[]
    END
  ) AS acl

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'procedure',
    'oid', procedure_scope.oid,
    'schema_oid', procedure_scope.pronamespace,
    'name', procedure_scope.proname,
    'identity_arguments', procedure_scope.identity_arguments,
    'owner', procedure_scope.proowner,
    'security_definer', procedure_scope.prosecdef,
    'acl_is_null', procedure_scope.proacl IS NULL
  )
  FROM procedure_scope

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'procedure_acl',
    'procedure_oid', procedure_scope.oid,
    'grantor', acl.grantor,
    'grantee', acl.grantee,
    'privilege', acl.privilege_type,
    'grant_option', acl.is_grantable
  )
  FROM procedure_scope
  CROSS JOIN LATERAL aclexplode(
    COALESCE(procedure_scope.proacl, acldefault('f', procedure_scope.proowner))
  ) AS acl

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'type',
    'oid', type_scope.oid,
    'schema_oid', type_scope.typnamespace,
    'name', type_scope.typname,
    'type_kind', type_scope.typtype,
    'owner', type_scope.typowner,
    'acl_is_null', type_scope.typacl IS NULL
  )
  FROM type_scope

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'type_acl',
    'type_oid', type_scope.oid,
    'grantor', acl.grantor,
    'grantee', acl.grantee,
    'privilege', acl.privilege_type,
    'grant_option', acl.is_grantable
  )
  FROM type_scope
  CROSS JOIN LATERAL aclexplode(
    COALESCE(type_scope.typacl, acldefault('T', type_scope.typowner))
  ) AS acl

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'default_acl_definition',
    'schema_oid', default_acl_scope.defaclnamespace,
    'owner', default_acl_scope.defaclrole,
    'object_kind', default_acl_scope.defaclobjtype,
    'acl_is_null', default_acl_scope.defaclacl IS NULL
  )
  FROM default_acl_scope

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'default_acl',
    'schema_oid', default_acl_scope.defaclnamespace,
    'owner', default_acl_scope.defaclrole,
    'object_kind', default_acl_scope.defaclobjtype,
    'grantor', acl.grantor,
    'grantee', acl.grantee,
    'privilege', acl.privilege_type,
    'grant_option', acl.is_grantable
  )
  FROM default_acl_scope
  CROSS JOIN LATERAL aclexplode(
    COALESCE(
      default_acl_scope.defaclacl,
      acldefault(default_acl_scope.defaclobjtype, default_acl_scope.defaclrole)
    )
  ) AS acl

  UNION ALL

  SELECT jsonb_build_object(
    'kind', 'accessible_security_definer',
    'oid', procedure_row.oid,
    'schema', namespace_row.nspname,
    'owner', procedure_row.proowner,
    'identity_arguments', pg_get_function_identity_arguments(procedure_row.oid)
  )
  FROM pg_proc AS procedure_row
  JOIN pg_namespace AS namespace_row ON namespace_row.oid = procedure_row.pronamespace
  JOIN role_scope AS app_role ON app_role.rolname = (SELECT app_role FROM parameters)
  CROSS JOIN parameters
  WHERE procedure_row.prosecdef
    AND namespace_row.nspname NOT IN ('pg_catalog', 'pg_toast', 'information_schema')
    AND namespace_row.nspname <> parameters.source_schema
    AND has_function_privilege(app_role.oid, procedure_row.oid, 'EXECUTE')
)
SELECT encode(
  x_extension.digest(
    convert_to(
      COALESCE(
        (SELECT jsonb_agg(entries.entry ORDER BY entries.entry::text)::text FROM entries),
        '[]'
      ),
      'UTF8'
    ),
    'sha256'
  ),
  'hex'
);
