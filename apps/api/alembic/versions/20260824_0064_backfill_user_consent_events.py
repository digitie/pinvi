"""기존 동의 row에서 복원 가능한 이벤트를 백필한다 (T-326).

Revision ID: 20260824_0064
Revises: 20260824_0063
Create Date: 2026-08-24

현재 상태 테이블에서 복원할 수 있는 것은 두 가지뿐이다:
  - `withdrawn_at IS NULL`  → `agreed_at` 시점의 `agreed` 1건
  - `withdrawn_at IS NOT NULL` → `agreed_at`의 `agreed` + `withdrawn_at`의 `withdrawn` 2건

**복원할 수 없는 것**: 재동의로 이미 덮어써진 과거 사이클(철회 → 재동의). 그 시점 정보는 row에
남아 있지 않으므로 만들어내지 않는다 — 없는 이력을 추정해 넣으면 그것이야말로 거짓 증빙이다.
백필 행은 `source='backfill'`로 표시해 이후 실시간 기록과 구분한다.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260824_0064"
down_revision: str | None = "20260824_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0064'"
)
_PREV_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0063'"
)


def _repin_boundary_contract(check: str) -> None:
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
    # 멱등하게 — 이미 백필된 환경에서 재실행해도 중복 삽입하지 않는다.
    # 두 이벤트를 한 문장(UNION ALL)으로 넣는 이유는 스냅샷 일관성이다. 문장을 나누면 각 문장이
    # 새 스냅샷을 떠서, 그 사이에 커밋된 철회/재동의를 두 문장이 서로 다르게 본다.
    op.execute(
        """
        INSERT INTO app.user_consent_events
            (user_id, consent_type, version, event, source, occurred_at)
        SELECT user_id, consent_type, version, event, 'backfill', occurred_at
        FROM (
            SELECT c.user_id, c.consent_type, c.version, 'agreed' AS event, c.agreed_at AS occurred_at
            FROM app.user_consents c
            UNION ALL
            SELECT c.user_id, c.consent_type, c.version, 'withdrawn', c.withdrawn_at
            FROM app.user_consents c
            WHERE c.withdrawn_at IS NOT NULL
        ) AS restored
        WHERE NOT EXISTS (
            SELECT 1 FROM app.user_consent_events e
            WHERE e.user_id = restored.user_id
              AND e.consent_type = restored.consent_type
              AND e.event = restored.event
              AND e.source = 'backfill'
        )
        """
    )
    _repin_boundary_contract(_BOUNDARY_CONTRACT_CHECK)


def downgrade() -> None:
    """**증빙 행을 지우지 않는다** — head pin만 되돌린다.

    백필 행을 DELETE하면 이 마이그레이션은 자기 upgrade의 역연산이 되지 못한다: upgrade는 그때의
    **현재 상태**에서 이벤트를 재유도하는데, 그 사이 재동의가 일어났다면 원래 시점을 복원할 수 없다
    (`record_consents`가 상태 row를 in-place로 덮어쓰기 때문이다). 즉 down→up 왕복이 증빙을
    조용히 바꾼다.

    upgrade가 `NOT EXISTS`로 멱등하므로 이 함수는 아무것도 지우지 않아도 왕복이 성립한다.
    이 저장소가 증빙을 폐기하는 downgrade를 fail-close시켜 온 선례(`0055`~`0061`)와도 같은 방향이다.
    """
    _repin_boundary_contract(_PREV_BOUNDARY_CONTRACT_CHECK)
