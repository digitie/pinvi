"""응답 유실 뒤 restore-fence CAS 재실행 영수증을 추가한다.

Restore principal의 POST는 Map에서 성공한 뒤 응답만 유실될 수 있다. 이 migration은
Idempotency-Key마다 최초 GET의 raw ETag/control tuple을 durable하게 보존한다. 따라서
재실행은 새 stream GET로 stale 판정을 내리지 않고 정확히 같은 If-Match와 body를 Map에
다시 보낼 수 있다. terminal receipt는 append-only이며, pending receipt도 입력 tuple을
변경할 수 없다.

동반: T-VN-41 영수증 table이 final boundary의 writer surface에 추가되므로 head pin과
boundary audit CHECK를 0050으로 의식적으로 함께 재고정한다.

Revision ID: 20260811_0050
Revises: 20260804_0049
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260811_0050"
down_revision: str | None = "20260804_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK_TEMPLATE = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '{revision}'"
)

_ATTEMPT_IMMUTABLE_FUNCTION = """
CREATE FUNCTION app.guard_ktm_cache_target_restore_fence_attempt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'cache target restore fence attempt is append-only' USING ERRCODE = '55000';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending'
           OR NEW.response_status IS NOT NULL
           OR NEW.response_etag IS NOT NULL
           OR NEW.response_body IS NOT NULL
           OR NEW.completed_at IS NOT NULL
        THEN
            RAISE EXCEPTION 'cache target restore fence attempt must start pending'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'completed cache target restore fence attempt is immutable' USING ERRCODE = '55000';
    END IF;

    IF NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.consumer_id IS DISTINCT FROM OLD.consumer_id
       OR NEW.external_system IS DISTINCT FROM OLD.external_system
       OR NEW.expected_restore_epoch IS DISTINCT FROM OLD.expected_restore_epoch
       OR NEW.expected_control_version IS DISTINCT FROM OLD.expected_control_version
       OR NEW.stream_etag IS DISTINCT FROM OLD.stream_etag
       OR NEW.reason IS DISTINCT FROM OLD.reason
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'cache target restore fence pre-CAS tuple is immutable' USING ERRCODE = '55000';
    END IF;

    IF NEW.status <> 'completed' THEN
        RAISE EXCEPTION 'cache target restore fence attempt may only complete' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$
"""


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
    op.create_table(
        "ktm_cache_target_restore_fence_attempts",
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_id", sa.Text(), nullable=False),
        sa.Column("external_system", sa.Text(), nullable=False, server_default="pinvi"),
        sa.Column("expected_restore_epoch", sa.BigInteger(), nullable=False),
        sa.Column("expected_control_version", sa.BigInteger(), nullable=False),
        sa.Column("stream_etag", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_etag", sa.Text(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "external_system = 'pinvi'",
            name="ck_ktm_ct_restore_attempt_system",
        ),
        sa.CheckConstraint(
            "expected_restore_epoch > 0 AND expected_control_version > 0",
            name="ck_ktm_ct_restore_attempt_control",
        ),
        sa.CheckConstraint(
            "btrim(consumer_id) = consumer_id AND consumer_id <> '' "
            "AND btrim(stream_etag) = stream_etag AND stream_etag <> '' "
            "AND btrim(reason) = reason AND char_length(reason) BETWEEN 1 AND 1000",
            name="ck_ktm_ct_restore_attempt_input",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND response_status IS NULL AND response_etag IS NULL "
            "AND response_body IS NULL AND completed_at IS NULL) OR "
            "(status = 'completed' AND response_status IN (200, 201) "
            "AND btrim(response_etag) = response_etag AND response_etag <> '' "
            "AND jsonb_typeof(response_body) = 'object' AND completed_at IS NOT NULL)",
            name="ck_ktm_ct_restore_attempt_terminal",
        ),
        sa.ForeignKeyConstraint(
            ["consumer_id"],
            ["app.ktm_cache_target_consumers.consumer_id"],
            name="fk_ktm_ct_restore_attempt_consumer",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "idempotency_key", name="pk_ktm_cache_target_restore_fence_attempts"
        ),
        schema="app",
    )
    op.execute(sa.text(_ATTEMPT_IMMUTABLE_FUNCTION))
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_ct_restore_attempt_row_guard "
            "BEFORE INSERT OR UPDATE OR DELETE ON app.ktm_cache_target_restore_fence_attempts "
            "FOR EACH ROW EXECUTE FUNCTION app.guard_ktm_cache_target_restore_fence_attempt()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_ct_restore_attempt_truncate_guard "
            "BEFORE TRUNCATE ON app.ktm_cache_target_restore_fence_attempts "
            "FOR EACH STATEMENT EXECUTE FUNCTION "
            "app.guard_ktm_cache_target_restore_fence_attempt()"
        )
    )
    _repin_boundary_contract("20260811_0050")


def downgrade() -> None:
    _repin_boundary_contract("20260804_0049")
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_ktm_ct_restore_attempt_truncate_guard "
            "ON app.ktm_cache_target_restore_fence_attempts"
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_ktm_ct_restore_attempt_row_guard "
            "ON app.ktm_cache_target_restore_fence_attempts"
        )
    )
    op.drop_table("ktm_cache_target_restore_fence_attempts", schema="app")
    op.execute(sa.text("DROP FUNCTION app.guard_ktm_cache_target_restore_fence_attempt()"))
