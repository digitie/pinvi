CREATE SCHEMA IF NOT EXISTS "app";

CREATE FUNCTION "app"."audit_log_append_only"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
        BEGIN
          IF TG_TABLE_SCHEMA = 'app'
             AND TG_TABLE_NAME = 'location_access_log'
             AND TG_OP = 'DELETE'
             AND current_setting('app.retention_location_delete_allowed', true) = 'on' THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'audit log is append-only — % blocked', TG_OP;
        END;
        $$;

CREATE FUNCTION "app"."guard_ktm_cache_target_restore_fence_attempt"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'cache target restore fence attempt is append-only' USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending'
           OR NEW.response_status IS NOT NULL
           OR NEW.response_etag IS NOT NULL
           OR NEW.response_body IS NOT NULL
           OR NEW.completed_at IS NOT NULL
        THEN
            RAISE EXCEPTION 'cache target restore fence attempt must start pending'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed cache target restore fence attempt is immutable' USING ERRCODE = '55000';
    END IF;
    IF NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.consumer_id IS DISTINCT FROM OLD.consumer_id
       OR NEW.external_system IS DISTINCT FROM OLD.external_system
       OR NEW.expected_restore_epoch IS DISTINCT FROM OLD.expected_restore_epoch
       OR NEW.expected_control_version IS DISTINCT FROM OLD.expected_control_version
       OR NEW.stream_etag IS DISTINCT FROM OLD.stream_etag
       OR NEW.reason IS DISTINCT FROM OLD.reason
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'cache target restore fence pre-CAS tuple is immutable' USING ERRCODE = '55000';
    END IF;
    IF NEW.status <> 'completed' THEN
        RAISE EXCEPTION 'cache target restore fence attempt may only complete' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION "app"."guard_ktm_curation_cutover_backfill_receipt"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $_$
DECLARE
    v_mapping_status text;
    v_import_status text;
    v_import_mode text;
    v_import_actor uuid;
    v_import_plan uuid;
    v_import_collection uuid;
    v_mapping_collection uuid;
    v_plan_legacy_id uuid;
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation cutover backfill receipt is append-only'
            USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending'
           OR NEW.import_receipt_id IS NOT NULL
           OR NEW.completed_at IS NOT NULL
        THEN
            RAISE EXCEPTION 'curation cutover backfill receipt must start pending'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed curation cutover backfill receipt is immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.receipt_id IS DISTINCT FROM OLD.receipt_id
       OR NEW.actor_admin_id IS DISTINCT FROM OLD.actor_admin_id
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
       OR NEW.mapping_receipt_id IS DISTINCT FROM OLD.mapping_receipt_id
       OR NEW.legacy_curated_feature_id IS DISTINCT FROM OLD.legacy_curated_feature_id
       OR NEW.curated_plan_id IS DISTINCT FROM OLD.curated_plan_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'curation cutover backfill receipt input is immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.status <> 'completed'
       OR NEW.import_receipt_id IS NULL
       OR NEW.completed_at IS NULL
    THEN
        RAISE EXCEPTION 'curation cutover backfill receipt may only complete'
            USING ERRCODE = '55000';
    END IF;

    SELECT mapping_receipt.status, mapping_item.collection_id
      INTO v_mapping_status, v_mapping_collection
      FROM app.ktm_curation_cutover_mapping_receipts AS mapping_receipt
      JOIN app.ktm_curation_cutover_mapping_receipt_items AS mapping_item
        ON mapping_item.receipt_id = mapping_receipt.receipt_id
     WHERE mapping_receipt.receipt_id = NEW.mapping_receipt_id
       AND mapping_item.legacy_curated_feature_id = NEW.legacy_curated_feature_id
     FOR UPDATE OF mapping_receipt, mapping_item;
    IF NOT FOUND OR v_mapping_status <> 'completed' THEN
        RAISE EXCEPTION 'curation cutover backfill requires completed mapping receipt'
            USING ERRCODE = '23514';
    END IF;

    SELECT import_receipt.status,
           import_receipt.mode,
           import_receipt.actor_admin_id,
           import_receipt.result_plan_id,
           import_receipt.source_curation_collection_id
      INTO v_import_status,
           v_import_mode,
           v_import_actor,
           v_import_plan,
           v_import_collection
      FROM app.ktm_curation_import_receipts AS import_receipt
     WHERE import_receipt.receipt_id = NEW.import_receipt_id
     FOR UPDATE;
    IF NOT FOUND
       OR v_import_status <> 'completed'
       OR v_import_mode <> 'cutover-backfill'
       OR v_import_actor <> NEW.actor_admin_id
       OR v_import_plan <> NEW.curated_plan_id
       OR v_import_collection <> v_mapping_collection
    THEN
        RAISE EXCEPTION 'curation cutover backfill import receipt does not match mapping'
            USING ERRCODE = '23514';
    END IF;

    SELECT CASE
             WHEN plan.source_curated_feature_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
             THEN plan.source_curated_feature_id::uuid
             ELSE NULL
           END
      INTO v_plan_legacy_id
      FROM app.curated_trip_plans AS plan
     WHERE plan.curated_plan_id = NEW.curated_plan_id
       AND plan.deleted_at IS NULL
     FOR UPDATE;
    IF NOT FOUND OR v_plan_legacy_id IS DISTINCT FROM NEW.legacy_curated_feature_id THEN
        RAISE EXCEPTION 'curation cutover backfill plan provenance does not match mapping'
            USING ERRCODE = '23514';
    END IF;

    -- Terminal seal과 legacy source POI 제거를 같은 parent/row lock 순서로 묶는다.
    PERFORM 1
      FROM app.curated_plan_pois AS poi
     WHERE poi.curated_plan_id = NEW.curated_plan_id
     ORDER BY poi.curated_poi_id
     FOR UPDATE;
    IF EXISTS (
        SELECT 1
          FROM app.curated_plan_pois AS poi
         WHERE poi.curated_plan_id = NEW.curated_plan_id
           AND poi.deleted_at IS NULL
           AND (
               poi.source_curated_feature_id IS NOT NULL
               OR poi.source_curated_feature_item_id IS NOT NULL
           )
    ) THEN
        RAISE EXCEPTION 'curation cutover backfill leaves active legacy source POI'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$_$;

CREATE FUNCTION "app"."guard_ktm_curation_cutover_mapping_receipt"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
DECLARE
    v_item_count bigint;
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation cutover mapping receipt is append-only'
            USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending' OR NEW.completed_at IS NOT NULL THEN
            RAISE EXCEPTION 'curation cutover mapping receipt must start pending'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed curation cutover mapping receipt is immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.receipt_id IS DISTINCT FROM OLD.receipt_id
       OR NEW.actor_admin_id IS DISTINCT FROM OLD.actor_admin_id
       OR NEW.map_release_revision IS DISTINCT FROM OLD.map_release_revision
       OR NEW.mapping_root_version IS DISTINCT FROM OLD.mapping_root_version
       OR NEW.mapping_root IS DISTINCT FROM OLD.mapping_root
       OR NEW.mapping_count IS DISTINCT FROM OLD.mapping_count
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'curation cutover mapping receipt input is immutable'
            USING ERRCODE = '55000';
    END IF;

    IF NEW.status <> 'completed' OR NEW.completed_at IS NULL THEN
        RAISE EXCEPTION 'curation cutover mapping receipt may only complete'
            USING ERRCODE = '55000';
    END IF;

    -- Item insert는 같은 receipt row를 FOR UPDATE로 잡는다. terminal 전 item set을
    -- 고정하고, terminal 뒤 member를 붙이는 race를 함께 직렬화한다.
    PERFORM 1
      FROM app.ktm_curation_cutover_mapping_receipt_items AS item
     WHERE item.receipt_id = OLD.receipt_id
     ORDER BY item.legacy_curated_feature_id
     FOR UPDATE;

    SELECT count(*)
      INTO v_item_count
      FROM app.ktm_curation_cutover_mapping_receipt_items AS item
     WHERE item.receipt_id = OLD.receipt_id;
    IF v_item_count <> NEW.mapping_count THEN
        RAISE EXCEPTION 'curation cutover mapping receipt item set is incomplete'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION "app"."guard_ktm_curation_cutover_mapping_receipt_item"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
DECLARE
    v_receipt_status text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation cutover mapping receipt item is append-only'
            USING ERRCODE = '55000';
    END IF;

    SELECT receipt.status
      INTO v_receipt_status
      FROM app.ktm_curation_cutover_mapping_receipts AS receipt
     WHERE receipt.receipt_id = NEW.receipt_id
     FOR UPDATE;
    IF v_receipt_status IS DISTINCT FROM 'pending' THEN
        RAISE EXCEPTION 'curation cutover mapping receipt item requires pending receipt'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION "app"."guard_ktm_curation_import_receipt"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
DECLARE
    v_item_count bigint;
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation import receipt is append-only' USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending'
           OR NEW.result_plan_id IS NOT NULL
           OR NEW.response_status IS NOT NULL
           OR NEW.response_body IS NOT NULL
           OR NEW.completed_at IS NOT NULL
        THEN
            RAISE EXCEPTION 'curation import receipt must start pending' USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed curation import receipt is immutable' USING ERRCODE = '55000';
    END IF;

    IF NEW.receipt_id IS DISTINCT FROM OLD.receipt_id
       OR NEW.actor_admin_id IS DISTINCT FROM OLD.actor_admin_id
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
       OR NEW.source_system IS DISTINCT FROM OLD.source_system
       OR NEW.source_curation_collection_id IS DISTINCT FROM OLD.source_curation_collection_id
       OR NEW.source_curation_collection_revision
          IS DISTINCT FROM OLD.source_curation_collection_revision
       OR NEW.source_curation_collection_etag
          IS DISTINCT FROM OLD.source_curation_collection_etag
       OR NEW.source_curation_item_set_hash_version
          IS DISTINCT FROM OLD.source_curation_item_set_hash_version
       OR NEW.source_curation_item_set_hash
          IS DISTINCT FROM OLD.source_curation_item_set_hash
       OR NEW.source_curation_item_count IS DISTINCT FROM OLD.source_curation_item_count
       OR NEW.mode IS DISTINCT FROM OLD.mode
       OR NEW.requested_is_published IS DISTINCT FROM OLD.requested_is_published
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'curation import request tuple is immutable' USING ERRCODE = '55000';
    END IF;

    IF NEW.status <> 'completed' THEN
        RAISE EXCEPTION 'curation import receipt may only complete' USING ERRCODE = '55000';
    END IF;

    PERFORM 1
      FROM app.curated_trip_plans AS plan
     WHERE plan.curated_plan_id = NEW.result_plan_id
       AND plan.deleted_at IS NULL
       AND plan.source_system = NEW.source_system
       AND plan.source_curation_collection_id = NEW.source_curation_collection_id
       AND plan.source_curation_collection_revision =
           NEW.source_curation_collection_revision
       AND plan.source_curation_collection_etag = NEW.source_curation_collection_etag
       AND plan.source_curation_item_set_hash_version =
           NEW.source_curation_item_set_hash_version
       AND plan.source_curation_item_set_hash = NEW.source_curation_item_set_hash
       AND plan.source_curation_item_count = NEW.source_curation_item_count
       AND (
           NEW.requested_is_published IS NULL
           OR plan.is_published = NEW.requested_is_published
       )
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'curation import receipt result plan proof does not match'
            USING ERRCODE = '23514';
    END IF;

    -- deleted row도 잠가 completion 직후 concurrent undelete가 exact set을 깨지 못하게 한다.
    PERFORM 1
      FROM app.curated_plan_pois AS poi
     WHERE poi.curated_plan_id = NEW.result_plan_id
       AND poi.source_curation_item_id IS NOT NULL
     ORDER BY poi.curated_poi_id
     FOR UPDATE;

    SELECT count(*)
      INTO v_item_count
      FROM app.ktm_curation_import_receipt_items AS item
     WHERE item.receipt_id = OLD.receipt_id;
    IF v_item_count <> NEW.source_curation_item_count THEN
        RAISE EXCEPTION 'curation import receipt item set is incomplete' USING ERRCODE = '55000';
    END IF;

    IF (
        SELECT count(*)
          FROM app.curated_plan_pois AS poi
         WHERE poi.curated_plan_id = NEW.result_plan_id
           AND poi.deleted_at IS NULL
           AND poi.source_curation_item_id IS NOT NULL
    ) <> v_item_count
       OR EXISTS (
           SELECT 1
             FROM app.ktm_curation_import_receipt_items AS item
             LEFT JOIN app.curated_plan_pois AS poi
               ON poi.curated_plan_id = NEW.result_plan_id
              AND poi.deleted_at IS NULL
              AND poi.source_curation_collection_id = item.source_curation_collection_id
              AND poi.source_curation_item_id = item.source_curation_item_id
              AND poi.source_curation_item_revision = item.source_curation_item_revision
              AND poi.source_curation_item_etag = item.source_curation_item_etag
              AND poi.feature_uuid = item.feature_uuid
            WHERE item.receipt_id = NEW.receipt_id
              AND poi.curated_poi_id IS NULL
       )
    THEN
        RAISE EXCEPTION 'curation import receipt POI set does not match'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION "app"."guard_ktm_curation_import_receipt_item"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
DECLARE
    v_receipt_status text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'curation import receipt item is append-only' USING ERRCODE = '55000';
    END IF;
    SELECT receipt.status
      INTO v_receipt_status
      FROM app.ktm_curation_import_receipts AS receipt
     WHERE receipt.receipt_id = NEW.receipt_id
     FOR UPDATE;
    IF v_receipt_status IS DISTINCT FROM 'pending' THEN
        RAISE EXCEPTION 'curation import receipt item requires pending receipt'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION "app"."guard_ktm_curation_import_receipt_response"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.status = 'pending'
       AND NEW.status = 'completed'
       AND (
           jsonb_typeof(NEW.response_body -> 'not_modified') IS DISTINCT FROM 'boolean'
           OR NEW.response_body ->> 'notice_plan_id' IS DISTINCT FROM NEW.result_plan_id::text
           OR NEW.response_body ->> 'source_system' IS DISTINCT FROM NEW.source_system
           OR NEW.response_body ->> 'source_curation_collection_id'
              IS DISTINCT FROM NEW.source_curation_collection_id::text
           OR NEW.response_body ->> 'source_curation_collection_revision'
              IS DISTINCT FROM NEW.source_curation_collection_revision::text
           OR NEW.response_body ->> 'source_curation_collection_etag'
              IS DISTINCT FROM NEW.source_curation_collection_etag
           OR NEW.response_body ->> 'source_curation_item_set_hash_version'
              IS DISTINCT FROM NEW.source_curation_item_set_hash_version
           OR NEW.response_body ->> 'source_curation_item_set_hash'
              IS DISTINCT FROM NEW.source_curation_item_set_hash
           OR NEW.response_body ->> 'source_curation_item_count'
              IS DISTINCT FROM NEW.source_curation_item_count::text
       )
    THEN
        RAISE EXCEPTION 'curation import receipt response does not match source tuple'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION "app"."guard_ktm_feature_reference_reconciliation_append_only"() RETURNS "trigger"
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

CREATE FUNCTION "app"."ktm_cache_target_active_source_v1"("lon" numeric, "lat" numeric, "radius_km" numeric, "update_enabled" boolean) RETURNS "text"
    LANGUAGE "plpgsql" IMMUTABLE STRICT
    SET "search_path" TO 'pg_catalog', 'app'
    AS $$
DECLARE
    lon_e6 bigint;
    lat_e6 bigint;
    radius_m bigint;
BEGIN
    IF lon < -180 OR lon > 180 THEN
        RAISE EXCEPTION 'lon is outside canonical range' USING ERRCODE = '22023';
    END IF;
    IF lat < -90 OR lat > 90 THEN
        RAISE EXCEPTION 'lat is outside canonical range' USING ERRCODE = '22023';
    END IF;
    IF radius_km <= 0 OR radius_km > 100 THEN
        RAISE EXCEPTION 'radius_km is outside canonical range' USING ERRCODE = '22023';
    END IF;
    lon_e6 := app.ktm_round_half_even_scaled(lon, 1000000);
    lat_e6 := app.ktm_round_half_even_scaled(lat, 1000000);
    radius_m := app.ktm_round_half_even_scaled(radius_km, 1000);
    IF radius_m <= 0 THEN
        RAISE EXCEPTION 'radius_km rounds to zero metres' USING ERRCODE = '22023';
    END IF;
    RETURN '{"coord":{"lat_e6":' || lat_e6::text ||
        ',"lon_e6":' || lon_e6::text ||
        '},"radius_m":' || radius_m::text ||
        ',"state":"active","update_enabled":' ||
        CASE WHEN update_enabled THEN 'true' ELSE 'false' END ||
        ',"version":"cache-target-source-v1"}';
END;
$$;

CREATE FUNCTION "app"."ktm_cache_target_deleted_source_v1"() RETURNS "text"
    LANGUAGE "sql" IMMUTABLE
    SET "search_path" TO 'pg_catalog'
    AS $$
    SELECT '{"state":"deleted","version":"cache-target-source-v1"}'::text
$$;

CREATE FUNCTION "app"."ktm_round_half_even_scaled"("value" numeric, "scale_factor" bigint) RETURNS bigint
    LANGUAGE "plpgsql" IMMUTABLE STRICT
    SET "search_path" TO 'pg_catalog'
    AS $$
DECLARE
    scaled numeric;
    lower_integer numeric;
    fraction numeric;
BEGIN
    IF scale_factor <= 0 THEN
        RAISE EXCEPTION 'scale_factor must be positive' USING ERRCODE = '22023';
    END IF;
    scaled := value * scale_factor;
    lower_integer := floor(scaled);
    fraction := scaled - lower_integer;
    IF fraction < 0.5 THEN
        RETURN lower_integer::bigint;
    ELSIF fraction > 0.5 THEN
        RETURN (lower_integer + 1)::bigint;
    ELSIF mod(lower_integer, 2) = 0 THEN
        RETURN lower_integer::bigint;
    END IF;
    RETURN (lower_integer + 1)::bigint;
END;
$$;

CREATE FUNCTION "app"."lock_ktm_cache_target_source_cutover"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
BEGIN
    PERFORM pg_advisory_xact_lock_shared(1263816009, 41);
    RETURN NULL;
END;
$$;

CREATE FUNCTION "app"."project_ktm_cache_target_source"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog', 'app', 'x_extension'
    AS $$
DECLARE
    poi_uuid uuid;
    active_source boolean;
    source_text text;
    source_fingerprint bytea;
    next_generation bigint;
    existing_fingerprint bytea;
    normalized_lon numeric;
    normalized_lat numeric;
    normalized_radius numeric;
BEGIN
    IF TG_OP = 'DELETE' THEN
        poi_uuid := OLD.attachment_id;
        active_source := false;
    ELSE
        poi_uuid := NEW.attachment_id;
        active_source := NEW.deleted_at IS NULL
            AND NEW.cache_target_lon IS NOT NULL
            AND NEW.cache_target_lat IS NOT NULL;
    END IF;

    SELECT source_generation, source_payload_fingerprint
      INTO next_generation, existing_fingerprint
      FROM app.ktm_cache_target_heads
     WHERE poi_id = poi_uuid
     FOR UPDATE;

    IF NOT active_source AND NOT FOUND THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;

    IF active_source THEN
        source_text := app.ktm_cache_target_active_source_v1(
            NEW.cache_target_lon,
            NEW.cache_target_lat,
            NEW.cache_target_radius_km,
            NEW.cache_target_update_enabled
        );
        normalized_lon := app.ktm_round_half_even_scaled(NEW.cache_target_lon, 1000000)
            / 1000000::numeric;
        normalized_lat := app.ktm_round_half_even_scaled(NEW.cache_target_lat, 1000000)
            / 1000000::numeric;
        normalized_radius := app.ktm_round_half_even_scaled(NEW.cache_target_radius_km, 1000)
            / 1000::numeric;
    ELSE
        source_text := app.ktm_cache_target_deleted_source_v1();
    END IF;
    source_fingerprint := x_extension.digest(convert_to(source_text, 'UTF8'), 'sha256');

    IF existing_fingerprint = source_fingerprint THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;

    next_generation := coalesce(next_generation, 0) + 1;
    INSERT INTO app.ktm_cache_target_heads (
        poi_id,
        external_system,
        target_key,
        desired_state,
        source_generation,
        source_payload_fingerprint,
        lon,
        lat,
        radius_km,
        update_enabled
    ) VALUES (
        poi_uuid,
        'pinvi',
        lower(poi_uuid::text),
        CASE WHEN active_source THEN 'active' ELSE 'deleted' END,
        next_generation,
        source_fingerprint,
        CASE WHEN active_source THEN normalized_lon ELSE NULL END,
        CASE WHEN active_source THEN normalized_lat ELSE NULL END,
        CASE WHEN active_source THEN normalized_radius ELSE 5 END,
        CASE WHEN active_source THEN NEW.cache_target_update_enabled ELSE false END
    )
    ON CONFLICT (poi_id) DO UPDATE SET
        desired_state = EXCLUDED.desired_state,
        source_generation = EXCLUDED.source_generation,
        source_payload_fingerprint = EXCLUDED.source_payload_fingerprint,
        lon = EXCLUDED.lon,
        lat = EXCLUDED.lat,
        radius_km = EXCLUDED.radius_km,
        update_enabled = EXCLUDED.update_enabled;

    INSERT INTO app.ktm_cache_target_commands (
        command_id,
        poi_id,
        operation,
        source_generation,
        payload,
        payload_fingerprint
    ) VALUES (
        x_extension.gen_random_uuid(),
        poi_uuid,
        CASE WHEN active_source THEN 'put' ELSE 'delete' END,
        next_generation,
        source_text::jsonb,
        source_fingerprint
    );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION "app"."reject_ktm_cache_target_boundary_audit_mutation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'pg_catalog'
    AS $$
BEGIN
    RAISE EXCEPTION 'cache target boundary audit is append-only' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION "app"."touch_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
        BEGIN
          NEW.updated_at := now();
          RETURN NEW;
        END;
        $$;

