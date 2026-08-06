"""PinVi DB migration + fresh admin one-shot bootstrap."""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Never, TextIO

from alembic.config import Config
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
_REVISION_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
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
    """Return the candidate image root derived only from this installed module."""

    command_module = Path(__file__).resolve()
    command_directory = command_module.parent
    app_directory = command_directory.parent
    candidate_root = app_directory.parent
    if (
        command_module.name == "admin_bootstrap.py"
        and command_directory.name == "commands"
        and app_directory.name == "app"
        and (candidate_root / "alembic.ini").is_file()
        and (candidate_root / "alembic" / "versions").is_dir()
    ):
        return candidate_root
    raise BootstrapAdminError("alembic_config_missing", "migration")


def _alembic_config() -> Config:
    root = _api_project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("prepend_sys_path", str(root))
    return config


def _static_revision_identifier(value: object) -> str:
    if not isinstance(value, str) or _REVISION_IDENTIFIER.fullmatch(value) is None:
        raise ValueError("revision identifier is not a canonical literal")
    return value


def _literal_assignment(module: ast.Module, name: str) -> ast.expr:
    assignments: list[ast.expr] = []
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            if len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
                if statement.targets[0].id == name:
                    assignments.append(statement.value)
        elif isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name) and statement.target.id == name:
                if statement.value is not None:
                    assignments.append(statement.value)
    if len(assignments) != 1:
        raise ValueError(f"{name} must have exactly one module-level literal assignment")
    return assignments[0]


def _literal_revision(node: ast.expr) -> str:
    if not isinstance(node, ast.Constant):
        raise ValueError("revision must be a literal string")
    return _static_revision_identifier(node.value)


def _literal_down_revisions(node: ast.expr) -> tuple[str, ...]:
    if isinstance(node, ast.Constant) and node.value is None:
        return ()
    values: tuple[ast.expr, ...]
    if isinstance(node, ast.Constant):
        values = (node,)
    elif isinstance(node, (ast.List, ast.Tuple)) and node.elts:
        values = tuple(node.elts)
    else:
        raise ValueError("down_revision must be a literal string, sequence, or None")
    revisions = tuple(_literal_revision(value) for value in values)
    if len(set(revisions)) != len(revisions):
        raise ValueError("down_revision must not contain duplicates")
    return revisions


def _parse_static_revision_graph(versions_directory: Path) -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {}
    revision_paths = sorted(
        path for path in versions_directory.glob("*.py") if path.name != "__init__.py"
    )
    if not revision_paths:
        raise ValueError("migration graph is empty")
    for revision_path in revision_paths:
        module = ast.parse(revision_path.read_text(encoding="utf-8"), filename=str(revision_path))
        revision = _literal_revision(_literal_assignment(module, "revision"))
        if revision in graph:
            raise ValueError("migration graph has duplicate revisions")
        graph[revision] = _literal_down_revisions(_literal_assignment(module, "down_revision"))
    if any(parent not in graph for parents in graph.values() for parent in parents):
        raise ValueError("migration graph has an unavailable parent")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(revision: str) -> None:
        if revision in visiting:
            raise ValueError("migration graph is cyclic")
        if revision in visited:
            return
        visiting.add(revision)
        for parent in graph[revision]:
            visit(parent)
        visiting.remove(revision)
        visited.add(revision)

    for revision in graph:
        visit(revision)
    return graph


def get_static_pinvi_head() -> str:
    """Return the single head from literal migration metadata without importing revisions."""

    try:
        graph = _parse_static_revision_graph(_api_project_root() / "alembic" / "versions")
    except Exception as exc:
        raise BootstrapAdminError("static_head_unavailable", "migration") from exc
    parents = {parent for revisions in graph.values() for parent in revisions}
    heads = sorted(set(graph).difference(parents))
    if len(heads) != 1 or not isinstance(heads[0], str) or not heads[0]:
        raise BootstrapAdminError("static_head_unavailable", "migration")
    return heads[0]


def run_alembic_upgrade_head() -> None:
    try:
        command.upgrade(_alembic_config(), "head")
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
