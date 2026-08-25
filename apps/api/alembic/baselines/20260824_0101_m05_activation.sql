CREATE SCHEMA IF NOT EXISTS "ops";

CREATE FUNCTION "ops"."guard_m05_activation_database_anchor_append_only"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
                USING ERRCODE = '55000';
        END;
        $$;

CREATE FUNCTION "ops"."guard_m05_hotswap_release_receipts_append_only"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
                USING ERRCODE = '55000';
        END;
        $$;

CREATE FUNCTION "ops"."m05_hotswap_release_topology_sha256"("p_source_schema" "name", "p_previous_schema" "name", "p_restore_schema" "name", "p_app_role" "name", "p_fence_role" "name", "p_restore_executor_role" "name") RETURNS "text"
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'pg_catalog'
    AS $$
        WITH RECURSIVE parameters AS (
          SELECT p_source_schema AS source_schema,
                 p_previous_schema AS previous_schema,
                 p_restore_schema AS restore_schema,
                 p_app_role AS app_role,
                 p_fence_role AS fence_role,
                 p_restore_executor_role AS restore_executor_role
        ),
        schema_scope AS (
          SELECT n.oid, n.nspname, n.nspowner, n.nspacl
          FROM pg_namespace n CROSS JOIN parameters p
          WHERE n.nspname IN (
            p.source_schema, p.previous_schema, p.restore_schema,
            'public'::name, 'x_extension'::name
          )
        ),
        active_schema_scope AS (
          SELECT s.* FROM schema_scope s CROSS JOIN parameters p
          WHERE s.nspname IN (p.source_schema, p.previous_schema, p.restore_schema)
        ),
        source_owner_scope AS (
          SELECT s.nspowner AS role_oid FROM schema_scope s CROSS JOIN parameters p
          WHERE s.nspname = p.source_schema
        ),
        accessible_security_definer_scope AS (
          SELECT proc.oid, proc.pronamespace, ns.nspname, proc.proowner, proc.proacl,
                 proc.prosecdef,
                 pg_get_function_identity_arguments(proc.oid) AS identity_arguments,
                 pg_get_functiondef(proc.oid) AS definition
          FROM pg_proc proc
          JOIN pg_namespace ns ON ns.oid = proc.pronamespace
          CROSS JOIN parameters p
          WHERE proc.prosecdef
            AND ns.nspname NOT IN ('pg_catalog', 'pg_toast', 'information_schema')
            AND ns.nspname <> p.source_schema
            AND has_function_privilege(p.app_role, proc.oid, 'EXECUTE')
        ),
        security_definer_role_closure(role_oid) AS (
          SELECT DISTINCT proowner FROM accessible_security_definer_scope
          UNION
          SELECT CASE WHEN membership.member = closure.role_oid
                      THEN membership.roleid ELSE membership.member END
          FROM security_definer_role_closure closure
          JOIN pg_auth_members membership
            ON membership.member = closure.role_oid OR membership.roleid = closure.role_oid
        ),
        role_scope AS (
          SELECT role_row.oid, role_row.rolname, role_row.rolcanlogin,
                 role_row.rolsuper, role_row.rolinherit, role_row.rolcreaterole,
                 role_row.rolcreatedb, role_row.rolreplication, role_row.rolbypassrls,
                 role_row.rolconnlimit,
                 CASE WHEN role_row.rolvaliduntil IS NULL THEN NULL
                      WHEN role_row.rolvaliduntil IN ('infinity'::timestamptz, '-infinity'::timestamptz)
                        THEN role_row.rolvaliduntil::text
                      ELSE to_char(role_row.rolvaliduntil AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') END AS valid_until_utc,
                 role_row.rolconfig
          FROM pg_roles role_row CROSS JOIN parameters p
          WHERE role_row.rolname IN (p.app_role, p.fence_role, p.restore_executor_role)
             OR role_row.oid IN (SELECT role_oid FROM source_owner_scope)
             OR role_row.oid IN (SELECT role_oid FROM security_definer_role_closure)
        ),
        relation_scope AS (
          SELECT c.oid, c.relnamespace, c.relname, c.relkind, c.relowner, c.relacl
          FROM pg_class c JOIN active_schema_scope s ON s.oid = c.relnamespace
          WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
        ),
        procedure_scope AS (
          SELECT proc.oid, proc.pronamespace, proc.proname, proc.proowner, proc.proacl,
                 proc.prosecdef, pg_get_function_identity_arguments(proc.oid) AS identity_arguments,
                 pg_get_functiondef(proc.oid) AS definition
          FROM pg_proc proc JOIN active_schema_scope s ON s.oid = proc.pronamespace
        ),
        trigger_scope AS (
          SELECT trigger_row.oid, trigger_row.tgrelid, trigger_row.tgname,
                 trigger_row.tgfoid, trigger_row.tgtype, trigger_row.tgenabled,
                 trigger_row.tgisinternal, trigger_row.tgconstraint,
                 trigger_row.tgdeferrable, trigger_row.tginitdeferred,
                 pg_get_triggerdef(trigger_row.oid, true) AS definition
          FROM pg_trigger trigger_row JOIN relation_scope relation_row
            ON relation_row.oid = trigger_row.tgrelid
        ),
        type_scope AS (
          SELECT type_row.oid, type_row.typnamespace, type_row.typname, type_row.typtype,
                 type_row.typowner, type_row.typacl
          FROM pg_type type_row JOIN active_schema_scope schema_row
            ON schema_row.oid = type_row.typnamespace
        ),
        default_acl_scope AS (
          SELECT default_acl.*
          FROM pg_default_acl default_acl
          WHERE default_acl.defaclnamespace IN (SELECT oid FROM active_schema_scope)
             OR (default_acl.defaclnamespace = 0 AND default_acl.defaclrole IN (
               SELECT role_oid FROM source_owner_scope
               UNION SELECT oid FROM pg_roles CROSS JOIN parameters
                 WHERE rolname = parameters.restore_executor_role
             ))
        ),
        payload AS (
          SELECT jsonb_build_object(
            'database', (
              SELECT jsonb_build_object(
                'oid', database_row.oid, 'acl_is_null', database_row.datacl IS NULL,
                'acl', COALESCE(jsonb_agg(jsonb_build_object(
                  'grantor', acl.grantor, 'grantee', acl.grantee,
                  'privilege', acl.privilege_type, 'grant_option', acl.is_grantable
                ) ORDER BY acl.grantor, acl.grantee, acl.privilege_type, acl.is_grantable), '[]'::jsonb)
              )
              FROM pg_database database_row
              LEFT JOIN LATERAL aclexplode(COALESCE(
                database_row.datacl, acldefault('d', database_row.datdba)
              )) acl ON true
              WHERE database_row.datname = current_database()
              GROUP BY database_row.oid, database_row.datacl, database_row.datdba
            ),
            'roles', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'oid', role_row.oid, 'name', role_row.rolname,
              'can_login', role_row.rolcanlogin, 'superuser', role_row.rolsuper,
              'inherit', role_row.rolinherit, 'create_role', role_row.rolcreaterole,
              'create_database', role_row.rolcreatedb, 'replication', role_row.rolreplication,
              'bypass_rls', role_row.rolbypassrls, 'connection_limit', role_row.rolconnlimit,
              'valid_until_utc', role_row.valid_until_utc, 'configuration', role_row.rolconfig
            ) ORDER BY role_row.oid) FROM role_scope role_row), '[]'::jsonb),
            'memberships', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'member', membership.member, 'role', membership.roleid,
              'grantor', membership.grantor, 'admin_option', membership.admin_option,
              'inherit_option', membership.inherit_option, 'set_option', membership.set_option
            ) ORDER BY membership.member, membership.roleid, membership.grantor)
              FROM pg_auth_members membership
              WHERE membership.member IN (SELECT oid FROM role_scope)
                 OR membership.roleid IN (SELECT oid FROM role_scope)), '[]'::jsonb),
            'schemas', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'oid', schema_row.oid, 'name', schema_row.nspname, 'owner', schema_row.nspowner,
              'acl_is_null', schema_row.nspacl IS NULL,
              'acl', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'grantor', acl.grantor, 'grantee', acl.grantee,
                'privilege', acl.privilege_type, 'grant_option', acl.is_grantable
              ) ORDER BY acl.grantor, acl.grantee, acl.privilege_type, acl.is_grantable)
              FROM aclexplode(COALESCE(schema_row.nspacl,
                acldefault('n', schema_row.nspowner))) acl), '[]'::jsonb)
            ) ORDER BY schema_row.oid) FROM schema_scope schema_row), '[]'::jsonb),
            'relations', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'oid', relation_row.oid, 'schema_oid', relation_row.relnamespace,
              'name', relation_row.relname, 'kind', relation_row.relkind,
              'owner', relation_row.relowner, 'acl_is_null', relation_row.relacl IS NULL,
              'acl', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'grantor', acl.grantor, 'grantee', acl.grantee,
                'privilege', acl.privilege_type, 'grant_option', acl.is_grantable
              ) ORDER BY acl.grantor, acl.grantee, acl.privilege_type, acl.is_grantable)
              FROM aclexplode(COALESCE(relation_row.relacl, acldefault(
                CASE WHEN relation_row.relkind = 'S' THEN 'S'::"char" ELSE 'r'::"char" END,
                relation_row.relowner))) acl), '[]'::jsonb),
              'columns', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'number', attribute_row.attnum, 'name', attribute_row.attname,
                'type_oid', attribute_row.atttypid, 'acl_is_null', attribute_row.attacl IS NULL,
                'acl', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                  'grantor', acl.grantor, 'grantee', acl.grantee,
                  'privilege', acl.privilege_type, 'grant_option', acl.is_grantable
                ) ORDER BY acl.grantor, acl.grantee, acl.privilege_type, acl.is_grantable)
                FROM aclexplode(CASE WHEN array_ndims(attribute_row.attacl) = 1
                  THEN attribute_row.attacl ELSE NULL::aclitem[] END) acl), '[]'::jsonb)
              ) ORDER BY attribute_row.attnum)
              FROM pg_attribute attribute_row
              WHERE attribute_row.attrelid = relation_row.oid
                AND attribute_row.attnum > 0 AND NOT attribute_row.attisdropped), '[]'::jsonb)
            ) ORDER BY relation_row.oid) FROM relation_scope relation_row), '[]'::jsonb),
            'procedures', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'oid', procedure_row.oid, 'schema_oid', procedure_row.pronamespace,
              'name', procedure_row.proname, 'owner', procedure_row.proowner,
              'security_definer', procedure_row.prosecdef,
              'identity_arguments', procedure_row.identity_arguments,
              'acl_is_null', procedure_row.proacl IS NULL, 'definition', procedure_row.definition,
              'acl', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'grantor', acl.grantor, 'grantee', acl.grantee,
                'privilege', acl.privilege_type, 'grant_option', acl.is_grantable
              ) ORDER BY acl.grantor, acl.grantee, acl.privilege_type, acl.is_grantable)
              FROM aclexplode(COALESCE(procedure_row.proacl,
                acldefault('f', procedure_row.proowner))) acl), '[]'::jsonb)
            ) ORDER BY procedure_row.oid) FROM procedure_scope procedure_row), '[]'::jsonb),
            'triggers', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'oid', trigger_row.oid, 'relation_oid', trigger_row.tgrelid,
              'name', trigger_row.tgname, 'function_oid', trigger_row.tgfoid,
              'type', trigger_row.tgtype, 'enabled', trigger_row.tgenabled,
              'internal', trigger_row.tgisinternal, 'constraint_oid', trigger_row.tgconstraint,
              'deferrable', trigger_row.tgdeferrable,
              'initially_deferred', trigger_row.tginitdeferred,
              'definition', trigger_row.definition
            ) ORDER BY trigger_row.oid) FROM trigger_scope trigger_row), '[]'::jsonb),
            'types', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'oid', type_row.oid, 'schema_oid', type_row.typnamespace,
              'name', type_row.typname, 'kind', type_row.typtype, 'owner', type_row.typowner,
              'acl_is_null', type_row.typacl IS NULL,
              'acl', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'grantor', acl.grantor, 'grantee', acl.grantee,
                'privilege', acl.privilege_type, 'grant_option', acl.is_grantable
              ) ORDER BY acl.grantor, acl.grantee, acl.privilege_type, acl.is_grantable)
              FROM aclexplode(COALESCE(type_row.typacl,
                acldefault('T', type_row.typowner))) acl), '[]'::jsonb)
            ) ORDER BY type_row.oid) FROM type_scope type_row), '[]'::jsonb),
            'default_acls', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'schema_oid', default_acl.defaclnamespace, 'owner', default_acl.defaclrole,
              'kind', default_acl.defaclobjtype, 'acl_is_null', default_acl.defaclacl IS NULL,
              'acl', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'grantor', acl.grantor, 'grantee', acl.grantee,
                'privilege', acl.privilege_type, 'grant_option', acl.is_grantable
              ) ORDER BY acl.grantor, acl.grantee, acl.privilege_type, acl.is_grantable)
              FROM aclexplode(COALESCE(default_acl.defaclacl,
                acldefault(default_acl.defaclobjtype, default_acl.defaclrole))) acl), '[]'::jsonb)
            ) ORDER BY default_acl.defaclnamespace, default_acl.defaclrole,
              default_acl.defaclobjtype) FROM default_acl_scope default_acl), '[]'::jsonb),
            'accessible_security_definers', COALESCE((SELECT jsonb_agg(jsonb_build_object(
              'oid', procedure_row.oid, 'schema', procedure_row.nspname,
              'owner', procedure_row.proowner, 'identity_arguments', procedure_row.identity_arguments,
              'security_definer', procedure_row.prosecdef,
              'acl_is_null', procedure_row.proacl IS NULL, 'definition', procedure_row.definition,
              'acl', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'grantor', acl.grantor, 'grantee', acl.grantee,
                'privilege', acl.privilege_type, 'grant_option', acl.is_grantable
              ) ORDER BY acl.grantor, acl.grantee, acl.privilege_type, acl.is_grantable)
              FROM aclexplode(COALESCE(procedure_row.proacl,
                acldefault('f', procedure_row.proowner))) acl), '[]'::jsonb)
            ) ORDER BY procedure_row.oid) FROM accessible_security_definer_scope procedure_row), '[]'::jsonb)
          ) AS value
        )
        SELECT encode(x_extension.digest(convert_to(payload.value::text, 'UTF8'), 'sha256'), 'hex')
        FROM payload
        $$;

