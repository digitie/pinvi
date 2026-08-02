"""docker-manager에 전달하는 causal canary raw receipt 계약."""

from __future__ import annotations

import asyncio
import sys
import uuid

import httpx
import pytest
from pydantic import ValidationError

from app.commands import cache_target_causal_canary as command
from app.services.cache_target_causal_canary import (
    CacheTargetCanaryFailure,
    CacheTargetCanaryReceipt,
)
from app.services.cache_target_event_consumer import CacheTargetSnapshot


def test_success_receipt_keeps_both_sides_and_backlog_counts_explicit() -> None:
    receipt = CacheTargetCanaryReceipt(
        status="succeeded",
        run_id=uuid.uuid4(),
        target_poi_id=uuid.uuid4(),
        put_command_id=uuid.uuid4(),
        delete_command_id=uuid.uuid4(),
        put_event_id=uuid.uuid4(),
        delete_event_id=uuid.uuid4(),
        put_generation=7,
        delete_generation=8,
        put_relay_order=11,
        delete_relay_order=12,
        baseline_cache_generation=20,
        put_cache_generation=21,
        final_cache_generation=22,
        pending_commands=0,
        leased_commands=0,
        dead_letter_commands=0,
        local_applied_cursor="cursor-12",
        remote_acked_cursor="cursor-12",
        local_count=4,
        remote_count=4,
        local_merkle_root="ab" * 32,
        remote_merkle_root="ab" * 32,
    )

    assert set(receipt.json_object()) == {
        "status",
        "run_id",
        "target_poi_id",
        "put_command_id",
        "delete_command_id",
        "put_event_id",
        "delete_event_id",
        "put_generation",
        "delete_generation",
        "put_relay_order",
        "delete_relay_order",
        "baseline_cache_generation",
        "put_cache_generation",
        "final_cache_generation",
        "pending_commands",
        "leased_commands",
        "dead_letter_commands",
        "local_applied_cursor",
        "remote_acked_cursor",
        "local_count",
        "remote_count",
        "local_merkle_root",
        "remote_merkle_root",
    }


def _snapshot_validation_error(marker: str) -> ValidationError:
    try:
        CacheTargetSnapshot.model_validate(
            {
                "snapshot_id": marker,
                "restore_epoch": "invalid",
                "raw_url": f"https://user:{marker}@invalid.test",
            }
        )
    except ValidationError as exc:
        return exc
    raise AssertionError("invalid snapshot이 ValidationError를 내지 않았습니다.")


@pytest.mark.parametrize(
    "failure",
    (
        _snapshot_validation_error("PYDANTIC-RAW-SECRET"),
        httpx.InvalidURL("https://user:URL-SECRET@invalid test"),
        ValueError("TOKEN-SECRET"),
    ),
    ids=("pydantic", "url", "token"),
)
def test_cli_unexpected_failure_is_exact_one_line_without_raw_cause(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
) -> None:
    async def fail(_args: object) -> dict[str, int | str]:
        raise failure

    monkeypatch.setattr(command, "_run", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        ["pinvi-cache-target-causal-canary", "--run-id", str(uuid.uuid4())],
    )

    with pytest.raises(SystemExit, match="1"):
        command.main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == '{"error_code":"internal_error","phase":"runtime"}\n'
    assert "Traceback" not in captured.err
    assert "SECRET" not in captured.err


def test_cli_typed_failure_keeps_only_code_and_phase(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fail(_args: object) -> dict[str, int | str]:
        raise CacheTargetCanaryFailure("final_snapshot_invalid", "delete_applied")

    monkeypatch.setattr(command, "_run", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        ["pinvi-cache-target-causal-canary", "--run-id", str(uuid.uuid4())],
    )

    with pytest.raises(SystemExit, match="1"):
        command.main()
    assert capsys.readouterr().err == (
        '{"error_code":"final_snapshot_invalid","phase":"delete_applied"}\n'
    )


@pytest.mark.parametrize("control", (asyncio.CancelledError(), SystemExit(7)))
def test_cli_does_not_swallow_cancellation_or_system_exit(
    monkeypatch: pytest.MonkeyPatch,
    control: BaseException,
) -> None:
    async def stop(_args: object) -> dict[str, int | str]:
        raise control

    monkeypatch.setattr(command, "_run", stop)
    monkeypatch.setattr(
        sys,
        "argv",
        ["pinvi-cache-target-causal-canary", "--run-id", str(uuid.uuid4())],
    )

    with pytest.raises(type(control)):
        command.main()