CREATE TABLE "app"."admin_audit_log" (
    "log_id" bigint NOT NULL,
    "actor_user_id" "uuid" NOT NULL,
    "action" character varying(64) NOT NULL,
    "resource_type" character varying(64) NOT NULL,
    "resource_id" character varying(128),
    "before_state" "jsonb",
    "after_state" "jsonb",
    "access_reason" "text",
    "target_pii_fields" character varying(64)[],
    "ip_hash" character varying(64) NOT NULL,
    "user_agent" character varying(512),
    "request_id" "uuid" NOT NULL,
    "prev_hash" character varying(64) NOT NULL,
    "content_hash" character varying(64) NOT NULL,
    "occurred_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE SEQUENCE "app"."admin_audit_log_log_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "app"."admin_audit_log_log_id_seq" OWNED BY "app"."admin_audit_log"."log_id";

CREATE TABLE "app"."api_call_log" (
    "log_id" bigint NOT NULL,
    "provider" character varying(64) NOT NULL,
    "endpoint" "text" NOT NULL,
    "status_code" integer,
    "latency_ms" integer,
    "error_class" character varying(64),
    "error_message" "text",
    "request_id" "uuid",
    "occurred_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE SEQUENCE "app"."api_call_log_log_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "app"."api_call_log_log_id_seq" OWNED BY "app"."api_call_log"."log_id";

CREATE TABLE "app"."category_mappings" (
    "category_key" "text" NOT NULL,
    "display_name_ko" "text",
    "marker_color" "text",
    "marker_icon" "text",
    "created_by_user_id" "uuid",
    "updated_by_user_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_category_mappings_ck_category_mappings_display_name" CHECK ((("display_name_ko" IS NULL) OR (("length"("btrim"("display_name_ko")) >= 1) AND ("length"("btrim"("display_name_ko")) <= 120)))),
    CONSTRAINT "ck_category_mappings_ck_category_mappings_marker_color" CHECK ((("marker_color" IS NULL) OR ("marker_color" ~ '^P-(0[1-9]|1[0-6])$'::"text"))),
    CONSTRAINT "ck_category_mappings_ck_category_mappings_marker_icon" CHECK ((("marker_icon" IS NULL) OR ("marker_icon" ~ '^[a-z0-9_-]{1,64}$'::"text")))
);

CREATE TABLE "app"."content_moderation_actions" (
    "action_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "report_id" "uuid" NOT NULL,
    "actor_user_id" "uuid",
    "action" character varying(32) NOT NULL,
    "action_reason" "text" NOT NULL,
    "before_state" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "after_state" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_content_moderation_actions_ck_content_moderation_act_5046" CHECK ((("action")::"text" = ANY ((ARRAY['review'::character varying, 'hide'::character varying, 'takedown'::character varying, 'restore'::character varying, 'reject'::character varying, 'appeal'::character varying])::"text"[])))
);

CREATE TABLE "app"."content_reports" (
    "report_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "target_type" character varying(32) NOT NULL,
    "target_id" "uuid" NOT NULL,
    "target_trip_id" "uuid",
    "target_owner_user_id" "uuid",
    "reporter_user_id" "uuid",
    "reason_code" character varying(32) NOT NULL,
    "reason_text" "text" NOT NULL,
    "status" character varying(32) DEFAULT 'received'::character varying NOT NULL,
    "target_snapshot" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "evidence" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "reviewer_user_id" "uuid",
    "resolution_summary" "text",
    "appeal_summary" "text",
    "reviewed_at" timestamp with time zone,
    "actioned_at" timestamp with time zone,
    "appealed_at" timestamp with time zone,
    "restored_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_content_reports_ck_content_reports_reason_code_allowed" CHECK ((("reason_code")::"text" = ANY ((ARRAY['spam'::character varying, 'harassment'::character varying, 'privacy'::character varying, 'illegal'::character varying, 'safety'::character varying, 'other'::character varying])::"text"[]))),
    CONSTRAINT "ck_content_reports_ck_content_reports_status_allowed" CHECK ((("status")::"text" = ANY ((ARRAY['received'::character varying, 'reviewing'::character varying, 'hidden'::character varying, 'taken_down'::character varying, 'rejected'::character varying, 'appealed'::character varying, 'restored'::character varying])::"text"[]))),
    CONSTRAINT "ck_content_reports_ck_content_reports_target_type_allowed" CHECK ((("target_type")::"text" = ANY ((ARRAY['trip'::character varying, 'comment'::character varying, 'attachment'::character varying, 'share_link'::character varying])::"text"[])))
);

CREATE TABLE "app"."curated_plan_attachments" (
    "attachment_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "trip_id" "uuid",
    "trip_poi_id" "uuid",
    "curated_plan_id" "uuid",
    "curated_poi_id" "uuid",
    "source_attachment_id" "uuid",
    "bucket" character varying(80) NOT NULL,
    "storage_key" character varying(1024) NOT NULL,
    "original_filename" character varying(255) NOT NULL,
    "content_type" character varying(255) NOT NULL,
    "byte_size" bigint NOT NULL,
    "public_url" "text",
    "checksum_sha256" character varying(64),
    "role" character varying(40) DEFAULT 'attachment'::character varying NOT NULL,
    "description" "text",
    "sort_order" integer DEFAULT 0 NOT NULL,
    "uploaded_by_user_id" "uuid" NOT NULL,
    "deleted_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "trip_day_index" integer,
    CONSTRAINT "ck_curated_plan_attachments_byte_size" CHECK (("byte_size" > 0)),
    CONSTRAINT "ck_curated_plan_attachments_ck_curated_plan_attachments_3c2a" CHECK (((("trip_id" IS NOT NULL) AND ("trip_day_index" IS NULL) AND ("trip_poi_id" IS NULL) AND ("curated_plan_id" IS NULL) AND ("curated_poi_id" IS NULL)) OR (("trip_id" IS NOT NULL) AND ("trip_day_index" IS NOT NULL) AND ("trip_poi_id" IS NULL) AND ("curated_plan_id" IS NULL) AND ("curated_poi_id" IS NULL)) OR (("trip_id" IS NULL) AND ("trip_day_index" IS NULL) AND ("trip_poi_id" IS NOT NULL) AND ("curated_plan_id" IS NULL) AND ("curated_poi_id" IS NULL)) OR (("trip_id" IS NULL) AND ("trip_day_index" IS NULL) AND ("trip_poi_id" IS NULL) AND ("curated_plan_id" IS NOT NULL) AND ("curated_poi_id" IS NULL)) OR (("trip_id" IS NULL) AND ("trip_day_index" IS NULL) AND ("trip_poi_id" IS NULL) AND ("curated_plan_id" IS NULL) AND ("curated_poi_id" IS NOT NULL)))),
    CONSTRAINT "ck_curated_plan_attachments_role" CHECK ((("role")::"text" = ANY ((ARRAY['attachment'::character varying, 'image'::character varying, 'document'::character varying, 'reference'::character varying])::"text"[]))),
    CONSTRAINT "ck_curated_plan_attachments_sort_order" CHECK (("sort_order" >= 0))
);

CREATE TABLE "app"."curated_plan_pois" (
    "curated_poi_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "curated_plan_id" "uuid" NOT NULL,
    "day_index" integer DEFAULT 1 NOT NULL,
    "sort_order" "text" NOT NULL COLLATE "pg_catalog"."C",
    "feature_id" "text",
    "feature_snapshot" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "memo" "text",
    "budget_amount" numeric(12,2),
    "currency" character varying(3) DEFAULT 'KRW'::character varying NOT NULL,
    "user_url" "text",
    "custom_marker_color" character varying(16),
    "custom_marker_icon" character varying(64),
    "version" integer DEFAULT 1 NOT NULL,
    "deleted_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "source_curated_feature_id" "text",
    "source_curated_feature_item_id" "text",
    "feature_uuid" "uuid",
    "source_curation_item_id" "uuid",
    "source_curation_item_revision" bigint,
    "source_curation_item_etag" character varying(128),
    "source_curation_import_receipt_id" "uuid",
    "source_curation_collection_id" "uuid",
    CONSTRAINT "ck_curated_plan_pois_budget_nonnegative" CHECK ((("budget_amount" IS NULL) OR ("budget_amount" >= (0)::numeric))),
    CONSTRAINT "ck_curated_plan_pois_curation_source" CHECK ((("num_nonnulls"("source_curation_import_receipt_id", "source_curation_collection_id", "source_curation_item_id", "source_curation_item_revision", "source_curation_item_etag") = 0) OR (("num_nonnulls"("source_curation_import_receipt_id", "source_curation_collection_id", "source_curation_item_id", "source_curation_item_revision", "source_curation_item_etag") = 5) AND ("feature_uuid" IS NOT NULL) AND ("source_curation_item_revision" > 0) AND (("source_curation_item_etag")::"text" ~ '^"sha256:[0-9a-f]{64}"$'::"text")))),
    CONSTRAINT "ck_curated_plan_pois_currency" CHECK ((("currency")::"text" ~ '^[A-Z]{3}$'::"text")),
    CONSTRAINT "ck_curated_plan_pois_custom_marker_color" CHECK ((("custom_marker_color" IS NULL) OR (("custom_marker_color")::"text" ~ "similar_to_escape"('P-[0-9]{2}'::"text")))),
    CONSTRAINT "ck_curated_plan_pois_day_index" CHECK (("day_index" >= 1))
);

CREATE TABLE "app"."curated_trip_plans" (
    "curated_plan_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "slug" character varying(160) NOT NULL,
    "title" character varying(300) NOT NULL,
    "category" character varying(128) DEFAULT 'recommended'::character varying NOT NULL,
    "summary" "text",
    "source_name" character varying(200),
    "destination" character varying(120),
    "starts_on" "date",
    "ends_on" "date",
    "is_published" boolean DEFAULT false NOT NULL,
    "created_by_admin_id" "uuid" NOT NULL,
    "updated_by_admin_id" "uuid" NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "deleted_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "source_system" character varying(80),
    "source_curated_feature_id" "text",
    "source_curated_feature_version" integer,
    "source_etag" character varying(128),
    "source_imported_at" timestamp with time zone,
    "source_curation_collection_id" "uuid",
    "source_curation_collection_revision" bigint,
    "source_curation_collection_etag" character varying(128),
    "source_curation_item_set_hash_version" character varying(64),
    "source_curation_item_set_hash" character varying(64),
    "source_curation_item_count" bigint,
    CONSTRAINT "ck_curated_trip_plans_curation_source" CHECK ((("num_nonnulls"("source_curation_collection_id", "source_curation_collection_revision", "source_curation_collection_etag", "source_curation_item_set_hash_version", "source_curation_item_set_hash", "source_curation_item_count") = 0) OR ((("source_system")::"text" = 'kor-travel-map'::"text") AND ("num_nonnulls"("source_curation_collection_id", "source_curation_collection_revision", "source_curation_collection_etag", "source_curation_item_set_hash_version", "source_curation_item_set_hash", "source_curation_item_count") = 6) AND ("source_curation_collection_revision" > 0) AND (("source_curation_collection_etag")::"text" ~ '^"sha256:[0-9a-f]{64}"$'::"text") AND (("source_curation_item_set_hash_version")::"text" = 'ktm-db-item-set-v1'::"text") AND (("source_curation_item_set_hash")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("source_curation_item_count" >= 0) AND ("source_curation_item_count" <= 2000))))),
    CONSTRAINT "ck_curated_trip_plans_date_range" CHECK (((("starts_on" IS NULL) AND ("ends_on" IS NULL)) OR (("starts_on" IS NOT NULL) AND ("ends_on" IS NOT NULL) AND ("ends_on" >= "starts_on"))))
);

CREATE TABLE "app"."data_integrity_violations" (
    "id" bigint NOT NULL,
    "rule_key" character varying(120) NOT NULL,
    "entity_kind" character varying(80) NOT NULL,
    "entity_id" "text" NOT NULL,
    "severity" character varying(16) DEFAULT 'warning'::character varying NOT NULL,
    "message" "text" NOT NULL,
    "details" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "status" character varying(16) DEFAULT 'open'::character varying NOT NULL,
    "detected_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "resolved_at" timestamp with time zone,
    "auto_fixable" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_data_integrity_violations_ck_data_integrity_violatio_bc98" CHECK ((("severity")::"text" = ANY ((ARRAY['info'::character varying, 'warning'::character varying, 'error'::character varying, 'critical'::character varying])::"text"[]))),
    CONSTRAINT "ck_data_integrity_violations_ck_data_integrity_violatio_ce8d" CHECK ((("status")::"text" = ANY ((ARRAY['open'::character varying, 'acknowledged'::character varying, 'resolved'::character varying, 'ignored'::character varying])::"text"[])))
);

CREATE SEQUENCE "app"."data_integrity_violations_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "app"."data_integrity_violations_id_seq" OWNED BY "app"."data_integrity_violations"."id";

CREATE TABLE "app"."dsr_requests" (
    "request_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "request_type" character varying(16) NOT NULL,
    "status" character varying(32) DEFAULT 'received'::character varying NOT NULL,
    "request_summary" character varying(500) NOT NULL,
    "request_details" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "identity_proof_metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "requester_email_hash" character varying(64) NOT NULL,
    "requester_email_masked" character varying(320) NOT NULL,
    "assigned_cpo_user_id" "uuid",
    "result_notice_email_id" "uuid",
    "evidence_attachment_id" "uuid",
    "received_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "due_at" timestamp with time zone DEFAULT ("now"() + '10 days'::interval) NOT NULL,
    "identity_verified_at" timestamp with time zone,
    "processing_started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "rejected_at" timestamp with time zone,
    "withdrawn_at" timestamp with time zone,
    "rejection_reason" "text",
    "result_summary" "text",
    "result_notice_hash" character varying(64),
    "export_manifest" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "partial_response" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_dsr_requests_ck_dsr_requests_request_type_allowed" CHECK ((("request_type")::"text" = ANY ((ARRAY['access'::character varying, 'correction'::character varying, 'delete'::character varying, 'suspend'::character varying])::"text"[]))),
    CONSTRAINT "ck_dsr_requests_ck_dsr_requests_status_allowed" CHECK ((("status")::"text" = ANY ((ARRAY['received'::character varying, 'identity_check'::character varying, 'processing'::character varying, 'completed'::character varying, 'rejected'::character varying, 'withdrawn'::character varying])::"text"[])))
);

CREATE TABLE "app"."email_queue" (
    "email_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "to_email" character varying(320) NOT NULL,
    "template" character varying(64) NOT NULL,
    "subject" character varying(255) NOT NULL,
    "payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "status" character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    "resend_id" character varying(128),
    "bounce_type" character varying(16),
    "attempts" integer DEFAULT 0 NOT NULL,
    "last_error" "text",
    "scheduled_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "sent_at" timestamp with time zone,
    "delivered_at" timestamp with time zone,
    "bounced_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_provider_event_id" character varying(128),
    "last_provider_event_at" timestamp with time zone,
    CONSTRAINT "ck_email_queue_ck_email_queue_bounce_type" CHECK ((("bounce_type" IS NULL) OR (("bounce_type")::"text" = ANY ((ARRAY['hard'::character varying, 'soft'::character varying])::"text"[])))),
    CONSTRAINT "ck_email_queue_ck_email_queue_status" CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'sent'::character varying, 'delivered'::character varying, 'delivery_delayed'::character varying, 'bounced'::character varying, 'complained'::character varying, 'suppressed'::character varying, 'failed'::character varying])::"text"[])))
);

CREATE TABLE "app"."email_suppressions" (
    "suppression_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "email_hash" character varying(64) NOT NULL,
    "reason" character varying(32) NOT NULL,
    "source" character varying(32) DEFAULT 'resend'::character varying NOT NULL,
    "provider_event_id" character varying(128),
    "first_seen_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_seen_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "released_at" timestamp with time zone,
    "released_by_user_id" "uuid",
    "release_reason" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_email_suppressions_ck_email_suppressions_reason" CHECK ((("reason")::"text" = ANY ((ARRAY['hard_bounce'::character varying, 'complaint'::character varying, 'provider_suppressed'::character varying, 'manual'::character varying])::"text"[]))),
    CONSTRAINT "ck_email_suppressions_ck_email_suppressions_source" CHECK ((("source")::"text" = ANY ((ARRAY['resend'::character varying, 'admin'::character varying])::"text"[])))
);

CREATE TABLE "app"."feature_suggestions" (
    "request_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "requester_user_id" "uuid" NOT NULL,
    "type" character varying(16) DEFAULT 'new_place'::character varying NOT NULL,
    "target_feature_id" "text",
    "kind" character varying(16) NOT NULL,
    "name" character varying(200) NOT NULL,
    "lng" numeric(9,6) NOT NULL,
    "lat" numeric(8,6) NOT NULL,
    "categories" character varying(80)[] DEFAULT ARRAY[]::character varying[] NOT NULL,
    "note" "text",
    "status" character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    "reviewed_by_admin_id" "uuid",
    "kor_travel_map_ref" "jsonb",
    "resolved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "source" character varying(16) DEFAULT 'user'::character varying NOT NULL,
    "external_ref" "jsonb",
    "target_feature_uuid" "uuid",
    CONSTRAINT "ck_feature_suggestions_ck_feature_suggestions_kind" CHECK ((("kind")::"text" = ANY ((ARRAY['place'::character varying, 'event'::character varying, 'notice'::character varying, 'price'::character varying, 'weather'::character varying, 'route'::character varying, 'area'::character varying])::"text"[]))),
    CONSTRAINT "ck_feature_suggestions_ck_feature_suggestions_korea_coord" CHECK ((("lng" >= 124.0) AND ("lng" <= 132.0) AND ("lat" >= 33.0) AND ("lat" <= 43.0))),
    CONSTRAINT "ck_feature_suggestions_ck_feature_suggestions_name" CHECK ((("char_length"(("name")::"text") >= 1) AND ("char_length"(("name")::"text") <= 200))),
    CONSTRAINT "ck_feature_suggestions_ck_feature_suggestions_note" CHECK ((("note" IS NULL) OR ("char_length"("note") <= 2000))),
    CONSTRAINT "ck_feature_suggestions_ck_feature_suggestions_status" CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying, 'added'::character varying, 'duplicate'::character varying])::"text"[]))),
    CONSTRAINT "ck_feature_suggestions_ck_feature_suggestions_type" CHECK ((("type")::"text" = ANY ((ARRAY['new_place'::character varying, 'correction'::character varying, 'closure'::character varying])::"text"[])))
);

CREATE TABLE "app"."kasi_special_days" (
    "special_day_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "dataset" character varying(40) NOT NULL,
    "sol_date" "date" NOT NULL,
    "name" character varying(200) NOT NULL,
    "sequence" character varying(40) DEFAULT ''::character varying NOT NULL,
    "is_holiday" boolean,
    "raw_payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "fetched_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_kasi_special_days_ck_kasi_special_days_dataset" CHECK ((("dataset")::"text" = ANY ((ARRAY['holidays'::character varying, 'national_holidays'::character varying, 'anniversaries'::character varying, 'solar_terms_24'::character varying, 'sundry_days'::character varying])::"text"[])))
);

CREATE TABLE "app"."ktm_cache_target_boundary_audits" (
    "transaction_id" "uuid" NOT NULL,
    "cutover_id" "uuid" NOT NULL,
    "contract_version" "text" NOT NULL,
    "status" "text" NOT NULL,
    "source_revision" "text" NOT NULL,
    "database_identity" "bytea" NOT NULL,
    "writer_registry_sha256" "bytea" NOT NULL,
    "initial_writer_fence_sha256" "bytea" NOT NULL,
    "final_writer_fence_sha256" "bytea" NOT NULL,
    "map_final_evidence_sha256" "bytea" NOT NULL,
    "audit_request_sha256" "bytea" NOT NULL,
    "prior_receipt_sha256" "bytea" NOT NULL,
    "schema_revision" "text" NOT NULL,
    "canary_run_id" "uuid" NOT NULL,
    "consumer_id" "text" NOT NULL,
    "initial_cutover_id" "uuid" NOT NULL,
    "initial_reconciliation_request_id" "uuid" NOT NULL,
    "initial_receipt_event_id" "uuid" NOT NULL,
    "initial_expectation_status" "text" NOT NULL,
    "pending_command_count" bigint NOT NULL,
    "leased_command_count" bigint NOT NULL,
    "dead_letter_command_count" bigint NOT NULL,
    "in_flight_command_count" bigint NOT NULL,
    "database_in_flight_transaction_count" bigint NOT NULL,
    "email_queue_pending_count" bigint NOT NULL,
    "telegram_outbox_pending_count" bigint NOT NULL,
    "location_audit_outbox_pending_count" bigint NOT NULL,
    "expected_initial_command_count" bigint NOT NULL,
    "expected_initial_event_count" bigint NOT NULL,
    "expected_initial_claim_item_count" bigint NOT NULL,
    "expected_synthetic_command_count" bigint NOT NULL,
    "expected_synthetic_event_count" bigint NOT NULL,
    "expected_synthetic_claim_count" bigint NOT NULL,
    "unexpected_generation7_command_count" bigint NOT NULL,
    "unexpected_non_synthetic_event_count" bigint NOT NULL,
    "unexpected_non_synthetic_claim_count" bigint NOT NULL,
    "initial_evidence_sha256" "bytea" NOT NULL,
    "canary_provenance_sha256" "bytea" NOT NULL,
    "final_local_remote_evidence_sha256" "bytea" NOT NULL,
    "evidence_sha256" "bytea" NOT NULL,
    "runtime_mutation_count" bigint NOT NULL,
    "external_mutation_count" bigint NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_cache_target_boundary_audits_ck_ktm_ct_boundary__1098" CHECK ((("initial_expectation_status" = 'received'::"text") AND ("expected_initial_command_count" >= 0) AND ("expected_initial_event_count" = ("expected_initial_command_count" + 1)) AND ("expected_initial_claim_item_count" = ("expected_initial_command_count" + 1)) AND ("expected_synthetic_command_count" = 2) AND ("expected_synthetic_event_count" = 2) AND ("expected_synthetic_claim_count" = 2) AND ("pending_command_count" = 0) AND ("leased_command_count" = 0) AND ("dead_letter_command_count" = 0) AND ("in_flight_command_count" = 0) AND ("database_in_flight_transaction_count" = 0) AND ("unexpected_generation7_command_count" = 0) AND ("unexpected_non_synthetic_event_count" = 0) AND ("unexpected_non_synthetic_claim_count" = 0))),
    CONSTRAINT "ck_ktm_cache_target_boundary_audits_ck_ktm_ct_boundary__4c55" CHECK ((("email_queue_pending_count" >= 0) AND ("telegram_outbox_pending_count" >= 0) AND ("location_audit_outbox_pending_count" >= 0))),
    CONSTRAINT "ck_ktm_cache_target_boundary_audits_ck_ktm_ct_boundary_evidence" CHECK ((("octet_length"("initial_evidence_sha256") = 32) AND ("octet_length"("canary_provenance_sha256") = 32) AND ("octet_length"("final_local_remote_evidence_sha256") = 32) AND ("octet_length"("evidence_sha256") = 32) AND ("runtime_mutation_count" = 0) AND ("external_mutation_count" = 0))),
    CONSTRAINT "ck_ktm_cache_target_boundary_audits_ck_ktm_ct_boundary_identity" CHECK ((("source_revision" ~ '^[0-9a-f]{40}$'::"text") AND ("octet_length"("database_identity") = 32) AND ("octet_length"("writer_registry_sha256") = 32) AND ("octet_length"("initial_writer_fence_sha256") = 32) AND ("octet_length"("final_writer_fence_sha256") = 32) AND ("initial_writer_fence_sha256" <> "final_writer_fence_sha256") AND ("octet_length"("map_final_evidence_sha256") = 32) AND ("octet_length"("audit_request_sha256") = 32) AND ("octet_length"("prior_receipt_sha256") = 32))),
    CONSTRAINT "ck_ktm_ct_boundary_contract" CHECK ((("contract_version" = 'pinvi-cache-target-final-boundary/v1'::"text") AND ("status" = 'succeeded'::"text") AND ("schema_revision" = '20260821_0061'::"text")))
);

