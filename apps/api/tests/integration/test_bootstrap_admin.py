"""PinVi one-shot admin bootstrap 검증."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.commands.admin_bootstrap import get_database_pinvi_head, run_admin_bootstrap_transaction
from app.core.security import hash_password, verify_password
from app.models.session import UserSession
from app.models.user import User
from app.services.bootstrap_admin import (
    MAX_CREDENTIAL_FILE_BYTES,
    BootstrapAdminError,
    read_bootstrap_admin_credential_file,
)

_EMAIL = "bootstrap-admin@example.com"
_PASSWORD = "temporary-test-passphrase"


def _write_credential_file(
    tmp_path: Path,
    *,
    email: str = _EMAIL,
    password: str = _PASSWORD,
) -> Path:
    path = tmp_path / "pinvi-admin-credential.json"
    path.write_text(
        json.dumps({"email": email, "password": password}),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _email_sha256(email: str = _EMAIL) -> str:
    return hashlib.sha256(email.casefold().encode("utf-8")).hexdigest()


async def _current_head(session_factory) -> str:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        head = await get_database_pinvi_head(db)
        await db.rollback()
        return head


@pytest.mark.asyncio
async def test_admin_bootstrap_creates_active_admin_after_head_check(
    session_factory,
    tmp_path: Path,
) -> None:
    credential_file = _write_credential_file(tmp_path)
    expected_head = await _current_head(session_factory)

    result = await run_admin_bootstrap_transaction(
        expected_head=expected_head,
        credential_file=credential_file,
    )

    assert result.action == "created"
    assert result.pinvi_head == expected_head
    assert result.admin_email_sha256 == _email_sha256()
    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.email == _EMAIL))
        assert user is not None
        assert user.status == "active"
        assert user.email_verified_at is not None
        assert user.is_active is True
        assert {"user", "admin"}.issubset(set(user.roles))
        assert user.password_hash is not None
        assert verify_password(_PASSWORD, user.password_hash)


@pytest.mark.asyncio
async def test_admin_bootstrap_is_idempotent(
    session_factory,
    tmp_path: Path,
) -> None:
    credential_file = _write_credential_file(tmp_path)
    expected_head = await _current_head(session_factory)

    first = await run_admin_bootstrap_transaction(
        expected_head=expected_head,
        credential_file=credential_file,
    )
    second = await run_admin_bootstrap_transaction(
        expected_head=expected_head,
        credential_file=credential_file,
    )

    assert first.action == "created"
    assert second.action == "unchanged"
    async with session_factory() as db:
        users = (await db.execute(select(User).where(User.email == _EMAIL))).scalars().all()
        assert len(users) == 1


@pytest.mark.asyncio
async def test_admin_bootstrap_repairs_existing_admin_and_revokes_sessions(
    session_factory,
    tmp_path: Path,
) -> None:
    credential_file = _write_credential_file(tmp_path)
    expected_head = await _current_head(session_factory)
    async with session_factory() as db:
        user = User(
            email=_EMAIL,
            password_hash=hash_password("old-password"),
            nickname=None,
            status="disabled",
            roles=["user"],
            email_verified_at=None,
            is_active=False,
            deleted_at=datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        db.add(
            UserSession(
                user_id=user.user_id,
                session_token_hash="old-session",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await db.commit()

    result = await run_admin_bootstrap_transaction(
        expected_head=expected_head,
        credential_file=credential_file,
    )

    assert result.action == "updated"
    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.email == _EMAIL))
        assert user is not None
        assert user.status == "active"
        assert user.email_verified_at is not None
        assert user.is_active is True
        assert user.deleted_at is None
        assert {"user", "admin"}.issubset(set(user.roles))
        assert user.password_hash is not None
        assert verify_password(_PASSWORD, user.password_hash)
        session = await db.scalar(
            select(UserSession).where(UserSession.session_token_hash == "old-session")
        )
        assert session is not None
        assert session.revoked_at is not None


@pytest.mark.asyncio
async def test_admin_bootstrap_rejects_head_mismatch_before_credential_access(
    session_factory,
    tmp_path: Path,
) -> None:
    missing_credential_file = tmp_path / "missing.json"

    with pytest.raises(BootstrapAdminError) as exc_info:
        await run_admin_bootstrap_transaction(
            expected_head="not_the_candidate_head",
            credential_file=missing_credential_file,
        )

    assert exc_info.value.code == "schema_revision_mismatch"
    assert exc_info.value.phase == "schema_check"


@pytest.mark.asyncio
async def test_admin_bootstrap_rolls_back_admin_on_invalid_credential_json(
    session_factory,
    tmp_path: Path,
) -> None:
    credential_file = tmp_path / "pinvi-admin-credential.json"
    credential_file.write_text(
        json.dumps({"email": _EMAIL, "password": _PASSWORD, "extra": "reject"}),
        encoding="utf-8",
    )
    credential_file.chmod(0o600)
    expected_head = await _current_head(session_factory)

    with pytest.raises(BootstrapAdminError) as exc_info:
        await run_admin_bootstrap_transaction(
            expected_head=expected_head,
            credential_file=credential_file,
        )

    assert exc_info.value.code == "credential_file_json_invalid"
    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.email == _EMAIL))
        assert user is None


def test_credential_file_rejects_relative_path(tmp_path: Path) -> None:
    credential_file = _write_credential_file(tmp_path)

    with pytest.raises(BootstrapAdminError) as exc_info:
        read_bootstrap_admin_credential_file(credential_file.relative_to(tmp_path))

    assert exc_info.value.code == "credential_file_path_invalid"


def test_credential_file_rejects_group_readable_mode(tmp_path: Path) -> None:
    credential_file = _write_credential_file(tmp_path)
    credential_file.chmod(0o640)

    with pytest.raises(BootstrapAdminError) as exc_info:
        read_bootstrap_admin_credential_file(credential_file)

    assert exc_info.value.code == "credential_file_mode_invalid"


def test_credential_file_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    credential_file = tmp_path / "pinvi-admin-credential.json"
    credential_file.write_text(
        '{"email":"bootstrap-admin@example.com","password":"temporary-test-passphrase",'
        '"password":"second-temporary-test-passphrase"}',
        encoding="utf-8",
    )
    credential_file.chmod(0o600)

    with pytest.raises(BootstrapAdminError) as exc_info:
        read_bootstrap_admin_credential_file(credential_file)

    assert exc_info.value.code == "credential_file_json_invalid"


def test_credential_file_rejects_symlink(tmp_path: Path) -> None:
    credential_file = _write_credential_file(tmp_path)
    symlink = tmp_path / "credential-link.json"
    symlink.symlink_to(credential_file)

    with pytest.raises(BootstrapAdminError) as exc_info:
        read_bootstrap_admin_credential_file(symlink)

    assert exc_info.value.code == "credential_file_not_regular"


def test_credential_file_rejects_hardlink(tmp_path: Path) -> None:
    credential_file = _write_credential_file(tmp_path)
    hardlink = tmp_path / "credential-hardlink.json"
    try:
        os.link(credential_file, hardlink)
    except OSError:
        pytest.skip("hardlink creation is unavailable on this filesystem")

    with pytest.raises(BootstrapAdminError) as exc_info:
        read_bootstrap_admin_credential_file(credential_file)

    assert exc_info.value.code == "credential_file_link_count_invalid"


def test_credential_file_rejects_owner_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    credential_file = _write_credential_file(tmp_path)
    monkeypatch.setattr(os, "geteuid", lambda: credential_file.stat().st_uid + 1)

    with pytest.raises(BootstrapAdminError) as exc_info:
        read_bootstrap_admin_credential_file(credential_file)

    assert exc_info.value.code == "credential_file_owner_mismatch"


def test_credential_file_rejects_oversized_content(tmp_path: Path) -> None:
    credential_file = tmp_path / "pinvi-admin-credential.json"
    credential_file.write_bytes(b"{" + (b" " * MAX_CREDENTIAL_FILE_BYTES) + b"}")
    credential_file.chmod(0o600)

    with pytest.raises(BootstrapAdminError) as exc_info:
        read_bootstrap_admin_credential_file(credential_file)

    assert exc_info.value.code == "credential_file_size_invalid"
