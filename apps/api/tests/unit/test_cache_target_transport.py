"""cache target role-bound service transport와 failure classification."""

from __future__ import annotations

import asyncio
import gc
import hashlib
import json
import uuid
import weakref
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.clients.kor_travel_map_cache_target import (
    CacheTargetContractError,
    CacheTargetServiceClient,
    CacheTargetServiceProblem,
    CacheTargetStateResult,
    _snapshot_lock,
    classify_cache_target_failure,
)
from app.core.cache_target_contract import (
    ActiveCacheTargetSource,
    cache_target_source_fingerprint,
)
from app.services.cache_target_event_consumer import CacheTargetSnapshot
from app.services.cache_target_sync_worker import build_cache_target_nack

Handler = Callable[[httpx.Request], httpx.Response]
TOKEN = "t" * 32


def _client(role: str, handler: Handler) -> CacheTargetServiceClient:
    http = httpx.AsyncClient(
        base_url="http://map.test",
        transport=httpx.MockTransport(handler),
    )
    return CacheTargetServiceClient(http, role=role, token=TOKEN)  # type: ignore[arg-type]


def _empty_snapshot_response() -> dict[str, object]:
    created_at = datetime.now(UTC)
    return {
        "data": {
            "snapshot_id": str(uuid.uuid4()),
            "restore_epoch": 7,
            "high_watermark_cursor": "cursor-0",
            "count": 0,
            "merkle_root": "72" * 32,
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(hours=2)).isoformat(),
            "items": [],
        },
        "meta": {"page": {"next_cursor": None}},
    }


@pytest.mark.parametrize(
    ("status_code", "code", "expected"),
    [
        (401, "UNAUTHORIZED", "halt"),
        (403, "FORBIDDEN", "halt"),
        (409, "CACHE_TARGET_RESTORE_EPOCH_MISMATCH", "halt"),
        (409, "CACHE_TARGET_IDEMPOTENCY_CONFLICT", "dead_letter"),
        (412, "PRECONDITION_FAILED", "reconcile"),
        (422, "VALIDATION_ERROR", "dead_letter"),
        (503, "SERVICE_UNAVAILABLE", "retry"),
    ],
)
def test_failure_classification(status_code: int, code: str, expected: str) -> None:
    assert classify_cache_target_failure(status_code=status_code, code=code) == expected


def test_mutation_result_rejects_coerced_tuple_and_noncanonical_etag() -> None:
    target_id = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    valid = {
        "external_system": "pinvi",
        "target_key": str(uuid.uuid4()),
        "state": "active",
        "restore_epoch": 7,
        "source_generation": 1,
        "source_payload_fingerprint": "a" * 64,
        "entity_tag": f'"{target_id}:1"',
        "target_id": str(target_id),
        "target_sequence": 1,
    }
    invalid_results = [
        {**valid, "restore_epoch": "7"},
        {**valid, "target_sequence": True},
        {**valid, "entity_tag": f'"{target_id}:not-a-version"'},
        {**valid, "entity_tag": f'"{target_id}:01"'},
        {**valid, "target_id": str(target_id).upper()},
    ]
    for invalid in invalid_results:
        with pytest.raises(ValueError):
            CacheTargetStateResult.model_validate(invalid)


