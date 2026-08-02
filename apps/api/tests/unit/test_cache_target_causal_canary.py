"""docker-manager에 전달하는 causal canary raw receipt 계약."""

from __future__ import annotations

import uuid

from app.services.cache_target_causal_canary import CacheTargetCanaryReceipt


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
