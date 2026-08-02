"""reconciliation receipt fingerprint migration의 실제 왕복 계약."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

API_DIR = Path(__file__).resolve().parents[2]
ACTUAL_ROOT = "11" * 32
LEGACY_ROOT = "22" * 32


def _alembic(database_url: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PINVI_DATABASE_URL"] = database_url
    return subprocess.run(  # noqa: S603
        ["alembic", *args],  # noqa: S607 -- repository venv의 고정 CLI
        cwd=API_DIR,
        env=env,
        check=check,
        capture_output=True,
        text=True,
    )


async def _truncate_app(database_url: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            rows = await connection.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'app' AND tablename <> 'alembic_version'"
                )
            )
            tables = [row[0] for row in rows]
            if tables:
                quoted = ", ".join(f'app."{table}"' for table in tables)
                await connection.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
    finally:
        await engine.dispose()


async def _seed_0045_receipts(database_url: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    actual_id, legacy_id, invalid_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = (
        (
            actual_id,
            1,
            {
                "expected_merkle_root": ACTUAL_ROOT,
                "actual_merkle_root": ACTUAL_ROOT,
            },
        ),
        (legacy_id, 2, {"merkle_root": LEGACY_ROOT}),
        (invalid_id, 3, {"status": "succeeded"}),
    )
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            for event_id, relay_order, payload in rows:
                await connection.execute(
                    text(
                        "INSERT INTO app.ktm_cache_target_events "
                        "(event_id, event_type, external_system, target_key, target_id, "
                        "restore_epoch, source_generation, target_sequence, relay_order, "
                        "source_payload_fingerprint, payload_fingerprint, occurred_at, payload) "
                        "VALUES (:event_id, 'cache_target.reconciled', 'pinvi', NULL, NULL, "
                        "1, NULL, NULL, :relay_order, NULL, decode(:payload_hash, 'hex'), "
                        "now(), CAST(:payload AS jsonb))"
                    ),
                    {
                        "event_id": event_id,
                        "relay_order": relay_order,
                        "payload_hash": f"{relay_order:064x}",
                        "payload": json.dumps(payload),
                    },
                )
    finally:
        await engine.dispose()
    return actual_id, legacy_id, invalid_id


@pytest.mark.asyncio
async def test_0046_backfill_fails_closed_and_round_trips(_database_url: str) -> None:
    """actual/legacy payload를 복구하고 invalid NULL은 upgrade 전체를 거부한다."""

    await _truncate_app(_database_url)
    _alembic(_database_url, "downgrade", "20260731_0045")
    actual_id, legacy_id, invalid_id = await _seed_0045_receipts(_database_url)

    try:
        failed = _alembic(_database_url, "upgrade", "20260801_0046", check=False)
        assert failed.returncode != 0

        engine = create_async_engine(_database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                version = await connection.scalar(
                    text("SELECT version_num FROM app.alembic_version")
                )
                assert version == "20260731_0045"
                await connection.execute(
                    text("DELETE FROM app.ktm_cache_target_events WHERE event_id = :event_id"),
                    {"event_id": invalid_id},
                )
        finally:
            await engine.dispose()

        _alembic(_database_url, "upgrade", "20260801_0046")
        engine = create_async_engine(_database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                fingerprints = dict(
                    (
                        await connection.execute(
                            text(
                                "SELECT event_id, encode(source_payload_fingerprint, 'hex') "
                                "FROM app.ktm_cache_target_events ORDER BY relay_order"
                            )
                        )
                    ).all()
                )
                assert fingerprints == {actual_id: ACTUAL_ROOT, legacy_id: LEGACY_ROOT}
        finally:
            await engine.dispose()

        _alembic(_database_url, "downgrade", "20260731_0045")
        engine = create_async_engine(_database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM app.ktm_cache_target_events "
                            "WHERE source_payload_fingerprint IS NULL"
                        )
                    )
                    == 2
                )
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            "UPDATE app.ktm_cache_target_events "
                            "SET source_payload_fingerprint = decode(:root, 'hex') "
                            "WHERE event_id = :event_id"
                        ),
                        {"root": ACTUAL_ROOT, "event_id": actual_id},
                    )
        finally:
            await engine.dispose()

        _alembic(_database_url, "upgrade", "20260801_0046")
    finally:
        _alembic(_database_url, "upgrade", "head")