@pytest.mark.asyncio
async def test_command_transport_sends_only_role_token_and_exact_preconditions() -> None:
    command_id = uuid.uuid4()
    target_key = str(uuid.uuid4())
    target_id = uuid.uuid4()
    occurred_at = datetime(2026, 7, 31, tzinfo=UTC)
    source_fingerprint = cache_target_source_fingerprint(
        ActiveCacheTargetSource(
            lon_e6=126_000_000,
            lat_e6=37_000_000,
            radius_m=5000,
            update_enabled=True,
        )
    ).hex()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == f"/v1/service/cache-targets/pinvi/{target_key}"
        assert request.headers["X-Kor-Travel-Map-Service-Token"] == TOKEN
        assert request.headers["Idempotency-Key"] == str(command_id)
        assert request.headers["If-None-Match"] == "*"
        assert "Authorization" not in request.headers
        assert request.read()
        assert request.headers["Content-Type"] == "application/json"
        assert request.content
        assert json.loads(request.content) == {
            "source_event_id": str(command_id),
            "restore_epoch": 7,
            "source_generation": 1,
            "coord": {"lon": "126.000000", "lat": "37.000000"},
            "radius_km": "5.000",
            "update_enabled": True,
            "occurred_at": "2026-07-31T00:00:00Z",
        }
        return httpx.Response(
            200,
            headers={"ETag": f'"{target_id}:1"'},
            json={
                "data": {
                    "external_system": "pinvi",
                    "target_key": target_key,
                    "state": "active",
                    "restore_epoch": 7,
                    "source_generation": 1,
                    "source_payload_fingerprint": source_fingerprint,
                    "entity_tag": f'"{target_id}:1"',
                    "target_id": str(target_id),
                    "target_sequence": 1,
                    "occurred_at": "2026-07-31T00:00:00Z",
                    "updated_at": "2026-07-31T00:00:01Z",
                },
                "meta": {},
            },
        )

    client = _client("command", handler)
    try:
        result = await client.put_target(
            external_system="pinvi",
            target_key=target_key,
            command_id=command_id,
            restore_epoch=7,
            source_generation=1,
            occurred_at=occurred_at,
            source_payload={
                "version": "cache-target-source-v1",
                "state": "active",
                "coord": {"lon_e6": 126_000_000, "lat_e6": 37_000_000},
                "radius_m": 5000,
                "update_enabled": True,
            },
            expected_etag=None,
        )
    finally:
        await client.aclose()

    assert result.status_code == 200
    assert result.etag == f'"{target_id}:1"'
    assert result.data.target_id == target_id


@pytest.mark.asyncio
async def test_consumer_target_read_returns_etag_for_command_cas_transition() -> None:
    target_key = str(uuid.uuid4())
    target_id = uuid.uuid4()
    entity_tag = f'"{target_id}:4"'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/service/cache-targets/pinvi/{target_key}"
        assert request.url.params.get("include_deleted") == "false"
        assert request.headers["X-Kor-Travel-Map-Service-Token"] == TOKEN
        assert "Idempotency-Key" not in request.headers
        return httpx.Response(
            200,
            headers={"ETag": entity_tag},
            json={
                "data": {
                    "external_system": "pinvi",
                    "target_key": target_key,
                    "state": "active",
                    "restore_epoch": 7,
                    "source_generation": 4,
                    "source_payload_fingerprint": "a" * 64,
                    "entity_tag": entity_tag,
                    "target_id": str(target_id),
                    "target_sequence": 4,
                    "occurred_at": "2026-08-02T00:00:00Z",
                    "updated_at": "2026-08-02T00:00:01Z",
                },
                "meta": {},
            },
        )

    client = _client("consumer", handler)
    try:
        result = await client.get_target(
            external_system="pinvi",
            target_key=target_key,
        )
    finally:
        await client.aclose()

    assert result.etag == entity_tag
    assert result.data.state == "active"


@pytest.mark.asyncio
async def test_consumer_target_read_accepts_tombstone_without_live_incarnation() -> None:
    target_key = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("include_deleted") == "true"
        return httpx.Response(
            200,
            json={
                "data": {
                    "external_system": "pinvi",
                    "target_key": target_key,
                    "state": "deleted",
                    "restore_epoch": 7,
                    "source_generation": 4,
                    "source_payload_fingerprint": "a" * 64,
                    "entity_tag": None,
                    "target_id": None,
                    "target_sequence": 4,
                    "occurred_at": "2026-08-02T00:00:00Z",
                    "updated_at": "2026-08-02T00:00:01Z",
                },
                "meta": {},
            },
        )

    client = _client("consumer", handler)
    try:
        result = await client.get_target(
            external_system="pinvi",
            target_key=target_key,
            include_deleted=True,
        )
    finally:
        await client.aclose()

    assert result.etag is None
    assert result.data.state == "deleted"
    assert result.data.target_sequence == 4


