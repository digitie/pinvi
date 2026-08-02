"""cache-target final boundary strict request/CLI 계약."""

from __future__ import annotations

import io
import json
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.commands import cache_target_final_boundary as command
from app.models.cache_target_sync import (
    KtmCacheTargetCommand,
    KtmCacheTargetEvent,
    KtmCacheTargetHead,
)
from app.services.cache_target_boundary_evidence import (
    canonical_sha256,
    validate_initial_state_event,
)
from app.services.cache_target_final_boundary import (
    CONTRACT_VERSION,
    WRITER_REGISTRY_SHA256,
    CacheTargetBoundaryFailure,
    CacheTargetBoundaryRequest,
)


def _request(operation: str = "preflight") -> dict[str, object]:
    map_evidence: dict[str, object] | None = (
        {
            "contract_version": "ktm-cache-target-final-evidence/v1",
            "external_system": "pinvi",
            "stream_state": "ready",
            "consumer_id": "pinvi-cache-target-consumer",
            "restore_epoch": 7,
            "control_version": 7,
            "stream_control_etag": '"stream:7"',
            "high_watermark_cursor": "cursor-7",
            "snapshot_count": 0,
            "snapshot_merkle_root": "0" * 64,
            "reconciliation_backlog_count": 0,
            "outbox_backlog_count": 0,
            "claim_backlog_count": 0,
            "delivery_backlog_count": 0,
        }
        if operation == "finalize"
        else None
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "operation": operation,
        "transaction_id": str(uuid.uuid4()),
        "cutover_id": str(uuid.uuid4()),
        "source_revision": "a" * 40,
        "database_identity": "b" * 64,
        "writer_registry_sha256": WRITER_REGISTRY_SHA256,
        "initial_writer_fence_sha256": "c" * 64,
        "final_writer_fence_sha256": "e" * 64 if operation == "finalize" else None,
        "prior_receipt_sha256": "d" * 64 if operation == "finalize" else None,
        "canary_run_id": str(uuid.uuid4()) if operation == "finalize" else None,
        "map_final_evidence": map_evidence,
        "map_final_evidence_sha256": (
            canonical_sha256(map_evidence).hex() if map_evidence is not None else None
        ),
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(extra="forbidden"), "request fields"),
        (
            lambda value: value.update(writer_registry_sha256="0" * 64),
            "writer registry",
        ),
        (lambda value: value.update(source_revision="A" * 40), "source_revision"),
        (lambda value: value.update(transaction_id=str(uuid.uuid4()).upper()), "transaction_id"),
        (lambda value: value.update(prior_receipt_sha256="d" * 64), "preflight binding"),
    ],
)
def test_boundary_request_rejects_non_exact_material(mutation, message: str) -> None:  # type: ignore[no-untyped-def]
    value = _request()
    mutation(value)
    with pytest.raises(ValueError, match=message):
        CacheTargetBoundaryRequest.parse(value)


def test_finalize_request_requires_prior_receipt_and_canary() -> None:
    value = _request("finalize")
    parsed = CacheTargetBoundaryRequest.parse(value)
    assert parsed.operation == "finalize"
    assert parsed.prior_receipt_sha256 == "d" * 64
    assert parsed.canary_run_id is not None
    assert canonical_sha256(parsed.json_object()).hex() == canonical_sha256(value).hex()

    value["canary_run_id"] = None
    with pytest.raises(ValueError, match="canary_run_id"):
        CacheTargetBoundaryRequest.parse(value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["map_final_evidence"].update(extra="forbidden"),
        lambda value: value["map_final_evidence"].update(outbox_backlog_count=1),
        lambda value: value.update(map_final_evidence_sha256="0" * 64),
        lambda value: value.update(final_writer_fence_sha256=value["initial_writer_fence_sha256"]),
    ],
    ids=("map-extra", "map-backlog", "map-digest", "same-fence"),
)
def test_finalize_request_rejects_non_exact_map_and_fence(mutation) -> None:  # type: ignore[no-untyped-def]
    value = _request("finalize")
    mutation(value)
    with pytest.raises(ValueError):
        CacheTargetBoundaryRequest.parse(value)