CREATE TABLE "app"."ktm_cache_target_canary_runs" (
    "run_id" "uuid" NOT NULL,
    "target_poi_id" "uuid" NOT NULL,
    "consumer_id" "text" NOT NULL,
    "status" "text" DEFAULT 'running'::"text" NOT NULL,
    "phase" "text" DEFAULT 'put_enqueued'::"text" NOT NULL,
    "put_command_id" "uuid" NOT NULL,
    "delete_command_id" "uuid",
    "put_event_id" "uuid",
    "delete_event_id" "uuid",
    "put_claim_id" "uuid",
    "delete_claim_id" "uuid",
    "put_generation" bigint NOT NULL,
    "delete_generation" bigint NOT NULL,
    "put_source_payload_fingerprint" "bytea" NOT NULL,
    "delete_source_payload_fingerprint" "bytea" NOT NULL,
    "put_event_payload_fingerprint" "bytea",
    "delete_event_payload_fingerprint" "bytea",
    "put_claim_status" "text",
    "delete_claim_status" "text",
    "put_acked_at" timestamp with time zone,
    "delete_acked_at" timestamp with time zone,
    "put_claim_completed_at" timestamp with time zone,
    "delete_claim_completed_at" timestamp with time zone,
    "put_relay_order" bigint,
    "delete_relay_order" bigint,
    "baseline_cache_generation" bigint NOT NULL,
    "put_cache_generation" bigint,
    "final_cache_generation" bigint,
    "final_restore_epoch" bigint,
    "final_stream_control_version" bigint,
    "final_stream_control_etag" "text",
    "baseline_cursor" "text" NOT NULL,
    "put_cursor" "text",
    "delete_cursor" "text",
    "final_local_applied_cursor" "text",
    "final_local_remote_acked_cursor" "text",
    "final_remote_snapshot_high_watermark_cursor" "text",
    "baseline_count" bigint NOT NULL,
    "baseline_merkle_root" "bytea" NOT NULL,
    "final_local_count" bigint,
    "final_remote_count" bigint,
    "final_local_merkle_root" "bytea",
    "final_remote_merkle_root" "bytea",
    "final_pending_commands" bigint,
    "final_leased_commands" bigint,
    "final_dead_letter_commands" bigint,
    "canary_provenance_sha256" "bytea",
    "final_evidence_sha256" "bytea",
    "terminal_error_code" "text",
    "failed_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_baseline" CHECK ((("baseline_cache_generation" >= 0) AND ("baseline_count" >= 0) AND ("octet_length"("baseline_merkle_root") = 32) AND ("length"("baseline_cursor") > 0))),
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_delete_802e" CHECK ((("num_nonnulls"("delete_event_id", "delete_claim_id", "delete_relay_order", "delete_cursor", "encode"("delete_event_payload_fingerprint", 'hex'::"text"), "delete_claim_status", "delete_acked_at", "delete_claim_completed_at") = ANY (ARRAY[0, 8])) AND (("delete_event_id" IS NULL) OR (("delete_event_id" IS NOT NULL) AND ("delete_claim_id" IS NOT NULL) AND ("delete_relay_order" IS NOT NULL) AND ("put_relay_order" IS NOT NULL) AND ("delete_relay_order" > "put_relay_order") AND ("delete_cursor" IS NOT NULL) AND ("length"("delete_cursor") > 0) AND ("delete_event_payload_fingerprint" IS NOT NULL) AND ("octet_length"("delete_event_payload_fingerprint") = 32) AND ("delete_claim_status" = 'acked'::"text") AND ("delete_acked_at" IS NOT NULL) AND ("delete_claim_completed_at" IS NOT NULL))))),
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_final_material" CHECK ((("num_nonnulls"(("final_cache_generation")::"text", ("final_restore_epoch")::"text", ("final_stream_control_version")::"text", "final_stream_control_etag", "final_local_applied_cursor", "final_local_remote_acked_cursor", "final_remote_snapshot_high_watermark_cursor", ("final_local_count")::"text", ("final_remote_count")::"text", "encode"("final_local_merkle_root", 'hex'::"text"), "encode"("final_remote_merkle_root", 'hex'::"text"), ("final_pending_commands")::"text", ("final_leased_commands")::"text", ("final_dead_letter_commands")::"text", "encode"("canary_provenance_sha256", 'hex'::"text"), "encode"("final_evidence_sha256", 'hex'::"text")) = 0) OR (("num_nonnulls"(("final_cache_generation")::"text", ("final_restore_epoch")::"text", ("final_stream_control_version")::"text", "final_stream_control_etag", "final_local_applied_cursor", "final_local_remote_acked_cursor", "final_remote_snapshot_high_watermark_cursor", ("final_local_count")::"text", ("final_remote_count")::"text", "encode"("final_local_merkle_root", 'hex'::"text"), "encode"("final_remote_merkle_root", 'hex'::"text"), ("final_pending_commands")::"text", ("final_leased_commands")::"text", ("final_dead_letter_commands")::"text", "encode"("canary_provenance_sha256", 'hex'::"text"), "encode"("final_evidence_sha256", 'hex'::"text")) = 16) AND ("final_cache_generation" > "put_cache_generation") AND ("final_restore_epoch" > 0) AND ("final_stream_control_version" > 0) AND ("length"("final_stream_control_etag") > 0) AND ("length"("final_local_applied_cursor") > 0) AND ("length"("final_local_remote_acked_cursor") > 0) AND ("length"("final_remote_snapshot_high_watermark_cursor") > 0) AND ("final_local_applied_cursor" = "final_local_remote_acked_cursor") AND ("final_local_remote_acked_cursor" = "final_remote_snapshot_high_watermark_cursor") AND ("final_local_count" >= 0) AND ("final_local_count" = "final_remote_count") AND ("octet_length"("final_local_merkle_root") = 32) AND ("final_local_merkle_root" = "final_remote_merkle_root") AND ("octet_length"("canary_provenance_sha256") = 32) AND ("octet_length"("final_evidence_sha256") = 32) AND ("final_pending_commands" = 0) AND ("final_leased_commands" = 0) AND ("final_dead_letter_commands" = 0)))),
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_generations" CHECK ((("put_generation" > 0) AND ("delete_generation" = ("put_generation" + 1)) AND ("octet_length"("put_source_payload_fingerprint") = 32) AND ("octet_length"("delete_source_payload_fingerprint") = 32) AND ("put_source_payload_fingerprint" <> "delete_source_payload_fingerprint"))),
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_phase" CHECK (("phase" = ANY (ARRAY['put_enqueued'::"text", 'put_applied'::"text", 'delete_enqueued'::"text", 'delete_applied'::"text", 'completed'::"text"]))),
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_phase_material" CHECK (((("phase" = 'put_enqueued'::"text") AND ("put_event_id" IS NULL) AND ("put_claim_id" IS NULL) AND ("put_relay_order" IS NULL) AND ("put_cache_generation" IS NULL) AND ("put_cursor" IS NULL) AND ("put_event_payload_fingerprint" IS NULL) AND ("put_claim_status" IS NULL) AND ("put_acked_at" IS NULL) AND ("put_claim_completed_at" IS NULL) AND ("delete_command_id" IS NULL) AND ("delete_event_id" IS NULL) AND ("delete_claim_id" IS NULL) AND ("delete_relay_order" IS NULL) AND ("delete_cursor" IS NULL) AND ("delete_event_payload_fingerprint" IS NULL) AND ("delete_claim_status" IS NULL) AND ("delete_acked_at" IS NULL) AND ("delete_claim_completed_at" IS NULL) AND ("final_cache_generation" IS NULL)) OR (("phase" = 'put_applied'::"text") AND ("put_event_id" IS NOT NULL) AND ("put_claim_id" IS NOT NULL) AND ("put_relay_order" IS NOT NULL) AND ("put_cache_generation" IS NOT NULL) AND ("put_cursor" IS NOT NULL) AND ("put_event_payload_fingerprint" IS NOT NULL) AND ("put_claim_status" IS NOT NULL) AND ("put_acked_at" IS NOT NULL) AND ("put_claim_completed_at" IS NOT NULL) AND ("delete_command_id" IS NULL) AND ("delete_event_id" IS NULL) AND ("delete_claim_id" IS NULL) AND ("delete_relay_order" IS NULL) AND ("delete_cursor" IS NULL) AND ("delete_event_payload_fingerprint" IS NULL) AND ("delete_claim_status" IS NULL) AND ("delete_acked_at" IS NULL) AND ("delete_claim_completed_at" IS NULL) AND ("final_cache_generation" IS NULL)) OR (("phase" = 'delete_enqueued'::"text") AND ("put_event_id" IS NOT NULL) AND ("put_claim_id" IS NOT NULL) AND ("put_relay_order" IS NOT NULL) AND ("put_cache_generation" IS NOT NULL) AND ("put_cursor" IS NOT NULL) AND ("put_event_payload_fingerprint" IS NOT NULL) AND ("put_claim_status" IS NOT NULL) AND ("put_acked_at" IS NOT NULL) AND ("put_claim_completed_at" IS NOT NULL) AND ("delete_command_id" IS NOT NULL) AND ("delete_event_id" IS NULL) AND ("delete_claim_id" IS NULL) AND ("delete_relay_order" IS NULL) AND ("delete_cursor" IS NULL) AND ("delete_event_payload_fingerprint" IS NULL) AND ("delete_claim_status" IS NULL) AND ("delete_acked_at" IS NULL) AND ("delete_claim_completed_at" IS NULL) AND ("final_cache_generation" IS NULL)) OR (("phase" = 'delete_applied'::"text") AND ("put_event_id" IS NOT NULL) AND ("put_claim_id" IS NOT NULL) AND ("put_relay_order" IS NOT NULL) AND ("put_cache_generation" IS NOT NULL) AND ("put_cursor" IS NOT NULL) AND ("put_event_payload_fingerprint" IS NOT NULL) AND ("put_claim_status" IS NOT NULL) AND ("put_acked_at" IS NOT NULL) AND ("put_claim_completed_at" IS NOT NULL) AND ("delete_command_id" IS NOT NULL) AND ("delete_event_id" IS NOT NULL) AND ("delete_claim_id" IS NOT NULL) AND ("delete_relay_order" IS NOT NULL) AND ("delete_cursor" IS NOT NULL) AND ("delete_event_payload_fingerprint" IS NOT NULL) AND ("delete_claim_status" IS NOT NULL) AND ("delete_acked_at" IS NOT NULL) AND ("delete_claim_completed_at" IS NOT NULL) AND ("final_cache_generation" IS NULL)) OR (("phase" = 'completed'::"text") AND ("put_event_id" IS NOT NULL) AND ("put_claim_id" IS NOT NULL) AND ("put_relay_order" IS NOT NULL) AND ("put_cache_generation" IS NOT NULL) AND ("put_cursor" IS NOT NULL) AND ("put_event_payload_fingerprint" IS NOT NULL) AND ("put_claim_status" IS NOT NULL) AND ("put_acked_at" IS NOT NULL) AND ("put_claim_completed_at" IS NOT NULL) AND ("delete_command_id" IS NOT NULL) AND ("delete_event_id" IS NOT NULL) AND ("delete_claim_id" IS NOT NULL) AND ("delete_relay_order" IS NOT NULL) AND ("delete_cursor" IS NOT NULL) AND ("delete_event_payload_fingerprint" IS NOT NULL) AND ("delete_claim_status" IS NOT NULL) AND ("delete_acked_at" IS NOT NULL) AND ("delete_claim_completed_at" IS NOT NULL) AND ("final_cache_generation" IS NOT NULL)))),
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_put_material" CHECK ((("num_nonnulls"("put_event_id", "put_claim_id", "put_relay_order", "put_cache_generation", "put_cursor", "encode"("put_event_payload_fingerprint", 'hex'::"text"), "put_claim_status", "put_acked_at", "put_claim_completed_at") = ANY (ARRAY[0, 9])) AND (("put_event_id" IS NULL) OR (("put_event_id" IS NOT NULL) AND ("put_claim_id" IS NOT NULL) AND ("put_relay_order" IS NOT NULL) AND ("put_relay_order" > 0) AND ("put_cache_generation" IS NOT NULL) AND ("put_cache_generation" > "baseline_cache_generation") AND ("put_cursor" IS NOT NULL) AND ("length"("put_cursor") > 0) AND ("put_event_payload_fingerprint" IS NOT NULL) AND ("octet_length"("put_event_payload_fingerprint") = 32) AND ("put_claim_status" = 'acked'::"text") AND ("put_acked_at" IS NOT NULL) AND ("put_claim_completed_at" IS NOT NULL))))),
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_stable_target" CHECK (("target_poi_id" = '15f98050-27d7-5f85-be21-dc53eded5d7d'::"uuid")),
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_status" CHECK (("status" = ANY (ARRAY['running'::"text", 'succeeded'::"text", 'failed'::"text"]))),
    CONSTRAINT "ck_ktm_cache_target_canary_runs_ck_ktm_ct_canary_terminal" CHECK (((("status" = 'running'::"text") AND ("terminal_error_code" IS NULL) AND ("failed_at" IS NULL) AND ("completed_at" IS NULL) AND ("phase" <> 'completed'::"text")) OR (("status" = 'succeeded'::"text") AND ("terminal_error_code" IS NULL) AND ("failed_at" IS NULL) AND ("completed_at" IS NOT NULL) AND ("phase" = 'completed'::"text")) OR (("status" = 'failed'::"text") AND ("length"("terminal_error_code") > 0) AND ("failed_at" IS NOT NULL) AND ("completed_at" IS NULL) AND ("phase" <> 'completed'::"text"))))
);

CREATE TABLE "app"."ktm_cache_target_commands" (
    "command_id" "uuid" NOT NULL,
    "poi_id" "uuid" NOT NULL,
    "operation" character varying(16) NOT NULL,
    "source_generation" bigint NOT NULL,
    "payload" "jsonb" NOT NULL,
    "payload_fingerprint" "bytea" NOT NULL,
    "expected_etag" "text",
    "status" character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    "attempts" integer DEFAULT 0 NOT NULL,
    "available_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "lease_owner" character varying(128),
    "lease_until" timestamp with time zone,
    "response_status" integer,
    "response_body" "jsonb",
    "response_etag" "text",
    "error_code" character varying(96),
    "error_detail" "jsonb",
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_ct_commands_attempts" CHECK (("attempts" >= 0)),
    CONSTRAINT "ck_ktm_ct_commands_fingerprint" CHECK (("octet_length"("payload_fingerprint") = 32)),
    CONSTRAINT "ck_ktm_ct_commands_generation" CHECK (("source_generation" > 0)),
    CONSTRAINT "ck_ktm_ct_commands_lease_pair" CHECK ((("lease_owner" IS NULL) = ("lease_until" IS NULL))),
    CONSTRAINT "ck_ktm_ct_commands_operation" CHECK ((("operation")::"text" = ANY ((ARRAY['put'::character varying, 'delete'::character varying, 'refresh'::character varying])::"text"[]))),
    CONSTRAINT "ck_ktm_ct_commands_status" CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'leased'::character varying, 'succeeded'::character varying, 'superseded'::character varying, 'dead_letter'::character varying])::"text"[])))
);

CREATE TABLE "app"."ktm_cache_target_consumers" (
    "consumer_id" character varying(64) NOT NULL,
    "external_system" character varying(32) DEFAULT 'pinvi'::character varying NOT NULL,
    "active_restore_epoch" bigint,
    "local_applied_cursor" "text",
    "remote_acked_cursor" "text",
    "high_watermark_cursor" "text",
    "stream_control_etag" "text",
    "snapshot_id" "text",
    "snapshot_count" bigint,
    "snapshot_merkle_root" "bytea",
    "reconcile_status" character varying(16) DEFAULT 'uninitialized'::character varying NOT NULL,
    "feature_cache_generation" bigint DEFAULT '0'::bigint NOT NULL,
    "ready" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "initial_cutover_id" "uuid",
    "initial_reconciliation_request_id" "uuid",
    "initial_begin_stream_etag" "text",
    "initial_reconciliation_etag" "text",
    "initial_source_count" bigint,
    "initial_source_merkle_root" "bytea",
    "initial_cutover_completed_at" timestamp with time zone,
    CONSTRAINT "ck_ktm_cache_target_consumers_ck_ktm_ct_consumers_initi_df8c" CHECK (((("initial_cutover_id" IS NULL) AND ("initial_reconciliation_request_id" IS NULL) AND ("initial_begin_stream_etag" IS NULL) AND ("initial_reconciliation_etag" IS NULL) AND ("initial_source_count" IS NULL) AND ("initial_source_merkle_root" IS NULL) AND ("initial_cutover_completed_at" IS NULL)) OR (("initial_cutover_id" IS NOT NULL) AND ("initial_source_count" >= 0) AND ("octet_length"("initial_source_merkle_root") = 32)))),
    CONSTRAINT "ck_ktm_ct_consumers_cache_generation" CHECK (("feature_cache_generation" >= 0)),
    CONSTRAINT "ck_ktm_ct_consumers_epoch" CHECK ((("active_restore_epoch" IS NULL) OR ("active_restore_epoch" > 0))),
    CONSTRAINT "ck_ktm_ct_consumers_merkle" CHECK ((("snapshot_merkle_root" IS NULL) OR ("octet_length"("snapshot_merkle_root") = 32))),
    CONSTRAINT "ck_ktm_ct_consumers_reconcile" CHECK ((("reconcile_status")::"text" = ANY ((ARRAY['uninitialized'::character varying, 'checking'::character varying, 'matched'::character varying, 'mismatched'::character varying, 'blocked'::character varying])::"text"[]))),
    CONSTRAINT "ck_ktm_ct_consumers_snapshot_count" CHECK ((("snapshot_count" IS NULL) OR ("snapshot_count" >= 0))),
    CONSTRAINT "ck_ktm_ct_consumers_system" CHECK ((("external_system")::"text" = 'pinvi'::"text"))
);

CREATE TABLE "app"."ktm_cache_target_event_claim_items" (
    "claim_id" "uuid" NOT NULL,
    "event_id" "uuid" NOT NULL,
    "position" integer NOT NULL,
    "delivery_cursor" "text" NOT NULL,
    "payload_fingerprint" "bytea" NOT NULL,
    "acked_at" timestamp with time zone,
    CONSTRAINT "ck_ktm_ct_claim_items_fingerprint" CHECK (("octet_length"("payload_fingerprint") = 32)),
    CONSTRAINT "ck_ktm_ct_claim_items_position" CHECK (("position" > 0))
);

CREATE TABLE "app"."ktm_cache_target_event_claims" (
    "claim_id" "uuid" NOT NULL,
    "consumer_id" character varying(64) NOT NULL,
    "lease_token" "uuid" NOT NULL,
    "lease_expires_at" timestamp with time zone NOT NULL,
    "status" character varying(16) DEFAULT 'active'::character varying NOT NULL,
    "acked_through_cursor" "text",
    "received_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "completed_at" timestamp with time zone,
    CONSTRAINT "ck_ktm_ct_event_claims_completion" CHECK ((((("status")::"text" = 'active'::"text") AND ("completed_at" IS NULL)) OR ((("status")::"text" <> 'active'::"text") AND ("completed_at" IS NOT NULL)))),
    CONSTRAINT "ck_ktm_ct_event_claims_status" CHECK ((("status")::"text" = ANY ((ARRAY['active'::character varying, 'acked'::character varying, 'expired'::character varying, 'invalidated'::character varying])::"text"[])))
);

CREATE TABLE "app"."ktm_cache_target_events" (
    "event_id" "uuid" NOT NULL,
    "event_type" character varying(64) NOT NULL,
    "external_system" character varying(32) NOT NULL,
    "target_key" character varying(36),
    "target_id" "uuid",
    "restore_epoch" bigint NOT NULL,
    "source_generation" bigint,
    "target_sequence" bigint,
    "relay_order" bigint NOT NULL,
    "source_payload_fingerprint" "bytea" NOT NULL,
    "occurred_at" timestamp with time zone NOT NULL,
    "payload" "jsonb" NOT NULL,
    "received_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "applied_at" timestamp with time zone,
    "payload_fingerprint" "bytea" NOT NULL,
    "source_event_id" "uuid" GENERATED ALWAYS AS (
CASE
    WHEN (("event_type")::"text" = 'cache_target.state_applied'::"text") THEN (("payload" ->> 'source_event_id'::"text"))::"uuid"
    ELSE NULL::"uuid"
END) STORED,
    CONSTRAINT "ck_ktm_cache_target_events_ck_ktm_ct_events_payload_fingerprint" CHECK (("octet_length"("payload_fingerprint") = 32)),
    CONSTRAINT "ck_ktm_ct_events_epoch" CHECK (("restore_epoch" > 0)),
    CONSTRAINT "ck_ktm_ct_events_relay_order" CHECK (("relay_order" > 0)),
    CONSTRAINT "ck_ktm_ct_events_scope_tuple" CHECK ((("octet_length"("source_payload_fingerprint") = 32) AND (((("event_type")::"text" = 'cache_target.reconciled'::"text") AND ("target_key" IS NULL) AND ("target_id" IS NULL) AND ("source_generation" IS NULL) AND ("target_sequence" IS NULL)) OR ((("event_type")::"text" <> 'cache_target.reconciled'::"text") AND ("target_key" IS NOT NULL) AND ("target_id" IS NOT NULL) AND ("source_generation" > 0) AND ("target_sequence" > 0))))),
    CONSTRAINT "ck_ktm_ct_events_system" CHECK ((("external_system")::"text" = 'pinvi'::"text")),
    CONSTRAINT "ck_ktm_ct_events_type" CHECK ((("event_type")::"text" = ANY ((ARRAY['cache_target.state_applied'::character varying, 'cache_target.links_reconciled'::character varying, 'refresh_request.status_changed'::character varying, 'cache_target.reconciled'::character varying])::"text"[])))
);

