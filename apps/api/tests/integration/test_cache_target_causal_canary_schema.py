"""migration 0048 production causal canary durable state constraints."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.cache_target_sync import (
    KtmCacheTargetCanaryRun,
    KtmCacheTargetCommand,
    KtmCacheTargetHead,
)

pytestmark = pytest.mark.asyncio

STABLE_TARGET_ID = uuid.UUID("15f98050-27d7-5f85-be21-dc53eded5d7d")


def _head(target_id: uuid.UUID, *, generation: int) -> KtmCacheTargetHead:
    return KtmCacheTargetHead(
        poi_id=target_id,
        external_system="pinvi",
        target_key=str(target_id),
        desired_state="active",
        source_generation=generation,
        source_payload_fingerprint=b"s" * 32,
        lon=Decimal("127.0"),
        lat=Decimal("37.0"),
        radius_km=Decimal("5.0"),
        update_enabled=True,
    )


def _command(
    target_id: uuid.UUID, command_id: uuid.UUID, *, generation: int
) -> KtmCacheTargetCommand:
    return KtmCacheTargetCommand(
        command_id=command_id,
        poi_id=target_id,
        operation="put",
        source_generation=generation,
        payload={"state": "active", "version": "cache-target-source-v1"},
        payload_fingerprint=b"s" * 32,
        status="pending",
    )


def _run(
    *,
    run_id: uuid.UUID,
    target_id: uuid.UUID,
    command_id: uuid.UUID,
    generation: int,
    phase: str = "put_enqueued",
) -> KtmCacheTargetCanaryRun:
    return KtmCacheTargetCanaryRun(
        run_id=run_id,
        target_poi_id=target_id,
        status="running",
        phase=phase,
        put_command_id=command_id,
        put_generation=generation,
        delete_generation=generation + 1,
        baseline_cache_generation=7,
        baseline_cursor="cursor-7",
        baseline_count=0,
        baseline_merkle_root=b"m" * 32,
    )


async def test_canary_run_accepts_stable_target_and_multiple_run_identity(session_factory) -> None:  # type: ignore[no-untyped-def]
    first_command = uuid.uuid4()
    async with session_factory() as db:
        db.add(_head(STABLE_TARGET_ID, generation=1))
        await db.flush()
        db.add(_command(STABLE_TARGET_ID, first_command, generation=1))
        await db.flush()
        db.add(
            _run(
                run_id=uuid.uuid4(),
                target_id=STABLE_TARGET_ID,
                command_id=first_command,
                generation=1,
            )
        )
        await db.commit()


async def test_canary_run_rejects_foreign_target_and_incomplete_phase_material(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    foreign_target = uuid.uuid4()
    foreign_command = uuid.uuid4()
    async with session_factory() as db:
        db.add(_head(foreign_target, generation=1))
        await db.flush()
        db.add(_command(foreign_target, foreign_command, generation=1))
        await db.flush()
        db.add(
            _run(
                run_id=uuid.uuid4(),
                target_id=foreign_target,
                command_id=foreign_command,
                generation=1,
            )
        )
        with pytest.raises(IntegrityError, match="ck_ktm_ct_canary_stable_target"):
            await db.commit()

    incomplete_command = uuid.uuid4()
    async with session_factory() as db:
        db.add(_head(STABLE_TARGET_ID, generation=3))
        await db.flush()
        db.add(_command(STABLE_TARGET_ID, incomplete_command, generation=3))
        await db.flush()
        db.add(
            _run(
                run_id=uuid.uuid4(),
                target_id=STABLE_TARGET_ID,
                command_id=incomplete_command,
                generation=3,
                phase="put_applied",
            )
        )
        with pytest.raises(IntegrityError, match="ck_ktm_ct_canary_phase_material"):
            await db.commit()


async def test_canary_run_allows_only_one_running_row_for_stable_target(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    first_command = uuid.uuid4()
    second_command = uuid.uuid4()
    async with session_factory() as db:
        db.add(_head(STABLE_TARGET_ID, generation=3))
        await db.flush()
        db.add_all(
            [
                _command(STABLE_TARGET_ID, first_command, generation=1),
                _command(STABLE_TARGET_ID, second_command, generation=3),
            ]
        )
        await db.flush()
        db.add_all(
            [
                _run(
                    run_id=uuid.uuid4(),
                    target_id=STABLE_TARGET_ID,
                    command_id=first_command,
                    generation=1,
                ),
                _run(
                    run_id=uuid.uuid4(),
                    target_id=STABLE_TARGET_ID,
                    command_id=second_command,
                    generation=3,
                ),
            ]
        )
        with pytest.raises(IntegrityError, match="uq_ktm_ct_canary_running_target"):
            await db.commit()


async def test_canary_run_command_fk_binds_target_and_generation(session_factory) -> None:  # type: ignore[no-untyped-def]
    foreign_target = uuid.uuid4()
    foreign_command = uuid.uuid4()
    async with session_factory() as db:
        db.add_all(
            [
                _head(STABLE_TARGET_ID, generation=1),
                _head(foreign_target, generation=1),
            ]
        )
        await db.flush()
        db.add(_command(foreign_target, foreign_command, generation=1))
        await db.flush()
        db.add(
            _run(
                run_id=uuid.uuid4(),
                target_id=STABLE_TARGET_ID,
                command_id=foreign_command,
                generation=1,
            )
        )
        with pytest.raises(IntegrityError, match="fk_ktm_ct_canary_put_command"):
            await db.commit()


async def test_canary_run_final_evidence_is_all_or_none(session_factory) -> None:  # type: ignore[no-untyped-def]
    command_id = uuid.uuid4()
    async with session_factory() as db:
        db.add(_head(STABLE_TARGET_ID, generation=1))
        await db.flush()
        db.add(_command(STABLE_TARGET_ID, command_id, generation=1))
        await db.flush()
        run = _run(
            run_id=uuid.uuid4(),
            target_id=STABLE_TARGET_ID,
            command_id=command_id,
            generation=1,
        )
        run.final_local_cursor = "cursor-without-other-evidence"
        db.add(run)
        with pytest.raises(IntegrityError, match="ck_ktm_ct_canary_final_material"):
            await db.commit()
