"""`/search` 제3자 제공 purpose를 감사 로그 CHECK 계약에 포함한다.

Revision ID: 20260824_0062
Revises: 20260821_0061
Create Date: 2026-08-24

`app/middleware/location_audit.py`가 `/search`(내 주변 검색, ADR-054 §9)에서
`third_party_place_search`를 발행하는데 `20260602_0003`이 만든
`ck_location_access_log_purpose`는 6종만 허용한다. 그래서 outbox에는 들어가지만
체인 적재에서 CHECK 위반이 나고, drain이 배치 전체를 abort해 **이후 모든 위치 감사 기록이
멈춘다**(위치정보법 제16조 확인자료 기록 중단). 제약을 실제 계약에 맞춘다.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0062'"
)
_PREV_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260821_0061'"
)

revision: str = "20260824_0062"
down_revision: str | None = "20260821_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_location_access_log_ck_location_access_log_purpose"

_OLD_PURPOSES = (
    "'viewport_query', 'nearby_attractions', 'weather_at_coord', "
    "'feature_request', 'region_covering', 'region_radius'"
)
_NEW_PURPOSES = f"{_OLD_PURPOSES}, 'third_party_place_search'"


def _repin_boundary_contract(check: str) -> None:
    """새 head에서만 final boundary가 열리도록 DB/service pin을 함께 전진시킨다.

    이 저장소는 head 마이그레이션마다 `FINALIZE_SCHEMA_REVISION`과 DB CHECK를 의식적으로
    재결박한다(`20260821_0061` 등 선례). 둘 중 하나만 옮기면 receipt INSERT가 CHECK 위반이
    되거나 finalize가 `schema_revision_mismatch`로 거부된다.
    """
    op.drop_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        check,
        schema="app",
    )


def upgrade() -> None:
    op.execute(f"ALTER TABLE app.location_access_log DROP CONSTRAINT {_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE app.location_access_log ADD CONSTRAINT {_CONSTRAINT} "
        f"CHECK (purpose IN ({_NEW_PURPOSES}))"
    )
    _repin_boundary_contract(_BOUNDARY_CONTRACT_CHECK)


def downgrade() -> None:
    """구 6종 제약으로 되돌리되 **검증하지 않는다**(`NOT VALID`).

    `trg_location_access_log_append_only`(`20260602_0003`)가 UPDATE/DELETE를 모두 막으므로
    이미 적재된 `third_party_place_search` 행을 정리할 수단이 없다. 정확한 역연산이 불가능한
    지점이며, `NOT VALID`는 기존 행을 남긴 채 이후 삽입만 다시 좁힌다.
    """
    op.execute(f"ALTER TABLE app.location_access_log DROP CONSTRAINT {_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE app.location_access_log ADD CONSTRAINT {_CONSTRAINT} "
        f"CHECK (purpose IN ({_OLD_PURPOSES})) NOT VALID"
    )
    _repin_boundary_contract(_PREV_BOUNDARY_CONTRACT_CHECK)