@pytest.mark.asyncio
async def test_command_refresh_create_then_consumer_status_poll_use_separate_tokens() -> None:
    request_id = uuid.uuid4()
    target_key = str(uuid.uuid4())
    command_token = "c" * 32
    consumer_token = "r" * 32
    status_url = f"/v1/service/refresh-requests/{request_id}"

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers["X-Kor-Travel-Map-Service-Token"]
        if request.method == "POST":
            assert token == command_token
            assert request.url.path == "/v1/service/refresh-requests"
            assert request.headers["Idempotency-Key"] == str(request_id)
            assert json.loads(request.content) == {
                "external_system": "pinvi",
                "target_keys": [target_key],
                "reason": "causal canary refresh",
            }
            return httpx.Response(
                202,
                headers={"Location": status_url, "Retry-After": "5"},
                json={
                    "data": {
                        "request_id": str(request_id),
                        "status": "queued",
                        "status_url": status_url,
                        "retry_after_seconds": 5,
                        "created_at": "2026-08-02T00:00:00Z",
                        "updated_at": "2026-08-02T00:00:00Z",
                    },
                    "meta": {},
                },
            )
        assert request.method == "GET"
        assert token == consumer_token
        assert request.url.path == status_url
        assert "Idempotency-Key" not in request.headers
        return httpx.Response(
            200,
            json={
                "data": {
                    "request_id": str(request_id),
                    "status": "succeeded",
                    "status_url": status_url,
                    "retry_after_seconds": None,
                    "created_at": "2026-08-02T00:00:00Z",
                    "updated_at": "2026-08-02T00:00:05Z",
                },
                "meta": {},
            },
        )

    transport = httpx.MockTransport(handler)
    command = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=transport),
        role="command",
        token=command_token,
    )
    consumer = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=transport),
        role="consumer",
        token=consumer_token,
    )
    try:
        created = await command.create_refresh_request(
            external_system="pinvi",
            target_keys=[target_key],
            reason="causal canary refresh",
            idempotency_key=request_id,
        )
        status = await consumer.get_refresh_request(request_id=request_id)
    finally:
        await command.aclose()
        await consumer.aclose()

    assert created.location == status_url
    assert created.retry_after == 5
    assert status.data.status == "succeeded"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["put", "delete"])
