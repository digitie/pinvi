"""cache target source generation projection과 command outbox trigger

Revision ID: 20260731_0042
Revises: 20260731_0041
Create Date: 2026-07-31 21:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0042"
down_revision: str | None = "20260731_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROUND_HALF_EVEN_FUNCTION = r"""
CREATE FUNCTION app.ktm_round_half_even_scaled(value numeric, scale_factor bigint)
RETURNS bigint
LANGUAGE plpgsql
IMMUTABLE
STRICT
SECURITY INVOKER
SET search_path = pg_catalog
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
$$
"""

_ACTIVE_SOURCE_FUNCTION = r"""
CREATE FUNCTION app.ktm_cache_target_active_source_v1(
    lon numeric,
    lat numeric,
    radius_km numeric,
    update_enabled boolean
)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
STRICT
SECURITY INVOKER
SET search_path = pg_catalog, app
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
$$
"""

_DELETED_SOURCE_FUNCTION = r"""
CREATE FUNCTION app.ktm_cache_target_deleted_source_v1()
RETURNS text
LANGUAGE sql
IMMUTABLE
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
    SELECT '{"state":"deleted","version":"cache-target-source-v1"}'::text
$$
"""

_PROJECT_TRIGGER_FUNCTION = r"""
CREATE FUNCTION app.project_ktm_cache_target_source()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app, x_extension
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
$$
"""

_BACKFILL = r"""
WITH source AS (
    SELECT
        attachment_id AS poi_id,
        app.ktm_cache_target_active_source_v1(
            cache_target_lon,
            cache_target_lat,
            cache_target_radius_km,
            cache_target_update_enabled
        ) AS source_text,
        app.ktm_round_half_even_scaled(cache_target_lon, 1000000) / 1000000::numeric AS lon,
        app.ktm_round_half_even_scaled(cache_target_lat, 1000000) / 1000000::numeric AS lat,
        app.ktm_round_half_even_scaled(cache_target_radius_km, 1000) / 1000::numeric AS radius_km,
        cache_target_update_enabled AS update_enabled
    FROM app.trip_day_pois
    WHERE deleted_at IS NULL
      AND cache_target_lon IS NOT NULL
      AND cache_target_lat IS NOT NULL
), inserted AS (
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
    )
    SELECT
        poi_id,
        'pinvi',
        lower(poi_id::text),
        'active',
        1,
        x_extension.digest(convert_to(source_text, 'UTF8'), 'sha256'),
        lon,
        lat,
        radius_km,
        update_enabled
    FROM source
    ON CONFLICT (poi_id) DO NOTHING
    RETURNING poi_id, source_generation
)
INSERT INTO app.ktm_cache_target_commands (
    command_id,
    poi_id,
    operation,
    source_generation,
    payload,
    payload_fingerprint
)
SELECT
    x_extension.gen_random_uuid(),
    source.poi_id,
    'put',
    inserted.source_generation,
    source.source_text::jsonb,
    x_extension.digest(convert_to(source.source_text, 'UTF8'), 'sha256')
FROM source
JOIN inserted USING (poi_id)
"""


def upgrade() -> None:
    op.execute(sa.text(_ROUND_HALF_EVEN_FUNCTION))
    op.execute(sa.text(_ACTIVE_SOURCE_FUNCTION))
    op.execute(sa.text(_DELETED_SOURCE_FUNCTION))
    op.execute(sa.text(_PROJECT_TRIGGER_FUNCTION))
    op.execute(sa.text(_BACKFILL))
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_trip_day_pois_cache_target_source "
            "AFTER INSERT OR UPDATE OR DELETE ON app.trip_day_pois "
            "FOR EACH ROW EXECUTE FUNCTION app.project_ktm_cache_target_source()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP TRIGGER IF EXISTS trg_trip_day_pois_cache_target_source ON app.trip_day_pois")
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS app.project_ktm_cache_target_source()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS app.ktm_cache_target_deleted_source_v1()"))
    op.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS "
            "app.ktm_cache_target_active_source_v1(numeric, numeric, numeric, boolean)"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS app.ktm_round_half_even_scaled(numeric, bigint)"))
