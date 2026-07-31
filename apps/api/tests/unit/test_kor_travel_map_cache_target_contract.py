"""kor-travel-map service OpenAPI의 cache-target byte/shape pin."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.config import (
    CACHE_TARGET_SERVICE_ARTIFACT_OWNER_REVISION,
    CACHE_TARGET_SERVICE_OPENAPI_SHA256,
)

_SNAPSHOT = (
    Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-service.json"
)
_ARTIFACT_COMMIT = "b54ea8aa450800e1ad5db1a71d14310a24cceb5b"
_FUNCTIONAL_OWNER_COMMIT = "686a9b05beed384a8a9b202a515790c7770dd834"
_SNAPSHOT_SHA256 = "11138dd42c6454d7dcb2e86e50a2286cd9bccc5471e9d4cbe2e60dfda62e402a"


def _spec() -> dict[str, Any]:
    loaded = json.loads(_SNAPSHOT.read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def test_service_snapshot_exact_bytes_and_runtime_pin_match_functional_owner() -> None:
    assert hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA256
    assert CACHE_TARGET_SERVICE_OPENAPI_SHA256 == _SNAPSHOT_SHA256
    assert CACHE_TARGET_SERVICE_ARTIFACT_OWNER_REVISION == _FUNCTIONAL_OWNER_COMMIT


def test_cache_target_consumer_paths_and_recovery_shapes_are_pinned() -> None:
    spec = _spec()
    paths = spec["paths"]
    required_methods = {
        "/v1/service/cache-target-streams/{external_system}": "get",
        "/v1/service/cache-target-event-claims": "post",
        "/v1/service/cache-target-event-acks": "post",
        "/v1/service/cache-target-event-nacks": "post",
        "/v1/service/cache-target-snapshots/{external_system}": "get",
        "/v1/service/cache-target-reconciliations": "post",
        "/v1/service/cache-target-reconciliations/{request_id}/seals": "post",
        "/v1/service/cache-target-reconciliations/{request_id}/snapshot": "get",
        "/v1/service/cache-target-reconciliations/{request_id}/completions": "post",
    }
    for path, method in required_methods.items():
        assert method in paths[path]

    schemas = spec["components"]["schemas"]
    preparing = schemas["CacheTargetReconciliationPreparing"]
    assert preparing["additionalProperties"] is False
    assert set(preparing["required"]) == {
        "request_id",
        "status",
        "restore_epoch",
        "entity_tag",
        "stream_entity_tag",
        "created_at",
    }
    assert preparing["properties"]["status"]["const"] == "preparing"
    assert "snapshot_id" not in preparing["properties"]
    assert "merkle_root" not in preparing["properties"]

    running = schemas["CacheTargetReconciliationRunning"]
    assert running["additionalProperties"] is False
    assert set(running["required"]) == {
        "request_id",
        "status",
        "snapshot_id",
        "restore_epoch",
        "count",
        "merkle_root",
        "high_watermark_cursor",
        "entity_tag",
        "stream_entity_tag",
        "created_at",
    }
    assert running["properties"]["request_id"]["format"] == "uuid"
    assert running["properties"]["snapshot_id"]["format"] == "uuid"
    assert running["properties"]["status"]["const"] == "running"
    assert running["properties"]["merkle_root"]["pattern"] == "^[0-9a-f]{64}$"

    active = schemas["CacheTargetStreamControlRecord"]["properties"]["active_reconciliation"][
        "anyOf"
    ][0]
    assert active["discriminator"] == {
        "mapping": {
            "preparing": "#/components/schemas/CacheTargetReconciliationPreparing",
            "running": "#/components/schemas/CacheTargetReconciliationRunning",
        },
        "propertyName": "status",
    }
    assert active["oneOf"] == [
        {"$ref": "#/components/schemas/CacheTargetReconciliationPreparing"},
        {"$ref": "#/components/schemas/CacheTargetReconciliationRunning"},
    ]

    begin_path = paths["/v1/service/cache-target-reconciliations"]["post"]
    seal_path = paths["/v1/service/cache-target-reconciliations/{request_id}/seals"]["post"]
    for operation in (begin_path, seal_path):
        assert operation["security"] == [{"ServiceToken": []}]
        idempotency = next(
            parameter
            for parameter in operation["parameters"]
            if parameter["name"] == "Idempotency-Key"
        )
        assert idempotency["required"] is True
        assert idempotency["schema"]["format"] == "uuid"

    begin_headers = {parameter["name"]: parameter for parameter in begin_path["parameters"]}
    assert begin_headers["If-Match"]["required"] is False
    assert begin_headers["If-None-Match"]["required"] is False
    assert "ETag" in begin_path["responses"]["201"]["headers"]
    assert {"412", "428", "default"} <= set(begin_path["responses"])

    seal_headers = {parameter["name"]: parameter for parameter in seal_path["parameters"]}
    assert seal_headers["If-Match"]["required"] is True
    assert "If-None-Match" not in seal_headers
    assert "ETag" in seal_path["responses"]["200"]["headers"]
    assert {"412", "428", "default"} <= set(seal_path["responses"])

    begin = schemas["CacheTargetReconciliationBeginRequest"]
    assert begin["additionalProperties"] is False
    assert set(begin["required"]) == {
        "external_system",
        "consumer_id",
        "expected_restore_epoch",
        "reason",
    }
    seal = schemas["CacheTargetReconciliationSealRequest"]
    assert seal["additionalProperties"] is False
    assert set(seal["required"]) == {
        "external_system",
        "consumer_id",
        "expected_restore_epoch",
        "expected_item_count",
        "expected_merkle_root",
    }
    assert seal["properties"]["expected_merkle_root"]["pattern"] == "^[0-9a-f]{64}$"

    completion_path = paths["/v1/service/cache-target-reconciliations/{request_id}/completions"][
        "post"
    ]
    idempotency = next(
        parameter
        for parameter in completion_path["parameters"]
        if parameter["name"] == "Idempotency-Key"
    )
    assert idempotency["required"] is True
    assert idempotency["schema"]["format"] == "uuid"
    completion = schemas["CacheTargetReconciliationCompletionRequest"]
    assert completion["additionalProperties"] is False
    assert set(completion["required"]) == {
        "external_system",
        "consumer_id",
        "snapshot_id",
        "expected_restore_epoch",
        "actual_merkle_root",
    }
    assert completion["properties"]["actual_merkle_root"]["pattern"] == "^[0-9a-f]{64}$"

    service_token = spec["components"]["securitySchemes"]["ServiceToken"]
    assert service_token["type"] == "apiKey"
    assert service_token["in"] == "header"
    assert service_token["name"] == "X-Kor-Travel-Map-Service-Token"
    request_snapshot_path = paths["/v1/service/cache-target-reconciliations/{request_id}/snapshot"][
        "get"
    ]
    assert request_snapshot_path["security"] == [{"ServiceToken": []}]
    assert completion_path["security"] == [{"ServiceToken": []}]

    problem = schemas["ProblemDetail"]
    assert {"type", "title", "status", "detail", "code", "request_id"} <= set(problem["required"])
    for operation, status_codes in (
        (begin_path, ("412", "428", "default")),
        (seal_path, ("412", "428", "default")),
    ):
        for status_code in status_codes:
            assert operation["responses"][status_code]["content"]["application/problem+json"][
                "schema"
            ] == {"$ref": "#/components/schemas/ProblemDetail"}

    nack_path = paths["/v1/service/cache-target-event-nacks"]["post"]
    assert "409" in nack_path["responses"]
    nack = schemas["CacheTargetNackRequest"]
    assert nack["properties"]["max_attempts"]["maximum"] == 100
    assert nack["properties"]["error_fingerprint"]["pattern"] == "^[0-9a-f]{64}$"