async def test_if_match_mutation_rejects_other_target_incarnation(operation: str) -> None:
    command_id = uuid.uuid4()
    target_key = str(uuid.uuid4())
    expected_target_id = uuid.uuid4()
    other_target_id = uuid.uuid4()
    occurred_at = datetime(2026, 7, 31, tzinfo=UTC)
    source_payload: dict[str, Any]
    state: str
    if operation == "put":
        state = "active"
        source_payload = {
            "version": "cache-target-source-v1",
            "state": "active",
            "coord": {"lon_e6": 126_000_000, "lat_e6": 37_000_000},
            "radius_m": 5000,
            "update_enabled": True,
        }
    else:
        state = "deleted"
        source_payload = {"version": "cache-target-source-v1", "state": "deleted"}
    source_fingerprint = hashlib.sha256(
        json.dumps(
            source_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-Match"] == f'"{expected_target_id}:7"'
        return httpx.Response(
            200,
            headers={"ETag": f'"{other_target_id}:8"'},
            json={
                "data": {
                    "external_system": "pinvi",
                    "target_key": target_key,
                    "state": state,
                    "restore_epoch": 7,
                    "source_generation": 2,
                    "source_payload_fingerprint": source_fingerprint,
                    "entity_tag": f'"{other_target_id}:8"',
                    "target_id": str(other_target_id),
                    "target_sequence": 2,
                },
                "meta": {},
            },
        )

    client = _client("command", handler)
    try:
        with pytest.raises(CacheTargetContractError, match="If-Match target incarnation"):
            if operation == "put":
                await client.put_target(
                    external_system="pinvi",
                    target_key=target_key,
                    command_id=command_id,
                    restore_epoch=7,
                    source_generation=2,
                    occurred_at=occurred_at,
                    source_payload=source_payload,
                    expected_etag=f'"{expected_target_id}:7"',
                )
            else:
                await client.delete_target(
                    external_system="pinvi",
                    target_key=target_key,
                    command_id=command_id,
                    restore_epoch=7,
                    source_generation=2,
                    occurred_at=occurred_at,
                    source_payload=source_payload,
                    expected_etag=f'"{expected_target_id}:7"',
                )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_principal_cannot_call_another_role_surface() -> None:
    client = _client("consumer", lambda request: httpx.Response(500))
    with pytest.raises(PermissionError, match="command"):
        await client.delete_target(
            external_system="pinvi",
            target_key=str(uuid.uuid4()),
            command_id=uuid.uuid4(),
            restore_epoch=7,
            source_generation=2,
            occurred_at=datetime.now(UTC),
            source_payload={"version": "cache-target-source-v1", "state": "deleted"},
            expected_etag='"target-1"',
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_command_consumer_transition_surfaces_fail_closed_before_http() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    request_id = uuid.uuid4()
    target_key = str(uuid.uuid4())
    command = _client("command", handler)
    consumer = _client("consumer", handler)
    try:
        with pytest.raises(PermissionError, match="consumer"):
            await command.get_target(external_system="pinvi", target_key=target_key)
        with pytest.raises(PermissionError, match="consumer"):
            await command.get_refresh_request(request_id=request_id)
        with pytest.raises(PermissionError, match="command"):
            await consumer.create_refresh_request(
                external_system="pinvi",
                target_keys=[target_key],
                reason="role split",
                idempotency_key=request_id,
            )
    finally:
        await command.aclose()
        await consumer.aclose()

    assert calls == 0


@pytest.mark.asyncio
async def test_generation7_swapped_server_credentials_fail_closed() -> None:
    command_token = "c" * 32
    consumer_token = "r" * 32
    seen_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_tokens.append(request.headers["X-Kor-Travel-Map-Service-Token"])
        return httpx.Response(
            403,
            json={
                "type": "about:blank",
                "title": "Forbidden",
                "status": 403,
                "code": "CACHE_TARGET_SCOPE_FORBIDDEN",
                "detail": "wrong generation 7 role credential",
            },
        )

    transport = httpx.MockTransport(handler)
    swapped_command = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=transport),
        role="command",
        token=consumer_token,
    )
    swapped_consumer = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=transport),
        role="consumer",
        token=command_token,
    )
    try:
        with pytest.raises(CacheTargetServiceProblem) as command_problem:
            await swapped_command.create_refresh_request(
                external_system="pinvi",
                target_keys=[str(uuid.uuid4())],
                reason="token swap negative gate",
                idempotency_key=uuid.uuid4(),
            )
        with pytest.raises(CacheTargetServiceProblem) as consumer_problem:
            await swapped_consumer.get_refresh_request(request_id=uuid.uuid4())
    finally:
        await swapped_command.aclose()
        await swapped_consumer.aclose()

    assert command_problem.value.status_code == 403
    assert command_problem.value.code == "CACHE_TARGET_SCOPE_FORBIDDEN"
    assert consumer_problem.value.status_code == 403
    assert consumer_problem.value.code == "CACHE_TARGET_SCOPE_FORBIDDEN"
    assert seen_tokens == [consumer_token, command_token]


@pytest.mark.asyncio
async def test_problem_preserves_typed_status_code_without_secret_body_logging() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "type": "about:blank",
                "title": "Conflict",
                "status": 409,
                "code": "CACHE_TARGET_IDEMPOTENCY_CONFLICT",
                "detail": "body mismatch",
            },
        )

    client = _client("command", handler)
    with pytest.raises(CacheTargetServiceProblem) as caught:
        await client.delete_target(
            external_system="pinvi",
            target_key=str(uuid.uuid4()),
            command_id=uuid.uuid4(),
            restore_epoch=7,
            source_generation=2,
            occurred_at=datetime.now(UTC),
            source_payload={"version": "cache-target-source-v1", "state": "deleted"},
            expected_etag='"target-1"',
        )
    await client.aclose()

    assert caught.value.status_code == 409
    assert caught.value.code == "CACHE_TARGET_IDEMPOTENCY_CONFLICT"
    assert caught.value.disposition == "dead_letter"


