"""보존 아카이브도 좌표 출처를 보관한다.

Revision ID: 20260825_0066
Revises: 20260824_0065
Create Date: 2026-08-25

`20260824_0065`가 `location_access_log`에 `coord_source`를 추가했지만 아카이브 테이블은 그대로였다.
`_ARCHIVE_LOCATION_SQL`이 컬럼을 **명시 나열**하는 방식이라 새 컬럼은 오류 없이 조용히 빠지고,
곧바로 `_DELETE_ARCHIVED_LOCATION_SQL`이 원본을 지운다 — 6개월 뒤 아카이브 시점에 출처가 영구
소실된다.

손실은 두 겹이다.

1. 확인자료의 내용 자체가 줄어든다. `20260628_0029` 이후 아카이브는 항상 무손실 사본이었다
   (`docs/data-model.md` §8.12 "동일 payload로 복사").
2. **아카이브 행의 `content_hash`가 재검증 불가능해진다.** 해시는 `coord_source`를 포함해
   계산되므로(`location_log_payload`), 그 값이 없는 사본으로는 어떤 재계산도 원래 해시를
   재현할 수 없다. 위변조 탐지 근거가 아카이브에서 사라진다.

컬럼을 추가하고 두 SQL의 나열을 함께 고친다. 나열 방식이 다시 낡지 않게 하는 것은
`tests/integration/test_retention_archive_fidelity.py`가 두 테이블의 컬럼 집합을 비교하는 일이다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260825_0066'"
)

revision: str = "20260825_0066"
down_revision: str | None = "20260824_0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_CHECK = "coord_source IS NULL OR coord_source IN ('device', 'map_pick')"


def _repin_boundary_contract(check: str) -> None:
    """새 head에서만 final boundary가 열리도록 DB/service pin을 함께 전진시킨다.

    이 저장소는 head 마이그레이션마다 `FINALIZE_SCHEMA_REVISION`과 DB CHECK를 의식적으로
    재결박한다(`20260824_0065` 등 선례). 둘 중 하나만 옮기면 receipt INSERT가 CHECK 위반이 되거나
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
    op.add_column(
        "location_access_log_archive",
        sa.Column("coord_source", sa.Text(), nullable=True),
        schema="app",
    )
    # 제약 이름은 **접미사만** 넘긴다. naming_convention이 `ck_%(table_name)s_%(constraint_name)s`라
    # 전체 이름을 넘기면 테이블명이 두 번 붙는데(`20260824_0065` 선례가 그렇다), 이 테이블은 이름이
    # 길어 그 결과가 66자가 되고 PostgreSQL이 63자로 **잘라 버린다** — 소스에 적힌 이름과 실제
    # 이름이 달라져 나중에 DROP할 수 없다.
    op.create_check_constraint(
        "coord_source",
        "location_access_log_archive",
        _SOURCE_CHECK,
        schema="app",
    )
    _repin_boundary_contract(_BOUNDARY_CONTRACT_CHECK)


def downgrade() -> None:
    """forward-only — 아카이브의 `coord_source`는 그 행의 `content_hash`가 커밋한 값이다.

    `20260824_0065`와 같은 이유다. 컬럼을 DROP하면 이미 아카이브된 행은 원래 해시를 재현할 수
    없게 되고, 아카이브는 원본이 삭제된 뒤의 **유일한 사본**이라 복구할 곳도 없다.
    """
    raise RuntimeError(
        "20260825_0066 downgrade is forward-only: 아카이브 행의 content_hash가 coord_source를 "
        "커밋하고 있어 컬럼을 DROP하면 원본이 이미 삭제된 확인자료가 영구히 재검증 불가가 된다"
    )
