"""날씨 소스 이관(ADR-068) feature_id -> location_id 해석 캐시 테이블을 추가한다.

Revision ID: 20260917_0102
Revises: 20260824_0101
Create Date: 2026-09-17

T-361(P2). `kor-travel-weather`의 좌표 해석(`/v1/weather/resolve`)은 1회 호출에
3.1 MB급 응답이라 조회 경로에 둘 수 없다 — 결과를 `app.weather_location_links`에
캐시한다. `source_location_ids`를 배열로 통째 저장하는 이유는
`docs/integrations/kor-travel-weather.md` §3.3 참조(대표 location 하나만 캐시하면
기상청 예보가 조용히 누락된다).

이 테이블은 아직 어떤 라우터도 읽지 않는다 — T-362/T-363이 처음 읽는다.

**두 번째 목적 — canonical exact head를 0101 단독에서 (0101, 0102)로 넓힌다.**
`20260824_0101_m05_activation_contract.py`가 도입한 `ck_ktm_ct_boundary_contract`
CHECK와 `app/services/cache_target_final_boundary.FINALIZE_SCHEMA_REVISIONS`는
"현재 head가 정확히 무엇인가"를 fail-close로 고정하는 M05 계약이다(그 파일의
`_advance_boundary_contract()` 주석: "finalize가 기준선 이후 M05 계약만 수용하도록
revision pin을 전진시킨다"). 0101 뒤에 아무 migration이나 추가하면 이 pin이 낡아
cache-target finalize 전체가 `schema_revision_mismatch`로 죽는다 — PR #545 CI에서
결정론적으로 재현·발견됨. 같은 이유로 `infra/postgres/bootstrap-pinvi-runtime-role.sh`
(runtime role GRANT)도 0102를 인식하도록 수정했고, `scripts/deploy-node.sh`
(N150 fresh 배포)·`scripts/restore-hotswap.sh`(N150 복구)도 함께 고쳤다 — 사용자
확인 후 진행(2026-09-17).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260917_0102"
down_revision: str | None = "20260824_0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 0101이 도입한 값(alembic/versions/20260824_0101_m05_activation_contract.py의
# _BOUNDARY_CONTRACT_CHECK) — downgrade에서 정확히 이 상태로 복원한다.
_PRIOR_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0101'"
)
# 이 revision이 새로 놓는 값 — 0101과 0102 둘 다 canonical head로 수용한다. **IN이
# 아니라 OR 체인이어야 한다** — PostgreSQL이 `IN (...)`을
# `= ANY (ARRAY[...])`로 정규화해 `pg_get_constraintdef()`가 다른 텍스트를 반환하고,
# scripts/restore-hotswap.sh의 `LIKE '%schema_revision = ''20260824_0101''%'` 검증이
# 깨진다(직접 실측 확인, `OR`는 원래 리터럴 형태를 그대로 보존한다). 다음 새 migration이
# 또 head를 전진시키면 이 OR 체인에 그 revision id를 추가할 것(같은 패턴을
# app/services/cache_target_final_boundary.FINALIZE_SCHEMA_REVISIONS,
# infra/postgres/bootstrap-pinvi-runtime-role.sh, scripts/deploy-node.sh,
# scripts/restore-hotswap.sh에도 반복해야 한다).
_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' "
    "AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102')"
)


def _set_boundary_contract(check_sql: str) -> None:
    op.drop_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        check_sql,
        schema="app",
    )


def upgrade() -> None:
    op.create_table(
        "weather_location_links",
        sa.Column("feature_id", sa.Text(), nullable=False),
        sa.Column("location_id", sa.Text(), nullable=False),
        sa.Column("source_location_ids", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column(
            "measurement_point",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_weather_location_links"),
        schema="app",
    )
    op.create_index(
        "ix_weather_location_links_stale",
        "weather_location_links",
        ["stale"],
        schema="app",
        postgresql_where=sa.text("stale"),
    )
    _set_boundary_contract(_BOUNDARY_CONTRACT_CHECK)


def downgrade() -> None:
    _set_boundary_contract(_PRIOR_BOUNDARY_CONTRACT_CHECK)
    op.drop_index(
        "ix_weather_location_links_stale",
        table_name="weather_location_links",
        schema="app",
    )
    op.drop_table("weather_location_links", schema="app")
