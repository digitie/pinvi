"""`app.user_oauth_identities` + `app.oauth_login_states` — Google/Naver/Kakao."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class UserOAuthIdentity(Base, TimestampMixin):
    __tablename__ = "user_oauth_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_user_id", name="uq_user_oauth_identities_provider_subject"
        ),
        UniqueConstraint("user_id", "provider", name="uq_user_oauth_identities_user_provider"),
    )

    identity_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(320))
    provider_email_verified: Mapped[bool | None] = mapped_column(Boolean)
    display_name_snapshot: Mapped[str | None] = mapped_column(String(120))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthLoginState(Base):
    __tablename__ = "oauth_login_states"

    state_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    nonce_hash: Mapped[str | None] = mapped_column(String(128))
    pkce_code_verifier_hash: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="login")
    return_to_path: Mapped[str | None] = mapped_column(String(255))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="CASCADE"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class OAuthMobileExchange(Base):
    """모바일 OAuth 1회용 교환 코드.

    웹은 callback에서 쿠키를 세팅하지만(ADR-032), 모바일은 cookie를 못 쓴다. Google callback이
    `pinvi://oauth?code=<code>` 딥링크로 리다이렉트하고, 앱이 그 code를
    `POST /mobile/auth/oauth/exchange`로 토큰과 교환한다. 토큰을 URL에 싣지 않도록 code→user_id만
    저장하고(세션은 exchange 시점에 발급), 짧은 TTL + 1회 소비로 막는다.
    """

    __tablename__ = "oauth_mobile_exchanges"

    code_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
