"""확정 takedown 첨부의 증거 보존 시작 시각.

nullable 열 하나와 기존 확정 takedown hold의 시작 시각 backfill이라 forward-safe다. 이전 코드는 이 열을
읽지 않으므로 rotation 중에는 hold 파일을 계속 보존(삭제 안 함)하고 용량에 계산할 뿐이다.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261107_0107"
down_revision: str | None = "20261106_0106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIOR = "contract_version = 'pinvi-cache-target-final-boundary/v1' AND status = 'succeeded' AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102' OR schema_revision = '20261105_0103' OR schema_revision = '20261105_0104' OR schema_revision = '20261105_0105' OR schema_revision = '20261106_0106')"
_CHECK = _PRIOR[:-1] + " OR schema_revision = '20261107_0107')"


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
    op.add_column(
        "curated_plan_attachments",
        sa.Column("evidence_hold_started_at", sa.DateTime(timezone=True)),
        schema="app",
    )
    # 지금 hold 중인 첨부에 takedown 조치 이력이 있으면 마지막 takedown 시각부터 보존 기간을 센다.
    # 신고 상태가 그 뒤 이의제기·거절로 바뀌었어도 런타임과 같이 takedown 시각을 쓴다(restore는 hold를
    # 이미 풀었으므로 대상이 아니다). 열린 신고가 있으면 런타임이 그 신고가 끝날 때까지 지우지 않는다.
    op.execute(
        """
        UPDATE app.curated_plan_attachments AS a
        SET evidence_hold_started_at = r.taken_down_at
        FROM (
            SELECT cr.target_id, max(act.created_at) AS taken_down_at
            FROM app.content_moderation_actions AS act
            JOIN app.content_reports AS cr ON cr.report_id = act.report_id
            WHERE cr.target_type = 'attachment' AND act.action = 'takedown'
            GROUP BY cr.target_id
        ) AS r
        WHERE a.attachment_id = r.target_id
          AND a.moderation_hold
          AND a.purged_at IS NULL
          AND a.evidence_hold_started_at IS NULL
        """
    )
    _boundary(_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM app.ktm_cache_target_boundary_audits WHERE schema_revision = '20261107_0107'"
    )
    _boundary(_PRIOR)
    op.drop_column("curated_plan_attachments", "evidence_hold_started_at", schema="app")
