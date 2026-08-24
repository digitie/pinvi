"""보존 아카이브도 append-only로 잠근다.

Revision ID: 20260825_0067
Revises: 20260825_0066
Create Date: 2026-08-25

`trg_location_access_log_append_only`(`20260602_0003`)는 **원본 테이블에만** 걸려 있다. 그런데
retention이 실행되면 원본은 삭제되고 `location_access_log_archive`가 확인자료의 **유일한 사본**이
된다 — 보호가 가장 필요해지는 순간에 그 테이블은 UPDATE/DELETE에 열려 있었다(T-336).

가드 함수는 새로 만들지 않고 `app.audit_log_append_only()`를 그대로 쓴다. `20260628_0029`가 넣은
retention 예외 절이 `TG_TABLE_NAME = 'location_access_log'`로 좁혀져 있어서, retention 트랜잭션이
`app.retention_location_delete_allowed`를 켠 그 순간에도 **아카이브 DELETE는 자동으로 완전 차단**된다.
별도 함수를 만들면 이 성질을 손으로 다시 맞춰야 한다.

`ENABLE ALWAYS`를 쓰는 이유: 아카이브는 위치정보법 제16조 확인자료의 유일한 사본이므로,
`session_replication_role = replica`로 트리거를 우회하는 경로(복제·관리 작업)에서도 보호가 유지돼야
한다. M05 evidence 테이블(`20260821_0060`/`0061`)이 같은 판단으로 같은 패턴을 쓴다.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260825_0067'"
)
_PREV_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260825_0066'"
)

revision: str = "20260825_0067"
down_revision: str | None = "20260825_0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "app.location_access_log_archive"
_ROW_TRIGGER = "trg_location_access_log_archive_append_only"
_TRUNCATE_TRIGGER = "trg_location_access_log_archive_truncate_append_only"


def _repin_boundary_contract(check: str) -> None:
    """새 head에서만 final boundary가 열리도록 DB/service pin을 함께 전진시킨다."""
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
    # `DROP IF EXISTS`는 장식이 아니다. `test_existing_0053_database_receives_0054_undelete_lock`이
    # `alembic_version`을 되돌려 마이그레이션을 **재생**하는데, 아카이브 테이블은 0029 생성이라 그
    # 하네스의 DROP 목록에 없다 — 순수 CREATE는 "already exists"로 실패한다.
    op.execute(f"DROP TRIGGER IF EXISTS {_ROW_TRIGGER} ON {_TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {_TRUNCATE_TRIGGER} ON {_TABLE}")

    op.execute(
        f"CREATE TRIGGER {_ROW_TRIGGER} BEFORE UPDATE OR DELETE ON {_TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION app.audit_log_append_only()"
    )
    op.execute(
        f"CREATE TRIGGER {_TRUNCATE_TRIGGER} BEFORE TRUNCATE ON {_TABLE} "
        "FOR EACH STATEMENT EXECUTE FUNCTION app.audit_log_append_only()"
    )
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ALWAYS TRIGGER {_ROW_TRIGGER}")
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ALWAYS TRIGGER {_TRUNCATE_TRIGGER}")

    _repin_boundary_contract(_BOUNDARY_CONTRACT_CHECK)


def downgrade() -> None:
    """되돌릴 수 있다 — 이 리비전은 데이터를 만들지도 바꾸지도 않는다.

    `20260825_0066`과 달리 forward-only로 잠글 이유가 없다. 보호를 푸는 것이지 증거를 잃는 것이
    아니기 때문이다.
    """
    op.execute(f"DROP TRIGGER IF EXISTS {_TRUNCATE_TRIGGER} ON {_TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {_ROW_TRIGGER} ON {_TABLE}")
    _repin_boundary_contract(_PREV_BOUNDARY_CONTRACT_CHECK)
