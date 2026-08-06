"""`pinvi-admin-bootstrap` CLI wrapper의 secret-free 출력 검증."""

from __future__ import annotations

import pytest

from app.commands import admin_bootstrap
from app.commands.admin_bootstrap import PinviAdminBootstrapResult
from app.services.bootstrap_admin import BootstrapAdminError


def test_cli_emits_typed_error_without_raw_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_credential = "redaction-sentinel-value"

    def _raise_typed() -> PinviAdminBootstrapResult:
        raise BootstrapAdminError("credential_file_json_invalid", "credential_file")

    monkeypatch.setenv(admin_bootstrap.CREDENTIAL_FILE_ENV, f"/run/pinvi/{raw_credential}.json")
    monkeypatch.setattr(admin_bootstrap, "run_pinvi_admin_bootstrap", _raise_typed)

    with pytest.raises(SystemExit) as exc_info:
        admin_bootstrap.main([])

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert raw_credential not in captured.out
    assert raw_credential not in captured.err
    assert captured.out == ""
    assert captured.err.strip() == (
        '{"error_code":"credential_file_json_invalid","phase":"credential_file"}'
    )


def test_cli_redacts_unexpected_exception_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_credential = "redaction-sentinel-value"

    def _raise_unexpected() -> PinviAdminBootstrapResult:
        raise RuntimeError(raw_credential)

    monkeypatch.setattr(admin_bootstrap, "run_pinvi_admin_bootstrap", _raise_unexpected)

    with pytest.raises(SystemExit) as exc_info:
        admin_bootstrap.main([])

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert raw_credential not in captured.out
    assert raw_credential not in captured.err
    assert captured.out == ""
    assert captured.err.strip() == '{"error_code":"internal_error","phase":"runtime"}'


def test_cli_rejects_arguments_without_echoing_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_credential = "redaction-sentinel-value"

    with pytest.raises(SystemExit) as exc_info:
        admin_bootstrap.main([f"--password={raw_credential}"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert raw_credential not in captured.out
    assert raw_credential not in captured.err
    assert captured.out == ""
    assert captured.err.strip() == '{"error_code":"invalid_arguments","phase":"startup"}'


def test_cli_success_output_contains_no_raw_credential(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_email = "bootstrap-admin@example.com"
    raw_credential = "redaction-sentinel-value"

    def _success() -> PinviAdminBootstrapResult:
        return PinviAdminBootstrapResult(
            action="created",
            pinvi_head="20260804_0049_feature_uuid_shadow_columns",
            admin_email_sha256="f" * 64,
        )

    monkeypatch.setenv(admin_bootstrap.CREDENTIAL_FILE_ENV, f"/run/pinvi/{raw_email}.json")
    monkeypatch.setattr(admin_bootstrap, "run_pinvi_admin_bootstrap", _success)

    admin_bootstrap.main([])

    captured = capsys.readouterr()
    assert raw_email not in captured.out
    assert raw_credential not in captured.out
    assert captured.err == ""
    assert captured.out.strip() == (
        '{"action":"created","admin_email_sha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",'
        '"pinvi_head":"20260804_0049_feature_uuid_shadow_columns"}'
    )


def test_api_lifespan_does_not_reference_bootstrap_admin() -> None:
    from app.main import lifespan

    assert "ensure_bootstrap_admin" not in lifespan.__code__.co_names