CREATE FUNCTION "ops"."record_m05_hotswap_release_receipt"("p_operation_id" "uuid", "p_marker_sha256" "text", "p_script_sha256" "text", "p_snapshot_sha256" "text", "p_drain_receipt_sha256" "text", "p_pg_restore_list_sha256" "text", "p_target_identity_sha256" "text", "p_source_identity_sha256" "text", "p_source_schema" "name", "p_restore_schema" "name", "p_previous_schema" "name", "p_app_role" "name", "p_fence_role" "name", "p_restore_executor_role" "name", "p_source_schema_oid_before" "oid", "p_restore_schema_oid" "oid", "p_app_schema_oid_after_switch" "oid", "p_previous_schema_oid_after_switch" "oid", "p_connect_restore_grants" "jsonb", "p_restore_executor_connect_restore_grants" "jsonb", "p_public_connect_was_granted" boolean, "p_pre_release_acl_topology_sha256" "text") RETURNS "text"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'pg_catalog'
    AS $_$
        DECLARE
            v_database_owner name;
            v_target_identity_sha256 text;
            v_app_connect_grants jsonb;
            v_restore_executor_connect_grants jsonb;
            v_public_connect_granted boolean;
            v_post_release_acl_topology_sha256 text;
            v_observed_at timestamptz := clock_timestamp();
            v_record_sha256 text;
        BEGIN
            IF p_operation_id IS NULL
               OR p_marker_sha256 !~ '^[0-9a-f]{64}$'
               OR p_script_sha256 !~ '^[0-9a-f]{64}$'
               OR p_snapshot_sha256 !~ '^[0-9a-f]{64}$'
               OR p_drain_receipt_sha256 !~ '^[0-9a-f]{64}$'
               OR p_pg_restore_list_sha256 !~ '^[0-9a-f]{64}$'
               OR p_target_identity_sha256 !~ '^[0-9a-f]{64}$'
               OR p_source_identity_sha256 !~ '^[0-9a-f]{64}$'
               OR p_pre_release_acl_topology_sha256 !~ '^[0-9a-f]{64}$'
               OR p_source_schema::text !~ '^[a-z_][a-z0-9_]*$'
               OR p_restore_schema::text !~ '^[a-z_][a-z0-9_]*$'
               OR p_previous_schema::text !~ '^[a-z_][a-z0-9_]*$'
               OR p_app_role::text !~ '^[a-z_][a-z0-9_]*$'
               OR p_fence_role::text !~ '^[a-z_][a-z0-9_]*$'
               OR p_restore_executor_role::text !~ '^[a-z_][a-z0-9_]*$'
               OR p_source_schema = p_restore_schema
               OR p_source_schema = p_previous_schema
               OR p_restore_schema = p_previous_schema
               OR p_app_role = p_fence_role
               OR p_app_role = p_restore_executor_role
               OR p_fence_role = p_restore_executor_role
               OR p_source_schema_oid_before <= 0
               OR p_restore_schema_oid <= 0
               OR p_app_schema_oid_after_switch <> p_restore_schema_oid
               OR p_previous_schema_oid_after_switch <> p_source_schema_oid_before
               OR jsonb_typeof(p_connect_restore_grants) <> 'array'
               OR jsonb_typeof(p_restore_executor_connect_restore_grants) <> 'array'
            THEN
                RAISE EXCEPTION 'M05 release receipt inputs are invalid' USING ERRCODE = '22023';
            END IF;

            SELECT database_row.datdba::regrole::text::name
              INTO v_database_owner
              FROM pg_database database_row
             WHERE database_row.datname = current_database();
            IF session_user::name <> p_fence_role OR v_database_owner <> p_fence_role THEN
                RAISE EXCEPTION 'M05 release receipt requires the configured fence database owner'
                    USING ERRCODE = '42501';
            END IF;

            SELECT encode(x_extension.digest(convert_to(
                current_database() || '|' || database_row.oid::text || '|' ||
                (pg_control_system()).system_identifier::text || '|' ||
                COALESCE(host(inet_server_addr()), '') || '|' || inet_server_port()::text,
                'UTF8'), 'sha256'), 'hex')
              INTO v_target_identity_sha256
              FROM pg_database database_row
             WHERE database_row.datname = current_database();
            IF v_target_identity_sha256 <> p_target_identity_sha256 THEN
                RAISE EXCEPTION 'M05 release receipt target identity changed' USING ERRCODE = '55000';
            END IF;
            IF (SELECT oid FROM pg_namespace WHERE nspname = p_source_schema)
                 <> p_app_schema_oid_after_switch
               OR (SELECT oid FROM pg_namespace WHERE nspname = p_previous_schema)
                 <> p_previous_schema_oid_after_switch
               OR to_regnamespace(p_restore_schema::text) IS NOT NULL THEN
                RAISE EXCEPTION 'M05 release receipt schema OID matrix is not switched'
                    USING ERRCODE = '55000';
            END IF;

            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'grant_option', acl.is_grantable, 'role', role_row.rolname
            ) ORDER BY role_row.rolname), '[]'::jsonb)
              INTO v_app_connect_grants
              FROM pg_database database_row
              CROSS JOIN LATERAL aclexplode(COALESCE(
                database_row.datacl, acldefault('d', database_row.datdba)
              )) acl
              JOIN pg_roles role_row ON role_row.oid = acl.grantee
             WHERE database_row.datname = current_database()
               AND acl.privilege_type = 'CONNECT'
               AND role_row.rolname = p_app_role;
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                'grant_option', acl.is_grantable, 'role', role_row.rolname
            ) ORDER BY role_row.rolname), '[]'::jsonb)
              INTO v_restore_executor_connect_grants
              FROM pg_database database_row
              CROSS JOIN LATERAL aclexplode(COALESCE(
                database_row.datacl, acldefault('d', database_row.datdba)
              )) acl
              JOIN pg_roles role_row ON role_row.oid = acl.grantee
             WHERE database_row.datname = current_database()
               AND acl.privilege_type = 'CONNECT'
               AND role_row.rolname = p_restore_executor_role;
            SELECT EXISTS (
                SELECT 1 FROM pg_database database_row
                CROSS JOIN LATERAL aclexplode(COALESCE(
                  database_row.datacl, acldefault('d', database_row.datdba)
                )) acl
                WHERE database_row.datname = current_database()
                  AND acl.grantee = 0 AND acl.privilege_type = 'CONNECT'
            ) INTO v_public_connect_granted;
            IF v_app_connect_grants <> p_connect_restore_grants
               OR v_restore_executor_connect_grants <> p_restore_executor_connect_restore_grants
               OR v_public_connect_granted <> p_public_connect_was_granted THEN
                RAISE EXCEPTION 'M05 release receipt CONNECT grants do not match the release state'
                    USING ERRCODE = '55000';
            END IF;

            v_post_release_acl_topology_sha256 := ops.m05_hotswap_release_topology_sha256(
                p_source_schema, p_previous_schema, p_restore_schema, p_app_role,
                p_fence_role, p_restore_executor_role
            );
            IF v_post_release_acl_topology_sha256 !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'M05 release receipt topology is invalid' USING ERRCODE = '55000';
            END IF;
            v_record_sha256 := encode(x_extension.digest(convert_to(jsonb_build_object(
                'operation_id', p_operation_id::text,
                'marker_sha256', p_marker_sha256,
                'script_sha256', p_script_sha256,
                'snapshot_sha256', p_snapshot_sha256,
                'drain_receipt_sha256', p_drain_receipt_sha256,
                'pg_restore_list_sha256', p_pg_restore_list_sha256,
                'target_identity_sha256', p_target_identity_sha256,
                'source_identity_sha256', p_source_identity_sha256,
                'source_schema', p_source_schema::text,
                'restore_schema', p_restore_schema::text,
                'previous_schema', p_previous_schema::text,
                'app_role', p_app_role::text,
                'fence_role', p_fence_role::text,
                'restore_executor_role', p_restore_executor_role::text,
                'source_schema_oid_before', p_source_schema_oid_before::text,
                'restore_schema_oid', p_restore_schema_oid::text,
                'app_schema_oid_after_switch', p_app_schema_oid_after_switch::text,
                'previous_schema_oid_after_switch', p_previous_schema_oid_after_switch::text,
                'connect_restore_grants', p_connect_restore_grants,
                'restore_executor_connect_restore_grants', p_restore_executor_connect_restore_grants,
                'public_connect_was_granted', p_public_connect_was_granted,
                'pre_release_acl_topology_sha256', p_pre_release_acl_topology_sha256,
                'post_release_acl_topology_sha256', v_post_release_acl_topology_sha256,
                'observed_at_utc', to_char(v_observed_at AT TIME ZONE 'UTC',
                  'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
            )::text, 'UTF8'), 'sha256'), 'hex');
            INSERT INTO ops.m05_hotswap_release_receipts (
                operation_id, marker_sha256, script_sha256, snapshot_sha256,
                drain_receipt_sha256, pg_restore_list_sha256, target_identity_sha256,
                source_identity_sha256, source_schema, restore_schema, previous_schema,
                app_role, fence_role, restore_executor_role, source_schema_oid_before,
                restore_schema_oid, app_schema_oid_after_switch, previous_schema_oid_after_switch,
                connect_restore_grants, restore_executor_connect_restore_grants,
                public_connect_was_granted, pre_release_acl_topology_sha256,
                post_release_acl_topology_sha256, observed_at, record_sha256
            ) VALUES (
                p_operation_id, p_marker_sha256, p_script_sha256, p_snapshot_sha256,
                p_drain_receipt_sha256, p_pg_restore_list_sha256, p_target_identity_sha256,
                p_source_identity_sha256, p_source_schema::text, p_restore_schema::text,
                p_previous_schema::text, p_app_role::text, p_fence_role::text,
                p_restore_executor_role::text, p_source_schema_oid_before::integer,
                p_restore_schema_oid::integer, p_app_schema_oid_after_switch::integer,
                p_previous_schema_oid_after_switch::integer, p_connect_restore_grants,
                p_restore_executor_connect_restore_grants, p_public_connect_was_granted,
                p_pre_release_acl_topology_sha256, v_post_release_acl_topology_sha256,
                v_observed_at, v_record_sha256
            );
            RETURN v_post_release_acl_topology_sha256;
        END;
        $_$;

CREATE FUNCTION "ops"."verify_m05_hotswap_release_receipt"("p_operation_id" "uuid", "p_marker_sha256" "text") RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'pg_catalog'
    AS $$
        SELECT COALESCE((
            SELECT receipt.record_sha256 = encode(x_extension.digest(convert_to(jsonb_build_object(
                'operation_id', receipt.operation_id::text,
                'marker_sha256', receipt.marker_sha256,
                'script_sha256', receipt.script_sha256,
                'snapshot_sha256', receipt.snapshot_sha256,
                'drain_receipt_sha256', receipt.drain_receipt_sha256,
                'pg_restore_list_sha256', receipt.pg_restore_list_sha256,
                'target_identity_sha256', receipt.target_identity_sha256,
                'source_identity_sha256', receipt.source_identity_sha256,
                'source_schema', receipt.source_schema,
                'restore_schema', receipt.restore_schema,
                'previous_schema', receipt.previous_schema,
                'app_role', receipt.app_role,
                'fence_role', receipt.fence_role,
                'restore_executor_role', receipt.restore_executor_role,
                'source_schema_oid_before', receipt.source_schema_oid_before::text,
                'restore_schema_oid', receipt.restore_schema_oid::text,
                'app_schema_oid_after_switch', receipt.app_schema_oid_after_switch::text,
                'previous_schema_oid_after_switch', receipt.previous_schema_oid_after_switch::text,
                'connect_restore_grants', receipt.connect_restore_grants,
                'restore_executor_connect_restore_grants', receipt.restore_executor_connect_restore_grants,
                'public_connect_was_granted', receipt.public_connect_was_granted,
                'pre_release_acl_topology_sha256', receipt.pre_release_acl_topology_sha256,
                'post_release_acl_topology_sha256', receipt.post_release_acl_topology_sha256,
                'observed_at_utc', to_char(receipt.observed_at AT TIME ZONE 'UTC',
                  'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
            )::text, 'UTF8'), 'sha256'), 'hex')
            FROM ops.m05_hotswap_release_receipts receipt
            WHERE receipt.operation_id = p_operation_id
              AND receipt.marker_sha256 = p_marker_sha256
        ), false)
        $$;

CREATE TABLE "ops"."m05_activation_database_anchor" (
    "generation" bigint NOT NULL,
    "receipt_sha256" character varying(64) NOT NULL,
    "record_sha256" character varying(64) NOT NULL,
    "observed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_m05_activation_database_anchor_ck_m05_anchor_generation" CHECK (("generation" > 0)),
    CONSTRAINT "ck_m05_activation_database_anchor_ck_m05_anchor_receipt_sha" CHECK ((("receipt_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_m05_activation_database_anchor_ck_m05_anchor_record_sha" CHECK ((("record_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text"))
);

CREATE SEQUENCE "ops"."m05_activation_database_anchor_generation_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "ops"."m05_activation_database_anchor_generation_seq" OWNED BY "ops"."m05_activation_database_anchor"."generation";

CREATE TABLE "ops"."m05_hotswap_release_receipts" (
    "operation_id" "uuid" NOT NULL,
    "marker_sha256" character varying(64) NOT NULL,
    "script_sha256" character varying(64) NOT NULL,
    "snapshot_sha256" character varying(64) NOT NULL,
    "drain_receipt_sha256" character varying(64) NOT NULL,
    "pg_restore_list_sha256" character varying(64) NOT NULL,
    "target_identity_sha256" character varying(64) NOT NULL,
    "source_identity_sha256" character varying(64) NOT NULL,
    "source_schema" "text" NOT NULL,
    "restore_schema" "text" NOT NULL,
    "previous_schema" "text" NOT NULL,
    "app_role" "text" NOT NULL,
    "fence_role" "text" NOT NULL,
    "restore_executor_role" "text" NOT NULL,
    "source_schema_oid_before" integer NOT NULL,
    "restore_schema_oid" integer NOT NULL,
    "app_schema_oid_after_switch" integer NOT NULL,
    "previous_schema_oid_after_switch" integer NOT NULL,
    "connect_restore_grants" "jsonb" NOT NULL,
    "restore_executor_connect_restore_grants" "jsonb" NOT NULL,
    "public_connect_was_granted" boolean NOT NULL,
    "pre_release_acl_topology_sha256" character varying(64) NOT NULL,
    "post_release_acl_topology_sha256" character varying(64) NOT NULL,
    "observed_at" timestamp with time zone DEFAULT "clock_timestamp"() NOT NULL,
    "record_sha256" character varying(64) NOT NULL,
    CONSTRAINT "ck_m05_hotswap_release_receipts_ck_m05_hotswap_release__0e7e" CHECK ((("source_schema_oid_before" > 0) AND ("restore_schema_oid" > 0) AND ("app_schema_oid_after_switch" = "restore_schema_oid") AND ("previous_schema_oid_after_switch" = "source_schema_oid_before"))),
    CONSTRAINT "ck_m05_hotswap_release_receipts_ck_m05_hotswap_release__26cc" CHECK ((("source_schema" <> "restore_schema") AND ("source_schema" <> "previous_schema") AND ("restore_schema" <> "previous_schema") AND ("app_role" <> "fence_role") AND ("app_role" <> "restore_executor_role") AND ("fence_role" <> "restore_executor_role"))),
    CONSTRAINT "ck_m05_hotswap_release_receipts_ck_m05_hotswap_release__55cf" CHECK (((("marker_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("script_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("snapshot_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("drain_receipt_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("pg_restore_list_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("target_identity_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("source_identity_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("pre_release_acl_topology_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("post_release_acl_topology_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("record_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text"))),
    CONSTRAINT "ck_m05_hotswap_release_receipts_ck_m05_hotswap_release__9a77" CHECK ((("jsonb_typeof"("connect_restore_grants") = 'array'::"text") AND ("jsonb_typeof"("restore_executor_connect_restore_grants") = 'array'::"text"))),
    CONSTRAINT "ck_m05_hotswap_release_receipts_ck_m05_hotswap_release__abe7" CHECK ((("source_schema" ~ '^[a-z_][a-z0-9_]*$'::"text") AND ("restore_schema" ~ '^[a-z_][a-z0-9_]*$'::"text") AND ("previous_schema" ~ '^[a-z_][a-z0-9_]*$'::"text") AND ("app_role" ~ '^[a-z_][a-z0-9_]*$'::"text") AND ("fence_role" ~ '^[a-z_][a-z0-9_]*$'::"text") AND ("restore_executor_role" ~ '^[a-z_][a-z0-9_]*$'::"text")))
);

ALTER TABLE ONLY "ops"."m05_activation_database_anchor" ALTER COLUMN "generation" SET DEFAULT "nextval"('"ops"."m05_activation_database_anchor_generation_seq"'::"regclass");

ALTER TABLE ONLY "ops"."m05_activation_database_anchor"
    ADD CONSTRAINT "pk_m05_activation_database_anchor" PRIMARY KEY ("generation");

ALTER TABLE ONLY "ops"."m05_hotswap_release_receipts"
    ADD CONSTRAINT "pk_m05_hotswap_release_receipts" PRIMARY KEY ("operation_id");

CREATE TRIGGER "trg_m05_activation_database_anchor_append_only" BEFORE DELETE OR UPDATE ON "ops"."m05_activation_database_anchor" FOR EACH ROW EXECUTE FUNCTION "ops"."guard_m05_activation_database_anchor_append_only"();

ALTER TABLE "ops"."m05_activation_database_anchor" ENABLE ALWAYS TRIGGER "trg_m05_activation_database_anchor_append_only";

CREATE TRIGGER "trg_m05_activation_database_anchor_truncate_append_only" BEFORE TRUNCATE ON "ops"."m05_activation_database_anchor" FOR EACH STATEMENT EXECUTE FUNCTION "ops"."guard_m05_activation_database_anchor_append_only"();

ALTER TABLE "ops"."m05_activation_database_anchor" ENABLE ALWAYS TRIGGER "trg_m05_activation_database_anchor_truncate_append_only";

CREATE TRIGGER "trg_m05_hotswap_release_receipts_append_only" BEFORE DELETE OR UPDATE ON "ops"."m05_hotswap_release_receipts" FOR EACH ROW EXECUTE FUNCTION "ops"."guard_m05_hotswap_release_receipts_append_only"();

ALTER TABLE "ops"."m05_hotswap_release_receipts" ENABLE ALWAYS TRIGGER "trg_m05_hotswap_release_receipts_append_only";

CREATE TRIGGER "trg_m05_hotswap_release_receipts_truncate_append_only" BEFORE TRUNCATE ON "ops"."m05_hotswap_release_receipts" FOR EACH STATEMENT EXECUTE FUNCTION "ops"."guard_m05_hotswap_release_receipts_append_only"();

ALTER TABLE "ops"."m05_hotswap_release_receipts" ENABLE ALWAYS TRIGGER "trg_m05_hotswap_release_receipts_truncate_append_only";
