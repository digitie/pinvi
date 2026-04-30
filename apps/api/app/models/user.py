from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.session import UserSession
    from app.models.trip import Trip


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "account_status IN "
            "('pending_email_verification', 'invited', 'active', 'disabled', 'deleted')",
            name=conv("ck_users_account_status"),
        ),
        CheckConstraint(
            "system_role IN ('admin', 'planner', 'participant')",
            name=conv("ck_users_system_role"),
        ),
        CheckConstraint(
            "birth_year_month IS NULL OR birth_year_month ~ '^[0-9]{6}$'",
            name=conv("ck_users_birth_year_month_format"),
        ),
        CheckConstraint(
            "gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'no_answer')",
            name=conv("ck_users_gender"),
        ),
        Index("ix_users_account_status", "account_status"),
        Index("ix_users_system_role", "system_role"),
        Index("ix_users_residence_sigungu_code", "residence_sigungu_code"),
        Index("ix_users_created_by_user_id", "created_by_user_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_email_verification",
    )
    system_role: Mapped[str] = mapped_column(String(32), nullable=False, default="planner")
    nickname: Mapped[str | None] = mapped_column(String(80))
    name: Mapped[str | None] = mapped_column(String(80))
    birth_year_month: Mapped[str | None] = mapped_column(String(6))
    gender: Mapped[str | None] = mapped_column(String(32))
    residence_sigungu_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_users_residence_sigungu_code",
            ondelete="SET NULL",
        ),
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_users_created_by_user_id", ondelete="SET NULL"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_privileged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    trips: Mapped[list[Trip]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    email_verification_tokens: Mapped[list[EmailVerificationToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class EmailVerificationToken(TimestampMixin, Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('register', 'invite_accept', 'email_change')",
            name=conv("ck_email_verification_tokens_purpose"),
        ),
        Index("ix_email_verification_tokens_user_id", "user_id"),
        Index("ix_email_verification_tokens_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_email_verification_tokens_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="email_verification_tokens")
