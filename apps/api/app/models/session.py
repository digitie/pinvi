"""`app.user_sessions` — refresh 토큰 hash + IP/UA + 회전 계열(로그인 유지, 0110)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class UserSession(Base, TimestampMixin):
    __tablename__ = "user_sessions"
    __table_args__ = (
        # naming convention이 접두를 붙여 DB 이름은 `ck_user_sessions_expires_within_absolute`(0110).
        CheckConstraint("expires_at <= absolute_expires_at", name="expires_within_absolute"),
        Index(
            "ix_user_sessions_family_active",
            "family_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    session_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 로그인 1회가 만든 refresh 회전 계열. 회전한 새 row가 같은 값을 잇는다(재사용 감지 시 계열째 폐기).
    family_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    # "로그인 유지"로 발급된 계열인지. 회전해도 잇는다.
    remember_me: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # 계열의 절대 만료(로그인 + `pinvi_remember_me_days`). 회전은 이 시각을 넘겨 연장하지 않는다.
    # 서비스는 늘 명시 값을 넣는다 — 기본값은 직접 INSERT 안전망(정책 최댓값)이다.
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("(now() + interval '365 days')"),
    )
    # 회전으로 폐기된 row에만 찍는다(로그아웃·관리자 폐기와 구분).
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(INET)
