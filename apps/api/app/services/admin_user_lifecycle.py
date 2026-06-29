"""Admin 사용자 lifecycle 액션."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_opaque_token
from app.models.oauth_identity import UserOAuthIdentity
from app.models.session import UserSession
from app.models.user import User
from app.models.user_email_verification import UserEmailVerification
from app.services.admin_users import (
    AdminUserNotFoundError,
    AdminUserPermissionError,
    AdminUserRoleTransitionError,
    normalize_roles,
)
from app.services.auth_session import revoke_active_user_sessions
from app.services.email_service import enqueue_password_reset_email, enqueue_verification_email

SIGNUP_VERIFICATION_TTL_HOURS = 24
BLOCKED_AUTH_STATUSES = {"disabled", "pending_delete", "deleted"}
PRIVILEGED_ROLES = {"admin", "operator", "cpo"}


@dataclass(frozen=True)
class AdminUserLifecycleResult:
    user: User
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    revoked_session_ids: list[uuid.UUID] = field(default_factory=list)
    verification_id: uuid.UUID | None = None
    email_dispatched: bool | None = None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def user_lifecycle_state(user: User) -> dict[str, Any]:
    return {
        "status": user.status,
        "is_active": user.is_active,
        "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
        "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
        "access_token_version": user.access_token_version or 0,
        "has_password": bool(user.password_hash),
    }


def _profile_restored_status(user: User) -> str:
    if user.email_verified_at is None:
        return "pending_verification"
    if user.nickname:
        return "active"
    return "pending_profile"


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def _get_user(db: AsyncSession, *, user_id: uuid.UUID) -> User:
    user = await db.scalar(select(User).where(User.user_id == user_id))
    if user is None:
        raise AdminUserNotFoundError("Not found.")
    return user


async def _active_session_ids(db: AsyncSession, *, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(UserSession.session_id).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )
    return list(result.scalars())


def _assert_not_self(*, user_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    if user_id == actor_id:
        raise AdminUserNotFoundError("Not found.")


def _assert_not_privileged(user: User) -> None:
    if PRIVILEGED_ROLES.intersection(normalize_roles(user.roles)):
        raise AdminUserPermissionError("권한 계정은 role 회수 후 lifecycle 액션을 수행해야 합니다.")


async def list_user_sessions(db: AsyncSession, *, user_id: uuid.UUID) -> list[UserSession]:
    await _get_user(db, user_id=user_id)
    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == user_id)
        .order_by(UserSession.created_at.desc(), UserSession.session_id.desc())
    )
    return list(result.scalars())


async def revoke_user_session_by_id(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> AdminUserLifecycleResult:
    user = await _get_user(db, user_id=user_id)
    session = await db.scalar(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.session_id == session_id,
        )
    )
    if session is None:
        raise AdminUserNotFoundError("Session not found.")

    before_state = {
        "session_id": str(session.session_id),
        "revoked_at": _dt(session.revoked_at),
        "access_token_version": user.access_token_version or 0,
    }
    revoked_ids: list[uuid.UUID] = []
    if session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        user.access_token_version = (user.access_token_version or 0) + 1
        revoked_ids.append(session.session_id)
    after_state = {
        "session_id": str(session.session_id),
        "revoked_at": _dt(session.revoked_at),
        "access_token_version": user.access_token_version or 0,
    }
    return AdminUserLifecycleResult(
        user=user,
        before_state=before_state,
        after_state=after_state,
        revoked_session_ids=revoked_ids,
    )


async def revoke_all_user_sessions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> AdminUserLifecycleResult:
    user = await _get_user(db, user_id=user_id)
    revoked_ids = await _active_session_ids(db, user_id=user_id)
    before_state = {
        "active_session_count": len(revoked_ids),
        "access_token_version": user.access_token_version or 0,
    }
    if revoked_ids:
        user.access_token_version = (user.access_token_version or 0) + 1
    await revoke_active_user_sessions(db, user_id=user_id, revoked_at=datetime.now(UTC))
    after_state = {
        "revoked_session_ids": [str(session_id) for session_id in revoked_ids],
        "access_token_version": user.access_token_version or 0,
    }
    return AdminUserLifecycleResult(
        user=user,
        before_state=before_state,
        after_state=after_state,
        revoked_session_ids=revoked_ids,
    )


async def resend_user_verification(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> AdminUserLifecycleResult:
    user = await _get_user(db, user_id=user_id)
    if user.email_verified_at is not None:
        raise AdminUserRoleTransitionError("이미 이메일 인증이 완료된 사용자입니다.")
    if user.status in BLOCKED_AUTH_STATUSES:
        raise AdminUserRoleTransitionError("현재 상태에서는 인증 메일을 재발송할 수 없습니다.")

    before_state = user_lifecycle_state(user)
    now = datetime.now(UTC)
    await db.execute(
        update(UserEmailVerification)
        .where(
            UserEmailVerification.user_id == user.user_id,
            UserEmailVerification.purpose == "signup",
            UserEmailVerification.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = generate_opaque_token(32)
    verification = UserEmailVerification(
        user_id=user.user_id,
        token_hash=_hash_token(raw_token),
        purpose="signup",
        expires_at=now + timedelta(hours=SIGNUP_VERIFICATION_TTL_HOURS),
    )
    db.add(verification)
    await db.flush()
    dispatched = await enqueue_verification_email(
        db,
        user_id=user.user_id,
        to_email=user.email,
        token=raw_token,
        expires_in_hours=SIGNUP_VERIFICATION_TTL_HOURS,
    )
    after_state = {
        **user_lifecycle_state(user),
        "verification_id": str(verification.verification_id),
        "email_dispatched": dispatched,
    }
    return AdminUserLifecycleResult(
        user=user,
        before_state=before_state,
        after_state=after_state,
        verification_id=verification.verification_id,
        email_dispatched=dispatched,
    )


async def force_password_reset(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> AdminUserLifecycleResult:
    user = await _get_user(db, user_id=user_id)
    if user.email_verified_at is None:
        raise AdminUserRoleTransitionError(
            "이메일 미인증 사용자는 비밀번호 재설정을 강제할 수 없습니다."
        )
    if user.status in BLOCKED_AUTH_STATUSES:
        raise AdminUserRoleTransitionError("현재 상태에서는 비밀번호 재설정을 강제할 수 없습니다.")

    before_state = user_lifecycle_state(user)
    revoked_ids = await _active_session_ids(db, user_id=user.user_id)
    now = datetime.now(UTC)
    await db.execute(
        update(UserEmailVerification)
        .where(
            UserEmailVerification.user_id == user.user_id,
            UserEmailVerification.purpose == "password_reset",
            UserEmailVerification.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = generate_opaque_token(32)
    verification = UserEmailVerification(
        user_id=user.user_id,
        token_hash=_hash_token(raw_token),
        purpose="password_reset",
        expires_at=now + timedelta(hours=1),
    )
    db.add(verification)
    user.password_hash = None
    user.access_token_version = (user.access_token_version or 0) + 1
    await revoke_active_user_sessions(db, user_id=user.user_id, revoked_at=now)
    await db.flush()
    dispatched = await enqueue_password_reset_email(
        db,
        user_id=user.user_id,
        to_email=user.email,
        token=raw_token,
    )
    after_state = {
        **user_lifecycle_state(user),
        "verification_id": str(verification.verification_id),
        "email_dispatched": dispatched,
        "revoked_session_ids": [str(session_id) for session_id in revoked_ids],
    }
    return AdminUserLifecycleResult(
        user=user,
        before_state=before_state,
        after_state=after_state,
        revoked_session_ids=revoked_ids,
        verification_id=verification.verification_id,
        email_dispatched=dispatched,
    )


async def reactivate_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> AdminUserLifecycleResult:
    _assert_not_self(user_id=user_id, actor_id=actor_id)
    user = await _get_user(db, user_id=user_id)
    if user.status not in {"disabled", "pending_delete"}:
        raise AdminUserRoleTransitionError("비활성 또는 삭제 대기 사용자만 재활성화할 수 있습니다.")

    before_state = user_lifecycle_state(user)
    user.status = _profile_restored_status(user)
    user.is_active = True
    user.deleted_at = None
    user.access_token_version = (user.access_token_version or 0) + 1
    return AdminUserLifecycleResult(
        user=user,
        before_state=before_state,
        after_state=user_lifecycle_state(user),
    )


async def schedule_user_delete(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> AdminUserLifecycleResult:
    _assert_not_self(user_id=user_id, actor_id=actor_id)
    user = await _get_user(db, user_id=user_id)
    _assert_not_privileged(user)
    if user.status in {"pending_delete", "deleted"}:
        raise AdminUserRoleTransitionError("이미 삭제 대기 또는 삭제 완료 상태입니다.")

    before_state = user_lifecycle_state(user)
    revoked_ids = await _active_session_ids(db, user_id=user.user_id)
    now = datetime.now(UTC)
    user.status = "pending_delete"
    user.is_active = False
    user.deleted_at = now
    user.access_token_version = (user.access_token_version or 0) + 1
    await revoke_active_user_sessions(db, user_id=user.user_id, revoked_at=now)
    after_state = {
        **user_lifecycle_state(user),
        "revoked_session_ids": [str(session_id) for session_id in revoked_ids],
    }
    return AdminUserLifecycleResult(
        user=user,
        before_state=before_state,
        after_state=after_state,
        revoked_session_ids=revoked_ids,
    )


async def anonymize_user_now(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> AdminUserLifecycleResult:
    _assert_not_self(user_id=user_id, actor_id=actor_id)
    user = await _get_user(db, user_id=user_id)
    _assert_not_privileged(user)
    if user.status == "deleted" and user.email.startswith("deleted+"):
        raise AdminUserRoleTransitionError("이미 anonymize 완료된 사용자입니다.")

    before_state = user_lifecycle_state(user)
    revoked_ids = await _active_session_ids(db, user_id=user.user_id)
    now = datetime.now(UTC)
    oauth_result = await db.execute(
        delete(UserOAuthIdentity)
        .where(UserOAuthIdentity.user_id == user.user_id)
        .returning(UserOAuthIdentity.identity_id)
    )
    deleted_oauth_identity_ids = list(oauth_result.scalars())

    user.email = f"deleted+{user.user_id}@deleted.pinvi.local"
    user.password_hash = None
    user.nickname = None
    user.avatar_url = None
    user.avatar_kind = "default"
    user.avatar_bucket = None
    user.avatar_storage_key = None
    user.avatar_content_type = None
    user.avatar_byte_size = None
    user.avatar_updated_at = None
    user.attachment_max_upload_bytes_override = None
    user.trip_attachment_quota_bytes_override = None
    user.user_attachment_quota_bytes_override = None
    user.gender = None
    user.birth_year_month = None
    user.residence_sigungu_code = None
    user.email_verified_at = None
    user.email_status = "suppressed"
    user.status = "deleted"
    user.is_active = False
    user.deleted_at = user.deleted_at or now
    user.access_token_version = (user.access_token_version or 0) + 1
    await revoke_active_user_sessions(db, user_id=user.user_id, revoked_at=now)

    after_state = {
        **user_lifecycle_state(user),
        "anonymized": True,
        "deleted_oauth_identity_count": len(deleted_oauth_identity_ids),
        "revoked_session_ids": [str(session_id) for session_id in revoked_ids],
    }
    return AdminUserLifecycleResult(
        user=user,
        before_state=before_state,
        after_state=after_state,
        revoked_session_ids=revoked_ids,
    )


async def self_delete_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> AdminUserLifecycleResult:
    user = await _get_user(db, user_id=user_id)
    _assert_not_privileged(user)
    if user.status in {"pending_delete", "deleted"}:
        raise AdminUserRoleTransitionError("이미 삭제 대기 또는 삭제 완료 상태입니다.")

    before_state = user_lifecycle_state(user)
    revoked_ids = await _active_session_ids(db, user_id=user.user_id)
    now = datetime.now(UTC)
    user.status = "pending_delete"
    user.is_active = False
    user.deleted_at = now
    user.access_token_version = (user.access_token_version or 0) + 1
    await revoke_active_user_sessions(db, user_id=user.user_id, revoked_at=now)
    after_state = {
        **user_lifecycle_state(user),
        "revoked_session_ids": [str(session_id) for session_id in revoked_ids],
    }
    return AdminUserLifecycleResult(
        user=user,
        before_state=before_state,
        after_state=after_state,
        revoked_session_ids=revoked_ids,
    )