@pytest.mark.asyncio
async def test_reconciliation_completion_binds_request_snapshot_epoch_root_and_key() -> None:
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == (
            f"/v1/service/cache-target-reconciliations/{request_id}/completions"
        )
        assert request.headers["Idempotency-Key"] == str(idempotency_key)
        assert json.loads(request.content) == {
            "external_system": "pinvi",
            "consumer_id": "pinvi-cache-target-consumer",
            "snapshot_id": str(snapshot_id),
            "expected_restore_epoch": 7,
            "actual_merkle_root": "72" * 32,
        }
        return httpx.Response(
            200,
            json={
                "data": {
                    "operation_id": str(request_id),
                    "status": "succeeded",
                    "snapshot_id": str(snapshot_id),
                    "status_url": None,
                },
                "meta": {},
            },
        )

    client = _client("consumer", handler)
    try:
        result = await client.complete_reconciliation(
            request_id=request_id,
            consumer_id="pinvi-cache-target-consumer",
            snapshot=CacheTargetSnapshot(
                snapshot_id=str(snapshot_id),
                restore_epoch=7,
                high_watermark_cursor="cursor-0",
                count=0,
                merkle_root="72" * 32,
                created_at=datetime(2026, 8, 1, tzinfo=UTC),
                expires_at=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(hours=2),
                items=[],
            ),
            idempotency_key=idempotency_key,
        )
    finally:
        await client.aclose()

    assert result.status == "succeeded"
    assert result.snapshot_id == snapshot_id


