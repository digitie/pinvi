"""PinVi가 소비하는 M05 Feature 참조 조정 service 계약 gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.config import (
    KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
)

_SNAPSHOT = (
    Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-service.json"
)
_MAP_SOURCE_REVISION = "db319a4798229098d04e68e3ac64338183ad547f"
_SNAPSHOT_SHA256 = "99ba6c178bf55401d3e1bb638a01b96f66bbac38d604534aa126a70f4be53d3d"
_LEASE_PATH = "/v1/service/feature-reference-reconciliations"
_ACK_PATH = f"{_LEASE_PATH}/{{event_id}}/acks"


def _spec() -> dict[str, Any]:
    loaded = json.loads(_SNAPSHOT.read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def test_feature_reference_reconciliation_service_snapshot_is_exact_candidate_bytes() -> None:
    assert hashlib.sha256(_SNAPSHOT.read_bytes()).hexdigest() == _SNAPSHOT_SHA256
    assert KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256 == _SNAPSHOT_SHA256
    assert KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION == _MAP_SOURCE_REVISION
    assert KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_CAPABILITY_GENERATION == 1


def test_feature_reference_reconciliation_lease_and_ack_contracts_are_exact() -> None:
    spec = _spec()
    lease = spec["paths"][_LEASE_PATH]["get"]
    assert lease["security"] == [{"ServiceToken": []}]
    assert lease["parameters"] == [
        {
            "in": "header",
            "name": "X-Reconciliation-Worker-Id",
            "required": True,
            "schema": {"format": "uuid", "title": "X-Reconciliation-Worker-Id", "type": "string"},
        }
    ]
    assert set(lease["responses"]) >= {"200", "204", "401", "403", "409", "422", "503"}
    assert lease["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/FeatureReferenceReconciliationLeaseResponse"
    }

    ack = spec["paths"][_ACK_PATH]["post"]
    assert ack["security"] == [{"ServiceToken": []}]
    assert [parameter["name"] for parameter in ack["parameters"]] == [
        "event_id",
        "Idempotency-Key",
    ]
    assert ack["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/FeatureReferenceReconciliationAckInput"
    }
    assert set(ack["responses"]) >= {"200", "401", "403", "409", "422", "503"}
    assert ack["responses"]["200"]["headers"]["Idempotency-Replayed"]["schema"] == {
        "enum": ["true"],
        "type": "string",
    }


def test_feature_reference_reconciliation_payload_schemas_are_closed_and_complete() -> None:
    schemas = _spec()["components"]["schemas"]
    event = schemas["FeatureReferenceReconciliationEventData"]
    assert event["additionalProperties"] is False
    assert set(event["required"]) == {
        "payload_schema_version",
        "event_id",
        "event_sequence",
        "occurred_at",
        "case_id",
        "resolution_id",
        "action",
        "old_feature",
        "replacement_feature",
        "manual_retire_transition_id",
        "manual_retire_row_revision_after_transition",
        "command_id",
    }
    assert event["properties"]["action"]["enum"] == ["rebind", "detach"]

    ack_input = schemas["FeatureReferenceReconciliationAckInput"]
    assert ack_input["additionalProperties"] is False
    assert set(ack_input["required"]) == {
        "worker_id",
        "lease_epoch",
        "event_sha256",
        "local_receipt_sha256",
    }
    assert ack_input["properties"]["event_sha256"]["pattern"] == r"^[0-9a-f]{64}$"
    assert ack_input["properties"]["local_receipt_sha256"]["pattern"] == r"^[0-9a-f]{64}$"
