"""`pinvi-admin-bootstrap` CLI wrapper의 secret-free 출력 검증."""

from __future__ import annotations

import pytest

from app.commands import admin_bootstrap
from app.commands.admin_bootstrap import CANDIDATE_HEAD_SCHEMA, PinviAdminBootstrapResult
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


def test_candidate_head_command_reads_no_credential_or_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_credential = "redaction-sentinel-value"

    def _database_or_credential_access() -> PinviAdminBootstrapResult:
        raise AssertionError("the candidate head command must not bootstrap")

    monkeypatch.setenv(admin_bootstrap.CREDENTIAL_FILE_ENV, f"/run/pinvi/{raw_credential}.json")
    monkeypatch.setattr(
        admin_bootstrap,
        "get_static_pinvi_head",
        lambda: "20260804_0049_feature_uuid_shadow_columns",
    )
    monkeypatch.setattr(
        admin_bootstrap, "run_pinvi_admin_bootstrap", _database_or_credential_access
    )

    admin_bootstrap.main(["head"])

    captured = capsys.readouterr()
    assert raw_credential not in captured.out
    assert raw_credential not in captured.err
    assert captured.err == ""
    assert captured.out.strip() == (
        '{"pinvi_head":"20260804_0049_feature_uuid_shadow_columns",'
        f'"schema":"{CANDIDATE_HEAD_SCHEMA}"}}'
    )


@pytest.mark.parametrize("heads", [(), ("first", "second")])
def test_static_candidate_head_requires_exactly_one_head(
    monkeypatch: pytest.MonkeyPatch,
    heads: tuple[str, ...],
) -> None:
    class _ScriptDirectory:
        def get_heads(self) -> tuple[str, ...]:
            return heads

    monkeypatch.setattr(
        admin_bootstrap.ScriptDirectory,
        "from_config",
        lambda _config: _ScriptDirectory(),
    )

    with pytest.raises(BootstrapAdminError, match="static_head_unavailable"):
        admin_bootstrap.get_static_pinvi_head()


def test_candidate_head_command_redacts_static_head_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_value = "redaction-sentinel-value"

    def _raise_static_head_error() -> str:
        raise BootstrapAdminError("static_head_unavailable", raw_value)

    monkeypatch.setattr(admin_bootstrap, "get_static_pinvi_head", _raise_static_head_error)

    with pytest.raises(SystemExit) as exc_info:
        admin_bootstrap.main(["head"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert raw_value not in captured.out
    assert raw_value not in captured.err
    assert captured.out == ""
    assert captured.err.strip() == '{"error_code":"static_head_unavailable","phase":"migration"}'


def test_candidate_head_command_replaces_unknown_typed_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_value = "redaction-sentinel-value"

    def _raise_unknown_typed_error() -> str:
        raise BootstrapAdminError(raw_value, raw_value)

    monkeypatch.setattr(admin_bootstrap, "get_static_pinvi_head", _raise_unknown_typed_error)

    with pytest.raises(SystemExit) as exc_info:
        admin_bootstrap.main(["head"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert raw_value not in captured.out
    assert raw_value not in captured.err
    assert captured.out == ""
    assert captured.err.strip() == '{"error_code":"internal_error","phase":"runtime"}'


def test_api_lifespan_does_not_reference_bootstrap_admin() -> None:
    from app.main import lifespan

    assert "ensure_bootstrap_admin" not in lifespan.__code__.co_names
