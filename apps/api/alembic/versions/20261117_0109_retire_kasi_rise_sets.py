"""KASI 해·달 출몰 저장 표 은퇴 — `trip_day_rise_sets`·`trip_poi_rise_sets` 삭제.

해·달 출몰은 응답을 만들 때 `astral`로 계산한다(`app/services/sun_times.py`, 2026-11-16 #752·11-17 달 출몰 이관).
두 표를 채우던 Dagster job(`pinvi_trip_day_rise_sets`·`kasi_poi_rise_set_job`)도 함께 은퇴했다. POI 표는 채우는
job이 없어 운영에서 전부 `pending_fetch`였고(2026-11-16 8,966행), 일자 표는 달 출몰만 남은 쓰임이었다.

forward-safe: 이 리비전의 코드는 두 표를 읽지도 쓰지도 않는다. 이전 코드(0108)는 두 표를 쓰므로 이 리비전을
적용한 DB에서 0108 코드를 돌리면 안 된다 — 배포는 마이그레이션 전진이다. downgrade는 0100 baseline과 같은
구조로 빈 표를 다시 만든다(값은 계산값이라 되살릴 필요가 없다).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261117_0109"
down_revision: str | None = "20261116_0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIOR = "contract_version = 'pinvi-cache-target-final-boundary/v1' AND status = 'succeeded' AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102' OR schema_revision = '20261105_0103' OR schema_revision = '20261105_0104' OR schema_revision = '20261105_0105' OR schema_revision = '20261106_0106' OR schema_revision = '20261107_0107' OR schema_revision = '20261116_0108')"
_CHECK = _PRIOR[:-1] + " OR schema_revision = '20261117_0109')"


def _boundary(check: str) -> None:
    op.drop_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"), "ktm_cache_target_boundary_audits", check, schema="app"
    )


def upgrade() -> None:
    op.execute("DROP TABLE app.trip_poi_rise_sets")
    op.execute("DROP TABLE app.trip_day_rise_sets")
    _boundary(_CHECK)


# 0100 baseline(`alembic/baselines/20260824_0100_app_schema.sql`)과 같은 구조.
_RECREATE = """
CREATE TABLE app.trip_day_rise_sets (
    trip_id uuid NOT NULL,
    day_index integer NOT NULL,
    locdate date,
    reference_poi_id uuid,
    reference_label text,
    longitude double precision,
    latitude double precision,
    sunrise_at timestamp with time zone,
    sunset_at timestamp with time zone,
    moonrise_at timestamp with time zone,
    moonset_at timestamp with time zone,
    status character varying(20) DEFAULT 'pending_date'::character varying NOT NULL,
    stale boolean DEFAULT false NOT NULL,
    raw_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    error jsonb,
    fetched_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT pk_trip_day_rise_sets PRIMARY KEY (trip_id, day_index),
    CONSTRAINT fk_trip_day_rise_sets_day FOREIGN KEY (trip_id, day_index)
        REFERENCES app.trip_days (trip_id, day_index) ON DELETE CASCADE
);
CREATE INDEX ix_trip_day_rise_sets_fillable ON app.trip_day_rise_sets USING btree (status)
    WHERE ((status)::text = 'pending_fetch'::text) OR stale;
CREATE TABLE app.trip_poi_rise_sets (
    poi_id uuid NOT NULL,
    locdate date,
    longitude double precision,
    latitude double precision,
    sunrise_at timestamp with time zone,
    sunset_at timestamp with time zone,
    moonrise_at timestamp with time zone,
    moonset_at timestamp with time zone,
    status character varying(20) DEFAULT 'pending_date'::character varying NOT NULL,
    raw_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    error jsonb,
    fetched_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_trip_poi_rise_sets_ck_trip_poi_rise_sets_status CHECK (
        (status)::text = ANY ((ARRAY['pending_date'::character varying, 'pending_coord'::character varying,
        'pending_fetch'::character varying, 'success'::character varying, 'failed'::character varying])::text[])
    ),
    CONSTRAINT pk_trip_poi_rise_sets PRIMARY KEY (poi_id),
    CONSTRAINT fk_trip_poi_rise_sets_poi_id FOREIGN KEY (poi_id)
        REFERENCES app.trip_day_pois (attachment_id) ON DELETE CASCADE
);
CREATE INDEX ix_trip_poi_rise_sets_locdate ON app.trip_poi_rise_sets USING btree (locdate);
CREATE INDEX ix_trip_poi_rise_sets_pending_fetch ON app.trip_poi_rise_sets USING btree (locdate)
    WHERE ((status)::text = 'pending_fetch'::text);
CREATE TRIGGER trg_trip_poi_rise_sets_touch_updated_at BEFORE UPDATE ON app.trip_poi_rise_sets
    FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at();
"""


def downgrade() -> None:
    op.execute(
        "DELETE FROM app.ktm_cache_target_boundary_audits WHERE schema_revision = '20261117_0109'"
    )
    _boundary(_PRIOR)
    # asyncpg는 한 prepared statement에 여러 명령을 받지 않는다 — 문장마다 실행한다.
    for statement in _RECREATE.split(";"):
        if statement.strip():
            op.execute(statement)