CREATE TABLE "app"."ktm_cache_target_heads" (
    "poi_id" "uuid" NOT NULL,
    "external_system" character varying(32) DEFAULT 'pinvi'::character varying NOT NULL,
    "target_key" character varying(36) NOT NULL,
    "desired_state" character varying(16) NOT NULL,
    "source_generation" bigint NOT NULL,
    "source_payload_fingerprint" "bytea" NOT NULL,
    "lon" numeric,
    "lat" numeric,
    "radius_km" numeric NOT NULL,
    "update_enabled" boolean NOT NULL,
    "remote_target_id" "uuid",
    "remote_etag" "text",
    "remote_restore_epoch" bigint,
    "remote_source_generation" bigint,
    "remote_target_sequence" bigint,
    "remote_status" character varying(32),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_ct_heads_active_coord" CHECK (((("desired_state")::"text" = 'deleted'::"text") OR (("lon" IS NOT NULL) AND ("lat" IS NOT NULL)))),
    CONSTRAINT "ck_ktm_ct_heads_fingerprint" CHECK (("octet_length"("source_payload_fingerprint") = 32)),
    CONSTRAINT "ck_ktm_ct_heads_generation" CHECK (("source_generation" > 0)),
    CONSTRAINT "ck_ktm_ct_heads_lat" CHECK ((("lat" IS NULL) OR (("lat" >= (33)::numeric) AND ("lat" <= 39.5)))),
    CONSTRAINT "ck_ktm_ct_heads_lon" CHECK ((("lon" IS NULL) OR (("lon" >= (124)::numeric) AND ("lon" <= (132)::numeric)))),
    CONSTRAINT "ck_ktm_ct_heads_radius" CHECK ((("radius_km" > (0)::numeric) AND ("radius_km" <= (100)::numeric))),
    CONSTRAINT "ck_ktm_ct_heads_remote_epoch" CHECK ((("remote_restore_epoch" IS NULL) OR ("remote_restore_epoch" > 0))),
    CONSTRAINT "ck_ktm_ct_heads_remote_generation" CHECK ((("remote_source_generation" IS NULL) OR ("remote_source_generation" > 0))),
    CONSTRAINT "ck_ktm_ct_heads_remote_sequence" CHECK ((("remote_target_sequence" IS NULL) OR ("remote_target_sequence" > 0))),
    CONSTRAINT "ck_ktm_ct_heads_state" CHECK ((("desired_state")::"text" = ANY ((ARRAY['active'::character varying, 'deleted'::character varying])::"text"[]))),
    CONSTRAINT "ck_ktm_ct_heads_system" CHECK ((("external_system")::"text" = 'pinvi'::"text")),
    CONSTRAINT "ck_ktm_ct_heads_target_key" CHECK ((("target_key")::"text" = "lower"(("poi_id")::"text")))
);

CREATE TABLE "app"."ktm_cache_target_reconciliation_expectations" (
    "request_id" "uuid" NOT NULL,
    "external_system" character varying(32) DEFAULT 'pinvi'::character varying NOT NULL,
    "snapshot_id" "uuid" NOT NULL,
    "restore_epoch" bigint NOT NULL,
    "snapshot_count" bigint NOT NULL,
    "snapshot_merkle_root" "bytea" NOT NULL,
    "high_watermark_cursor" "text" NOT NULL,
    "status" character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    "receipt_event_id" "uuid",
    "resolved_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_cache_target_reconciliation_expectations_ck_ktm__010f" CHECK (("snapshot_count" >= 0)),
    CONSTRAINT "ck_ktm_cache_target_reconciliation_expectations_ck_ktm__15d8" CHECK (("length"("high_watermark_cursor") > 0)),
    CONSTRAINT "ck_ktm_cache_target_reconciliation_expectations_ck_ktm__19c9" CHECK (("restore_epoch" > 0)),
    CONSTRAINT "ck_ktm_cache_target_reconciliation_expectations_ck_ktm__5bc9" CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'received'::character varying, 'invalidated'::character varying])::"text"[]))),
    CONSTRAINT "ck_ktm_cache_target_reconciliation_expectations_ck_ktm__808b" CHECK ((((("status")::"text" = 'pending'::"text") AND ("receipt_event_id" IS NULL) AND ("resolved_at" IS NULL)) OR ((("status")::"text" = 'received'::"text") AND ("receipt_event_id" IS NOT NULL) AND ("resolved_at" IS NOT NULL)) OR ((("status")::"text" = 'invalidated'::"text") AND ("receipt_event_id" IS NULL) AND ("resolved_at" IS NOT NULL)))),
    CONSTRAINT "ck_ktm_cache_target_reconciliation_expectations_ck_ktm__8471" CHECK ((("external_system")::"text" = 'pinvi'::"text")),
    CONSTRAINT "ck_ktm_cache_target_reconciliation_expectations_ck_ktm__84d9" CHECK (("octet_length"("snapshot_merkle_root") = 32))
);

CREATE TABLE "app"."ktm_cache_target_restore_fence_attempts" (
    "idempotency_key" "uuid" NOT NULL,
    "consumer_id" "text" NOT NULL,
    "external_system" "text" DEFAULT 'pinvi'::"text" NOT NULL,
    "expected_restore_epoch" bigint NOT NULL,
    "expected_control_version" bigint NOT NULL,
    "stream_etag" "text" NOT NULL,
    "reason" "text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "response_status" integer,
    "response_etag" "text",
    "response_body" "jsonb",
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_cache_target_restore_fence_attempts_ck_ktm_ct_re_0659" CHECK ((("btrim"("consumer_id") = "consumer_id") AND ("consumer_id" <> ''::"text") AND ("btrim"("stream_etag") = "stream_etag") AND ("stream_etag" <> ''::"text") AND ("btrim"("reason") = "reason") AND (("char_length"("reason") >= 1) AND ("char_length"("reason") <= 1000)))),
    CONSTRAINT "ck_ktm_cache_target_restore_fence_attempts_ck_ktm_ct_re_4d19" CHECK (((("status" = 'pending'::"text") AND ("response_status" IS NULL) AND ("response_etag" IS NULL) AND ("response_body" IS NULL) AND ("completed_at" IS NULL)) OR (("status" = 'completed'::"text") AND ("response_status" = ANY (ARRAY[200, 201])) AND ("btrim"("response_etag") = "response_etag") AND ("response_etag" <> ''::"text") AND ("jsonb_typeof"("response_body") = 'object'::"text") AND ("completed_at" IS NOT NULL)))),
    CONSTRAINT "ck_ktm_cache_target_restore_fence_attempts_ck_ktm_ct_re_b472" CHECK (("external_system" = 'pinvi'::"text")),
    CONSTRAINT "ck_ktm_cache_target_restore_fence_attempts_ck_ktm_ct_re_df54" CHECK ((("expected_restore_epoch" > 0) AND ("expected_control_version" > 0)))
);

CREATE TABLE "app"."ktm_curation_cutover_backfill_receipts" (
    "receipt_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "actor_admin_id" "uuid" NOT NULL,
    "idempotency_key" "uuid" NOT NULL,
    "request_fingerprint" character varying(64) NOT NULL,
    "mapping_receipt_id" "uuid" NOT NULL,
    "legacy_curated_feature_id" "uuid" NOT NULL,
    "curated_plan_id" "uuid" NOT NULL,
    "import_receipt_id" "uuid",
    "status" character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_curation_cutover_backfill_receipts_fingerprint" CHECK ((("request_fingerprint")::"text" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ktm_curation_cutover_backfill_receipts_terminal" CHECK ((((("status")::"text" = 'pending'::"text") AND ("import_receipt_id" IS NULL) AND ("completed_at" IS NULL)) OR ((("status")::"text" = 'completed'::"text") AND ("import_receipt_id" IS NOT NULL) AND ("completed_at" IS NOT NULL))))
);

CREATE TABLE "app"."ktm_curation_cutover_mapping_receipt_items" (
    "receipt_id" "uuid" NOT NULL,
    "legacy_curated_feature_id" "uuid" NOT NULL,
    "collection_id" "uuid" NOT NULL,
    "curation_item_id" "uuid" NOT NULL,
    "mapping_kind" character varying(32) NOT NULL,
    "source_row_hash" character varying(64) NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_curation_cutover_mapping_receipt_items_source" CHECK (((("mapping_kind")::"text" = ANY ((ARRAY['legacy_projection'::character varying, 'official_membership'::character varying, 'manual_membership'::character varying])::"text"[])) AND (("source_row_hash")::"text" ~ '^[0-9a-f]{64}$'::"text")))
);

CREATE TABLE "app"."ktm_curation_cutover_mapping_receipts" (
    "receipt_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "actor_admin_id" "uuid" NOT NULL,
    "map_release_revision" character varying(40) NOT NULL,
    "mapping_root_version" character varying(64) NOT NULL,
    "mapping_root" character varying(64) NOT NULL,
    "mapping_count" bigint NOT NULL,
    "status" character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_curation_cutover_mapping_receipts_release" CHECK ((("map_release_revision")::"text" ~ '^[0-9a-f]{40}$'::"text")),
    CONSTRAINT "ck_ktm_curation_cutover_mapping_receipts_root" CHECK (((("mapping_root_version")::"text" = 'ktm-curation-cutover-mapping-v1'::"text") AND (("mapping_root")::"text" ~ '^[0-9a-f]{64}$'::"text") AND ("mapping_count" >= 0))),
    CONSTRAINT "ck_ktm_curation_cutover_mapping_receipts_terminal" CHECK ((((("status")::"text" = 'pending'::"text") AND ("completed_at" IS NULL)) OR ((("status")::"text" = 'completed'::"text") AND ("completed_at" IS NOT NULL))))
);

CREATE TABLE "app"."ktm_curation_import_receipt_items" (
    "receipt_id" "uuid" NOT NULL,
    "source_curation_collection_id" "uuid" NOT NULL,
    "source_curation_item_id" "uuid" NOT NULL,
    "source_curation_item_revision" bigint NOT NULL,
    "source_curation_item_etag" character varying(128) NOT NULL,
    "feature_uuid" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_curation_import_receipt_items_source" CHECK ((("source_curation_item_revision" > 0) AND (("source_curation_item_etag")::"text" ~ '^"sha256:[0-9a-f]{64}"$'::"text")))
);

CREATE TABLE "app"."ktm_curation_import_receipts" (
    "receipt_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "actor_admin_id" "uuid" NOT NULL,
    "idempotency_key" "uuid" NOT NULL,
    "request_fingerprint" character varying(64) NOT NULL,
    "source_system" character varying(32) DEFAULT 'kor-travel-map'::character varying NOT NULL,
    "source_curation_collection_id" "uuid" NOT NULL,
    "source_curation_collection_revision" bigint NOT NULL,
    "source_curation_collection_etag" character varying(128) NOT NULL,
    "source_curation_item_set_hash_version" character varying(64) NOT NULL,
    "source_curation_item_set_hash" character varying(64) NOT NULL,
    "source_curation_item_count" bigint NOT NULL,
    "mode" character varying(16) NOT NULL,
    "requested_is_published" boolean,
    "status" character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    "result_plan_id" "uuid",
    "response_status" integer,
    "response_body" "jsonb",
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_curation_import_receipts_fingerprint" CHECK ((("request_fingerprint")::"text" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ktm_curation_import_receipts_request" CHECK (((("source_system")::"text" = 'kor-travel-map'::"text") AND (("mode")::"text" = ANY ((ARRAY['create'::character varying, 'refresh'::character varying, 'cutover-backfill'::character varying])::"text"[])))),
    CONSTRAINT "ck_ktm_curation_import_receipts_source" CHECK ((("source_curation_collection_revision" > 0) AND (("source_curation_collection_etag")::"text" ~ '^"sha256:[0-9a-f]{64}"$'::"text") AND (("source_curation_item_set_hash_version")::"text" = 'ktm-db-item-set-v1'::"text") AND (("source_curation_item_set_hash")::"text" ~ '^[0-9a-f]{64}$'::"text") AND (("source_curation_item_count" >= 0) AND ("source_curation_item_count" <= 2000)))),
    CONSTRAINT "ck_ktm_curation_import_receipts_terminal" CHECK ((((("status")::"text" = 'pending'::"text") AND ("result_plan_id" IS NULL) AND ("response_status" IS NULL) AND ("response_body" IS NULL) AND ("completed_at" IS NULL)) OR ((("status")::"text" = 'completed'::"text") AND ("result_plan_id" IS NOT NULL) AND ("response_status" = ANY (ARRAY[200, 201])) AND ("jsonb_typeof"("response_body") = 'object'::"text") AND (("response_body" ->> 'notice_plan_id'::"text") = ("result_plan_id")::"text") AND (("response_body" ->> 'source_curation_collection_id'::"text") = ("source_curation_collection_id")::"text") AND ("completed_at" IS NOT NULL))))
);

