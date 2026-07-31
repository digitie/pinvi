"""cache target role-bound service transport와 failure classification."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.clients.kor_travel_map_cache_target import (
    CacheTargetServiceClient,
    CacheTargetServiceProblem,
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
                items=[],
            ),
            idempotency_key=idempotency_key,
        )
    finally:
        await client.aclose()

    assert result.status == "succeeded"


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
    assert seal.etag == f'"{request_id}:2"'


@pytest.mark.asyncio
async def test_request_bound_snapshot_pages_keep_one_header_and_collect_all_items() -> None:
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    target_keys = [uuid.uuid4(), uuid.uuid4()]
    calls = 0

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
