"""Pinvi `0061` catalog을 새 설치용 Alembic 기준선으로 고정한다.

Revision ID: 20260824_0100
Revises:
Create Date: 2026-08-24

이 revision은 과거 migration graph를 실행하지 않는다. 동봉한 PostgreSQL 16 schema
snapshot은 clean `20260821_0061` catalog에서 data/owner/privilege/version table을 제외해
생성했으며, digest가 맞을 때에만 문 단위로 실행한다.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0100"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASELINE_FILE = "20260824_0100_app_schema.sql"
_BASELINE_SHA256 = "6b9600b715d788eb5a635b6e5a970b5244c5f23851e30001fc003b104d4f23d4"
_BASELINE_STATEMENT_COUNT = 445
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def _split_postgres_statements(source: str) -> tuple[str, ...]:
    """dollar-quoted function body를 보존한 채 top-level SQL 문만 분리한다."""

    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    quote: str | None = None
    dollar_quote: str | None = None

    while index < len(source):
        if dollar_quote is not None:
            if source.startswith(dollar_quote, index):
                buffer.append(dollar_quote)
                index += len(dollar_quote)
                dollar_quote = None
            else:
                buffer.append(source[index])
                index += 1
            continue

        if quote is not None:
            character = source[index]
            buffer.append(character)
            index += 1
            if character == quote:
                if index < len(source) and source[index] == quote:
                    buffer.append(source[index])
                    index += 1
                else:
                    quote = None
            continue

        if source.startswith("--", index):
            newline = source.find("\n", index)
            index = len(source) if newline == -1 else newline + 1
            continue
        if source.startswith("/*", index):
            comment_end = source.find("*/", index + 2)
            if comment_end == -1:
                raise RuntimeError("0100 baseline has an unterminated block comment")
            index = comment_end + 2
            continue

        character = source[index]
        if character in "'\"":
            quote = character
            buffer.append(character)
            index += 1
            continue
        if character == "$":
            match = _DOLLAR_QUOTE.match(source, index)
            if match is not None:
                dollar_quote = match.group(0)
                buffer.append(dollar_quote)
                index += len(dollar_quote)
                continue
        if character == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer.clear()
            index += 1
            continue
        buffer.append(character)
        index += 1

    if quote is not None or dollar_quote is not None:
        raise RuntimeError("0100 baseline has an unterminated SQL literal")
    trailing = "".join(buffer).strip()
    if trailing:
        raise RuntimeError("0100 baseline has a trailing SQL statement without a terminator")
    if len(statements) != _BASELINE_STATEMENT_COUNT:
        raise RuntimeError("0100 baseline statement count is invalid")
    return tuple(statements)


def _baseline_statements() -> tuple[str, ...]:
    path = Path(__file__).resolve().parents[1] / "baselines" / _BASELINE_FILE
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RuntimeError("0100 baseline schema artifact is unavailable") from exc
    if hashlib.sha256(payload).hexdigest() != _BASELINE_SHA256:
        raise RuntimeError("0100 baseline schema artifact digest is invalid")
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("0100 baseline schema artifact is not UTF-8") from exc
    return _split_postgres_statements(source)


def upgrade() -> None:
    # legacy `0061` first revision과 같은 extension ownership을 보장한다. schema snapshot의
    # function은 table보다 먼저 정의되므로 transaction-local body validation만 끈다.
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS x_extension")
    for extension in ("pgcrypto", "pg_trgm", "citext"):
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension} SCHEMA x_extension")
    op.execute("SET LOCAL check_function_bodies = false")
    for statement in _baseline_statements():
        op.execute(sa.text(statement))


def downgrade() -> None:
    raise RuntimeError("0100 app schema baseline is forward-only")
