"""PinVi DB migration + fresh admin one-shot bootstrap."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Never, TextIO

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.db import session as db_session
from app.services.bootstrap_admin import (
    BootstrapAdminError,
    BootstrapAdminResult,
    ensure_bootstrap_admin,
    read_bootstrap_admin_credential_file,
)

CREDENTIAL_FILE_ENV = "PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE"
CANDIDATE_HEAD_SCHEMA = "pinvi.candidate-head.v1"
_ERROR_PHASE_BY_CODE = {
    "alembic_config_missing": "migration",
    "credential_file_changed": "credential_file",
    "credential_file_env_missing": "credential_file",
    "credential_file_json_invalid": "credential_file",
    "credential_file_link_count_invalid": "credential_file",
    "credential_file_missing": "credential_file",
    "credential_file_mode_invalid": "credential_file",
    "credential_file_not_regular": "credential_file",
    "credential_file_owner_mismatch": "credential_file",
    "credential_file_path_invalid": "credential_file",
    "credential_file_size_invalid": "credential_file",
    "credential_file_unavailable": "credential_file",
    "migration_failed": "migration",
    "schema_revision_mismatch": "schema_check",
    "schema_version_invalid": "schema_check",
    "schema_version_unavailable": "schema_check",
    "static_head_unavailable": "migration",
}


@dataclass(frozen=True)
class PinviAdminBootstrapResult:
    action: str
    pinvi_head: str
    admin_email_sha256: str

    def json_object(self) -> dict[str, str]:
        return {
            "action": self.action,
            "admin_email_sha256": self.admin_email_sha256,
            "pinvi_head": self.pinvi_head,
        }


def _api_project_root() -> Path:
    for candidate in [Path.cwd(), *Path(__file__).resolve().parents]:
        if (candidate / "alembic.ini").is_file() and (candidate / "alembic").is_dir():
            return candidate
    raise BootstrapAdminError("alembic_config_missing", "migration")


def _alembic_config(api_root: Path | None = None) -> Config:
    root = api_root or _api_project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("prepend_sys_path", str(root))
    return config


def get_static_pinvi_head(api_root: Path | None = None) -> str:
    """Return the candidate image's source-static Alembic head."""

    try:
        script = ScriptDirectory.from_config(_alembic_config(api_root))
        heads = script.get_heads()
    except Exception as exc:
        raise BootstrapAdminError("static_head_unavailable", "migration") from exc
    if len(heads) != 1 or not isinstance(heads[0], str) or not heads[0]:
        raise BootstrapAdminError("static_head_unavailable", "migration")
    return heads[0]


def run_alembic_upgrade_head(api_root: Path | None = None) -> None:
    try:
        command.upgrade(_alembic_config(api_root), "head")
    except Exception as exc:
        raise BootstrapAdminError("migration_failed", "migration") from exc


async def get_database_pinvi_head(db: AsyncSession) -> str:
    try:
        result = await db.execute(text("SELECT version_num FROM app.alembic_version FOR UPDATE"))
        rows = result.scalars().all()
    except SQLAlchemyError as exc:
        raise BootstrapAdminError("schema_version_unavailable", "schema_check") from exc
    if len(rows) != 1 or not isinstance(rows[0], str) or not rows[0]:
        raise BootstrapAdminError("schema_version_invalid", "schema_check")
    return rows[0]


async def run_admin_bootstrap_transaction(
    *,
    expected_head: str,
    credential_file: Path,
) -> PinviAdminBootstrapResult:
    async with db_session.async_session_factory() as db:
        async with db.begin():
            database_head = await get_database_pinvi_head(db)
            if database_head != expected_head:
                raise BootstrapAdminError("schema_revision_mismatch", "schema_check")
            credential = read_bootstrap_admin_credential_file(credential_file)
            result: BootstrapAdminResult = await ensure_bootstrap_admin(
                db,
                credential=credential,
            )
            return PinviAdminBootstrapResult(
                action=result.action,
                pinvi_head=database_head,
                admin_email_sha256=result.admin_email_sha256,
            )


async def _run_admin_phase(expected_head: str, credential_file: Path) -> PinviAdminBootstrapResult:
    return await run_admin_bootstrap_transaction(
        expected_head=expected_head,
        credential_file=credential_file,
    )


def _credential_file_from_env() -> Path:
    value = os.environ.get(CREDENTIAL_FILE_ENV)
    if value is None or not value.strip():
        raise BootstrapAdminError("credential_file_env_missing", "credential_file")
    return Path(value)


def run_pinvi_admin_bootstrap() -> PinviAdminBootstrapResult:
    credential_file = _credential_file_from_env()
    expected_head = get_static_pinvi_head()
    try:
        run_alembic_upgrade_head()
        return asyncio.run(_run_admin_phase(expected_head, credential_file))
    finally:
        asyncio.run(db_session.engine.dispose())


class _SecretFreeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        print(
            '{"error_code":"invalid_arguments","phase":"startup"}',
            file=sys.stderr,
        )
        raise SystemExit(2)


def _parse_args(argv: Sequence[str] | None = None) -> str:
    parser = _SecretFreeArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("head",))
    parsed = parser.parse_args(argv)
    command: str | None = parsed.command
    return command or "bootstrap"


def _print_json(payload: dict[str, str], *, stream: TextIO | None = None) -> None:
    output = stream or sys.stdout
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=output)


def _typed_error_payload(error: BootstrapAdminError) -> dict[str, str]:
    phase = _ERROR_PHASE_BY_CODE.get(error.code)
    if phase is None:
        return {"error_code": "internal_error", "phase": "runtime"}
    return {"error_code": error.code, "phase": phase}


def main(argv: Sequence[str] | None = None) -> None:
    command = _parse_args(argv)
    try:
        if command == "head":
            _print_json(
                {
                    "pinvi_head": get_static_pinvi_head(),
                    "schema": CANDIDATE_HEAD_SCHEMA,
                }
            )
            return
        result = run_pinvi_admin_bootstrap()
    except BootstrapAdminError as exc:
        _print_json(_typed_error_payload(exc), stream=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        _print_json({"error_code": "internal_error", "phase": "runtime"}, stream=sys.stderr)
        raise SystemExit(1) from None
    _print_json(result.json_object())


if __name__ == "__main__":
    main()