@pytest.mark.asyncio
async def test_reconciliation_completion_rejects_other_snapshot_receipt() -> None:
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "operation_id": str(request_id),
                    "status": "succeeded",
                    "snapshot_id": str(uuid.uuid4()),
                    "status_url": None,
                },
                "meta": {},
            },
        )

    client = _client("consumer", handler)
    try:
        with pytest.raises(CacheTargetContractError, match="snapshot identity"):
            await client.complete_reconciliation(
                request_id=request_id,
                consumer_id="pinvi-cache-target-consumer",
                snapshot=CacheTargetSnapshot(
                    snapshot_id=str(snapshot_id),
                    restore_epoch=7,
                    high_watermark_cursor="cursor-0",
                    count=0,
                    merkle_root="72" * 32,
                    created_at=datetime(2026, 8, 1, tzinfo=UTC),
                    expires_at=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(hours=2),
                    items=[],
                ),
                idempotency_key=uuid.uuid4(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_initial_reconciliation_begin_and_seal_keep_distinct_etags_and_exact_bodies() -> None:
    request_id = uuid.uuid4()
    begin_key = uuid.uuid4()
    seal_key = uuid.uuid4()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            assert request.url.path == "/v1/service/cache-target-reconciliations"
            assert request.headers["If-Match"] == '"pinvi:7"'
            assert request.headers["Idempotency-Key"] == str(begin_key)
            assert json.loads(request.content) == {
                "external_system": "pinvi",
                "consumer_id": "pinvi-cache-target-consumer",
                "expected_restore_epoch": 7,
                "reason": "initial backfill",
            }
            status = "preparing"
            etag = f'"{request_id}:1"'
        else:
            assert (
                request.url.path == f"/v1/service/cache-target-reconciliations/{request_id}/seals"
            )
            assert request.headers["If-Match"] == f'"{request_id}:1"'
            assert request.headers["Idempotency-Key"] == str(seal_key)
            assert json.loads(request.content) == {
                "external_system": "pinvi",
                "consumer_id": "pinvi-cache-target-consumer",
                "expected_restore_epoch": 7,
                "expected_item_count": 249,
                "expected_merkle_root": "72" * 32,
            }
            status = "running"
            etag = f'"{request_id}:2"'
        return httpx.Response(
            201 if calls == 1 else 200,
            headers={"ETag": etag},
            json={
                "data": {
                    "operation_id": str(request_id),
                    "status": status,
                    "snapshot_id": None if calls == 1 else str(request_id),
                    "status_url": f"/v1/service/cache-target-reconciliations/{request_id}",
                    "entity_tag": etag,
                    "stream_entity_tag": '"pinvi:8"',
                },
                "meta": {},
            },
        )

    client = _client("recovery", handler)
    try:
        begin = await client.begin_initial_reconciliation(
            consumer_id="pinvi-cache-target-consumer",
            expected_restore_epoch=7,
            reason="initial backfill",
            idempotency_key=begin_key,
            stream_etag='"pinvi:7"',
        )
        seal = await client.seal_initial_reconciliation(
            request_id=request_id,
            consumer_id="pinvi-cache-target-consumer",
            expected_restore_epoch=7,
            expected_item_count=249,
            expected_merkle_root="72" * 32,
            idempotency_key=seal_key,
            stream_etag=begin.etag,
        )
    finally:
        await client.aclose()

    assert begin.operation.status == "preparing"
    assert begin.etag == f'"{request_id}:1"'
    assert seal.operation.status == "running"
    assert seal.operation.snapshot_id == request_id
    assert seal.etag == f'"{request_id}:2"'


def test_seal_reconciliation_rejects_other_operation_receipt() -> None:
    request_id = uuid.uuid4()
    etag = f'"{request_id}:2"'
    response = httpx.Response(
        200,
        headers={"ETag": etag},
        json={
            "data": {
                "operation_id": str(uuid.uuid4()),
                "status": "running",
                "snapshot_id": str(uuid.uuid4()),
                "status_url": None,
                "entity_tag": etag,
                "stream_entity_tag": '"pinvi:8"',
            },
            "meta": {},
        },
    )

    with pytest.raises(CacheTargetContractError, match="identity/status/ETag"):
        CacheTargetServiceClient._recovery_result(
            response,
            expected_status="running",
            expected_operation_id=request_id,
        )


@pytest.mark.asyncio
async def test_reconciliation_completion_rejects_other_operation_receipt() -> None:
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "operation_id": str(uuid.uuid4()),
                    "status": "succeeded",
                    "snapshot_id": str(snapshot_id),
                    "status_url": None,
                },
                "meta": {},
            },
        )

    client = _client("consumer", handler)
    try:
        with pytest.raises(CacheTargetContractError, match="operation identity"):
            await client.complete_reconciliation(
                request_id=request_id,
                consumer_id="pinvi-cache-target-consumer",
                snapshot=CacheTargetSnapshot(
                    snapshot_id=str(snapshot_id),
                    restore_epoch=7,
                    high_watermark_cursor="cursor-0",
                    count=0,
                    merkle_root="72" * 32,
                    created_at=datetime(2026, 8, 1, tzinfo=UTC),
                    expires_at=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(hours=2),
                    items=[],
                ),
                idempotency_key=uuid.uuid4(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_request_bound_snapshot_pages_keep_one_header_and_collect_all_items() -> None:
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    target_keys = [uuid.uuid4(), uuid.uuid4()]
    calls = 0
    created_at = datetime.now(UTC) - timedelta(hours=3)
    window = {
        "created_at": created_at.isoformat(),
        "expires_at": (created_at + timedelta(hours=2)).isoformat(),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path.endswith(f"/{request_id}/snapshot")
        assert request.url.params["page_size"] == "1000"
        if calls == 1:
            assert "cursor" not in request.url.params
            index = 0
            next_cursor = "opaque-next"
        else:
            assert request.url.params["cursor"] == "opaque-next"
            index = 1
            next_cursor = None
        return httpx.Response(
            200,
            json={
                "data": {
                    "snapshot_id": str(snapshot_id),
                    "restore_epoch": 7,
                    "high_watermark_cursor": "cursor-2",
                    "count": 2,
                    "merkle_root": "72" * 32,
                    **window,
                    "items": [
                        {
                            "external_system": "pinvi",
                            "target_key": str(target_keys[index]),
                            "state": "active",
                            "source_generation": 1,
                            "source_payload_fingerprint": "73" * 32,
                        }
                    ],
                },
                "meta": {"page": {"next_cursor": next_cursor}},
            },
        )

    client = _client("consumer", handler)
    try:
        snapshot = await client.get_reconciliation_snapshot(request_id)
    finally:
        await client.aclose()

    assert calls == 2
    assert [item.target_key for item in snapshot.items] == [str(key) for key in target_keys]


@pytest.mark.asyncio
async def test_generic_snapshot_rejects_less_than_one_hour_traversal_window() -> None:
    created_at = datetime.now(UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/service/cache-target-snapshots/pinvi"
        return httpx.Response(
            200,
            json={
                "data": {
                    "snapshot_id": str(uuid.uuid4()),
                    "restore_epoch": 7,
                    "high_watermark_cursor": "cursor-0",
                    "count": 0,
                    "merkle_root": "72" * 32,
                    "created_at": created_at.isoformat(),
                    "expires_at": (created_at + timedelta(minutes=59)).isoformat(),
                    "items": [],
                },
                "meta": {"page": {"next_cursor": None}},
            },
        )

    client = _client("consumer", handler)
    try:
        with pytest.raises(CacheTargetContractError, match="1시간보다 짧습니다"):
            await client.get_snapshot()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_snapshot_requests_are_single_flight_per_external_system() -> None:
    active = 0
    maximum_active = 0
    both_entered = asyncio.Event()
    request_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, maximum_active
        assert request.url.path in {
            "/v1/service/cache-target-snapshots/pinvi",
            f"/v1/service/cache-target-reconciliations/{request_id}/snapshot",
        }
        active += 1
        maximum_active = max(maximum_active, active)
        if maximum_active > 1:
            both_entered.set()
        await asyncio.sleep(0)
        active -= 1
        return httpx.Response(200, json=_empty_snapshot_response())

    clients = [
        CacheTargetServiceClient(
            httpx.AsyncClient(
                base_url="http://map.test",
                transport=httpx.MockTransport(handler),
            ),
            role="consumer",
            token=TOKEN,
        )
        for _ in range(2)
    ]
    try:
        await asyncio.gather(
            clients[0].get_snapshot(),
            clients[1].get_reconciliation_snapshot(request_id),
        )
    finally:
        await asyncio.gather(*(client.aclose() for client in clients))

    assert maximum_active == 1
    assert not both_entered.is_set()


def test_snapshot_lock_registry_does_not_retain_closed_event_loop() -> None:
    async def contend() -> None:
        owner_entered = asyncio.Event()
        release_owner = asyncio.Event()

        async def owner() -> None:
            async with _snapshot_lock("pinvi"):
                owner_entered.set()
                await release_owner.wait()

        async def waiter() -> None:
            await owner_entered.wait()
            async with _snapshot_lock("pinvi"):
                pass

        owner_task = asyncio.create_task(owner())
        waiter_task = asyncio.create_task(waiter())
        await owner_entered.wait()
        await asyncio.sleep(0)
        assert not waiter_task.done()
        release_owner.set()
        await asyncio.gather(owner_task, waiter_task)

    loop = asyncio.new_event_loop()
    loop_reference = weakref.ref(loop)
    try:
        loop.run_until_complete(contend())
    finally:
        loop.close()
    del loop
    gc.collect()

    assert loop_reference() is None


@pytest.mark.asyncio
async def test_snapshot_request_uses_map_build_timeout_margin() -> None:
    observed_timeout: dict[str, float] | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_timeout
        observed_timeout = request.extensions.get("timeout")
        return httpx.Response(200, json=_empty_snapshot_response())

    client = _client("consumer", handler)
    try:
        await client.get_snapshot()
    finally:
        await client.aclose()

    assert observed_timeout == {
        "connect": 5.0,
        "read": 70.0,
        "write": 5.0,
        "pool": 5.0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "code", "retry_after"),
    [
        (429, "SNAPSHOT_CAPACITY_EXCEEDED", "2701"),
        (503, "SNAPSHOT_BARRIER_TIMEOUT", "1"),
        (503, "SNAPSHOT_BUILD_TIMEOUT", "1"),
        (503, "SNAPSHOT_BUSY", "1"),
        (503, "SNAPSHOT_TTL_TOO_SHORT", "1"),
    ],
)
async def test_snapshot_retries_only_typed_capacity_and_unavailable_problems(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    code: str,
    retry_after: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                status_code,
                headers={"Retry-After": retry_after},
                json={"code": code},
            )
        return httpx.Response(200, json=_empty_snapshot_response())

    sleep = AsyncMock()
    monkeypatch.setattr(
        "app.clients.kor_travel_map_cache_target.asyncio.sleep",
        sleep,
    )
    client = _client("consumer", handler)
    try:
        await client.get_snapshot()
    finally:
        await client.aclose()

    assert calls == 2
    sleep.assert_awaited_once_with(int(retry_after))


@pytest.mark.asyncio
async def test_snapshot_item_limit_is_non_retryable_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            413,
            json={"code": "SNAPSHOT_ITEM_LIMIT_EXCEEDED"},
        )

    sleep = AsyncMock()
    monkeypatch.setattr(
        "app.clients.kor_travel_map_cache_target.asyncio.sleep",
        sleep,
    )
    client = _client("consumer", handler)
    try:
        with pytest.raises(CacheTargetServiceProblem) as raised:
            await client.get_snapshot()
    finally:
        await client.aclose()

    assert calls == 1
    assert raised.value.status_code == 413
    assert raised.value.code == "SNAPSHOT_ITEM_LIMIT_EXCEEDED"
    assert raised.value.disposition == "dead_letter"
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_retryable_snapshot_problem_requires_canonical_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"code": "SNAPSHOT_BUSY"},
        )

    client = _client("consumer", handler)
    try:
        with pytest.raises(CacheTargetContractError, match="Retry-After"):
            await client.get_snapshot()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_snapshot_retry_budget_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "1"},
            json={"code": "SNAPSHOT_CAPACITY_EXCEEDED"},
        )

    sleep = AsyncMock()
    monkeypatch.setattr(
        "app.clients.kor_travel_map_cache_target.asyncio.sleep",
        sleep,
    )
    client = _client("consumer", handler)
    try:
        with pytest.raises(CacheTargetServiceProblem) as raised:
            await client.get_snapshot()
    finally:
        await client.aclose()

    assert calls == 3
    assert raised.value.code == "SNAPSHOT_CAPACITY_EXCEEDED"
    assert sleep.await_count == 2


