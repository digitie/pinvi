"""로그인 유지(remember me) — refresh session 계열·절대 만료·재사용 감지 컬럼.

- `user_sessions.family_id`: 로그인 1회가 만든 refresh 회전 계열. 회전하면 새 row가 같은 값을 잇는다.
- `user_sessions.remember_me`: "로그인 유지"로 발급된 계열인지. 회전해도 그대로 잇는다.
- `user_sessions.absolute_expires_at`: 그 계열의 절대 만료(로그인 + `pinvi_remember_me_days`). 회전이 이 시각을
  넘겨 연장하지 않는다 — 7일 미끄럼 세션도 이 상한을 넘지 못한다.
- `user_sessions.rotated_at`: 회전으로 폐기된 row에만 찍는다. 회전된 토큰이 유예 시간 뒤 다시 쓰이면 계열 전체를
  폐기한다(재사용 감지).
- `oauth_login_states.remember_me`·`oauth_mobile_exchanges.remember_me`: OAuth start에서 고른 값을 callback·
  모바일 교환까지 서버 쪽에 싣는다(callback 쿼리 값은 믿지 않는다).

기존 row: `family_id`는 row마다 새 uuid, `remember_me`는 false, `absolute_expires_at`은 그 row의 `created_at`
(= 마지막 회전 시각) + 365일이다. 로그인 시각을 모르므로 정책 최댓값으로 시작하고, 적용 시각 하나로 몰지 않아
1년 뒤 기존 사용자가 한꺼번에 다시 로그인하지 않게 한다. 7일 미끄럼 만료는 그대로 먼저 걸리므로 지금 로그인한
사용자는 로그아웃되지 않는다.

잠금: `user_sessions`는 살아 있는 세션 + 폐기/만료 30일 이내 row뿐이라 작다. `gen_random_uuid()` 기본값(volatile)과
backfill UPDATE가 표를 다시 쓰는 동안 ACCESS EXCLUSIVE를 쥐므로, 긴 트랜잭션 뒤에 줄 서서 로그인·갱신을 막지 않게
`lock_timeout`을 5초로 둔다(초과하면 migration이 실패하고 API 기동이 재시도한다).

forward-safe: 새 컬럼은 모두 기본값이 있어 이전 코드(0109)의 INSERT도 그대로 성공한다. 단 0110을 둔 채 코드만
0109로 되돌리면 그동안의 회전이 기본값 row를 만들어 로그인 유지가 7일 세션으로 풀리고 재사용 감지가 끊긴다
(`docs/api/auth.md` §3.5).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "20261127_0110"
down_revision: str | None = "20261117_0109"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIOR = "contract_version = 'pinvi-cache-target-final-boundary/v1' AND status = 'succeeded' AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102' OR schema_revision = '20261105_0103' OR schema_revision = '20261105_0104' OR schema_revision = '20261105_0105' OR schema_revision = '20261106_0106' OR schema_revision = '20261107_0107' OR schema_revision = '20261116_0108' OR schema_revision = '20261117_0109')"
_CHECK = _PRIOR[:-1] + " OR schema_revision = '20261127_0110')"


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
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column(
        "user_sessions",
        sa.Column(
            "family_id",
            pg.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        schema="app",
    )
    op.add_column(
        "user_sessions",
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="app",
    )
    op.add_column(
        "user_sessions",
        sa.Column(
            "absolute_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            # 서비스는 늘 명시 값을 넣는다. 이 기본값은 기존 row 채움 + 직접 INSERT 안전망(정책 최댓값)이다.
            server_default=sa.text("(now() + interval '365 days')"),
        ),
        schema="app",
    )
    op.add_column(
        "user_sessions",
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        schema="app",
    )
    op.execute(
        "UPDATE app.user_sessions "
        "SET absolute_expires_at = GREATEST(created_at + interval '365 days', expires_at)"
    )
    op.create_check_constraint(
        op.f("ck_user_sessions_expires_within_absolute"),
        "user_sessions",
        "expires_at <= absolute_expires_at",
        schema="app",
    )
    op.create_index(
        op.f("ix_user_sessions_family_active"),
        "user_sessions",
        ["family_id"],
        schema="app",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.add_column(
        "oauth_login_states",
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="app",
    )
    op.add_column(
        "oauth_mobile_exchanges",
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="app",
    )
    _boundary(_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM app.ktm_cache_target_boundary_audits WHERE schema_revision = '20261127_0110'"
    )
    _boundary(_PRIOR)
    op.drop_column("oauth_mobile_exchanges", "remember_me", schema="app")
    op.drop_column("oauth_login_states", "remember_me", schema="app")
    op.drop_index(op.f("ix_user_sessions_family_active"), table_name="user_sessions", schema="app")
    op.drop_constraint(
        op.f("ck_user_sessions_expires_within_absolute"),
        "user_sessions",
        schema="app",
        type_="check",
    )
    op.drop_column("user_sessions", "rotated_at", schema="app")
    op.drop_column("user_sessions", "absolute_expires_at", schema="app")
    op.drop_column("user_sessions", "remember_me", schema="app")
    op.drop_column("user_sessions", "family_id", schema="app")
