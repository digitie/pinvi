"""Map feature 참조에 UUID shadow 컬럼을 추가한다 (T-VN-32C, Map ADR-068).

Map은 feature 정본 PK를 UUID surrogate로 전환 중이다(T-VN-32A/B). PinVi가 저장
중인 legacy ``f_*`` 참조 3열(``trip_day_pois.feature_id`` ·
``curated_plan_pois.feature_id`` · ``feature_suggestions.target_feature_id``)
옆에 nullable UUID shadow 컬럼을 추가한다.

**backfill은 여기서 하지 않는다** — 값 채움은 검증된 alias map DB-to-DB 이관
(`app.services.feature_uuid_cutover` — Map alias-map 표면을 pull, 독립 checksum
재계산·파생 검증 통과 후에만 적용)의 소관이다. migration이 로컬 파생만으로
채우면 "검증된" 조건(양 저장소 checksum 일치)을 우회하게 된다.

legacy 컬럼은 유지한다 — 제거는 Map T-VN-39 soak 이후의 별도 결정이다.

동반: **final boundary schema pin re-pin(의식적)**. T-VN-41 final boundary는
finalize 시점 alembic head를 service pin(`FINALIZE_SCHEMA_REVISION`)과 audit
DB CHECK(`ck_ktm_ct_boundary_contract`)로 이중 고정한다(fail-close by design —
head가 전진하면 어떤 migration이든 boundary 재검토·re-pin을 강제받는다).
본 revision의 검토 결론: 0049는 `ktm_cache_target_*` 테이블·writer registry·
boundary 불변식 무접촉이므로 pin만 `20260804_0049`로 올린다. production final
boundary는 아직 닫혀 있고(audit 행 0), 기존 행이 없어 CHECK 교체는 무손실이다.

Revision ID: 20260804_0049
Revises: 20260802_0048
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260804_0049"
down_revision: str | None = "20260802_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TARGETS: tuple[tuple[str, str], ...] = (
    ("trip_day_pois", "feature_uuid"),
    ("curated_plan_pois", "feature_uuid"),
    ("feature_suggestions", "target_feature_uuid"),
)


_BOUNDARY_CONTRACT_CHECK_TEMPLATE = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '{revision}'"
)


def _repin_boundary_contract(revision_value: str) -> None:
    op.drop_constraint(
        "ck_ktm_ct_boundary_contract",
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ktm_ct_boundary_contract",
        "ktm_cache_target_boundary_audits",
        _BOUNDARY_CONTRACT_CHECK_TEMPLATE.format(revision=revision_value),
        schema="app",
    )


def upgrade() -> None:
    for table, column in _TARGETS:
        op.add_column(
            table,
            sa.Column(column, postgresql.UUID(as_uuid=True), nullable=True),
            schema="app",
        )
    _repin_boundary_contract("20260804_0049")


def downgrade() -> None:
    _repin_boundary_contract("20260802_0048")
    for table, column in reversed(_TARGETS):
        op.drop_column(table, column, schema="app")
