"""kor-travel-map service OpenAPI의 cache-target byte/shape pin."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from app.core.config import (
    KOR_TRAVEL_MAP_C6C_CANCEL_PROBE_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_CURATION_SNAPSHOT_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
)

_SNAPSHOT = (
    Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-service.json"
)
_SERVICE_PROVENANCE = (
    Path(__file__).resolve().parents[4] / "contracts" / "kor-travel-map-service-provenance-v1.json"
)
_MAP_RELEASE_REVISION = "13e1852b8049ebd3e1ce6eb58fe16e208cea45e0"
_SNAPSHOT_SHA256 = "e71e7b1112f98857a6deefe20a1ca48c689cb04647f2e9dc71664fdb69634a7b"

_GENERATION7_ROLE_SCOPES = {
    "command": {"cache-target:command"},
    "consumer": {
        "cache-target:read",
        "cache-target:claim",
        "cache-target:ack",
        "cache-target:nack",
        "cache-target:snapshot",
    },
    "restore": {"cache-target:restore-fence"},
    "recovery": {"cache-target:recovery", "cache-target:recovery-replay"},
}
_GENERATION7_OPERATION_CONTRACT = {
    ("put", "/v1/service/cache-targets/{external_system}/{target_key}"): (
        "cache-target:command",
        "command",
    ),
    ("get", "/v1/service/cache-targets/{external_system}/{target_key}"): (
        "cache-target:read",
        "consumer",
    ),
    ("delete", "/v1/service/cache-targets/{external_system}/{target_key}"): (
        "cache-target:command",
        "command",
    ),
    ("get", "/v1/service/cache-target-streams/{external_system}"): (
        "cache-target:read",
        "consumer",
    ),
    ("post", "/v1/service/cache-target-streams/{external_system}/restore-fences"): (
        "cache-target:restore-fence",
        "restore",
    ),
    ("post", "/v1/service/refresh-requests"): ("cache-target:command", "command"),
    ("get", "/v1/service/refresh-requests/{request_id}"): (
        "cache-target:read",
        "consumer",
    ),
    ("post", "/v1/service/cache-target-event-claims"): (
        "cache-target:claim",
        "consumer",
    ),
    ("post", "/v1/service/cache-target-event-acks"): (
        "cache-target:ack",
        "consumer",
    ),
    ("post", "/v1/service/cache-target-event-nacks"): (
        "cache-target:nack",
        "consumer",
    ),
    ("get", "/v1/service/cache-target-event-dead-letters/{event_id}"): (
        "cache-target:recovery-replay",
        "recovery",
    ),
    ("post", "/v1/service/cache-target-event-dead-letters/{event_id}/replays"): (
        "cache-target:recovery-replay",
        "recovery",
    ),
    ("post", "/v1/service/cache-target-reconciliations"): (
        "cache-target:recovery",
        "recovery",
    ),
    ("post", "/v1/service/cache-target-reconciliations/{request_id}/seals"): (
        "cache-target:recovery",
        "recovery",
    ),
    ("post", "/v1/service/cache-target-reconciliations/{request_id}/completions"): (
        "cache-target:snapshot",
        "consumer",
    ),
    ("get", "/v1/service/cache-target-snapshots/{external_system}"): (
        "cache-target:snapshot",
        "consumer",
    ),
    ("get", "/v1/service/cache-target-reconciliations/{request_id}/snapshot"): (
        "cache-target:snapshot",
        "consumer",
    ),
}


def _spec() -> dict[str, Any]:
    loaded = json.loads(_SNAPSHOT.read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def test_service_snapshot_exact_bytes_runtime_pin_and_provenance_match_map_release() -> None:
    assert hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA256
    assert KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256 == _SNAPSHOT_SHA256
    assert KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION == _MAP_RELEASE_REVISION
    assert KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION == 7
    assert KOR_TRAVEL_MAP_C6C_CANCEL_PROBE_CAPABILITY_GENERATION == 2
    assert KOR_TRAVEL_MAP_CURATION_SNAPSHOT_CAPABILITY_GENERATION == 1
    assert json.loads(_SERVICE_PROVENANCE.read_text()) == {
        "capabilities": {
            "c6c_cancel_probe": {"generation": 2},
            "cache_target": {"generation": 7},
            "curation_snapshot": {"generation": 1},
        },
        "map_release_revision": KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
        "service_openapi_sha256": KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
        "version": 1,
    }


def test_wheel_build_includes_the_general_service_provenance() -> None:
    package_artifact = files("app").joinpath(
        "_contract_data/kor-travel-map-service-provenance-v1.json"
    )
    assert package_artifact.is_file() is False
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    assert (
        '"../../contracts/kor-travel-map-service-provenance-v1.json" = '
        '"app/_contract_data/kor-travel-map-service-provenance-v1.json"'
    ) in pyproject.read_text()
    dockerfile = pyproject.parent / "Dockerfile"
    dockerfile_text = dockerfile.read_text()
    canonical_copy = (
        "COPY contracts/kor-travel-map-service-provenance-v1.json "
        "/contracts/kor-travel-map-service-provenance-v1.json"
    )
    assert canonical_copy in dockerfile_text
    assert dockerfile_text.index(canonical_copy) < dockerfile_text.index(
        "RUN pip install --upgrade pip && pip install -e ."
    )
    assert "RUN pip install --no-deps -e . && rm -rf /contracts" in dockerfile_text


def test_c6c_fixture_contract_is_pinned_but_not_a_pinvi_runtime_scope() -> None:
    spec = _spec()
    fixture_path = "/v1/ops/contract-fixtures/c6c-cancel-probe/{transaction_id}"
    finalize_path = f"{fixture_path}/finalize"

    operations = (
        spec["paths"][fixture_path]["put"],
        spec["paths"][fixture_path]["get"],
        spec["paths"][finalize_path]["post"],
    )
    for operation in operations:
        assert operation["security"] == [{"OpsScope": [], "OpsToken": []}]
        scope_header = next(
            parameter
            for parameter in operation["parameters"]
            if parameter["name"] == "X-Kor-Travel-Map-Ops-Scope"
        )
        assert scope_header["description"] == (
            "C6c contract fixture service principal은 exact fixture route에서 `ops:fixture`가 "
            "필수다. scope 문자열만으로는 권한이 되지 않는다."
        )
    record = spec["components"]["schemas"]["C6cCancelProbeFixtureRecord"]
    assert record["properties"]["capability_generation"]["const"] == 2
    app_sources = "\n".join(
        path.read_text() for path in (Path(__file__).resolve().parents[2] / "app").rglob("*.py")
    )
    assert "ops:fixture" not in app_sources
    assert "contract-fixtures" not in app_sources


def test_generation7_service_scope_and_caller_inventory_is_exact() -> None:
    spec = _spec()
    actual: dict[tuple[str, str], str] = {}
    for path, path_item in spec["paths"].items():
        if not path.startswith(("/v1/service/cache-target", "/v1/service/refresh-requests")):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "put", "post", "delete"}:
                continue
            actual[(method, path)] = operation["x-required-service-scope"]

    assert set(actual) == set(_GENERATION7_OPERATION_CONTRACT)
    for route, (required_scope, caller_role) in _GENERATION7_OPERATION_CONTRACT.items():
        assert actual[route] == required_scope
        assert required_scope in _GENERATION7_ROLE_SCOPES[caller_role]


def test_curation_snapshot_generation1_service_contract_is_exact() -> None:
    spec = _spec()
    expected = {
        "/v1/service/curation-collections/{collection_id}/detail-snapshot",
        "/v1/service/curation-items/{curation_item_id}/detail-snapshot",
    }
    actual = {
        path
        for path in spec["paths"]
        if path.startswith(("/v1/service/curation-collections", "/v1/service/curation-items"))
    }
    assert actual == expected
    for path in expected:
        operation = spec["paths"][path]["get"]
        assert operation["security"] == [{"ServiceToken": []}]
        assert operation["x-required-service-scope"] == "pinvi:curation-snapshot:read"

    collection = spec["components"]["schemas"]["CurationCollectionDetailSnapshot"]
    assert collection["additionalProperties"] is False
    assert collection["properties"]["row_revision"]["pattern"] == r"^[1-9][0-9]*$"
    assert collection["properties"]["etag"]["pattern"] == r"^sha256:[0-9a-f]{64}$"
    assert collection["properties"]["item_set_hash"]["pattern"] == r"^[0-9a-f]{64}$"
    assert collection["properties"]["items"]["maxItems"] == 200
    collection_metadata = spec["components"]["schemas"]["CurationSnapshotCollection"][
        "properties"
    ]
    assert collection_metadata["theme_slug"]["minLength"] == 1
    assert collection_metadata["theme_slug"]["maxLength"] == 128
    assert collection_metadata["theme_name"]["minLength"] == 1
    assert collection_metadata["theme_name"]["maxLength"] == 200
    assert collection_metadata["title"]["minLength"] == 1
    assert collection_metadata["title"]["maxLength"] == 300
    assert collection_metadata["edition_key"]["maxLength"] == 100


def test_cache_target_consumer_paths_and_recovery_shapes_are_pinned() -> None:
    spec = _spec()
    paths = spec["paths"]
    required_methods = {
        "/v1/service/cache-target-streams/{external_system}": "get",
        "/v1/service/cache-target-streams/{external_system}/restore-fences": "post",
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
    alias_map_checksum = schemas["FeatureAliasMapChecksumData"]
    assert "derivation_enforced" in alias_map_checksum["required"]
    assert alias_map_checksum["properties"]["derivation_enforced"] == {
        "title": "Derivation Enforced",
        "type": "boolean",
    }

    snapshot = schemas["CacheTargetSnapshotData"]
    assert {"created_at", "expires_at"} <= set(snapshot["required"])
    assert snapshot["properties"]["created_at"]["format"] == "date-time"
    assert snapshot["properties"]["expires_at"]["format"] == "date-time"
    assert "최소 60분" in snapshot["properties"]["expires_at"]["description"]
    assert "reconciliation-bound" in snapshot["properties"]["expires_at"]["description"]

    refresh_keys = schemas["CacheTargetRefreshRequest"]["properties"]["target_keys"]
    assert refresh_keys["minItems"] == 1
    assert refresh_keys["maxItems"] == 500
    assert refresh_keys["uniqueItems"] is True
    assert refresh_keys["items"] == {
        "description": "Trimmed Unicode NFC canonical cache target identity.",
        "maxLength": 512,
        "minLength": 1,
        "type": "string",
    }

    source_parameters = paths["/v1/service/cache-targets/{external_system}/{target_key}"]["put"][
        "parameters"
    ]
    identities = {
        parameter["name"]: parameter
        for parameter in source_parameters
        if parameter["name"] in {"external_system", "target_key"}
    }
    assert identities["external_system"]["description"] == (
        "Trimmed Unicode NFC canonical external system identity."
    )
    assert identities["external_system"]["schema"]["maxLength"] == 112
    assert identities["target_key"]["description"] == (
        "Trimmed Unicode NFC canonical cache target identity."
    )
    assert identities["target_key"]["schema"]["maxLength"] == 512

    generic_snapshot = paths["/v1/service/cache-target-snapshots/{external_system}"]["get"]
    assert {"413", "429", "503"} <= set(generic_snapshot["responses"])
    for response_code in ("429", "503"):
        assert "Retry-After" in generic_snapshot["responses"][response_code]["headers"]

    mutation_response = schemas["CacheTargetSourceMutationResponse"]
    assert mutation_response["properties"]["data"] == {
        "$ref": "#/components/schemas/CacheTargetSourceMutationRecord"
    }
    mutation_record = schemas["CacheTargetSourceMutationRecord"]
    assert {"target_id", "entity_tag", "target_sequence"} <= set(mutation_record["required"])
    assert mutation_record["properties"]["target_id"] == {
        "format": "uuid",
        "title": "Target Id",
        "type": "string",
    }
    assert mutation_record["properties"]["entity_tag"]["type"] == "string"
    assert mutation_record["properties"]["target_sequence"] == {
        "minimum": 1.0,
        "title": "Target Sequence",
        "type": "integer",
    }

    read_response = schemas["CacheTargetSourceReadResponse"]
    assert read_response["properties"]["data"] == {
        "$ref": "#/components/schemas/CacheTargetSourceRecord"
    }
    read_record = schemas["CacheTargetSourceRecord"]
    assert read_record["properties"]["target_id"]["anyOf"][-1] == {"type": "null"}
    assert read_record["properties"]["entity_tag"]["anyOf"][-1] == {"type": "null"}

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

    reconciled = schemas["CacheTargetReconciledPayload"]
    assert reconciled["additionalProperties"] is False
    assert set(reconciled["required"]) == {
        "request_id",
        "snapshot_id",
        "actual_merkle_root",
        "expected_merkle_root",
        "status",
        "version",
    }
    assert reconciled["properties"]["request_id"]["format"] == "uuid"
    assert reconciled["properties"]["snapshot_id"]["format"] == "uuid"
    for field in ("actual_merkle_root", "expected_merkle_root"):
        assert reconciled["properties"][field]["pattern"] == "^[0-9a-f]{64}$"
    assert reconciled["properties"]["status"]["const"] == "succeeded"
    assert reconciled["properties"]["version"]["const"] == "cache-target-reconciliation-v1"

    operation = schemas["CacheTargetRecoveryOperationRecord"]
    assert operation["additionalProperties"] is False
    assert set(operation["required"]) == {"operation_id", "status"}
    assert operation["properties"]["operation_id"] == {
        "format": "uuid",
        "title": "Operation Id",
        "type": "string",
    }
    assert operation["properties"]["status"]["enum"] == [
        "accepted",
        "pending",
        "leased",
        "retry",
        "dead",
        "delivered",
        "preparing",
        "running",
        "succeeded",
        "failed",
        "superseded",
    ]
    assert operation["properties"]["snapshot_id"]["anyOf"] == [
        {"format": "uuid", "type": "string"},
        {"type": "null"},
    ]

    restore_path = paths["/v1/service/cache-target-streams/{external_system}/restore-fences"][
        "post"
    ]
    assert restore_path["security"] == [{"ServiceToken": []}]
    restore_headers = {parameter["name"]: parameter for parameter in restore_path["parameters"]}
    assert restore_headers["Idempotency-Key"]["required"] is True
    assert restore_headers["Idempotency-Key"]["schema"]["format"] == "uuid"
    assert restore_headers["If-Match"]["required"] is True
    assert "201" in restore_path["responses"]
    assert "200" in restore_path["responses"]
    assert restore_path["responses"]["200"]["description"] == "exact Idempotency-Key replay"
    assert (
        restore_path["responses"]["200"]["headers"] == restore_path["responses"]["201"]["headers"]
    )
    assert restore_path["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CacheTargetRestoreFenceResponse"
    }
    assert "ETag" in restore_path["responses"]["201"]["headers"]
    assert {"412", "428", "default"} <= set(restore_path["responses"])
    assert restore_path["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CacheTargetRestoreFenceResponse"
    }
    restore_response = schemas["CacheTargetRestoreFenceResponse"]
    assert restore_response["properties"]["data"] == {
        "$ref": "#/components/schemas/CacheTargetRestoreFenceRecord"
    }
    restore_record = schemas["CacheTargetRestoreFenceRecord"]
    assert restore_record["additionalProperties"] is False
    assert restore_record["oneOf"] == [
        {
            "properties": {
                "superseded_reconciliation_count": {"const": 0},
                "superseded_reconciliation_request_id": {"type": "null"},
            },
            "required": [
                "superseded_reconciliation_count",
                "superseded_reconciliation_request_id",
            ],
        },
        {
            "properties": {
                "superseded_reconciliation_count": {"const": 1},
                "superseded_reconciliation_request_id": {
                    "format": "uuid",
                    "type": "string",
                },
            },
            "required": [
                "superseded_reconciliation_count",
                "superseded_reconciliation_request_id",
            ],
        },
    ]
    assert set(restore_record["required"]) == {
        "external_system",
        "restore_epoch",
        "control_version",
        "entity_tag",
        "fence_id",
        "previous_restore_epoch",
        "previous_control_version",
        "invalidated_claim_count",
        "superseded_delivery_count",
        "superseded_reconciliation_count",
        "superseded_reconciliation_request_id",
    }
    assert restore_record["properties"]["fence_id"]["format"] == "uuid"
    for field in (
        "restore_epoch",
        "control_version",
        "previous_restore_epoch",
        "previous_control_version",
    ):
        assert restore_record["properties"][field]["minimum"] == 1
    for field in ("invalidated_claim_count", "superseded_delivery_count"):
        assert restore_record["properties"][field]["minimum"] == 0
    reconciliation_count = restore_record["properties"]["superseded_reconciliation_count"]
    assert reconciliation_count["minimum"] == 0
    assert reconciliation_count["maximum"] == 1
    assert restore_record["properties"]["superseded_reconciliation_request_id"]["anyOf"] == [
        {"format": "uuid", "type": "string"},
        {"type": "null"},
    ]

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
