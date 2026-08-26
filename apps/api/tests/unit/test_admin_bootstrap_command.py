"""`pinvi-admin-bootstrap` CLI wrapper의 secret-free 출력 검증."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.commands import admin_bootstrap
from app.commands.admin_bootstrap import CANDIDATE_HEAD_SCHEMA, PinviAdminBootstrapResult
from app.services.bootstrap_admin import BootstrapAdminError


def _candidate_image_root(
    tmp_path: Path,
    *,
    revisions: dict[str, str],
) -> Path:
    root = tmp_path / "candidate-image"
    command_module = root / "app" / "commands" / "admin_bootstrap.py"
    command_module.parent.mkdir(parents=True)
    command_module.write_text("# candidate image command module\n", encoding="utf-8")
    (root / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n", encoding="utf-8")
    versions = root / "alembic" / "versions"
    versions.mkdir(parents=True)
    for filename, source in revisions.items():
        (versions / filename).write_text(source, encoding="utf-8")
    return root


def _use_candidate_image_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(
        admin_bootstrap,
        "__file__",
        str(root / "app" / "commands" / "admin_bootstrap.py"),
    )


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


def test_validate_credential_command_reads_credential_without_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    credential_file = Path("/run/pinvi/bootstrap-admin.json")
    monkeypatch.setenv(admin_bootstrap.CREDENTIAL_FILE_ENV, str(credential_file))
    monkeypatch.setattr(
        admin_bootstrap,
        "read_bootstrap_admin_credential_file",
        lambda path: (
            None if path == credential_file else pytest.fail("unexpected credential path")
        ),
    )
    monkeypatch.setattr(
        admin_bootstrap,
        "run_pinvi_admin_bootstrap",
        lambda: pytest.fail("credential validation must not run migration or bootstrap"),
    )

    admin_bootstrap.main(["validate-credential"])

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.strip() == '{"action":"credential_valid"}'


def test_static_candidate_head_never_executes_revision_modules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    side_effect_marker = tmp_path / "revision-module-was-executed"
    root = _candidate_image_root(
        tmp_path,
        revisions={
            "base.py": 'revision = "base"\ndown_revision = None\n',
            "tip.py": (
                "from pathlib import Path\n"
                f"Path({str(side_effect_marker)!r}).write_text('executed', encoding='utf-8')\n"
                "raise RuntimeError('revision module executed')\n"
                'revision = "tip"\ndown_revision = "base"\n'
            ),
        },
    )
    _use_candidate_image_root(monkeypatch, root)

    assert admin_bootstrap.get_static_pinvi_head() == "tip"
    assert not side_effect_marker.exists()


def test_static_candidate_head_ignores_cwd_decoy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _candidate_image_root(
        tmp_path / "installed",
        revisions={
            "base.py": 'revision = "image_base"\ndown_revision = None\n',
            "tip.py": 'revision = "image_tip"\ndown_revision = "image_base"\n',
        },
    )
    decoy = _candidate_image_root(
        tmp_path / "decoy",
        revisions={"decoy.py": 'revision = "cwd_decoy"\ndown_revision = None\n'},
    )
    _use_candidate_image_root(monkeypatch, root)
    monkeypatch.chdir(decoy)

    assert admin_bootstrap.get_static_pinvi_head() == "image_tip"


@pytest.mark.parametrize(
    "revisions",
    [
        {},
        {
            "a.py": 'revision = "a"\ndown_revision = "b"\n',
            "b.py": 'revision = "b"\ndown_revision = "a"\n',
        },
        {
            "a.py": 'revision = "a"\ndown_revision = None\n',
            "b.py": 'revision = "b"\ndown_revision = None\n',
        },
        {"tip.py": 'revision = "tip"\ndown_revision = "unavailable_parent"\n'},
        {"tip.py": "revision = configured_revision\ndown_revision = None\n"},
        {"tip.py": 'revision = "tip"\ndown_revision = configured_parent\n'},
        {"tip.py": 'revision = "tip"\nrevision = "other"\ndown_revision = None\n'},
    ],
)
def test_static_candidate_head_rejects_empty_ambiguous_and_dynamic_graphs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    revisions: dict[str, str],
) -> None:
    root = _candidate_image_root(tmp_path, revisions=revisions)
    _use_candidate_image_root(monkeypatch, root)

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