@pytest.mark.parametrize(
    "argv",
    [[], ["verify"], ["finalize", "secret-value"]],
)
def test_boundary_argparse_error_is_secret_free_json(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        command._parse_args(argv)
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == '{"error_code":"invalid_arguments","phase":"startup"}\n'
    assert "secret-value" not in captured.err


class _BinaryStdin:
    def __init__(self, value: bytes) -> None:
        self.buffer = io.BytesIO(value)


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"{}\n{}\n",
        b'{"operation":"preflight","operation":"finalize"}\n',
        b"\xff\n",
    ],
)
def test_boundary_stdin_error_never_echoes_input(
    raw: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdin", _BinaryStdin(raw))
    with pytest.raises(CacheTargetBoundaryFailure, match="invalid_request"):
        command._read_request("preflight")


def test_boundary_stdin_accepts_one_exact_json_line(monkeypatch: pytest.MonkeyPatch) -> None:
    value = _request()
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    monkeypatch.setattr(sys, "stdin", _BinaryStdin(raw))
    parsed = command._read_request("preflight")
    assert parsed.transaction_id == uuid.UUID(str(value["transaction_id"]))


def _initial_provenance() -> tuple[KtmCacheTargetCommand, KtmCacheTargetHead, KtmCacheTargetEvent]:
    command_id = uuid.uuid4()
    poi_id = uuid.uuid4()
    target_id = uuid.uuid4()
    payload = {
        "version": "cache-target-source-v1",
        "state": "active",
        "coord": {"lon_e6": 127000000, "lat_e6": 37000000},
        "radius_m": 5000,
        "update_enabled": True,
    }
    fingerprint = canonical_sha256(payload)
    command_row = KtmCacheTargetCommand(
        command_id=command_id,
        poi_id=poi_id,
        operation="put",
        source_generation=3,
        payload=payload,
        payload_fingerprint=fingerprint,
        status="succeeded",
    )
    head = KtmCacheTargetHead(
        poi_id=poi_id,
        external_system="pinvi",
        target_key=str(poi_id),
        desired_state="active",
        source_generation=3,
        source_payload_fingerprint=fingerprint,
        lon=Decimal("127"),
        lat=Decimal("37"),
        radius_km=Decimal("5"),
        update_enabled=True,
        remote_target_id=target_id,
        remote_etag='"target:3"',
        remote_restore_epoch=7,
        remote_source_generation=3,
        remote_target_sequence=9,
        remote_status="active",
    )
    event_payload = {
        "version": "cache-target-event-v1",
        "state": "active",
        "source_event_id": str(command_id),
        "target": {
            "target_id": str(target_id),
            "entity_tag": '"target:3"',
            "coord": {"lon_e6": 127000000, "lat_e6": 37000000},
            "radius_m": 5000,
            "update_enabled": True,
        },
    }
    event = KtmCacheTargetEvent(
        event_id=uuid.uuid4(),
        source_event_id=command_id,
        event_type="cache_target.state_applied",
        external_system="pinvi",
        target_key=str(poi_id),
        target_id=target_id,
        restore_epoch=7,
        source_generation=3,
        target_sequence=9,
        relay_order=1,
        source_payload_fingerprint=fingerprint,
        payload_fingerprint=canonical_sha256(event_payload),
        occurred_at=datetime.now(UTC),
        payload=event_payload,
        applied_at=datetime.now(UTC),
    )
    return command_row, head, event


@pytest.mark.parametrize(
    "mutation",
    [
        lambda _command, _head, event: setattr(event, "event_type", "cache_target.reconciled"),
        lambda _command, _head, event: setattr(event, "external_system", "foreign"),
        lambda _command, _head, event: setattr(event, "target_key", str(uuid.uuid4())),
        lambda _command, _head, event: setattr(event, "target_id", uuid.uuid4()),
        lambda _command, _head, event: setattr(event, "restore_epoch", 8),
        lambda _command, _head, event: setattr(event, "source_event_id", uuid.uuid4()),
        lambda _command, _head, event: setattr(event, "source_generation", 4),
        lambda _command, _head, event: setattr(event, "target_sequence", 10),
        lambda _command, _head, event: setattr(event, "source_payload_fingerprint", b"x" * 32),
        lambda _command, _head, event: setattr(event, "payload", {"version": "wrong"}),
        lambda _command, _head, event: setattr(event, "payload_fingerprint", b"x" * 32),
        lambda _command, _head, event: setattr(event, "applied_at", None),
    ],
    ids=(
        "event-type",
        "external-system",
        "target-key",
        "target-id",
        "restore-epoch",
        "source-event-id",
        "source-generation",
        "target-sequence",
        "source-fingerprint",
        "payload",
        "payload-fingerprint",
        "applied-at",
    ),
)
def test_initial_state_event_rejects_each_provenance_field_mutation(mutation) -> None:  # type: ignore[no-untyped-def]
    command_row, head, event = _initial_provenance()
    mutation(command_row, head, event)
    with pytest.raises(ValueError, match="initial event provenance"):
        validate_initial_state_event(
            command=command_row,
            event=event,
            head=head,
            restore_epoch=7,
        )
