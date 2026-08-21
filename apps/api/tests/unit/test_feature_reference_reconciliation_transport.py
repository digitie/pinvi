"""M05 Map reconciliation lease/ACK service transport contract."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable

import httpx
import pytest

from app.clients.kor_travel_map_feature_reference_reconciliation import (
    FeatureReferenceReconciliationContractError,
    FeatureReferenceReconciliationLeaseConflict,
    FeatureReferenceReconciliationProblem,
    FeatureReferenceReconciliationServiceClient,
)

Handler = Callable[[httpx.Request], httpx.Response]
READ_TOKEN = "r" * 32
ACK_TOKEN = "a" * 32


def _client(
    role: str, handler: Handler, *, token: str | None = None
) -> FeatureReferenceReconciliationServiceClient:
    return FeatureReferenceReconciliationServiceClient(
        httpx.AsyncClient(
            base_url="http://map.test",
            transport=httpx.MockTransport(handler),
        ),
        role=role,  # type: ignore[arg-type]
        token=token or (READ_TOKEN if role == "read" else ACK_TOKEN),
    )


def _event(*, action: str = "rebind") -> dict[str, object]:
    old = {
        "feature_id": "f_manual",
        "feature_uuid": "11111111-1111-4111-8111-111111111111",
        "row_revision": 4,
    }
    replacement = {
        "feature_id": "f_provider",
        "feature_uuid": "22222222-2222-4222-8222-222222222222",
        "row_revision": 9,
    }
    return {
        "payload_schema_version": 1,
        "event_id": "33333333-3333-4333-8333-333333333333",
        "event_sequence": 12,
        "occurred_at": "2026-08-21T00:00:00+00:00",
        "case_id": "44444444-4444-4444-8444-444444444444",
        "resolution_id": "55555555-5555-4555-8555-555555555555",
        "action": action,
        "old_feature": old,
        "replacement_feature": replacement if action == "rebind" else None,
        "manual_retire_transition_id": 40,
        "manual_retire_row_revision_after_transition": 5,
        "command_id": 81,
    }


@pytest.mark.asyncio
async def test_read_lease_uses_exact_path_header_and_strict_event_shape() -> None:
    worker_id = uuid.UUID("66666666-6666-4666-8666-666666666666")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/service/feature-reference-reconciliations"
        assert request.headers["X-Kor-Travel-Map-Service-Token"] == READ_TOKEN
        assert request.headers["X-Reconciliation-Worker-Id"] == str(worker_id)
        assert "Idempotency-Key" not in request.headers
        return httpx.Response(
            200,
            json={
                "data": {
                    "outcome": "leased",
                    "lease_epoch": 3,
                    "lease_expires_at": "2026-08-21T00:01:00+00:00",
                    "event": _event(),
                    "event_sha256": "a" * 64,
                },
                "meta": {"duration_ms": 1, "request_id": "map-request"},
            },
        )

    client = _client("read", handler)
    try:
        lease = await client.lease(worker_id=worker_id)
    finally:
        await client.aclose()

    assert lease is not None
    assert lease.event.action == "rebind"
    assert lease.event.replacement_feature is not None
    assert lease.event.event_sequence == 12


@pytest.mark.asyncio
async def test_empty_and_other_worker_lease_are_distinct_outcomes() -> None:
    worker_id = uuid.uuid4()
    empty = _client("read", lambda _request: httpx.Response(204))
    try:
        assert await empty.lease(worker_id=worker_id) is None
    finally:
        await empty.aclose()

    def conflict(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "type": "https://map.test/errors/lease-conflict",
                "title": "lease conflict",
                "status": 409,
                "detail": "other worker",
                "code": "FEATURE_REFERENCE_RECONCILIATION_LEASE_CONFLICT",
                "request_id": "map-request",
                "errors": [],
            },
        )

    client = _client("read", conflict)
    try:
        with pytest.raises(FeatureReferenceReconciliationLeaseConflict) as raised:
            await client.lease(worker_id=worker_id)
    finally:
        await client.aclose()
    assert raised.value.code == "FEATURE_REFERENCE_RECONCILIATION_LEASE_CONFLICT"


@pytest.mark.asyncio
async def test_ack_uses_separate_token_and_preserves_replay_receipt() -> None:
    worker_id = uuid.UUID("66666666-6666-4666-8666-666666666666")
    event_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    key = uuid.UUID("77777777-7777-4777-8777-777777777777")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/service/feature-reference-reconciliations/{event_id}/acks"
        assert request.headers["X-Kor-Travel-Map-Service-Token"] == ACK_TOKEN
        assert request.headers["Idempotency-Key"] == str(key)
        assert json.loads(request.content) == {
            "worker_id": str(worker_id),
            "lease_epoch": 3,
            "event_sha256": "a" * 64,
            "local_receipt_sha256": "b" * 64,
        }
        return httpx.Response(
            200,
            headers={"Idempotency-Replayed": "true"},
            json={
                "data": {"outcome": "replayed", "acked_through_sequence": 12},
                "meta": {"duration_ms": 1, "request_id": "map-request"},
            },
        )

    client = _client("ack", handler)
    try:
        receipt = await client.acknowledge(
            event_id=event_id,
            event_sequence=12,
            worker_id=worker_id,
            lease_epoch=3,
            event_sha256="a" * 64,
            local_receipt_sha256="b" * 64,
            idempotency_key=key,
        )
    finally:
        await client.aclose()
    assert receipt.outcome == "replayed"
    assert receipt.acked_through_sequence == 12


@pytest.mark.asyncio
async def test_transport_rejects_malformed_event_and_ack_replay_header() -> None:
    worker_id = uuid.uuid4()

    def malformed_lease(_request: httpx.Request) -> httpx.Response:
        event = _event(action="detach")
        event["replacement_feature"] = _event()["replacement_feature"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "outcome": "leased",
                    "lease_epoch": 3,
                    "lease_expires_at": "2026-08-21T00:01:00+00:00",
                    "event": event,
                    "event_sha256": "a" * 64,
                },
                "meta": {"duration_ms": 1},
            },
        )

    client = _client("read", malformed_lease)
    try:
        with pytest.raises(FeatureReferenceReconciliationContractError):
            await client.lease(worker_id=worker_id)
    finally:
        await client.aclose()

    def malformed_replay(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Idempotency-Replayed": "true"},
            json={
                "data": {"outcome": "acked", "acked_through_sequence": 12},
                "meta": {"duration_ms": 1},
            },
        )

    client = _client("ack", malformed_replay)
    try:
        with pytest.raises(FeatureReferenceReconciliationContractError):
            await client.acknowledge(
                event_id=uuid.uuid4(),
                event_sequence=12,
                worker_id=worker_id,
                lease_epoch=1,
                event_sha256="a" * 64,
                local_receipt_sha256="b" * 64,
                idempotency_key=uuid.uuid4(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_role_and_non_success_boundaries_fail_closed() -> None:
    client = _client("read", lambda _request: httpx.Response(200, json={"data": {}, "meta": {}}))
    try:
        with pytest.raises(PermissionError):
            await client.acknowledge(
                event_id=uuid.uuid4(),
                event_sequence=12,
                worker_id=uuid.uuid4(),
                lease_epoch=1,
                event_sha256="a" * 64,
                local_receipt_sha256="b" * 64,
                idempotency_key=uuid.uuid4(),
            )
    finally:
        await client.aclose()

    client = _client(
        "ack",
        lambda _request: httpx.Response(
            422,
            json={"code": "VALIDATION_ERROR"},
        ),
    )
    try:
        with pytest.raises(FeatureReferenceReconciliationProblem) as raised:
            await client.acknowledge(
                event_id=uuid.uuid4(),
                event_sequence=12,
                worker_id=uuid.uuid4(),
                lease_epoch=1,
                event_sha256="a" * 64,
                local_receipt_sha256="b" * 64,
                idempotency_key=uuid.uuid4(),
            )
    finally:
        await client.aclose()
    assert raised.value.status_code == 422


@pytest.mark.asyncio
async def test_ack_rejects_cursor_before_event_sequence() -> None:
    client = _client(
        "ack",
        lambda _request: httpx.Response(
            200,
            json={
                "data": {"outcome": "acked", "acked_through_sequence": 0},
                "meta": {"duration_ms": 1, "request_id": "map-request"},
            },
        ),
    )
    try:
        with pytest.raises(FeatureReferenceReconciliationContractError):
            await client.acknowledge(
                event_id=uuid.uuid4(),
                event_sequence=12,
                worker_id=uuid.uuid4(),
                lease_epoch=1,
                event_sha256="a" * 64,
                local_receipt_sha256="b" * 64,
                idempotency_key=uuid.uuid4(),
            )
    finally:
        await client.aclose()
