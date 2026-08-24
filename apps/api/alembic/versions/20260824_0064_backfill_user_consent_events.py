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
    op.execute(
        """
        INSERT INTO app.user_consent_events
            (user_id, consent_type, version, event, source, occurred_at)
        SELECT c.user_id, c.consent_type, c.version, 'agreed', 'backfill', c.agreed_at
        FROM app.user_consents c
        WHERE NOT EXISTS (
            SELECT 1 FROM app.user_consent_events e
            WHERE e.user_id = c.user_id
              AND e.consent_type = c.consent_type
              AND e.event = 'agreed'
              AND e.source = 'backfill'
        )
        """
    )
    op.execute(
        """
        INSERT INTO app.user_consent_events
            (user_id, consent_type, version, event, source, occurred_at)
        SELECT c.user_id, c.consent_type, c.version, 'withdrawn', 'backfill', c.withdrawn_at
        FROM app.user_consents c
        WHERE c.withdrawn_at IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM app.user_consent_events e
            WHERE e.user_id = c.user_id
              AND e.consent_type = c.consent_type
              AND e.event = 'withdrawn'
              AND e.source = 'backfill'
        )
        """
    )
    _repin_boundary_contract(_BOUNDARY_CONTRACT_CHECK)


def downgrade() -> None:
    """백필 행만 지운다. 실시간으로 기록된 이벤트는 건드리지 않는다."""
    op.execute("DELETE FROM app.user_consent_events WHERE source = 'backfill'")
    _repin_boundary_contract(_PREV_BOUNDARY_CONTRACT_CHECK)
