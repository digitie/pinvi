"""고정 관리자/테스트 사용자 credential file과 로그인 ID 계약 단위 검증.

값은 모두 테스트 전용 가짜 값이다. 운영 값은 저장소에 두지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.commands import admin_bootstrap
from app.commands.admin_bootstrap import PinviAdminBootstrapResult
from app.schemas.auth import LoginRequest, PasswordResetConfirmRequest, RegisterRequest
from app.services.bootstrap_admin import (
    BootstrapAdminCredential,
    BootstrapAdminError,
    FixedAccountsCredential,
    read_bootstrap_admin_credential_file,
    read_fixed_accounts_file,
)

_FAKE_LOGIN = "fixedlogin"
_FAKE_SHORT_PASSWORD = "x."
_FAKE_TEST_EMAIL = "fixed-tester@example.com"
_FAKE_TEST_PASSWORD = "y!"


def _write(tmp_path: Path, payload: object, *, name: str = "fixed-accounts.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


def _full_payload() -> dict[str, dict[str, str]]:
    return {
        "admin": {"login": _FAKE_LOGIN, "password": _FAKE_SHORT_PASSWORD},
        "test_user": {"email": _FAKE_TEST_EMAIL, "password": _FAKE_TEST_PASSWORD},
    }


# --- 로그인 ID ---------------------------------------------------------------


@pytest.mark.parametrize("identifier", ["fixedlogin", "abc", "a1b2c3"])
def test_login_request_accepts_fixed_login_id(identifier: str) -> None:
    assert LoginRequest(email=identifier, password="p").email == identifier


def test_login_request_still_normalizes_email() -> None:
    assert LoginRequest(email="User@Example.COM", password="p").email == "User@example.com"


@pytest.mark.parametrize(
    "identifier",
    ["not-an-email", "ab", "Fixedlogin", "1abc", "fixed login", "fixed.login", "a" * 33, ""],
)
def test_login_request_rejects_other_non_email_identifiers(identifier: str) -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email=identifier, password="p")


def test_registration_still_requires_email_and_eight_character_password() -> None:
    consents = [
        {"consent_type": kind, "version": "v1.0"}
        for kind in ("tos", "privacy", "lbs_tos", "location_collection")
    ]
    with pytest.raises(ValidationError):
        RegisterRequest(
            email=_FAKE_LOGIN, password="long-enough-pw", nickname="n", consents=consents
        )
    with pytest.raises(ValidationError):
        RegisterRequest(
            email=_FAKE_TEST_EMAIL, password=_FAKE_TEST_PASSWORD, nickname="n", consents=consents
        )


def test_password_reset_still_requires_eight_characters() -> None:
    with pytest.raises(ValidationError):
        PasswordResetConfirmRequest(token="t" * 43, new_password=_FAKE_SHORT_PASSWORD)


# --- 고정 계정 파일 ------------------------------------------------------------


def test_fixed_accounts_file_accepts_short_passwords_for_both_accounts(tmp_path: Path) -> None:
    credential = read_fixed_accounts_file(_write(tmp_path, _full_payload()))

    assert credential.admin == BootstrapAdminCredential(
        email=_FAKE_LOGIN, password=_FAKE_SHORT_PASSWORD
    )
    assert credential.test_user == BootstrapAdminCredential(
        email=_FAKE_TEST_EMAIL, password=_FAKE_TEST_PASSWORD
    )


def test_primary_admin_credential_keeps_eight_character_minimum(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"email": "primary-admin@example.com", "password": _FAKE_SHORT_PASSWORD},
        name="primary.json",
    )
    with pytest.raises(BootstrapAdminError) as exc_info:
        read_bootstrap_admin_credential_file(path)
    assert exc_info.value.code == "credential_file_json_invalid"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"admin": None, "test_user": None},
        {"admin": {"login": _FAKE_LOGIN, "password": ""}},
        {"admin": {"login": "not-an-email", "password": "p"}},
        {"test_user": {"email": _FAKE_LOGIN, "password": "p"}},
        {"test_user": {"email": _FAKE_TEST_EMAIL, "password": "p", "roles": ["admin"]}},
        {**_full_payload(), "extra": {}},
    ],
)
def test_fixed_accounts_file_rejects_invalid_payloads(tmp_path: Path, payload: object) -> None:
    with pytest.raises(BootstrapAdminError) as exc_info:
        read_fixed_accounts_file(_write(tmp_path, payload))
    assert exc_info.value.code == "credential_file_json_invalid"


def test_fixed_accounts_file_rejects_same_identity_for_admin_and_test_user(
    tmp_path: Path,
) -> None:
    payload = {
        "admin": {"login": _FAKE_TEST_EMAIL.upper(), "password": "p"},
        "test_user": {"email": _FAKE_TEST_EMAIL, "password": "q"},
    }
    with pytest.raises(BootstrapAdminError) as exc_info:
        read_fixed_accounts_file(_write(tmp_path, payload))
    assert exc_info.value.code == "fixed_accounts_conflict"


def test_fixed_accounts_file_uses_owner_only_file_checks(tmp_path: Path) -> None:
    path = _write(tmp_path, _full_payload())
    path.chmod(0o644)
    with pytest.raises(BootstrapAdminError) as exc_info:
        read_fixed_accounts_file(path)
    assert exc_info.value.code == "credential_file_mode_invalid"


def test_fixed_account_conflict_with_primary_admin_is_rejected() -> None:
    fixed = FixedAccountsCredential(
        admin=None,
        test_user=BootstrapAdminCredential(email=_FAKE_TEST_EMAIL, password="p"),
    )
    with pytest.raises(BootstrapAdminError) as exc_info:
        admin_bootstrap._reject_fixed_account_conflict(
            BootstrapAdminCredential(email=_FAKE_TEST_EMAIL.upper(), password="long-enough"),
            fixed,
        )
    assert exc_info.value.code == "fixed_accounts_conflict"
    admin_bootstrap._reject_fixed_account_conflict(
        BootstrapAdminCredential(email="primary-admin@example.com", password="long-enough"),
        fixed,
    )


# --- CLI 배선 -----------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "])
def test_fixed_accounts_env_absent_or_blank_is_optional(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(admin_bootstrap.FIXED_ACCOUNTS_FILE_ENV, raising=False)
    else:
        monkeypatch.setenv(admin_bootstrap.FIXED_ACCOUNTS_FILE_ENV, value)
    assert admin_bootstrap._fixed_accounts_from_env() is None


def test_fixed_accounts_env_reads_configured_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write(tmp_path, _full_payload())
    monkeypatch.setenv(admin_bootstrap.FIXED_ACCOUNTS_FILE_ENV, str(path))
    credential = admin_bootstrap._fixed_accounts_from_env()
    assert credential is not None
    assert credential.identities() == [_FAKE_LOGIN, _FAKE_TEST_EMAIL]


def test_bootstrap_reads_fixed_accounts_before_migration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A broken fixed-accounts file must fail before any schema mutation."""

    primary = _write(
        tmp_path,
        {"email": "primary-admin@example.com", "password": "long-enough-pw"},
        name="primary.json",
    )
    broken = _write(tmp_path, {"admin": {"login": "not-an-email", "password": "p"}})
    monkeypatch.setenv(admin_bootstrap.CREDENTIAL_FILE_ENV, str(primary))
    monkeypatch.delenv(admin_bootstrap.CREDENTIAL_BINDING_ENV, raising=False)
    monkeypatch.setenv(admin_bootstrap.FIXED_ACCOUNTS_FILE_ENV, str(broken))
    monkeypatch.setattr(
        admin_bootstrap,
        "run_alembic_upgrade_head",
        lambda: pytest.fail("migration must not run with an invalid fixed-accounts file"),
    )

    with pytest.raises(BootstrapAdminError) as exc_info:
        admin_bootstrap.run_pinvi_admin_bootstrap()
    assert exc_info.value.code == "credential_file_json_invalid"


def test_cli_success_output_reports_fixed_actions_without_identities(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        admin_bootstrap,
        "run_pinvi_admin_bootstrap",
        lambda: PinviAdminBootstrapResult(
            action="unchanged",
            pinvi_head="head",
            admin_email_sha256="f" * 64,
            fixed_admin_action="updated",
            fixed_test_user_action="created",
        ),
    )

    admin_bootstrap.main([])

    out = capsys.readouterr().out.strip()
    assert out == (
        '{"action":"unchanged","admin_email_sha256":"' + "f" * 64 + '",'
        '"fixed_admin_action":"updated","fixed_test_user_action":"created",'
        '"pinvi_head":"head"}'
    )
    assert _FAKE_LOGIN not in out
    assert _FAKE_TEST_EMAIL not in out


def test_fixed_accounts_conflict_has_typed_phase() -> None:
    assert admin_bootstrap._typed_error_payload(
        BootstrapAdminError("fixed_accounts_conflict", "credential_file")
    ) == {"error_code": "fixed_accounts_conflict", "phase": "credential_file"}
