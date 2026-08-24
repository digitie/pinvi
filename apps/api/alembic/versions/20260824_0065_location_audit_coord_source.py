"""확인자료가 좌표의 **출처**를 함께 기록하게 한다.

Revision ID: 20260824_0065
Revises: 20260824_0064
Create Date: 2026-08-24

`location_access_log`는 좌표를 적지만 그것이 **사용자 자신의 위치**인지 **지도에서 고른 지점**인지
구분하지 않았다. 둘은 법적으로 다른 것이다 — 개인위치정보는 전자뿐이고, 후자는 사용자가 화면에서
찍은 좌표다. 구분이 없으니 두 문제가 동시에 생겼다.

1. 사용자에게 보여줄 "위치 사용 내역"이 지도 클릭까지 "당신의 위치를 썼다"고 말한다.
2. 동의 게이트(T-327)를 좌표 endpoint에 걸 수 없다. 막으면 지도에서 POI를 고르는 기능이 깨지고,
   안 막으면 철회한 사용자의 실제 위치도 통과한다. 출처를 모르니 어느 쪽도 옳지 않다.

`coord_source`를 nullable로 추가한다. NULL은 "이 행이 기록될 때 출처 개념이 없었다"는 뜻이며,
과거 행을 소급 판정하지 않는다 — 판정할 근거가 없기 때문이다.

`reverse_geocode`도 purpose 계약에 넣는다. `/geo/reverse`는 문서 3곳이 감사 대상이라고 규정했지만
`_classify_purpose`가 분류한 적이 없었다(T-330에서 문서를 정정). 출처를 적을 수 있게 된 지금은
`map_pick`으로 정직하게 기록할 수 있으므로 계약을 열어 실제로 감사한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0065'"
)
_PREV_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0064'"
)

revision: str = "20260824_0065"
down_revision: str | None = "20260824_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSE_CONSTRAINT = "ck_location_access_log_ck_location_access_log_purpose"
_OLD_PURPOSES = (
    "'viewport_query', 'nearby_attractions', 'weather_at_coord', "
    "'feature_request', 'region_covering', 'region_radius', 'third_party_place_search'"
)
_NEW_PURPOSES = f"{_OLD_PURPOSES}, 'reverse_geocode'"

_SOURCE_CHECK = "coord_source IS NULL OR coord_source IN ('device', 'map_pick')"


def _repin_boundary_contract(check: str) -> None:
    """새 head에서만 final boundary가 열리도록 DB/service pin을 함께 전진시킨다.

    이 저장소는 head 마이그레이션마다 `FINALIZE_SCHEMA_REVISION`과 DB CHECK를 의식적으로
    재결박한다(`20260824_0064` 등 선례). 둘 중 하나만 옮기면 receipt INSERT가 CHECK 위반이 되거나
    finalize가 `schema_revision_mismatch`로 거부된다.
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
    for table in ("location_access_log", "location_audit_outbox"):
        op.add_column(
            table,
            sa.Column("coord_source", sa.Text(), nullable=True),
            schema="app",
        )
        op.create_check_constraint(
            f"ck_{table}_coord_source",
            table,
            _SOURCE_CHECK,
            schema="app",
        )

    op.execute(f"ALTER TABLE app.location_access_log DROP CONSTRAINT {_PURPOSE_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE app.location_access_log ADD CONSTRAINT {_PURPOSE_CONSTRAINT} "
        f"CHECK (purpose IN ({_NEW_PURPOSES}))"
    )
    _repin_boundary_contract(_BOUNDARY_CONTRACT_CHECK)


def downgrade() -> None:
    """컬럼과 제약을 되돌린다.

    `purpose` 되돌리기는 `20260824_0062`와 같은 이유로 `NOT VALID`다 — append-only 트리거가
    UPDATE/DELETE를 막으므로 이미 적재된 `reverse_geocode` 행을 정리할 수단이 없다. 기존 행을 남긴
    채 이후 삽입만 다시 좁힌다.

    `coord_source` 컬럼은 DROP한다. 이 방향은 데이터를 잃지만, 컬럼 자체가 이 리비전에서 생긴 것이라
    그 안의 값도 전부 이 리비전 이후의 것이다.
    """
    op.execute(f"ALTER TABLE app.location_access_log DROP CONSTRAINT {_PURPOSE_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE app.location_access_log ADD CONSTRAINT {_PURPOSE_CONSTRAINT} "
        f"CHECK (purpose IN ({_OLD_PURPOSES})) NOT VALID"
    )

    for table in ("location_access_log", "location_audit_outbox"):
        op.drop_constraint(f"ck_{table}_coord_source", table, schema="app", type_="check")
        op.drop_column(table, "coord_source", schema="app")

    _repin_boundary_contract(_PREV_BOUNDARY_CONTRACT_CHECK)
