"""PinVi one-shot admin bootstrap 도메인 로직."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.core.time import utc_now
from app.models.user import User
from app.schemas.auth import normalize_login_identifier
from app.services.auth_session import revoke_active_user_sessions

BootstrapAdminAction = Literal["created", "updated", "unchanged"]
MAX_CREDENTIAL_FILE_BYTES = 4096
FIXED_TEST_USER_ROLES = ["user"]


class BootstrapAdminError(Exception):
    """Secret-free bootstrap failure surfaced by the one-shot CLI."""

    def __init__(self, code: str, phase: str) -> None:
        super().__init__(code)
        self.code = code
        self.phase = phase


@dataclass(frozen=True)
class BootstrapAdminCredential:
    email: str
    password: str

    @property
    def email_sha256(self) -> str:
        return hashlib.sha256(self.email.casefold().encode("utf-8")).hexdigest()

    @property
    def binding_sha256(self) -> str:
        return hashlib.sha256(
            self.email.encode("utf-8") + b"\0" + self.password.encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class BootstrapAdminResult:
    action: BootstrapAdminAction
    admin_email_sha256: str


class _CredentialPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _roles_with_admin(roles: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for role in [*(roles or []), "user", "admin"]:
        if role not in seen:
            seen.add(role)
            result.append(role)
    return result


def _validate_credential_file_stat(file_stat: os.stat_result) -> None:
    if not stat.S_ISREG(file_stat.st_mode):
        raise BootstrapAdminError("credential_file_not_regular", "credential_file")
    if file_stat.st_uid != os.geteuid():
        raise BootstrapAdminError("credential_file_owner_mismatch", "credential_file")
    if stat.S_IMODE(file_stat.st_mode) != 0o600:
        raise BootstrapAdminError("credential_file_mode_invalid", "credential_file")
    if file_stat.st_nlink != 1:
        raise BootstrapAdminError("credential_file_link_count_invalid", "credential_file")
    if file_stat.st_size <= 0 or file_stat.st_size > MAX_CREDENTIAL_FILE_BYTES:
        raise BootstrapAdminError("credential_file_size_invalid", "credential_file")


def _read_owner_only_file(path: str | Path) -> bytes:
    """Read a bounded, owner-only file without following symlinks."""

    credential_path = Path(path)
    if not credential_path.is_absolute():
        raise BootstrapAdminError("credential_file_path_invalid", "credential_file")

    try:
        before = os.lstat(credential_path)
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.ENOTDIR}:
            raise BootstrapAdminError("credential_file_missing", "credential_file") from None
        raise BootstrapAdminError("credential_file_unavailable", "credential_file") from None
    _validate_credential_file_stat(before)

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(credential_path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise BootstrapAdminError("credential_file_not_regular", "credential_file") from None
        raise BootstrapAdminError("credential_file_unavailable", "credential_file") from None

    try:
        after = os.fstat(fd)
        _validate_credential_file_stat(after)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise BootstrapAdminError("credential_file_changed", "credential_file")
        data = os.read(fd, MAX_CREDENTIAL_FILE_BYTES + 1)
    finally:
        os.close(fd)

    if len(data) > MAX_CREDENTIAL_FILE_BYTES:
        raise BootstrapAdminError("credential_file_size_invalid", "credential_file")
    return data


def _parse_credential_json[PayloadT: BaseModel](data: bytes, model: type[PayloadT]) -> PayloadT:
    try:
        raw = data.decode("utf-8")
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        return model.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ValidationError):
        raise BootstrapAdminError("credential_file_json_invalid", "credential_file") from None


def read_bootstrap_admin_credential_file(path: str | Path) -> BootstrapAdminCredential:
    """Read a bounded, owner-only credential JSON file without following symlinks."""

    credential = _parse_credential_json(_read_owner_only_file(path), _CredentialPayload)

    return BootstrapAdminCredential(
        email=str(credential.email).strip(),
        password=credential.password,
    )


async def ensure_bootstrap_admin(
    db: AsyncSession,
    *,
    credential: BootstrapAdminCredential,
) -> BootstrapAdminResult:
    """Create or repair the bootstrap admin account inside the caller transaction.

    The caller owns migration, schema-head verification, commit, rollback, and output
    redaction. This function never reads process environment variables.
    """

    email = credential.email.strip()
    if not email or not credential.password:
        raise BootstrapAdminError("credential_file_json_invalid", "credential_file")
    now = utc_now()

    user = await db.scalar(select(User).where(User.email == email).with_for_update())
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(credential.password),
            nickname="Pinvi Admin",
            status="active",
            roles=["user", "admin"],
            email_verified_at=now,
            email_status="active",
            is_active=True,
            deleted_at=None,
        )
        db.add(user)
        return BootstrapAdminResult(
            action="created",
            admin_email_sha256=credential.email_sha256,
        )

    changed = False
    password_changed = False

    if not user.password_hash or not verify_password(credential.password, user.password_hash):
        user.password_hash = hash_password(credential.password)
        user.access_token_version = (user.access_token_version or 0) + 1
        changed = True
        password_changed = True

    roles = _roles_with_admin(user.roles)
    if roles != list(user.roles or []):
        user.roles = roles
        changed = True

    if user.nickname is None:
        user.nickname = "Pinvi Admin"
        changed = True
    if user.status != "active":
        user.status = "active"
        changed = True
    if user.email_verified_at is None:
        user.email_verified_at = now
        changed = True
    if user.email_status != "active":
        user.email_status = "active"
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if user.deleted_at is not None:
        user.deleted_at = None
        changed = True

    if password_changed:
        await revoke_active_user_sessions(db, user_id=user.user_id, revoked_at=now)

    if changed:
        return BootstrapAdminResult(
            action="updated",
            admin_email_sha256=credential.email_sha256,
        )

    return BootstrapAdminResult(
        action="unchanged",
        admin_email_sha256=credential.email_sha256,
    )


# ---------------------------------------------------------------------------
# 고정 계정(fixed accounts)
#
# 운영자가 호스트에 둔 별도 credential file로, 배포마다 같은 고정 관리자와 테스트 사용자를
# 다시 맞춘다. 일반 가입·재설정 경로의 비밀번호 정책(8자 이상)은 이 파일로 만든 두 계정에만
# 적용하지 않는다 — 운영자가 의도적으로 짧은 값을 고정할 수 있게 하기 위함이다.
# ---------------------------------------------------------------------------


class _FixedAdminPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=1, max_length=320)
    # 정책 예외: 고정 계정은 일반 비밀번호 최소 길이(8)를 적용하지 않는다.
    password: str = Field(min_length=1, max_length=200)

    @field_validator("login")
    @classmethod
    def _login_identifier(cls, value: str) -> str:
        return normalize_login_identifier(value)


class _FixedTestUserPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    # 정책 예외: 고정 계정은 일반 비밀번호 최소 길이(8)를 적용하지 않는다.
    password: str = Field(min_length=1, max_length=200)


class _FixedAccountsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    admin: _FixedAdminPayload | None = None
    test_user: _FixedTestUserPayload | None = None


@dataclass(frozen=True)
class FixedAccountsCredential:
    admin: BootstrapAdminCredential | None
    test_user: BootstrapAdminCredential | None

    def identities(self) -> list[str]:
        return [
            account.email.casefold()
            for account in (self.admin, self.test_user)
            if account is not None
        ]


@dataclass(frozen=True)
class FixedAccountsResult:
    admin_action: BootstrapAdminAction | None
    test_user_action: BootstrapAdminAction | None


def read_fixed_accounts_file(path: str | Path) -> FixedAccountsCredential:
    """Read the owner-only fixed admin/test user file with the same file checks."""

    payload = _parse_credential_json(_read_owner_only_file(path), _FixedAccountsPayload)
    if payload.admin is None and payload.test_user is None:
        raise BootstrapAdminError("credential_file_json_invalid", "credential_file")
    credential = FixedAccountsCredential(
        admin=(
            BootstrapAdminCredential(email=payload.admin.login, password=payload.admin.password)
            if payload.admin is not None
            else None
        ),
        test_user=(
            BootstrapAdminCredential(
                email=str(payload.test_user.email).strip(),
                password=payload.test_user.password,
            )
            if payload.test_user is not None
            else None
        ),
    )
    identities = credential.identities()
    if len(set(identities)) != len(identities):
        raise BootstrapAdminError("fixed_accounts_conflict", "credential_file")
    return credential


async def ensure_fixed_test_user(
    db: AsyncSession,
    *,
    credential: BootstrapAdminCredential,
) -> BootstrapAdminAction:
    """Create or re-assert the fixed, active, verified ordinary test user.

    The test user is always reset to exactly the ``user`` role so a role granted in the
    admin console does not survive the next deploy.
    """

    email = credential.email.strip()
    if not email or not credential.password:
        raise BootstrapAdminError("credential_file_json_invalid", "credential_file")
    now = utc_now()

    user = await db.scalar(select(User).where(User.email == email).with_for_update())
    if user is None:
        db.add(
            User(
                email=email,
                password_hash=hash_password(credential.password),
                nickname="Pinvi Test",
                status="active",
                roles=list(FIXED_TEST_USER_ROLES),
                email_verified_at=now,
                email_status="active",
                is_active=True,
                deleted_at=None,
            )
        )
        return "created"

    changed = False
    revoke_sessions = False

    if not user.password_hash or not verify_password(credential.password, user.password_hash):
        user.password_hash = hash_password(credential.password)
        changed = True
        revoke_sessions = True
    if list(user.roles or []) != FIXED_TEST_USER_ROLES:
        user.roles = list(FIXED_TEST_USER_ROLES)
        changed = True
        revoke_sessions = True
    if user.nickname is None:
        user.nickname = "Pinvi Test"
        changed = True
    if user.status != "active":
        user.status = "active"
        changed = True
    if user.email_verified_at is None:
        user.email_verified_at = now
        changed = True
    if user.email_status != "active":
        user.email_status = "active"
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if user.deleted_at is not None:
        user.deleted_at = None
        changed = True

    if revoke_sessions:
        user.access_token_version = (user.access_token_version or 0) + 1
        await revoke_active_user_sessions(db, user_id=user.user_id, revoked_at=now)

    return "updated" if changed else "unchanged"


async def ensure_fixed_accounts(
    db: AsyncSession,
    *,
    credential: FixedAccountsCredential,
) -> FixedAccountsResult:
    """Re-assert the fixed admin and test user inside the caller transaction."""

    admin_action: BootstrapAdminAction | None = None
    if credential.admin is not None:
        admin_action = (await ensure_bootstrap_admin(db, credential=credential.admin)).action
    test_user_action: BootstrapAdminAction | None = None
    if credential.test_user is not None:
        test_user_action = await ensure_fixed_test_user(db, credential=credential.test_user)
    return FixedAccountsResult(admin_action=admin_action, test_user_action=test_user_action)