@pytest.mark.parametrize(
    ("created_at", "expires_at"),
    [
        (datetime(2026, 8, 1), datetime(2026, 8, 1, 1)),
        (
            datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 8, 1, tzinfo=UTC),
        ),
    ],
)
def test_snapshot_rejects_invalid_lifetime(
    created_at: datetime,
    expires_at: datetime,
) -> None:
    with pytest.raises(ValueError, match="snapshot"):
        CacheTargetSnapshot(
            snapshot_id=str(uuid.uuid4()),
            restore_epoch=7,
            high_watermark_cursor="cursor-0",
            count=0,
            merkle_root="72" * 32,
            created_at=created_at,
            expires_at=expires_at,
            items=[],
        )


def test_snapshot_contract_declares_high_watermark_as_replay_lower_bound() -> None:
    description = CacheTargetSnapshot.model_json_schema()["properties"]["high_watermark_cursor"][
        "description"
    ]

    assert "replay lower-bound" in description
    assert "event_id" in description
    assert "dedupe" in description


@pytest.mark.parametrize(
    ("permanent", "expected"),
    [(True, "permanent"), (False, "transient")],
)
def test_nack_disposition_and_error_fingerprint_are_typed(permanent: bool, expected: str) -> None:
    body = build_cache_target_nack(
        claim_id=uuid.uuid4(),
        lease_token=uuid.uuid4(),
        event_id=uuid.uuid4(),
        consumer_id="pinvi-cache-target-consumer",
        error=RuntimeError("credential must never enter the receipt"),
        permanent=permanent,
        max_attempts=5,
    )

    assert body["disposition"] == expected
    assert body["error_fingerprint"] == hashlib.sha256(b"RuntimeError").hexdigest()
    assert "credential" not in str(body)