CREATE TABLE "app"."ktm_feature_reference_reconciliation_applied_receipts" (
    "event_id" "uuid" NOT NULL,
    "event_sequence" bigint NOT NULL,
    "event_sha256" character varying(64) NOT NULL,
    "action" character varying(16) NOT NULL,
    "old_feature_id" "text" NOT NULL,
    "old_feature_uuid" "uuid" NOT NULL,
    "replacement_feature_id" "text",
    "replacement_feature_uuid" "uuid",
    "impact_root_sha256" character varying(64) NOT NULL,
    "impact_count" bigint NOT NULL,
    "receipt_sha256" character varying(64) NOT NULL,
    "applied_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_applied_receipt_2db0" CHECK ((((("action")::"text" = 'rebind'::"text") AND ("replacement_feature_id" IS NOT NULL)) OR ((("action")::"text" = 'detach'::"text") AND ("replacement_feature_id" IS NULL)))),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_applied_receipt_3eed" CHECK ((("old_feature_id" IS NOT NULL) AND ("old_feature_uuid" IS NOT NULL))),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_applied_receipt_5291" CHECK ((("receipt_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_applied_receipt_7101" CHECK (("impact_count" >= 0)),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_applied_receipt_b0ce" CHECK (("event_sequence" > 0)),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_applied_receipt_b4f6" CHECK ((("event_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_applied_receipt_c2d9" CHECK ((("impact_root_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_applied_receipt_d49a" CHECK (((("replacement_feature_id" IS NULL) AND ("replacement_feature_uuid" IS NULL)) OR (("replacement_feature_id" IS NOT NULL) AND ("replacement_feature_uuid" IS NOT NULL))))
);

CREATE TABLE "app"."ktm_feature_reference_reconciliation_delivery_attempts" (
    "event_id" "uuid" NOT NULL,
    "attempt_sequence" bigint NOT NULL,
    "event_sequence" bigint NOT NULL,
    "event_sha256" character varying(64) NOT NULL,
    "status" character varying(16) NOT NULL,
    "block_fingerprint_sha256" character varying(64),
    "observation_root_sha256" character varying(64) NOT NULL,
    "observed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_delivery_attemp_0aa0" CHECK ((("observation_root_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text")),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_delivery_attemp_134c" CHECK (("event_sequence" > 0)),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_delivery_attemp_64d2" CHECK (("attempt_sequence" > 0)),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_delivery_attemp_dd59" CHECK ((("block_fingerprint_sha256" IS NULL) OR (("block_fingerprint_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text"))),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_delivery_attemp_deb1" CHECK ((((("status")::"text" = 'blocked'::"text") AND ("block_fingerprint_sha256" IS NOT NULL)) OR ((("status")::"text" = 'applied'::"text") AND ("block_fingerprint_sha256" IS NULL)))),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_delivery_attemp_f54a" CHECK ((("event_sha256")::"text" ~ '^[0-9a-f]{64}$'::"text"))
);

CREATE TABLE "app"."ktm_feature_reference_reconciliation_impacts" (
    "event_id" "uuid" NOT NULL,
    "impact_index" integer NOT NULL,
    "target_relation" character varying(32) NOT NULL,
    "target_id" "uuid" NOT NULL,
    "old_feature_id" "text" NOT NULL,
    "old_feature_uuid" "uuid" NOT NULL,
    "replacement_feature_id" "text",
    "replacement_feature_uuid" "uuid",
    "outcome" character varying(24) NOT NULL,
    "recorded_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_impacts_ck_ktm__16d9" CHECK ((("old_feature_id" IS NOT NULL) AND ("old_feature_uuid" IS NOT NULL))),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_impacts_ck_ktm__42fa" CHECK ((("target_relation")::"text" = ANY ((ARRAY['trip_day_pois'::character varying, 'curated_plan_pois'::character varying, 'feature_suggestions'::character varying])::"text"[]))),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_impacts_ck_ktm__813e" CHECK (((("replacement_feature_id" IS NULL) AND ("replacement_feature_uuid" IS NULL)) OR (("replacement_feature_id" IS NOT NULL) AND ("replacement_feature_uuid" IS NOT NULL)))),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_impacts_ck_ktm__caf3" CHECK ((((("outcome")::"text" = 'rebind'::"text") AND ("replacement_feature_id" IS NOT NULL)) OR ((("outcome")::"text" = 'detach'::"text") AND ("replacement_feature_id" IS NULL)) OR (("outcome")::"text" = 'already_reconciled'::"text"))),
    CONSTRAINT "ck_ktm_feature_reference_reconciliation_impacts_ck_ktm__d7a1" CHECK (("impact_index" >= 0))
);

CREATE TABLE "app"."location_access_log" (
    "log_id" bigint NOT NULL,
    "user_id" "uuid" NOT NULL,
    "occurred_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "endpoint" "text" NOT NULL,
    "purpose" character varying(64) NOT NULL,
    "lat" numeric(9,6),
    "lng" numeric(9,6),
    "request_id" "uuid" NOT NULL,
    "ip_hash" character varying(64) NOT NULL,
    "prev_hash" character varying(64) NOT NULL,
    "content_hash" character varying(64) NOT NULL,
    CONSTRAINT "ck_location_access_log_ck_location_access_log_purpose" CHECK ((("purpose")::"text" = ANY ((ARRAY['viewport_query'::character varying, 'nearby_attractions'::character varying, 'weather_at_coord'::character varying, 'feature_request'::character varying, 'region_covering'::character varying, 'region_radius'::character varying])::"text"[])))
);

CREATE TABLE "app"."location_access_log_archive" (
    "log_id" bigint NOT NULL,
    "user_id" "uuid" NOT NULL,
    "occurred_at" timestamp with time zone NOT NULL,
    "endpoint" "text" NOT NULL,
    "purpose" character varying(64) NOT NULL,
    "lat" numeric(9,6),
    "lng" numeric(9,6),
    "request_id" "uuid" NOT NULL,
    "ip_hash" character varying(64) NOT NULL,
    "prev_hash" character varying(64) NOT NULL,
    "content_hash" character varying(64) NOT NULL,
    "retention_run_id" "uuid" NOT NULL,
    "archived_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE SEQUENCE "app"."location_access_log_archive_log_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "app"."location_access_log_archive_log_id_seq" OWNED BY "app"."location_access_log_archive"."log_id";

CREATE SEQUENCE "app"."location_access_log_log_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "app"."location_access_log_log_id_seq" OWNED BY "app"."location_access_log"."log_id";

CREATE TABLE "app"."location_audit_outbox" (
    "outbox_id" bigint NOT NULL,
    "user_id" "uuid" NOT NULL,
    "occurred_at" timestamp with time zone NOT NULL,
    "endpoint" "text" NOT NULL,
    "purpose" character varying(64) NOT NULL,
    "lat" numeric(9,6),
    "lng" numeric(9,6),
    "request_id" "uuid" NOT NULL,
    "ip_hash" character varying(64) NOT NULL,
    "processed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE SEQUENCE "app"."location_audit_outbox_outbox_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "app"."location_audit_outbox_outbox_id_seq" OWNED BY "app"."location_audit_outbox"."outbox_id";

CREATE TABLE "app"."mcp_tokens" (
    "token_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "token_hash" character varying(255) NOT NULL,
    "token_prefix" character varying(16) NOT NULL,
    "token_suffix" character varying(12) NOT NULL,
    "name" character varying(120) NOT NULL,
    "scopes" character varying(32)[] DEFAULT ARRAY['mcp:read'::character varying] NOT NULL,
    "expires_at" timestamp with time zone,
    "last_used_at" timestamp with time zone,
    "last_used_ip_hash" character varying(64),
    "revoked_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_mcp_tokens_ck_mcp_tokens_mcp_tokens_name_length" CHECK ((("char_length"(("name")::"text") >= 1) AND ("char_length"(("name")::"text") <= 120))),
    CONSTRAINT "ck_mcp_tokens_ck_mcp_tokens_mcp_tokens_scopes_allowed" CHECK ((("cardinality"("scopes") > 0) AND ("scopes" <@ ARRAY['mcp:read'::character varying])))
);

CREATE TABLE "app"."oauth_login_states" (
    "state_hash" character varying(128) NOT NULL,
    "nonce_hash" character varying(128),
    "pkce_code_verifier_hash" character varying(128),
    "provider" character varying(32) NOT NULL,
    "mode" character varying(16) DEFAULT 'login'::character varying NOT NULL,
    "return_to_path" character varying(255),
    "user_id" "uuid",
    "expires_at" timestamp with time zone NOT NULL,
    "consumed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_oauth_login_states_ck_oauth_login_states_mode" CHECK ((("mode")::"text" = ANY ((ARRAY['login'::character varying, 'link'::character varying])::"text"[]))),
    CONSTRAINT "ck_oauth_login_states_ck_oauth_login_states_provider" CHECK ((("provider")::"text" = ANY ((ARRAY['google'::character varying, 'naver'::character varying, 'kakao'::character varying])::"text"[])))
);

CREATE TABLE "app"."oauth_mobile_exchanges" (
    "code_hash" character varying(128) NOT NULL,
    "user_id" "uuid" NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "consumed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE TABLE "app"."rate_limit_buckets" (
    "bucket_hash" character varying(64) NOT NULL,
    "window_start" timestamp with time zone NOT NULL,
    "limit_name" character varying(80) NOT NULL,
    "count" integer DEFAULT 0 NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_rate_limit_buckets_ck_rate_limit_buckets_count_nonnegative" CHECK (("count" >= 0))
);

CREATE TABLE "app"."rate_limit_overrides" (
    "override_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "limit_name" character varying(80) NOT NULL,
    "bucket_hash" character varying(64) NOT NULL,
    "identity_kind" character varying(32) NOT NULL,
    "identity_fingerprint" character varying(64) NOT NULL,
    "identity_label" character varying(160) NOT NULL,
    "action" character varying(16) NOT NULL,
    "reason" "text" NOT NULL,
    "created_by_user_id" "uuid" NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "revoked_at" timestamp with time zone,
    "revoked_by_user_id" "uuid",
    "revoked_reason" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_rate_limit_overrides_ck_rate_limit_overrides_action_allowed" CHECK ((("action")::"text" = ANY ((ARRAY['blocked'::character varying, 'allowed'::character varying])::"text"[]))),
    CONSTRAINT "ck_rate_limit_overrides_ck_rate_limit_overrides_identit_98ea" CHECK ((("identity_kind")::"text" = ANY ((ARRAY['ip'::character varying, 'ip_email'::character varying, 'user'::character varying, 'shared_token'::character varying])::"text"[])))
);

CREATE TABLE "app"."resend_webhook_events" (
    "event_id" character varying(128) NOT NULL,
    "svix_id" character varying(128),
    "event_type" character varying(64) NOT NULL,
    "entity_ref" "uuid",
    "resend_email_id" character varying(128),
    "event_created_at" timestamp with time zone,
    "payload_summary" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "processed_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE TABLE "app"."retention_runs" (
    "run_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "mode" character varying(16) NOT NULL,
    "scope" character varying(32) DEFAULT 'all'::character varying NOT NULL,
    "status" character varying(32) NOT NULL,
    "candidate_snapshot" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "result" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "kill_switch_enabled" boolean DEFAULT false NOT NULL,
    "confirm_phrase" "text",
    "access_reason" "text" NOT NULL,
    "actor_user_id" "uuid" NOT NULL,
    "error_message" "text",
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_retention_runs_ck_retention_runs_mode" CHECK ((("mode")::"text" = ANY ((ARRAY['dry_run'::character varying, 'execute'::character varying])::"text"[]))),
    CONSTRAINT "ck_retention_runs_ck_retention_runs_scope" CHECK ((("scope")::"text" = ANY ((ARRAY['all'::character varying, 'pii'::character varying, 'location'::character varying])::"text"[]))),
    CONSTRAINT "ck_retention_runs_ck_retention_runs_status" CHECK ((("status")::"text" = ANY ((ARRAY['dry_run'::character varying, 'approved'::character varying, 'executing'::character varying, 'completed'::character varying, 'failed'::character varying, 'rolled_back'::character varying])::"text"[])))
);

CREATE TABLE "app"."security_incidents" (
    "incident_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "incident_type" character varying(64) NOT NULL,
    "severity" character varying(16) NOT NULL,
    "status" character varying(32) DEFAULT 'detected'::character varying NOT NULL,
    "source" character varying(64),
    "summary" character varying(240) NOT NULL,
    "details" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "affected_user_count" integer DEFAULT 0 NOT NULL,
    "notification_required" boolean DEFAULT false NOT NULL,
    "assigned_cpo_user_id" "uuid",
    "request_id" "uuid",
    "detected_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "acknowledged_at" timestamp with time zone,
    "resolved_at" timestamp with time zone,
    "notified_at" timestamp with time zone,
    "kisa_reported_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "cpo_review_due_at" timestamp with time zone DEFAULT ("now"() + '00:30:00'::interval) NOT NULL,
    "external_report_due_at" timestamp with time zone DEFAULT ("now"() + '72:00:00'::interval) NOT NULL,
    "cpo_notified_at" timestamp with time zone,
    "notification_decision_at" timestamp with time zone,
    "notification_payload_hash" character varying(64),
    "external_report_receipt_ref" character varying(160),
    "evidence_attachment_id" "uuid",
    CONSTRAINT "ck_security_incidents_ck_security_incidents_severity_allowed" CHECK ((("severity")::"text" = ANY ((ARRAY['low'::character varying, 'medium'::character varying, 'high'::character varying, 'critical'::character varying])::"text"[]))),
    CONSTRAINT "ck_security_incidents_ck_security_incidents_status_allowed" CHECK ((("status")::"text" = ANY ((ARRAY['detected'::character varying, 'triage'::character varying, 'notification_decision'::character varying, 'reported'::character varying, 'closed'::character varying])::"text"[])))
);

CREATE TABLE "app"."storage_settings" (
    "settings_id" integer DEFAULT 1 NOT NULL,
    "avatar_max_upload_bytes" bigint DEFAULT 2097152 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "attachment_max_upload_bytes" bigint DEFAULT 10485760 NOT NULL,
    "trip_attachment_quota_bytes" bigint DEFAULT 104857600 NOT NULL,
    "user_attachment_quota_bytes" bigint DEFAULT 1073741824 NOT NULL,
    CONSTRAINT "ck_storage_settings_ck_storage_settings_storage_setting_0010" CHECK (("settings_id" = 1)),
    CONSTRAINT "ck_storage_settings_ck_storage_settings_storage_setting_19d4" CHECK (("user_attachment_quota_bytes" > 0)),
    CONSTRAINT "ck_storage_settings_ck_storage_settings_storage_setting_2825" CHECK (("avatar_max_upload_bytes" > 0)),
    CONSTRAINT "ck_storage_settings_ck_storage_settings_storage_setting_3d91" CHECK (("trip_attachment_quota_bytes" > 0)),
    CONSTRAINT "ck_storage_settings_ck_storage_settings_storage_setting_a679" CHECK (("attachment_max_upload_bytes" > 0))
);

CREATE TABLE "app"."telegram_system_notification_outbox" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "category" character varying(64) NOT NULL,
    "payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "status" character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    "attempts" integer DEFAULT 0 NOT NULL,
    "last_error" "text",
    "scheduled_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "sent_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE TABLE "app"."telegram_targets" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "telegram_bot_token_ref" character varying(128) DEFAULT 'system'::character varying NOT NULL,
    "telegram_chat_id" character varying(64) NOT NULL,
    "telegram_chat_type" character varying(16),
    "telegram_message_thread_id" character varying(64),
    "telegram_label" character varying(80),
    "title_snapshot" character varying(255),
    "is_default" boolean DEFAULT false NOT NULL,
    "is_enabled" boolean DEFAULT true NOT NULL,
    "last_verified_at" timestamp with time zone,
    "last_send_status" character varying(32),
    "deleted_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_telegram_targets_ck_telegram_targets_telegram_target_9d4d" CHECK ((("char_length"(("telegram_chat_id")::"text") >= 1) AND ("char_length"(("telegram_chat_id")::"text") <= 64)))
);

CREATE TABLE "app"."trip_comments" (
    "comment_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "trip_id" "uuid" NOT NULL,
    "author_user_id" "uuid",
    "body" "text" NOT NULL,
    "target_type" character varying(16) DEFAULT 'trip'::character varying NOT NULL,
    "target_id" "uuid",
    "day_index" integer,
    "deleted_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_trip_comments_ck_trip_comments_body_len" CHECK ((("length"("body") >= 1) AND ("length"("body") <= 2000))),
    CONSTRAINT "ck_trip_comments_ck_trip_comments_target_type" CHECK ((("target_type")::"text" = ANY ((ARRAY['trip'::character varying, 'day'::character varying, 'poi'::character varying])::"text"[])))
);

CREATE TABLE "app"."trip_companions" (
    "companion_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "trip_id" "uuid" NOT NULL,
    "user_id" "uuid",
    "invited_email" character varying(320),
    "invited_nickname" character varying(80),
    "role" character varying(16) DEFAULT 'editor'::character varying NOT NULL,
    "invited_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "joined_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_trip_companions_ck_trip_companions_role" CHECK ((("role")::"text" = ANY ((ARRAY['co_owner'::character varying, 'editor'::character varying, 'viewer'::character varying])::"text"[]))),
    CONSTRAINT "ck_trip_companions_ck_trip_companions_target" CHECK ((("user_id" IS NOT NULL) OR ("invited_email" IS NOT NULL)))
);

CREATE TABLE "app"."trip_day_pois" (
    "attachment_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "trip_id" "uuid" NOT NULL,
    "day_index" integer NOT NULL,
    "sort_order" "text" NOT NULL COLLATE "pg_catalog"."C",
    "feature_id" "text",
    "feature_link_broken_at" timestamp with time zone,
    "feature_snapshot" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "custom_marker_color" character varying(16),
    "custom_marker_icon" character varying(64),
    "planned_arrival_at" timestamp with time zone,
    "planned_departure_at" timestamp with time zone,
    "user_note" "text",
    "budget_amount" numeric(12,2),
    "actual_amount" numeric(12,2),
    "currency" character varying(3) DEFAULT 'KRW'::character varying NOT NULL,
    "user_url" "text",
    "added_by_user_id" "uuid" NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "deleted_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "source" character varying(16),
    "external_ref" "jsonb",
    "cache_target_lon" numeric GENERATED ALWAYS AS ((COALESCE(("feature_snapshot" #>> '{coord,lon}'::"text"[]), ("feature_snapshot" ->> 'lon'::"text")))::numeric) STORED,
    "cache_target_lat" numeric GENERATED ALWAYS AS ((COALESCE(("feature_snapshot" #>> '{coord,lat}'::"text"[]), ("feature_snapshot" ->> 'lat'::"text")))::numeric) STORED,
    "cache_target_radius_km" numeric DEFAULT 5.000 NOT NULL,
    "cache_target_update_enabled" boolean DEFAULT true NOT NULL,
    "feature_uuid" "uuid",
    CONSTRAINT "ck_tdp_cache_lat_consistent" CHECK (((("feature_snapshot" #>> '{coord,lat}'::"text"[]) IS NULL) OR (("feature_snapshot" ->> 'lat'::"text") IS NULL) OR ((("feature_snapshot" #>> '{coord,lat}'::"text"[]))::numeric = (("feature_snapshot" ->> 'lat'::"text"))::numeric))),
    CONSTRAINT "ck_tdp_cache_lon_consistent" CHECK (((("feature_snapshot" #>> '{coord,lon}'::"text"[]) IS NULL) OR (("feature_snapshot" ->> 'lon'::"text") IS NULL) OR ((("feature_snapshot" #>> '{coord,lon}'::"text"[]))::numeric = (("feature_snapshot" ->> 'lon'::"text"))::numeric))),
    CONSTRAINT "ck_trip_day_pois_cache_coord_pair" CHECK ((("cache_target_lon" IS NULL) = ("cache_target_lat" IS NULL))),
    CONSTRAINT "ck_trip_day_pois_cache_lat_korea" CHECK ((("cache_target_lat" IS NULL) OR (("cache_target_lat" >= (33)::numeric) AND ("cache_target_lat" <= 39.5)))),
    CONSTRAINT "ck_trip_day_pois_cache_lon_korea" CHECK ((("cache_target_lon" IS NULL) OR (("cache_target_lon" >= (124)::numeric) AND ("cache_target_lon" <= (132)::numeric)))),
    CONSTRAINT "ck_trip_day_pois_cache_radius" CHECK ((("cache_target_radius_km" > (0)::numeric) AND ("cache_target_radius_km" <= (100)::numeric))),
    CONSTRAINT "ck_trip_day_pois_ck_trip_day_pois_actual_nonnegative" CHECK ((("actual_amount" IS NULL) OR ("actual_amount" >= (0)::numeric))),
    CONSTRAINT "ck_trip_day_pois_ck_trip_day_pois_budget_nonnegative" CHECK ((("budget_amount" IS NULL) OR ("budget_amount" >= (0)::numeric))),
    CONSTRAINT "ck_trip_day_pois_ck_trip_day_pois_currency" CHECK ((("currency")::"text" ~ '^[A-Z]{3}$'::"text")),
    CONSTRAINT "ck_trip_day_pois_ck_trip_day_pois_custom_marker_color" CHECK ((("custom_marker_color" IS NULL) OR (("custom_marker_color")::"text" ~ "similar_to_escape"('P-[0-9]{2}'::"text"))))
);

CREATE TABLE "app"."trip_day_rise_sets" (
    "trip_id" "uuid" NOT NULL,
    "day_index" integer NOT NULL,
    "locdate" "date",
    "reference_poi_id" "uuid",
    "reference_label" "text",
    "longitude" double precision,
    "latitude" double precision,
    "sunrise_at" timestamp with time zone,
    "sunset_at" timestamp with time zone,
    "moonrise_at" timestamp with time zone,
    "moonset_at" timestamp with time zone,
    "status" character varying(20) DEFAULT 'pending_date'::character varying NOT NULL,
    "stale" boolean DEFAULT false NOT NULL,
    "raw_payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "error" "jsonb",
    "fetched_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE TABLE "app"."trip_days" (
    "trip_id" "uuid" NOT NULL,
    "day_index" integer NOT NULL,
    "date" "date",
    "title" character varying(200),
    "note" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "marker_color" character varying(16),
    CONSTRAINT "ck_trip_days_ck_trip_days_day_index" CHECK (("day_index" >= 1))
);

CREATE TABLE "app"."trip_poi_rise_sets" (
    "poi_id" "uuid" NOT NULL,
    "locdate" "date",
    "longitude" double precision,
    "latitude" double precision,
    "sunrise_at" timestamp with time zone,
    "sunset_at" timestamp with time zone,
    "moonrise_at" timestamp with time zone,
    "moonset_at" timestamp with time zone,
    "status" character varying(20) DEFAULT 'pending_date'::character varying NOT NULL,
    "raw_payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "error" "jsonb",
    "fetched_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_trip_poi_rise_sets_ck_trip_poi_rise_sets_status" CHECK ((("status")::"text" = ANY ((ARRAY['pending_date'::character varying, 'pending_coord'::character varying, 'pending_fetch'::character varying, 'success'::character varying, 'failed'::character varying])::"text"[])))
);

CREATE TABLE "app"."trip_share_links" (
    "share_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "trip_id" "uuid" NOT NULL,
    "token_hash" character varying(128) NOT NULL,
    "created_by_user_id" "uuid" NOT NULL,
    "visibility" character varying(16) DEFAULT 'view_only'::character varying NOT NULL,
    "expires_at" timestamp with time zone,
    "revoked_at" timestamp with time zone,
    "last_used_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_trip_share_links_ck_trip_share_links_visibility" CHECK ((("visibility")::"text" = ANY ((ARRAY['view_only'::character varying, 'comment'::character varying, 'edit'::character varying])::"text"[])))
);

CREATE TABLE "app"."trip_telegram_targets" (
    "trip_id" "uuid" NOT NULL,
    "telegram_target_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE TABLE "app"."trips" (
    "trip_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "owner_user_id" "uuid" NOT NULL,
    "title" character varying(200) NOT NULL,
    "description" "text",
    "region_hint" character varying(120),
    "cover_attachment_id" "uuid",
    "start_date" "date",
    "end_date" "date",
    "fuel_types" character varying(16)[],
    "visibility" character varying(16) DEFAULT 'private'::character varying NOT NULL,
    "status" character varying(16) DEFAULT 'draft'::character varying NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "deleted_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "primary_region_code" character varying(10),
    "primary_region_source" character varying(16),
    CONSTRAINT "ck_trips_ck_trips_date_range" CHECK (((("start_date" IS NULL) AND ("end_date" IS NULL)) OR (("start_date" IS NOT NULL) AND ("end_date" IS NOT NULL) AND ("end_date" >= "start_date")))),
    CONSTRAINT "ck_trips_ck_trips_primary_region_code" CHECK ((("primary_region_code" IS NULL) OR (("primary_region_code")::"text" ~ '^[0-9]{2,10}$'::"text"))),
    CONSTRAINT "ck_trips_ck_trips_primary_region_pair" CHECK (((("primary_region_code" IS NULL) AND ("primary_region_source" IS NULL)) OR (("primary_region_code" IS NOT NULL) AND ("primary_region_source" IS NOT NULL)))),
    CONSTRAINT "ck_trips_ck_trips_primary_region_source" CHECK ((("primary_region_source" IS NULL) OR (("primary_region_source")::"text" = ANY ((ARRAY['manual'::character varying, 'poi_snapshot'::character varying, 'geocoded'::character varying])::"text"[])))),
    CONSTRAINT "ck_trips_ck_trips_status" CHECK ((("status")::"text" = ANY ((ARRAY['draft'::character varying, 'planned'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'archived'::character varying])::"text"[]))),
    CONSTRAINT "ck_trips_ck_trips_visibility" CHECK ((("visibility")::"text" = ANY ((ARRAY['private'::character varying, 'unlisted'::character varying, 'public'::character varying])::"text"[])))
);

CREATE TABLE "app"."user_consents" (
    "user_id" "uuid" NOT NULL,
    "consent_type" character varying(32) NOT NULL,
    "version" character varying(32) NOT NULL,
    "agreed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "withdrawn_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_user_consents_ck_user_consents_consent_type" CHECK ((("consent_type")::"text" = ANY ((ARRAY['tos'::character varying, 'privacy'::character varying, 'lbs_tos'::character varying, 'location_collection'::character varying, 'demographic_use'::character varying, 'marketing'::character varying])::"text"[])))
);

CREATE TABLE "app"."user_email_verifications" (
    "verification_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "token_hash" character varying(128) NOT NULL,
    "purpose" character varying(32) DEFAULT 'signup'::character varying NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "used_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_user_email_verifications_ck_user_email_verifications_purpose" CHECK ((("purpose")::"text" = ANY ((ARRAY['signup'::character varying, 'password_reset'::character varying, 'email_change'::character varying])::"text"[])))
);

CREATE TABLE "app"."user_oauth_identities" (
    "identity_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "provider" character varying(32) NOT NULL,
    "provider_user_id" character varying(255) NOT NULL,
    "provider_email" character varying(320),
    "provider_email_verified" boolean,
    "display_name_snapshot" character varying(120),
    "linked_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_login_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_user_oauth_identities_ck_user_oauth_identities_provider" CHECK ((("provider")::"text" = ANY ((ARRAY['google'::character varying, 'naver'::character varying, 'kakao'::character varying])::"text"[])))
);

CREATE TABLE "app"."user_sessions" (
    "session_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "session_token_hash" character varying(128) NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "revoked_at" timestamp with time zone,
    "user_agent" character varying(512),
    "ip_address" "inet",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

CREATE TABLE "app"."users" (
    "user_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "email" character varying(320) NOT NULL,
    "password_hash" character varying(255),
    "nickname" character varying(80),
    "avatar_url" character varying(1024),
    "avatar_kind" character varying(16) DEFAULT 'default'::character varying NOT NULL,
    "gender" character varying(16),
    "birth_year_month" character varying(6),
    "residence_sigungu_code" character varying(5),
    "status" character varying(32) DEFAULT 'pending_verification'::character varying NOT NULL,
    "roles" character varying(16)[] DEFAULT ARRAY['user'::character varying] NOT NULL,
    "email_verified_at" timestamp with time zone,
    "email_status" character varying(16) DEFAULT 'active'::character varying NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "deleted_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "access_token_version" integer DEFAULT 0 NOT NULL,
    "avatar_bucket" character varying(80),
    "avatar_storage_key" character varying(1024),
    "avatar_content_type" character varying(255),
    "avatar_byte_size" bigint,
    "avatar_updated_at" timestamp with time zone,
    "attachment_max_upload_bytes_override" bigint,
    "trip_attachment_quota_bytes_override" bigint,
    "user_attachment_quota_bytes_override" bigint,
    CONSTRAINT "ck_users_ck_users_access_token_version_nonnegative" CHECK (("access_token_version" >= 0)),
    CONSTRAINT "ck_users_ck_users_attachment_max_upload_bytes_override_positive" CHECK ((("attachment_max_upload_bytes_override" IS NULL) OR ("attachment_max_upload_bytes_override" > 0))),
    CONSTRAINT "ck_users_ck_users_email_status" CHECK ((("email_status")::"text" = ANY ((ARRAY['active'::character varying, 'bounced'::character varying, 'complained'::character varying, 'suppressed'::character varying])::"text"[]))),
    CONSTRAINT "ck_users_ck_users_gender" CHECK ((("gender" IS NULL) OR (("gender")::"text" = ANY ((ARRAY['female'::character varying, 'male'::character varying, 'non_binary'::character varying, 'no_answer'::character varying])::"text"[])))),
    CONSTRAINT "ck_users_ck_users_status" CHECK ((("status")::"text" = ANY ((ARRAY['pending_verification'::character varying, 'pending_profile'::character varying, 'active'::character varying, 'disabled'::character varying, 'pending_delete'::character varying, 'deleted'::character varying])::"text"[]))),
    CONSTRAINT "ck_users_ck_users_trip_attachment_quota_bytes_override_positive" CHECK ((("trip_attachment_quota_bytes_override" IS NULL) OR ("trip_attachment_quota_bytes_override" > 0))),
    CONSTRAINT "ck_users_ck_users_user_attachment_quota_bytes_override_positive" CHECK ((("user_attachment_quota_bytes_override" IS NULL) OR ("user_attachment_quota_bytes_override" > 0)))
);

ALTER TABLE ONLY "app"."admin_audit_log" ALTER COLUMN "log_id" SET DEFAULT "nextval"('"app"."admin_audit_log_log_id_seq"'::"regclass");

ALTER TABLE ONLY "app"."api_call_log" ALTER COLUMN "log_id" SET DEFAULT "nextval"('"app"."api_call_log_log_id_seq"'::"regclass");

ALTER TABLE ONLY "app"."data_integrity_violations" ALTER COLUMN "id" SET DEFAULT "nextval"('"app"."data_integrity_violations_id_seq"'::"regclass");

ALTER TABLE ONLY "app"."location_access_log" ALTER COLUMN "log_id" SET DEFAULT "nextval"('"app"."location_access_log_log_id_seq"'::"regclass");

ALTER TABLE ONLY "app"."location_access_log_archive" ALTER COLUMN "log_id" SET DEFAULT "nextval"('"app"."location_access_log_archive_log_id_seq"'::"regclass");

ALTER TABLE ONLY "app"."location_audit_outbox" ALTER COLUMN "outbox_id" SET DEFAULT "nextval"('"app"."location_audit_outbox_outbox_id_seq"'::"regclass");

ALTER TABLE ONLY "app"."admin_audit_log"
    ADD CONSTRAINT "pk_admin_audit_log" PRIMARY KEY ("log_id");

ALTER TABLE ONLY "app"."api_call_log"
    ADD CONSTRAINT "pk_api_call_log" PRIMARY KEY ("log_id");

ALTER TABLE ONLY "app"."category_mappings"
    ADD CONSTRAINT "pk_category_mappings" PRIMARY KEY ("category_key");

ALTER TABLE ONLY "app"."content_moderation_actions"
    ADD CONSTRAINT "pk_content_moderation_actions" PRIMARY KEY ("action_id");

ALTER TABLE ONLY "app"."content_reports"
    ADD CONSTRAINT "pk_content_reports" PRIMARY KEY ("report_id");

ALTER TABLE ONLY "app"."curated_plan_attachments"
    ADD CONSTRAINT "pk_curated_plan_attachments" PRIMARY KEY ("attachment_id");

ALTER TABLE ONLY "app"."curated_plan_pois"
    ADD CONSTRAINT "pk_curated_plan_pois" PRIMARY KEY ("curated_poi_id");

ALTER TABLE ONLY "app"."curated_trip_plans"
    ADD CONSTRAINT "pk_curated_trip_plans" PRIMARY KEY ("curated_plan_id");

ALTER TABLE ONLY "app"."data_integrity_violations"
    ADD CONSTRAINT "pk_data_integrity_violations" PRIMARY KEY ("id");

ALTER TABLE ONLY "app"."dsr_requests"
    ADD CONSTRAINT "pk_dsr_requests" PRIMARY KEY ("request_id");

ALTER TABLE ONLY "app"."email_queue"
    ADD CONSTRAINT "pk_email_queue" PRIMARY KEY ("email_id");

ALTER TABLE ONLY "app"."email_suppressions"
    ADD CONSTRAINT "pk_email_suppressions" PRIMARY KEY ("suppression_id");

ALTER TABLE ONLY "app"."feature_suggestions"
    ADD CONSTRAINT "pk_feature_suggestions" PRIMARY KEY ("request_id");

ALTER TABLE ONLY "app"."kasi_special_days"
    ADD CONSTRAINT "pk_kasi_special_days" PRIMARY KEY ("special_day_id");

ALTER TABLE ONLY "app"."ktm_cache_target_boundary_audits"
    ADD CONSTRAINT "pk_ktm_cache_target_boundary_audits" PRIMARY KEY ("transaction_id");

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "pk_ktm_cache_target_canary_runs" PRIMARY KEY ("run_id");

ALTER TABLE ONLY "app"."ktm_cache_target_commands"
    ADD CONSTRAINT "pk_ktm_cache_target_commands" PRIMARY KEY ("command_id");

ALTER TABLE ONLY "app"."ktm_cache_target_consumers"
    ADD CONSTRAINT "pk_ktm_cache_target_consumers" PRIMARY KEY ("consumer_id");

ALTER TABLE ONLY "app"."ktm_cache_target_event_claim_items"
    ADD CONSTRAINT "pk_ktm_cache_target_event_claim_items" PRIMARY KEY ("claim_id", "event_id");

ALTER TABLE ONLY "app"."ktm_cache_target_event_claims"
    ADD CONSTRAINT "pk_ktm_cache_target_event_claims" PRIMARY KEY ("claim_id");

ALTER TABLE ONLY "app"."ktm_cache_target_events"
    ADD CONSTRAINT "pk_ktm_cache_target_events" PRIMARY KEY ("event_id");

ALTER TABLE ONLY "app"."ktm_cache_target_heads"
    ADD CONSTRAINT "pk_ktm_cache_target_heads" PRIMARY KEY ("poi_id");

ALTER TABLE ONLY "app"."ktm_cache_target_reconciliation_expectations"
    ADD CONSTRAINT "pk_ktm_cache_target_reconciliation_expectations" PRIMARY KEY ("request_id");

ALTER TABLE ONLY "app"."ktm_cache_target_restore_fence_attempts"
    ADD CONSTRAINT "pk_ktm_cache_target_restore_fence_attempts" PRIMARY KEY ("idempotency_key");

ALTER TABLE ONLY "app"."ktm_curation_cutover_backfill_receipts"
    ADD CONSTRAINT "pk_ktm_curation_cutover_backfill_receipts" PRIMARY KEY ("receipt_id");

ALTER TABLE ONLY "app"."ktm_curation_cutover_mapping_receipt_items"
    ADD CONSTRAINT "pk_ktm_curation_cutover_mapping_receipt_items" PRIMARY KEY ("receipt_id", "legacy_curated_feature_id");

ALTER TABLE ONLY "app"."ktm_curation_cutover_mapping_receipts"
    ADD CONSTRAINT "pk_ktm_curation_cutover_mapping_receipts" PRIMARY KEY ("receipt_id");

ALTER TABLE ONLY "app"."ktm_curation_import_receipt_items"
    ADD CONSTRAINT "pk_ktm_curation_import_receipt_items" PRIMARY KEY ("receipt_id", "source_curation_item_id");

ALTER TABLE ONLY "app"."ktm_curation_import_receipts"
    ADD CONSTRAINT "pk_ktm_curation_import_receipts" PRIMARY KEY ("receipt_id");

ALTER TABLE ONLY "app"."ktm_feature_reference_reconciliation_applied_receipts"
    ADD CONSTRAINT "pk_ktm_feature_reference_reconciliation_applied_receipts" PRIMARY KEY ("event_id");

ALTER TABLE ONLY "app"."ktm_feature_reference_reconciliation_delivery_attempts"
    ADD CONSTRAINT "pk_ktm_feature_reference_reconciliation_delivery_attempts" PRIMARY KEY ("event_id", "attempt_sequence");

ALTER TABLE ONLY "app"."ktm_feature_reference_reconciliation_impacts"
    ADD CONSTRAINT "pk_ktm_feature_reference_reconciliation_impacts" PRIMARY KEY ("event_id", "impact_index");

ALTER TABLE ONLY "app"."location_access_log"
    ADD CONSTRAINT "pk_location_access_log" PRIMARY KEY ("log_id");

ALTER TABLE ONLY "app"."location_access_log_archive"
    ADD CONSTRAINT "pk_location_access_log_archive" PRIMARY KEY ("log_id");

ALTER TABLE ONLY "app"."location_audit_outbox"
    ADD CONSTRAINT "pk_location_audit_outbox" PRIMARY KEY ("outbox_id");

ALTER TABLE ONLY "app"."mcp_tokens"
    ADD CONSTRAINT "pk_mcp_tokens" PRIMARY KEY ("token_id");

ALTER TABLE ONLY "app"."oauth_login_states"
    ADD CONSTRAINT "pk_oauth_login_states" PRIMARY KEY ("state_hash");

ALTER TABLE ONLY "app"."oauth_mobile_exchanges"
    ADD CONSTRAINT "pk_oauth_mobile_exchanges" PRIMARY KEY ("code_hash");

ALTER TABLE ONLY "app"."rate_limit_buckets"
    ADD CONSTRAINT "pk_rate_limit_buckets" PRIMARY KEY ("bucket_hash", "window_start");

ALTER TABLE ONLY "app"."rate_limit_overrides"
    ADD CONSTRAINT "pk_rate_limit_overrides" PRIMARY KEY ("override_id");

ALTER TABLE ONLY "app"."resend_webhook_events"
    ADD CONSTRAINT "pk_resend_webhook_events" PRIMARY KEY ("event_id");

ALTER TABLE ONLY "app"."retention_runs"
    ADD CONSTRAINT "pk_retention_runs" PRIMARY KEY ("run_id");

ALTER TABLE ONLY "app"."security_incidents"
    ADD CONSTRAINT "pk_security_incidents" PRIMARY KEY ("incident_id");

ALTER TABLE ONLY "app"."storage_settings"
    ADD CONSTRAINT "pk_storage_settings" PRIMARY KEY ("settings_id");

ALTER TABLE ONLY "app"."telegram_system_notification_outbox"
    ADD CONSTRAINT "pk_telegram_system_notification_outbox" PRIMARY KEY ("id");

ALTER TABLE ONLY "app"."telegram_targets"
    ADD CONSTRAINT "pk_telegram_targets" PRIMARY KEY ("id");

ALTER TABLE ONLY "app"."trip_comments"
    ADD CONSTRAINT "pk_trip_comments" PRIMARY KEY ("comment_id");

ALTER TABLE ONLY "app"."trip_companions"
    ADD CONSTRAINT "pk_trip_companions" PRIMARY KEY ("companion_id");

ALTER TABLE ONLY "app"."trip_day_pois"
    ADD CONSTRAINT "pk_trip_day_pois" PRIMARY KEY ("attachment_id");

ALTER TABLE ONLY "app"."trip_day_rise_sets"
    ADD CONSTRAINT "pk_trip_day_rise_sets" PRIMARY KEY ("trip_id", "day_index");

ALTER TABLE ONLY "app"."trip_days"
    ADD CONSTRAINT "pk_trip_days" PRIMARY KEY ("trip_id", "day_index");

ALTER TABLE ONLY "app"."trip_poi_rise_sets"
    ADD CONSTRAINT "pk_trip_poi_rise_sets" PRIMARY KEY ("poi_id");

ALTER TABLE ONLY "app"."trip_share_links"
    ADD CONSTRAINT "pk_trip_share_links" PRIMARY KEY ("share_id");

ALTER TABLE ONLY "app"."trip_telegram_targets"
    ADD CONSTRAINT "pk_trip_telegram_targets" PRIMARY KEY ("trip_id", "telegram_target_id");

ALTER TABLE ONLY "app"."trips"
    ADD CONSTRAINT "pk_trips" PRIMARY KEY ("trip_id");

ALTER TABLE ONLY "app"."user_consents"
    ADD CONSTRAINT "pk_user_consents" PRIMARY KEY ("user_id", "consent_type", "version");

ALTER TABLE ONLY "app"."user_email_verifications"
    ADD CONSTRAINT "pk_user_email_verifications" PRIMARY KEY ("verification_id");

ALTER TABLE ONLY "app"."user_oauth_identities"
    ADD CONSTRAINT "pk_user_oauth_identities" PRIMARY KEY ("identity_id");

ALTER TABLE ONLY "app"."user_sessions"
    ADD CONSTRAINT "pk_user_sessions" PRIMARY KEY ("session_id");

ALTER TABLE ONLY "app"."users"
    ADD CONSTRAINT "pk_users" PRIMARY KEY ("user_id");

ALTER TABLE ONLY "app"."admin_audit_log"
    ADD CONSTRAINT "uq_admin_audit_log_prev_hash" UNIQUE ("prev_hash");

ALTER TABLE ONLY "app"."curated_plan_pois"
    ADD CONSTRAINT "uq_curated_plan_pois_curation_item" UNIQUE ("curated_plan_id", "source_curation_item_id");

ALTER TABLE ONLY "app"."curated_trip_plans"
    ADD CONSTRAINT "uq_curated_trip_plans_curation_identity" UNIQUE ("curated_plan_id", "source_curation_collection_id");

ALTER TABLE ONLY "app"."email_suppressions"
    ADD CONSTRAINT "uq_email_suppressions_email_hash" UNIQUE ("email_hash");

ALTER TABLE ONLY "app"."kasi_special_days"
    ADD CONSTRAINT "uq_kasi_special_days_identity" UNIQUE ("dataset", "sol_date", "sequence", "name");

ALTER TABLE ONLY "app"."ktm_cache_target_boundary_audits"
    ADD CONSTRAINT "uq_ktm_ct_boundary_cutover" UNIQUE ("cutover_id");

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "uq_ktm_ct_canary_delete_command" UNIQUE ("delete_command_id");

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "uq_ktm_ct_canary_delete_event" UNIQUE ("delete_event_id");

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "uq_ktm_ct_canary_final_evidence" UNIQUE ("run_id", "canary_provenance_sha256", "final_evidence_sha256");

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "uq_ktm_ct_canary_put_command" UNIQUE ("put_command_id");

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "uq_ktm_ct_canary_put_event" UNIQUE ("put_event_id");

ALTER TABLE ONLY "app"."ktm_cache_target_event_claim_items"
    ADD CONSTRAINT "uq_ktm_ct_claim_items_cursor" UNIQUE ("claim_id", "delivery_cursor");

ALTER TABLE ONLY "app"."ktm_cache_target_event_claim_items"
    ADD CONSTRAINT "uq_ktm_ct_claim_items_position" UNIQUE ("claim_id", "position");

ALTER TABLE ONLY "app"."ktm_cache_target_event_claim_items"
    ADD CONSTRAINT "uq_ktm_ct_claim_items_terminal_provenance" UNIQUE ("claim_id", "event_id", "delivery_cursor", "payload_fingerprint", "acked_at");

ALTER TABLE ONLY "app"."ktm_cache_target_event_claims"
    ADD CONSTRAINT "uq_ktm_ct_claims_terminal_provenance" UNIQUE ("claim_id", "consumer_id", "status", "acked_through_cursor", "completed_at");

ALTER TABLE ONLY "app"."ktm_cache_target_commands"
    ADD CONSTRAINT "uq_ktm_ct_commands_provenance" UNIQUE ("command_id", "poi_id", "source_generation", "payload_fingerprint");

ALTER TABLE ONLY "app"."ktm_cache_target_consumers"
    ADD CONSTRAINT "uq_ktm_ct_consumers_initial_boundary" UNIQUE ("consumer_id", "initial_cutover_id", "initial_reconciliation_request_id");

ALTER TABLE ONLY "app"."ktm_cache_target_event_claims"
    ADD CONSTRAINT "uq_ktm_ct_event_claims_lease_token" UNIQUE ("lease_token");

ALTER TABLE ONLY "app"."ktm_cache_target_events"
    ADD CONSTRAINT "uq_ktm_ct_events_provenance" UNIQUE ("event_id", "source_event_id", "source_generation", "source_payload_fingerprint", "payload_fingerprint");

ALTER TABLE ONLY "app"."ktm_cache_target_events"
    ADD CONSTRAINT "uq_ktm_ct_events_stream_order" UNIQUE ("external_system", "restore_epoch", "relay_order");

ALTER TABLE ONLY "app"."ktm_cache_target_heads"
    ADD CONSTRAINT "uq_ktm_ct_heads_system_key" UNIQUE ("external_system", "target_key");

ALTER TABLE ONLY "app"."ktm_cache_target_reconciliation_expectations"
    ADD CONSTRAINT "uq_ktm_ct_reconcile_expectations_boundary" UNIQUE ("request_id", "receipt_event_id", "status");

ALTER TABLE ONLY "app"."ktm_cache_target_reconciliation_expectations"
    ADD CONSTRAINT "uq_ktm_ct_reconcile_expectations_receipt" UNIQUE ("receipt_event_id");

ALTER TABLE ONLY "app"."ktm_cache_target_reconciliation_expectations"
    ADD CONSTRAINT "uq_ktm_ct_reconcile_expectations_snapshot" UNIQUE ("snapshot_id");

ALTER TABLE ONLY "app"."ktm_curation_cutover_backfill_receipts"
    ADD CONSTRAINT "uq_ktm_curation_cutover_backfill_receipts_actor_key" UNIQUE ("actor_admin_id", "idempotency_key");

ALTER TABLE ONLY "app"."ktm_curation_cutover_backfill_receipts"
    ADD CONSTRAINT "uq_ktm_curation_cutover_backfill_receipts_import" UNIQUE ("import_receipt_id");

ALTER TABLE ONLY "app"."ktm_curation_cutover_backfill_receipts"
    ADD CONSTRAINT "uq_ktm_curation_cutover_backfill_receipts_plan" UNIQUE ("curated_plan_id");

ALTER TABLE ONLY "app"."ktm_curation_cutover_mapping_receipt_items"
    ADD CONSTRAINT "uq_ktm_curation_cutover_mapping_receipt_items_curation_item" UNIQUE ("receipt_id", "curation_item_id");

ALTER TABLE ONLY "app"."ktm_curation_cutover_mapping_receipts"
    ADD CONSTRAINT "uq_ktm_curation_cutover_mapping_receipts_map_release" UNIQUE ("map_release_revision");

ALTER TABLE ONLY "app"."ktm_curation_cutover_mapping_receipts"
    ADD CONSTRAINT "uq_ktm_curation_cutover_mapping_receipts_map_root" UNIQUE ("map_release_revision", "mapping_root_version", "mapping_root");

ALTER TABLE ONLY "app"."ktm_curation_import_receipt_items"
    ADD CONSTRAINT "uq_ktm_curation_import_receipt_items_proof" UNIQUE ("receipt_id", "source_curation_collection_id", "source_curation_item_id", "source_curation_item_revision", "source_curation_item_etag", "feature_uuid");

ALTER TABLE ONLY "app"."ktm_curation_import_receipts"
    ADD CONSTRAINT "uq_ktm_curation_import_receipts_actor_key" UNIQUE ("actor_admin_id", "idempotency_key");

ALTER TABLE ONLY "app"."ktm_curation_import_receipts"
    ADD CONSTRAINT "uq_ktm_curation_import_receipts_collection" UNIQUE ("receipt_id", "source_curation_collection_id");

ALTER TABLE ONLY "app"."ktm_feature_reference_reconciliation_impacts"
    ADD CONSTRAINT "uq_ktm_frr_impact_target" UNIQUE ("event_id", "target_relation", "target_id");

ALTER TABLE ONLY "app"."ktm_feature_reference_reconciliation_applied_receipts"
    ADD CONSTRAINT "uq_ktm_frr_receipt_event_sequence" UNIQUE ("event_sequence");

ALTER TABLE ONLY "app"."ktm_feature_reference_reconciliation_applied_receipts"
    ADD CONSTRAINT "uq_ktm_frr_receipt_event_sha" UNIQUE ("event_sha256");

ALTER TABLE ONLY "app"."ktm_feature_reference_reconciliation_applied_receipts"
    ADD CONSTRAINT "uq_ktm_frr_receipt_sha" UNIQUE ("receipt_sha256");

ALTER TABLE ONLY "app"."mcp_tokens"
    ADD CONSTRAINT "uq_mcp_tokens_token_hash" UNIQUE ("token_hash");

ALTER TABLE ONLY "app"."resend_webhook_events"
    ADD CONSTRAINT "uq_resend_webhook_events_svix_id" UNIQUE ("svix_id");

ALTER TABLE ONLY "app"."trip_share_links"
    ADD CONSTRAINT "uq_trip_share_links_token_hash" UNIQUE ("token_hash");

ALTER TABLE ONLY "app"."user_email_verifications"
    ADD CONSTRAINT "uq_user_email_verifications_token_hash" UNIQUE ("token_hash");

ALTER TABLE ONLY "app"."user_oauth_identities"
    ADD CONSTRAINT "uq_user_oauth_identities_provider_subject" UNIQUE ("provider", "provider_user_id");

ALTER TABLE ONLY "app"."user_oauth_identities"
    ADD CONSTRAINT "uq_user_oauth_identities_user_provider" UNIQUE ("user_id", "provider");

ALTER TABLE ONLY "app"."user_sessions"
    ADD CONSTRAINT "uq_user_sessions_session_token_hash" UNIQUE ("session_token_hash");

ALTER TABLE ONLY "app"."users"
    ADD CONSTRAINT "uq_users_email" UNIQUE ("email");

CREATE INDEX "ix_admin_audit_log_occurred" ON "app"."admin_audit_log" USING "brin" ("occurred_at");

CREATE INDEX "ix_admin_audit_log_resource" ON "app"."admin_audit_log" USING "btree" ("resource_type", "resource_id", "occurred_at" DESC);

CREATE INDEX "ix_api_call_log_occurred" ON "app"."api_call_log" USING "brin" ("occurred_at");

CREATE INDEX "ix_api_call_log_provider_time" ON "app"."api_call_log" USING "btree" ("provider", "occurred_at" DESC);

CREATE INDEX "ix_category_mappings_updated_at" ON "app"."category_mappings" USING "btree" ("updated_at");

CREATE INDEX "ix_content_moderation_actions_actor_created" ON "app"."content_moderation_actions" USING "btree" ("actor_user_id", "created_at" DESC) WHERE ("actor_user_id" IS NOT NULL);

CREATE INDEX "ix_content_moderation_actions_report_created" ON "app"."content_moderation_actions" USING "btree" ("report_id", "created_at" DESC);

CREATE INDEX "ix_content_reports_open" ON "app"."content_reports" USING "btree" ("created_at") WHERE (("status")::"text" = ANY ((ARRAY['received'::character varying, 'reviewing'::character varying, 'appealed'::character varying])::"text"[]));

CREATE INDEX "ix_content_reports_owner_created" ON "app"."content_reports" USING "btree" ("target_owner_user_id", "created_at" DESC) WHERE ("target_owner_user_id" IS NOT NULL);

CREATE INDEX "ix_content_reports_reporter_created" ON "app"."content_reports" USING "btree" ("reporter_user_id", "created_at" DESC) WHERE ("reporter_user_id" IS NOT NULL);

CREATE INDEX "ix_content_reports_status_created" ON "app"."content_reports" USING "btree" ("status", "created_at" DESC);

CREATE INDEX "ix_content_reports_target" ON "app"."content_reports" USING "btree" ("target_type", "target_id");

CREATE INDEX "ix_content_reports_trip_created" ON "app"."content_reports" USING "btree" ("target_trip_id", "created_at" DESC) WHERE ("target_trip_id" IS NOT NULL);

CREATE INDEX "ix_curated_plan_attachments_curated_plan" ON "app"."curated_plan_attachments" USING "btree" ("curated_plan_id", "sort_order") WHERE (("curated_plan_id" IS NOT NULL) AND ("deleted_at" IS NULL));

CREATE INDEX "ix_curated_plan_attachments_curated_poi" ON "app"."curated_plan_attachments" USING "btree" ("curated_poi_id", "sort_order") WHERE (("curated_poi_id" IS NOT NULL) AND ("deleted_at" IS NULL));

CREATE INDEX "ix_curated_plan_attachments_storage_key" ON "app"."curated_plan_attachments" USING "btree" ("bucket", "storage_key");

CREATE INDEX "ix_curated_plan_attachments_trip" ON "app"."curated_plan_attachments" USING "btree" ("trip_id", "sort_order") WHERE (("trip_id" IS NOT NULL) AND ("deleted_at" IS NULL));

CREATE INDEX "ix_curated_plan_attachments_trip_day" ON "app"."curated_plan_attachments" USING "btree" ("trip_id", "trip_day_index", "sort_order") WHERE (("trip_id" IS NOT NULL) AND ("trip_day_index" IS NOT NULL) AND ("deleted_at" IS NULL));

CREATE INDEX "ix_curated_plan_attachments_trip_poi" ON "app"."curated_plan_attachments" USING "btree" ("trip_poi_id", "sort_order") WHERE (("trip_poi_id" IS NOT NULL) AND ("deleted_at" IS NULL));

CREATE INDEX "ix_curated_plan_pois_feature" ON "app"."curated_plan_pois" USING "btree" ("feature_id") WHERE (("deleted_at" IS NULL) AND ("feature_id" IS NOT NULL));

CREATE INDEX "ix_curated_plan_pois_plan_day" ON "app"."curated_plan_pois" USING "btree" ("curated_plan_id", "day_index") WHERE ("deleted_at" IS NULL);

CREATE INDEX "ix_curated_plan_pois_source_item" ON "app"."curated_plan_pois" USING "btree" ("source_curated_feature_id", "source_curated_feature_item_id") WHERE (("deleted_at" IS NULL) AND ("source_curated_feature_id" IS NOT NULL) AND ("source_curated_feature_item_id" IS NOT NULL));

CREATE INDEX "ix_curated_trip_plans_category" ON "app"."curated_trip_plans" USING "btree" ("category", "updated_at" DESC);

CREATE INDEX "ix_curated_trip_plans_published" ON "app"."curated_trip_plans" USING "btree" ("is_published", "updated_at" DESC);

CREATE INDEX "ix_data_integrity_violations_entity" ON "app"."data_integrity_violations" USING "btree" ("entity_kind", "entity_id");

CREATE INDEX "ix_data_integrity_violations_status_severity_detected" ON "app"."data_integrity_violations" USING "btree" ("status", "severity", "detected_at");

CREATE INDEX "ix_dsr_requests_assigned_cpo" ON "app"."dsr_requests" USING "btree" ("assigned_cpo_user_id") WHERE ("assigned_cpo_user_id" IS NOT NULL);

CREATE INDEX "ix_dsr_requests_open_due" ON "app"."dsr_requests" USING "btree" ("due_at") WHERE (("status")::"text" = ANY ((ARRAY['received'::character varying, 'identity_check'::character varying, 'processing'::character varying])::"text"[]));

CREATE INDEX "ix_dsr_requests_status_due" ON "app"."dsr_requests" USING "btree" ("status", "due_at");

CREATE INDEX "ix_dsr_requests_type_status" ON "app"."dsr_requests" USING "btree" ("request_type", "status");

CREATE INDEX "ix_dsr_requests_user_created" ON "app"."dsr_requests" USING "btree" ("user_id", "created_at" DESC);

CREATE INDEX "ix_email_queue_pending" ON "app"."email_queue" USING "btree" ("scheduled_at") WHERE (("status")::"text" = 'pending'::"text");

CREATE INDEX "ix_email_queue_provider_event" ON "app"."email_queue" USING "btree" ("last_provider_event_id");

CREATE INDEX "ix_email_queue_to_email" ON "app"."email_queue" USING "btree" ("to_email");

CREATE INDEX "ix_email_suppressions_active_hash" ON "app"."email_suppressions" USING "btree" ("email_hash") WHERE ("released_at" IS NULL);

CREATE INDEX "ix_email_suppressions_reason" ON "app"."email_suppressions" USING "btree" ("reason") WHERE ("released_at" IS NULL);

CREATE INDEX "ix_feature_suggestions_requester_created_at" ON "app"."feature_suggestions" USING "btree" ("requester_user_id", "created_at");

CREATE INDEX "ix_feature_suggestions_status_created_at" ON "app"."feature_suggestions" USING "btree" ("status", "created_at");

CREATE INDEX "ix_kasi_special_days_dataset_date" ON "app"."kasi_special_days" USING "btree" ("dataset", "sol_date");

CREATE INDEX "ix_kasi_special_days_sol_date" ON "app"."kasi_special_days" USING "btree" ("sol_date");

CREATE INDEX "ix_ktm_ct_claim_items_ack_gap" ON "app"."ktm_cache_target_event_claim_items" USING "btree" ("claim_id", "position") WHERE ("acked_at" IS NULL);

CREATE INDEX "ix_ktm_ct_commands_due" ON "app"."ktm_cache_target_commands" USING "btree" ("available_at", "command_id") WHERE (("status")::"text" = ANY ((ARRAY['pending'::character varying, 'leased'::character varying])::"text"[]));

CREATE INDEX "ix_ktm_ct_commands_lease" ON "app"."ktm_cache_target_commands" USING "btree" ("lease_until", "command_id") WHERE (("status")::"text" = 'leased'::"text");

CREATE INDEX "ix_ktm_ct_event_claims_lease" ON "app"."ktm_cache_target_event_claims" USING "btree" ("lease_expires_at", "claim_id") WHERE (("status")::"text" = 'active'::"text");

CREATE INDEX "ix_ktm_ct_events_epoch_relay" ON "app"."ktm_cache_target_events" USING "btree" ("restore_epoch", "relay_order");

CREATE INDEX "ix_ktm_ct_reconcile_expectations_pending" ON "app"."ktm_cache_target_reconciliation_expectations" USING "btree" ("external_system", "restore_epoch", "created_at") WHERE (("status")::"text" = 'pending'::"text");

CREATE INDEX "ix_ktm_curation_cutover_backfill_receipts_mapping_created" ON "app"."ktm_curation_cutover_backfill_receipts" USING "btree" ("mapping_receipt_id", "created_at");

CREATE INDEX "ix_ktm_curation_cutover_mapping_receipts_actor_created" ON "app"."ktm_curation_cutover_mapping_receipts" USING "btree" ("actor_admin_id", "created_at");

CREATE INDEX "ix_ktm_curation_import_receipts_collection_created" ON "app"."ktm_curation_import_receipts" USING "btree" ("source_curation_collection_id", "created_at");

CREATE INDEX "ix_ktm_frr_attempt_event_observed" ON "app"."ktm_feature_reference_reconciliation_delivery_attempts" USING "btree" ("event_id", "observed_at");

CREATE INDEX "ix_ktm_frr_impact_target" ON "app"."ktm_feature_reference_reconciliation_impacts" USING "btree" ("target_relation", "target_id");

CREATE INDEX "ix_location_access_log_archive_occurred" ON "app"."location_access_log_archive" USING "brin" ("occurred_at");

CREATE INDEX "ix_location_access_log_archive_run" ON "app"."location_access_log_archive" USING "btree" ("retention_run_id", "log_id" DESC);

CREATE INDEX "ix_location_access_log_archive_user_time" ON "app"."location_access_log_archive" USING "btree" ("user_id", "occurred_at" DESC);

CREATE INDEX "ix_location_access_log_occurred" ON "app"."location_access_log" USING "brin" ("occurred_at");

CREATE INDEX "ix_location_access_log_user_time" ON "app"."location_access_log" USING "btree" ("user_id", "occurred_at" DESC);

CREATE INDEX "ix_location_audit_outbox_pending" ON "app"."location_audit_outbox" USING "btree" ("outbox_id") WHERE ("processed_at" IS NULL);

CREATE INDEX "ix_mcp_tokens_expires_at" ON "app"."mcp_tokens" USING "btree" ("expires_at");

CREATE INDEX "ix_mcp_tokens_user_active" ON "app"."mcp_tokens" USING "btree" ("user_id", "updated_at" DESC) WHERE ("revoked_at" IS NULL);

CREATE INDEX "ix_mcp_tokens_user_created_at" ON "app"."mcp_tokens" USING "btree" ("user_id", "created_at");

CREATE INDEX "ix_oauth_login_states_active" ON "app"."oauth_login_states" USING "btree" ("expires_at") WHERE ("consumed_at" IS NULL);

CREATE INDEX "ix_oauth_mobile_exchanges_expires_at" ON "app"."oauth_mobile_exchanges" USING "btree" ("expires_at");

CREATE INDEX "ix_rate_limit_buckets_expires_at" ON "app"."rate_limit_buckets" USING "btree" ("expires_at");

CREATE INDEX "ix_rate_limit_buckets_limit_updated" ON "app"."rate_limit_buckets" USING "btree" ("limit_name", "updated_at");

CREATE INDEX "ix_rate_limit_overrides_bucket_active" ON "app"."rate_limit_overrides" USING "btree" ("bucket_hash", "limit_name", "expires_at");

CREATE INDEX "ix_rate_limit_overrides_created_at" ON "app"."rate_limit_overrides" USING "btree" ("created_at");

CREATE INDEX "ix_rate_limit_overrides_expires_at" ON "app"."rate_limit_overrides" USING "btree" ("expires_at");

CREATE INDEX "ix_resend_webhook_events_entity" ON "app"."resend_webhook_events" USING "btree" ("entity_ref", "processed_at");

CREATE INDEX "ix_resend_webhook_events_processed" ON "app"."resend_webhook_events" USING "btree" ("processed_at");

CREATE INDEX "ix_retention_runs_created_at" ON "app"."retention_runs" USING "btree" ("created_at" DESC);

CREATE INDEX "ix_retention_runs_status" ON "app"."retention_runs" USING "btree" ("status", "created_at" DESC);

CREATE INDEX "ix_security_incidents_external_report_due_at" ON "app"."security_incidents" USING "btree" ("external_report_due_at") WHERE (("status")::"text" <> 'closed'::"text");

CREATE INDEX "ix_security_incidents_severity_detected_at" ON "app"."security_incidents" USING "btree" ("severity", "detected_at");

CREATE INDEX "ix_security_incidents_status_detected_at" ON "app"."security_incidents" USING "btree" ("status", "detected_at");

CREATE INDEX "ix_telegram_outbox_pending" ON "app"."telegram_system_notification_outbox" USING "btree" ("scheduled_at") WHERE (("status")::"text" = 'pending'::"text");

CREATE INDEX "ix_telegram_targets_user_active" ON "app"."telegram_targets" USING "btree" ("user_id", "created_at" DESC) WHERE ("deleted_at" IS NULL);

CREATE INDEX "ix_trip_comments_author" ON "app"."trip_comments" USING "btree" ("author_user_id") WHERE ("author_user_id" IS NOT NULL);

CREATE INDEX "ix_trip_comments_trip_created_at" ON "app"."trip_comments" USING "btree" ("trip_id", "created_at") WHERE ("deleted_at" IS NULL);

CREATE INDEX "ix_trip_companions_trip" ON "app"."trip_companions" USING "btree" ("trip_id");

CREATE INDEX "ix_trip_companions_user" ON "app"."trip_companions" USING "btree" ("user_id") WHERE ("user_id" IS NOT NULL);

CREATE INDEX "ix_trip_day_pois_external_ref" ON "app"."trip_day_pois" USING "btree" ((("external_ref" ->> 'provider'::"text")), (("external_ref" ->> 'external_id'::"text"))) WHERE (("external_ref" IS NOT NULL) AND ("feature_id" IS NULL) AND ("deleted_at" IS NULL));

CREATE INDEX "ix_trip_day_pois_feature" ON "app"."trip_day_pois" USING "btree" ("feature_id");

CREATE INDEX "ix_trip_day_pois_trip_day" ON "app"."trip_day_pois" USING "btree" ("trip_id", "day_index") WHERE ("deleted_at" IS NULL);

CREATE INDEX "ix_trip_day_rise_sets_fillable" ON "app"."trip_day_rise_sets" USING "btree" ("status") WHERE ((("status")::"text" = 'pending_fetch'::"text") OR "stale");

CREATE INDEX "ix_trip_poi_rise_sets_locdate" ON "app"."trip_poi_rise_sets" USING "btree" ("locdate");

CREATE INDEX "ix_trip_poi_rise_sets_pending_fetch" ON "app"."trip_poi_rise_sets" USING "btree" ("locdate") WHERE (("status")::"text" = 'pending_fetch'::"text");

CREATE INDEX "ix_trip_share_links_trip_active" ON "app"."trip_share_links" USING "btree" ("trip_id") WHERE ("revoked_at" IS NULL);

CREATE INDEX "ix_trip_telegram_targets_target" ON "app"."trip_telegram_targets" USING "btree" ("telegram_target_id");

CREATE INDEX "ix_trips_owner_status" ON "app"."trips" USING "btree" ("owner_user_id", "status", "start_date") WHERE ("deleted_at" IS NULL);

CREATE INDEX "ix_trips_primary_region" ON "app"."trips" USING "btree" ("primary_region_code") WHERE (("primary_region_code" IS NOT NULL) AND ("deleted_at" IS NULL));

CREATE INDEX "ix_user_email_verifications_user_id" ON "app"."user_email_verifications" USING "btree" ("user_id");

CREATE INDEX "ix_user_sessions_user_active" ON "app"."user_sessions" USING "btree" ("user_id", "expires_at") WHERE ("revoked_at" IS NULL);

CREATE INDEX "ix_users_status" ON "app"."users" USING "btree" ("status");

CREATE UNIQUE INDEX "uq_curated_plan_pois_plan_day_sort" ON "app"."curated_plan_pois" USING "btree" ("curated_plan_id", "day_index", "sort_order") WHERE ("deleted_at" IS NULL);

CREATE UNIQUE INDEX "uq_curated_trip_plans_curation_collection_active" ON "app"."curated_trip_plans" USING "btree" ("source_system", "source_curation_collection_id") WHERE (("deleted_at" IS NULL) AND (("source_system")::"text" = 'kor-travel-map'::"text") AND ("source_curation_collection_id" IS NOT NULL));

CREATE UNIQUE INDEX "uq_curated_trip_plans_slug_active" ON "app"."curated_trip_plans" USING "btree" ("slug") WHERE ("deleted_at" IS NULL);

CREATE UNIQUE INDEX "uq_curated_trip_plans_source_active" ON "app"."curated_trip_plans" USING "btree" ("source_system", "source_curated_feature_id") WHERE (("deleted_at" IS NULL) AND ("source_system" IS NOT NULL) AND ("source_curated_feature_id" IS NOT NULL));

CREATE UNIQUE INDEX "uq_data_integrity_violations_active_rule_entity" ON "app"."data_integrity_violations" USING "btree" ("rule_key", "entity_kind", "entity_id") WHERE ((("status")::"text" = ANY ((ARRAY['open'::character varying, 'acknowledged'::character varying])::"text"[])) AND ("resolved_at" IS NULL));

CREATE UNIQUE INDEX "uq_feature_suggestions_active_external_ref" ON "app"."feature_suggestions" USING "btree" ((("external_ref" ->> 'provider'::"text")), (("external_ref" ->> 'external_id'::"text"))) WHERE (("external_ref" IS NOT NULL) AND (("status")::"text" = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'added'::character varying])::"text"[])));

CREATE UNIQUE INDEX "uq_ktm_ct_canary_running_target" ON "app"."ktm_cache_target_canary_runs" USING "btree" ("target_poi_id") WHERE ("status" = 'running'::"text");

CREATE UNIQUE INDEX "uq_ktm_ct_commands_state_generation" ON "app"."ktm_cache_target_commands" USING "btree" ("poi_id", "source_generation", "operation") WHERE (("operation")::"text" = ANY ((ARRAY['put'::character varying, 'delete'::character varying])::"text"[]));

CREATE UNIQUE INDEX "uq_ktm_ct_events_target_sequence" ON "app"."ktm_cache_target_events" USING "btree" ("external_system", "target_key", "restore_epoch", "source_generation", "target_sequence") WHERE ("target_key" IS NOT NULL);

CREATE UNIQUE INDEX "uq_trip_companions_trip_invited" ON "app"."trip_companions" USING "btree" ("trip_id", "lower"(("invited_email")::"text")) WHERE ("invited_email" IS NOT NULL);

CREATE UNIQUE INDEX "uq_trip_companions_trip_user" ON "app"."trip_companions" USING "btree" ("trip_id", "user_id") WHERE ("user_id" IS NOT NULL);

CREATE UNIQUE INDEX "uq_trip_day_pois_day_sort" ON "app"."trip_day_pois" USING "btree" ("trip_id", "day_index", "sort_order") WHERE ("deleted_at" IS NULL);

CREATE UNIQUE INDEX "ux_feature_suggestions_user_pending_dedup" ON "app"."feature_suggestions" USING "btree" ("requester_user_id", "type", "kind", "lower"(("name")::"text"), "lng", "lat", COALESCE("target_feature_id", ''::"text")) WHERE (("status")::"text" = 'pending'::"text");

CREATE TRIGGER "trg_admin_audit_log_append_only" BEFORE DELETE OR UPDATE ON "app"."admin_audit_log" FOR EACH ROW EXECUTE FUNCTION "app"."audit_log_append_only"();

CREATE TRIGGER "trg_category_mappings_touch_updated_at" BEFORE UPDATE ON "app"."category_mappings" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_content_reports_touch_updated_at" BEFORE UPDATE ON "app"."content_reports" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_curated_trip_plans_touch_updated_at" BEFORE UPDATE ON "app"."curated_trip_plans" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_dsr_requests_touch_updated_at" BEFORE UPDATE ON "app"."dsr_requests" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_email_queue_touch_updated_at" BEFORE UPDATE ON "app"."email_queue" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_email_suppressions_touch_updated_at" BEFORE UPDATE ON "app"."email_suppressions" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_feature_suggestions_touch_updated_at" BEFORE UPDATE ON "app"."feature_suggestions" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_kasi_special_days_touch_updated_at" BEFORE UPDATE ON "app"."kasi_special_days" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_ktm_cache_target_commands_touch" BEFORE UPDATE ON "app"."ktm_cache_target_commands" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_ktm_cache_target_consumers_touch" BEFORE UPDATE ON "app"."ktm_cache_target_consumers" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_ktm_cache_target_heads_touch" BEFORE UPDATE ON "app"."ktm_cache_target_heads" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_ktm_ct_boundary_audit_row_immutable" BEFORE DELETE OR UPDATE ON "app"."ktm_cache_target_boundary_audits" FOR EACH ROW EXECUTE FUNCTION "app"."reject_ktm_cache_target_boundary_audit_mutation"();

CREATE TRIGGER "trg_ktm_ct_boundary_audit_truncate_immutable" BEFORE TRUNCATE ON "app"."ktm_cache_target_boundary_audits" FOR EACH STATEMENT EXECUTE FUNCTION "app"."reject_ktm_cache_target_boundary_audit_mutation"();

CREATE TRIGGER "trg_ktm_ct_restore_attempt_row_guard" BEFORE INSERT OR DELETE OR UPDATE ON "app"."ktm_cache_target_restore_fence_attempts" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_cache_target_restore_fence_attempt"();

CREATE TRIGGER "trg_ktm_ct_restore_attempt_truncate_guard" BEFORE TRUNCATE ON "app"."ktm_cache_target_restore_fence_attempts" FOR EACH STATEMENT EXECUTE FUNCTION "app"."guard_ktm_cache_target_restore_fence_attempt"();

CREATE TRIGGER "trg_ktm_curation_cutover_backfill_receipts_guard" BEFORE INSERT OR DELETE OR UPDATE ON "app"."ktm_curation_cutover_backfill_receipts" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_curation_cutover_backfill_receipt"();

CREATE TRIGGER "trg_ktm_curation_cutover_backfill_receipts_truncate_guard" BEFORE TRUNCATE ON "app"."ktm_curation_cutover_backfill_receipts" FOR EACH STATEMENT EXECUTE FUNCTION "app"."guard_ktm_curation_cutover_backfill_receipt"();

CREATE TRIGGER "trg_ktm_curation_cutover_mapping_receipt_items_guard" BEFORE INSERT OR DELETE OR UPDATE ON "app"."ktm_curation_cutover_mapping_receipt_items" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_curation_cutover_mapping_receipt_item"();

CREATE TRIGGER "trg_ktm_curation_cutover_mapping_receipt_items_truncate_guard" BEFORE TRUNCATE ON "app"."ktm_curation_cutover_mapping_receipt_items" FOR EACH STATEMENT EXECUTE FUNCTION "app"."guard_ktm_curation_cutover_mapping_receipt_item"();

CREATE TRIGGER "trg_ktm_curation_cutover_mapping_receipts_guard" BEFORE INSERT OR DELETE OR UPDATE ON "app"."ktm_curation_cutover_mapping_receipts" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_curation_cutover_mapping_receipt"();

CREATE TRIGGER "trg_ktm_curation_cutover_mapping_receipts_truncate_guard" BEFORE TRUNCATE ON "app"."ktm_curation_cutover_mapping_receipts" FOR EACH STATEMENT EXECUTE FUNCTION "app"."guard_ktm_curation_cutover_mapping_receipt"();

CREATE TRIGGER "trg_ktm_curation_import_receipt_item_row_guard" BEFORE INSERT OR DELETE OR UPDATE ON "app"."ktm_curation_import_receipt_items" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_curation_import_receipt_item"();

CREATE TRIGGER "trg_ktm_curation_import_receipt_item_truncate_guard" BEFORE TRUNCATE ON "app"."ktm_curation_import_receipt_items" FOR EACH STATEMENT EXECUTE FUNCTION "app"."guard_ktm_curation_import_receipt_item"();

CREATE TRIGGER "trg_ktm_curation_import_receipt_response_guard" BEFORE UPDATE ON "app"."ktm_curation_import_receipts" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_curation_import_receipt_response"();

CREATE TRIGGER "trg_ktm_curation_import_receipt_row_guard" BEFORE INSERT OR DELETE OR UPDATE ON "app"."ktm_curation_import_receipts" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_curation_import_receipt"();

CREATE TRIGGER "trg_ktm_curation_import_receipt_truncate_guard" BEFORE TRUNCATE ON "app"."ktm_curation_import_receipts" FOR EACH STATEMENT EXECUTE FUNCTION "app"."guard_ktm_curation_import_receipt"();

CREATE TRIGGER "trg_ktm_feature_reference_reconciliation_applied_receipts_appen" BEFORE INSERT OR DELETE OR UPDATE ON "app"."ktm_feature_reference_reconciliation_applied_receipts" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_feature_reference_reconciliation_append_only"();

ALTER TABLE "app"."ktm_feature_reference_reconciliation_applied_receipts" ENABLE ALWAYS TRIGGER "trg_ktm_feature_reference_reconciliation_applied_receipts_appen";

CREATE TRIGGER "trg_ktm_feature_reference_reconciliation_applied_receipts_trunc" BEFORE TRUNCATE ON "app"."ktm_feature_reference_reconciliation_applied_receipts" FOR EACH STATEMENT EXECUTE FUNCTION "app"."guard_ktm_feature_reference_reconciliation_append_only"();

ALTER TABLE "app"."ktm_feature_reference_reconciliation_applied_receipts" ENABLE ALWAYS TRIGGER "trg_ktm_feature_reference_reconciliation_applied_receipts_trunc";

CREATE TRIGGER "trg_ktm_feature_reference_reconciliation_delivery_attempts_appe" BEFORE INSERT OR DELETE OR UPDATE ON "app"."ktm_feature_reference_reconciliation_delivery_attempts" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_feature_reference_reconciliation_append_only"();

ALTER TABLE "app"."ktm_feature_reference_reconciliation_delivery_attempts" ENABLE ALWAYS TRIGGER "trg_ktm_feature_reference_reconciliation_delivery_attempts_appe";

CREATE TRIGGER "trg_ktm_feature_reference_reconciliation_delivery_attempts_trun" BEFORE TRUNCATE ON "app"."ktm_feature_reference_reconciliation_delivery_attempts" FOR EACH STATEMENT EXECUTE FUNCTION "app"."guard_ktm_feature_reference_reconciliation_append_only"();

ALTER TABLE "app"."ktm_feature_reference_reconciliation_delivery_attempts" ENABLE ALWAYS TRIGGER "trg_ktm_feature_reference_reconciliation_delivery_attempts_trun";

CREATE TRIGGER "trg_ktm_feature_reference_reconciliation_impacts_append_only" BEFORE INSERT OR DELETE OR UPDATE ON "app"."ktm_feature_reference_reconciliation_impacts" FOR EACH ROW EXECUTE FUNCTION "app"."guard_ktm_feature_reference_reconciliation_append_only"();

ALTER TABLE "app"."ktm_feature_reference_reconciliation_impacts" ENABLE ALWAYS TRIGGER "trg_ktm_feature_reference_reconciliation_impacts_append_only";

CREATE TRIGGER "trg_ktm_feature_reference_reconciliation_impacts_truncate_appen" BEFORE TRUNCATE ON "app"."ktm_feature_reference_reconciliation_impacts" FOR EACH STATEMENT EXECUTE FUNCTION "app"."guard_ktm_feature_reference_reconciliation_append_only"();

ALTER TABLE "app"."ktm_feature_reference_reconciliation_impacts" ENABLE ALWAYS TRIGGER "trg_ktm_feature_reference_reconciliation_impacts_truncate_appen";

CREATE TRIGGER "trg_location_access_log_append_only" BEFORE DELETE OR UPDATE ON "app"."location_access_log" FOR EACH ROW EXECUTE FUNCTION "app"."audit_log_append_only"();

CREATE TRIGGER "trg_mcp_tokens_touch_updated_at" BEFORE UPDATE ON "app"."mcp_tokens" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_retention_runs_touch_updated_at" BEFORE UPDATE ON "app"."retention_runs" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_security_incidents_touch_updated_at" BEFORE UPDATE ON "app"."security_incidents" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_telegram_targets_touch_updated_at" BEFORE UPDATE ON "app"."telegram_targets" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_trip_comments_touch_updated_at" BEFORE UPDATE ON "app"."trip_comments" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_trip_day_pois_cache_target_cutover_fence" BEFORE INSERT OR DELETE OR UPDATE ON "app"."trip_day_pois" FOR EACH STATEMENT EXECUTE FUNCTION "app"."lock_ktm_cache_target_source_cutover"();

CREATE TRIGGER "trg_trip_day_pois_cache_target_source" AFTER INSERT OR DELETE OR UPDATE ON "app"."trip_day_pois" FOR EACH ROW EXECUTE FUNCTION "app"."project_ktm_cache_target_source"();

CREATE TRIGGER "trg_trip_day_pois_touch_updated_at" BEFORE UPDATE ON "app"."trip_day_pois" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_trip_poi_rise_sets_touch_updated_at" BEFORE UPDATE ON "app"."trip_poi_rise_sets" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_trips_touch_updated_at" BEFORE UPDATE ON "app"."trips" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

CREATE TRIGGER "trg_users_touch_updated_at" BEFORE UPDATE ON "app"."users" FOR EACH ROW EXECUTE FUNCTION "app"."touch_updated_at"();

ALTER TABLE ONLY "app"."admin_audit_log"
    ADD CONSTRAINT "fk_admin_audit_log_actor_user_id" FOREIGN KEY ("actor_user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."category_mappings"
    ADD CONSTRAINT "fk_category_mappings_created_by_user_id" FOREIGN KEY ("created_by_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."category_mappings"
    ADD CONSTRAINT "fk_category_mappings_updated_by_user_id" FOREIGN KEY ("updated_by_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."content_moderation_actions"
    ADD CONSTRAINT "fk_content_moderation_actions_actor_user_id" FOREIGN KEY ("actor_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."content_moderation_actions"
    ADD CONSTRAINT "fk_content_moderation_actions_report_id" FOREIGN KEY ("report_id") REFERENCES "app"."content_reports"("report_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."content_reports"
    ADD CONSTRAINT "fk_content_reports_reporter_user_id" FOREIGN KEY ("reporter_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."content_reports"
    ADD CONSTRAINT "fk_content_reports_reviewer_user_id" FOREIGN KEY ("reviewer_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."content_reports"
    ADD CONSTRAINT "fk_content_reports_target_owner_user_id" FOREIGN KEY ("target_owner_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."content_reports"
    ADD CONSTRAINT "fk_content_reports_target_trip_id" FOREIGN KEY ("target_trip_id") REFERENCES "app"."trips"("trip_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."curated_plan_attachments"
    ADD CONSTRAINT "fk_curated_plan_attachments_curated_plan_id" FOREIGN KEY ("curated_plan_id") REFERENCES "app"."curated_trip_plans"("curated_plan_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."curated_plan_attachments"
    ADD CONSTRAINT "fk_curated_plan_attachments_curated_poi_id" FOREIGN KEY ("curated_poi_id") REFERENCES "app"."curated_plan_pois"("curated_poi_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."curated_plan_attachments"
    ADD CONSTRAINT "fk_curated_plan_attachments_source_attachment_id" FOREIGN KEY ("source_attachment_id") REFERENCES "app"."curated_plan_attachments"("attachment_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."curated_plan_attachments"
    ADD CONSTRAINT "fk_curated_plan_attachments_trip_day" FOREIGN KEY ("trip_id", "trip_day_index") REFERENCES "app"."trip_days"("trip_id", "day_index") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."curated_plan_attachments"
    ADD CONSTRAINT "fk_curated_plan_attachments_trip_id" FOREIGN KEY ("trip_id") REFERENCES "app"."trips"("trip_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."curated_plan_attachments"
    ADD CONSTRAINT "fk_curated_plan_attachments_trip_poi_id" FOREIGN KEY ("trip_poi_id") REFERENCES "app"."trip_day_pois"("attachment_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."curated_plan_attachments"
    ADD CONSTRAINT "fk_curated_plan_attachments_uploaded_by_user_id" FOREIGN KEY ("uploaded_by_user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."curated_plan_pois"
    ADD CONSTRAINT "fk_curated_plan_pois_curated_plan_id" FOREIGN KEY ("curated_plan_id") REFERENCES "app"."curated_trip_plans"("curated_plan_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."curated_plan_pois"
    ADD CONSTRAINT "fk_curated_plan_pois_curation_parent" FOREIGN KEY ("curated_plan_id", "source_curation_collection_id") REFERENCES "app"."curated_trip_plans"("curated_plan_id", "source_curation_collection_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."curated_plan_pois"
    ADD CONSTRAINT "fk_curated_plan_pois_curation_receipt_item" FOREIGN KEY ("source_curation_import_receipt_id", "source_curation_collection_id", "source_curation_item_id", "source_curation_item_revision", "source_curation_item_etag", "feature_uuid") REFERENCES "app"."ktm_curation_import_receipt_items"("receipt_id", "source_curation_collection_id", "source_curation_item_id", "source_curation_item_revision", "source_curation_item_etag", "feature_uuid") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."curated_trip_plans"
    ADD CONSTRAINT "fk_curated_trip_plans_created_by_admin_id" FOREIGN KEY ("created_by_admin_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."curated_trip_plans"
    ADD CONSTRAINT "fk_curated_trip_plans_updated_by_admin_id" FOREIGN KEY ("updated_by_admin_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."dsr_requests"
    ADD CONSTRAINT "fk_dsr_requests_assigned_cpo_user_id" FOREIGN KEY ("assigned_cpo_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."dsr_requests"
    ADD CONSTRAINT "fk_dsr_requests_result_notice_email_id" FOREIGN KEY ("result_notice_email_id") REFERENCES "app"."email_queue"("email_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."dsr_requests"
    ADD CONSTRAINT "fk_dsr_requests_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."email_queue"
    ADD CONSTRAINT "fk_email_queue_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."email_suppressions"
    ADD CONSTRAINT "fk_email_suppressions_released_by_user_id" FOREIGN KEY ("released_by_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."feature_suggestions"
    ADD CONSTRAINT "fk_feature_suggestions_requester_user_id" FOREIGN KEY ("requester_user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."feature_suggestions"
    ADD CONSTRAINT "fk_feature_suggestions_reviewed_by_admin_id" FOREIGN KEY ("reviewed_by_admin_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."ktm_cache_target_boundary_audits"
    ADD CONSTRAINT "fk_ktm_ct_boundary_canary_evidence" FOREIGN KEY ("canary_run_id", "canary_provenance_sha256", "final_local_remote_evidence_sha256") REFERENCES "app"."ktm_cache_target_canary_runs"("run_id", "canary_provenance_sha256", "final_evidence_sha256") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_boundary_audits"
    ADD CONSTRAINT "fk_ktm_ct_boundary_initial_consumer" FOREIGN KEY ("consumer_id", "initial_cutover_id", "initial_reconciliation_request_id") REFERENCES "app"."ktm_cache_target_consumers"("consumer_id", "initial_cutover_id", "initial_reconciliation_request_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_boundary_audits"
    ADD CONSTRAINT "fk_ktm_ct_boundary_initial_receipt" FOREIGN KEY ("initial_reconciliation_request_id", "initial_receipt_event_id", "initial_expectation_status") REFERENCES "app"."ktm_cache_target_reconciliation_expectations"("request_id", "receipt_event_id", "status") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_consumer" FOREIGN KEY ("consumer_id") REFERENCES "app"."ktm_cache_target_consumers"("consumer_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_delete_ack" FOREIGN KEY ("delete_claim_id", "delete_event_id", "delete_cursor", "delete_event_payload_fingerprint", "delete_acked_at") REFERENCES "app"."ktm_cache_target_event_claim_items"("claim_id", "event_id", "delivery_cursor", "payload_fingerprint", "acked_at") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_delete_claim_terminal" FOREIGN KEY ("delete_claim_id", "consumer_id", "delete_claim_status", "delete_cursor", "delete_claim_completed_at") REFERENCES "app"."ktm_cache_target_event_claims"("claim_id", "consumer_id", "status", "acked_through_cursor", "completed_at") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_delete_command" FOREIGN KEY ("delete_command_id", "target_poi_id", "delete_generation", "delete_source_payload_fingerprint") REFERENCES "app"."ktm_cache_target_commands"("command_id", "poi_id", "source_generation", "payload_fingerprint") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_delete_event" FOREIGN KEY ("delete_event_id", "delete_command_id", "delete_generation", "delete_source_payload_fingerprint", "delete_event_payload_fingerprint") REFERENCES "app"."ktm_cache_target_events"("event_id", "source_event_id", "source_generation", "source_payload_fingerprint", "payload_fingerprint") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_put_ack" FOREIGN KEY ("put_claim_id", "put_event_id", "put_cursor", "put_event_payload_fingerprint", "put_acked_at") REFERENCES "app"."ktm_cache_target_event_claim_items"("claim_id", "event_id", "delivery_cursor", "payload_fingerprint", "acked_at") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_put_claim_terminal" FOREIGN KEY ("put_claim_id", "consumer_id", "put_claim_status", "put_cursor", "put_claim_completed_at") REFERENCES "app"."ktm_cache_target_event_claims"("claim_id", "consumer_id", "status", "acked_through_cursor", "completed_at") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_put_command" FOREIGN KEY ("put_command_id", "target_poi_id", "put_generation", "put_source_payload_fingerprint") REFERENCES "app"."ktm_cache_target_commands"("command_id", "poi_id", "source_generation", "payload_fingerprint") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_put_event" FOREIGN KEY ("put_event_id", "put_command_id", "put_generation", "put_source_payload_fingerprint", "put_event_payload_fingerprint") REFERENCES "app"."ktm_cache_target_events"("event_id", "source_event_id", "source_generation", "source_payload_fingerprint", "payload_fingerprint") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_canary_runs"
    ADD CONSTRAINT "fk_ktm_ct_canary_target" FOREIGN KEY ("target_poi_id") REFERENCES "app"."ktm_cache_target_heads"("poi_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_event_claim_items"
    ADD CONSTRAINT "fk_ktm_ct_claim_items_claim" FOREIGN KEY ("claim_id") REFERENCES "app"."ktm_cache_target_event_claims"("claim_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_event_claim_items"
    ADD CONSTRAINT "fk_ktm_ct_claim_items_event" FOREIGN KEY ("event_id") REFERENCES "app"."ktm_cache_target_events"("event_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_commands"
    ADD CONSTRAINT "fk_ktm_ct_commands_poi" FOREIGN KEY ("poi_id") REFERENCES "app"."ktm_cache_target_heads"("poi_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_event_claims"
    ADD CONSTRAINT "fk_ktm_ct_event_claims_consumer" FOREIGN KEY ("consumer_id") REFERENCES "app"."ktm_cache_target_consumers"("consumer_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_reconciliation_expectations"
    ADD CONSTRAINT "fk_ktm_ct_reconcile_expectations_receipt" FOREIGN KEY ("receipt_event_id") REFERENCES "app"."ktm_cache_target_events"("event_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_cache_target_restore_fence_attempts"
    ADD CONSTRAINT "fk_ktm_ct_restore_attempt_consumer" FOREIGN KEY ("consumer_id") REFERENCES "app"."ktm_cache_target_consumers"("consumer_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_cutover_backfill_receipts"
    ADD CONSTRAINT "fk_ktm_curation_cutover_backfill_receipts_actor" FOREIGN KEY ("actor_admin_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_cutover_backfill_receipts"
    ADD CONSTRAINT "fk_ktm_curation_cutover_backfill_receipts_import" FOREIGN KEY ("import_receipt_id") REFERENCES "app"."ktm_curation_import_receipts"("receipt_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_cutover_backfill_receipts"
    ADD CONSTRAINT "fk_ktm_curation_cutover_backfill_receipts_mapping" FOREIGN KEY ("mapping_receipt_id") REFERENCES "app"."ktm_curation_cutover_mapping_receipts"("receipt_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_cutover_backfill_receipts"
    ADD CONSTRAINT "fk_ktm_curation_cutover_backfill_receipts_mapping_item" FOREIGN KEY ("mapping_receipt_id", "legacy_curated_feature_id") REFERENCES "app"."ktm_curation_cutover_mapping_receipt_items"("receipt_id", "legacy_curated_feature_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_cutover_backfill_receipts"
    ADD CONSTRAINT "fk_ktm_curation_cutover_backfill_receipts_plan" FOREIGN KEY ("curated_plan_id") REFERENCES "app"."curated_trip_plans"("curated_plan_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_cutover_mapping_receipt_items"
    ADD CONSTRAINT "fk_ktm_curation_cutover_mapping_receipt_items_receipt" FOREIGN KEY ("receipt_id") REFERENCES "app"."ktm_curation_cutover_mapping_receipts"("receipt_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_cutover_mapping_receipts"
    ADD CONSTRAINT "fk_ktm_curation_cutover_mapping_receipts_actor" FOREIGN KEY ("actor_admin_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_import_receipt_items"
    ADD CONSTRAINT "fk_ktm_curation_import_receipt_items_receipt" FOREIGN KEY ("receipt_id", "source_curation_collection_id") REFERENCES "app"."ktm_curation_import_receipts"("receipt_id", "source_curation_collection_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_import_receipts"
    ADD CONSTRAINT "fk_ktm_curation_import_receipts_actor" FOREIGN KEY ("actor_admin_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_curation_import_receipts"
    ADD CONSTRAINT "fk_ktm_curation_import_receipts_result_source" FOREIGN KEY ("result_plan_id", "source_curation_collection_id") REFERENCES "app"."curated_trip_plans"("curated_plan_id", "source_curation_collection_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."ktm_feature_reference_reconciliation_impacts"
    ADD CONSTRAINT "fk_ktm_frr_impact_receipt" FOREIGN KEY ("event_id") REFERENCES "app"."ktm_feature_reference_reconciliation_applied_receipts"("event_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."location_access_log_archive"
    ADD CONSTRAINT "fk_location_access_log_archive_retention_run_id" FOREIGN KEY ("retention_run_id") REFERENCES "app"."retention_runs"("run_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."location_access_log_archive"
    ADD CONSTRAINT "fk_location_access_log_archive_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."location_access_log"
    ADD CONSTRAINT "fk_location_access_log_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."location_audit_outbox"
    ADD CONSTRAINT "fk_location_audit_outbox_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."mcp_tokens"
    ADD CONSTRAINT "fk_mcp_tokens_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."oauth_login_states"
    ADD CONSTRAINT "fk_oauth_login_states_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."oauth_mobile_exchanges"
    ADD CONSTRAINT "fk_oauth_mobile_exchanges_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."rate_limit_overrides"
    ADD CONSTRAINT "fk_rate_limit_overrides_created_by_user_id" FOREIGN KEY ("created_by_user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."rate_limit_overrides"
    ADD CONSTRAINT "fk_rate_limit_overrides_revoked_by_user_id" FOREIGN KEY ("revoked_by_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."retention_runs"
    ADD CONSTRAINT "fk_retention_runs_actor_user_id" FOREIGN KEY ("actor_user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."security_incidents"
    ADD CONSTRAINT "fk_security_incidents_assigned_cpo_user_id" FOREIGN KEY ("assigned_cpo_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."telegram_targets"
    ADD CONSTRAINT "fk_telegram_targets_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trip_comments"
    ADD CONSTRAINT "fk_trip_comments_author_user_id" FOREIGN KEY ("author_user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."trip_comments"
    ADD CONSTRAINT "fk_trip_comments_trip_id" FOREIGN KEY ("trip_id") REFERENCES "app"."trips"("trip_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trip_companions"
    ADD CONSTRAINT "fk_trip_companions_trip_id" FOREIGN KEY ("trip_id") REFERENCES "app"."trips"("trip_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trip_companions"
    ADD CONSTRAINT "fk_trip_companions_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE SET NULL;

ALTER TABLE ONLY "app"."trip_day_pois"
    ADD CONSTRAINT "fk_trip_day_pois_added_by_user_id" FOREIGN KEY ("added_by_user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."trip_day_pois"
    ADD CONSTRAINT "fk_trip_day_pois_day" FOREIGN KEY ("trip_id", "day_index") REFERENCES "app"."trip_days"("trip_id", "day_index") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trip_day_rise_sets"
    ADD CONSTRAINT "fk_trip_day_rise_sets_day" FOREIGN KEY ("trip_id", "day_index") REFERENCES "app"."trip_days"("trip_id", "day_index") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trip_days"
    ADD CONSTRAINT "fk_trip_days_trip_id" FOREIGN KEY ("trip_id") REFERENCES "app"."trips"("trip_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trip_poi_rise_sets"
    ADD CONSTRAINT "fk_trip_poi_rise_sets_poi_id" FOREIGN KEY ("poi_id") REFERENCES "app"."trip_day_pois"("attachment_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trip_share_links"
    ADD CONSTRAINT "fk_trip_share_links_created_by_user_id" FOREIGN KEY ("created_by_user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."trip_share_links"
    ADD CONSTRAINT "fk_trip_share_links_trip_id" FOREIGN KEY ("trip_id") REFERENCES "app"."trips"("trip_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trip_telegram_targets"
    ADD CONSTRAINT "fk_trip_telegram_targets_target_id" FOREIGN KEY ("telegram_target_id") REFERENCES "app"."telegram_targets"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trip_telegram_targets"
    ADD CONSTRAINT "fk_trip_telegram_targets_trip_id" FOREIGN KEY ("trip_id") REFERENCES "app"."trips"("trip_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."trips"
    ADD CONSTRAINT "fk_trips_owner_user_id" FOREIGN KEY ("owner_user_id") REFERENCES "app"."users"("user_id") ON DELETE RESTRICT;

ALTER TABLE ONLY "app"."user_consents"
    ADD CONSTRAINT "fk_user_consents_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."user_email_verifications"
    ADD CONSTRAINT "fk_user_email_verifications_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."user_oauth_identities"
    ADD CONSTRAINT "fk_user_oauth_identities_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE CASCADE;

ALTER TABLE ONLY "app"."user_sessions"
    ADD CONSTRAINT "fk_user_sessions_user_id" FOREIGN KEY ("user_id") REFERENCES "app"."users"("user_id") ON DELETE CASCADE;
