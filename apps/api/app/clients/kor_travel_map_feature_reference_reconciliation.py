"""Map M05 Feature 참조 재결합 service delivery 전용 transport.

이 모듈은 Map service OpenAPI를 HTTP로만 소비한다. local trip/curation/suggestion의
판정과 receipt 생성은 ``services.feature_reference_reconciliation``가 소유하며,
이 transport는 lease/ACK wire contract를 strict하게 검증한다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.clients.kor_travel_map import _error_code

_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"  # noqa: S105 - header name
_WORKER_ID_HEADER = "X-Reconciliation-Worker-Id"
_IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
_LEASE_PATH = "/v1/service/feature-reference-reconciliations"


class FeatureReferenceReconciliationError(RuntimeError):
    """M05 Map delivery transport/contract 오류의 공통 기반."""


class FeatureReferenceReconciliationUnavailable(FeatureReferenceReconciliationError):
    """network, timeout, 또는 Map 5xx로 결과가 확정되지 않음."""


class FeatureReferenceReconciliationContractError(FeatureReferenceReconciliationError):
    """vendored OpenAPI success envelope와 다른 응답."""


class FeatureReferenceReconciliationProblem(FeatureReferenceReconciliationError):
    """Map RFC7807 non-success를 status/code로 보존한다."""

    def __init__(self, *, status_code: int, code: str | None) -> None:
        super().__init__(f"Map feature-reference reconciliation problem: {status_code} {code}")
        self.status_code = status_code
        self.code = code


class FeatureReferenceReconciliationLeaseConflict(FeatureReferenceReconciliationProblem):
    """다른 worker가 아직 유효한 lease를 보유한다."""


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeatureReferenceReconciliationMeta(_ClosedModel):
    duration_ms: int = Field(ge=0)
    request_id: str = ""
    page: dict[str, Any] | None = None
    cluster: dict[str, Any] | None = None


class FeatureReference(_ClosedModel):
    feature_id: str = Field(min_length=1)
    feature_uuid: uuid.UUID
    row_revision: int = Field(ge=1)


class FeatureReferenceReconciliationEvent(_ClosedModel):
    payload_schema_version: Literal[1]
    event_id: uuid.UUID
    event_sequence: int = Field(ge=1)
    occurred_at: datetime
    case_id: uuid.UUID
    resolution_id: uuid.UUID
    action: Literal["rebind", "detach"]
    old_feature: FeatureReference
    replacement_feature: FeatureReference | None
    manual_retire_transition_id: int = Field(ge=1)
    manual_retire_row_revision_after_transition: int = Field(ge=2)
    command_id: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_action_reference(self) -> FeatureReferenceReconciliationEvent:
        if self.action == "rebind" and self.replacement_feature is None:
            raise ValueError("rebind event requires replacement_feature")
        if self.action == "detach" and self.replacement_feature is not None:
            raise ValueError("detach event cannot include replacement_feature")
        return self


class FeatureReferenceReconciliationLease(_ClosedModel):
    outcome: Literal["leased"]
    lease_epoch: int = Field(ge=1)
    lease_expires_at: datetime
    event: FeatureReferenceReconciliationEvent
    event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FeatureReferenceReconciliationAck(_ClosedModel):
    outcome: Literal["acked", "replayed"]
    acked_through_sequence: int = Field(ge=0)


class FeatureReferenceReconciliationServiceClient:
    """read 또는 ACK 단일 scope token에 고정된 M05 service transport."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        role: Literal["read", "ack"],
        token: str,
    ) -> None:
        self._http = http
        self._role = role
        self._token = token

    async def aclose(self) -> None:
        await self._http.aclose()

    async def lease(self, *, worker_id: uuid.UUID) -> FeatureReferenceReconciliationLease | None:
        self._require_role("read")
        response = await self._send(
            "GET",
            _LEASE_PATH,
            headers={_WORKER_ID_HEADER: str(worker_id)},
            accepted_statuses=frozenset(
                {httpx.codes.OK, httpx.codes.NO_CONTENT, httpx.codes.CONFLICT}
            ),
        )
        if response.status_code == httpx.codes.NO_CONTENT:
            if response.content:
                raise FeatureReferenceReconciliationContractError(
                    "empty reconciliation lease response must not have a body"
                )
            return None
        if response.status_code == httpx.codes.CONFLICT:
            raise FeatureReferenceReconciliationLeaseConflict(
                status_code=response.status_code,
                code=_error_code(response),
            )
        payload = _success_envelope(response)
        try:
            return FeatureReferenceReconciliationLease.model_validate(payload["data"])
        except ValidationError as exc:
            raise FeatureReferenceReconciliationContractError(
                "Map reconciliation lease data contract is invalid"
            ) from exc

    async def acknowledge(
        self,
        *,
        event_id: uuid.UUID,
        worker_id: uuid.UUID,
        lease_epoch: int,
        event_sha256: str,
        local_receipt_sha256: str,
        idempotency_key: uuid.UUID,
    ) -> FeatureReferenceReconciliationAck:
        self._require_role("ack")
        response = await self._send(
            "POST",
            f"{_LEASE_PATH}/{event_id}/acks",
            headers={_IDEMPOTENCY_KEY_HEADER: str(idempotency_key)},
            body={
                "worker_id": str(worker_id),
                "lease_epoch": lease_epoch,
                "event_sha256": event_sha256,
                "local_receipt_sha256": local_receipt_sha256,
            },
        )
        payload = _success_envelope(response)
        try:
            result = FeatureReferenceReconciliationAck.model_validate(payload["data"])
        except ValidationError as exc:
            raise FeatureReferenceReconciliationContractError(
                "Map reconciliation ACK data contract is invalid"
            ) from exc
        replayed = response.headers.get("Idempotency-Replayed")
        if replayed not in {None, "true"}:
            raise FeatureReferenceReconciliationContractError(
                "Map reconciliation ACK replay header is invalid"
            )
        if replayed == "true" and result.outcome != "replayed":
            raise FeatureReferenceReconciliationContractError(
                "Map reconciliation ACK replay header/outcome differ"
            )
        return result

    def _require_role(self, expected: Literal["read", "ack"]) -> None:
        if self._role != expected:
            raise PermissionError(
                f"feature-reference reconciliation {expected} principal 전용입니다."
            )

    async def _send(
        self,
        method: Literal["GET", "POST"],
        path: str,
        *,
        headers: dict[str, str],
        body: dict[str, object] | None = None,
        accepted_statuses: frozenset[int] = frozenset({httpx.codes.OK, httpx.codes.NO_CONTENT}),
    ) -> httpx.Response:
        request_headers = {_SERVICE_TOKEN_HEADER: self._token, **headers}
        try:
            response = await self._http.request(
                method,
                path,
                headers=request_headers,
                json=body,
            )
        except httpx.RequestError as exc:
            raise FeatureReferenceReconciliationUnavailable(
                f"Map feature-reference reconciliation transport failed: {exc!r}"
            ) from exc
        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise FeatureReferenceReconciliationUnavailable(
                f"Map feature-reference reconciliation returned {response.status_code}"
            )
        if response.status_code not in accepted_statuses:
            raise FeatureReferenceReconciliationProblem(
                status_code=response.status_code,
                code=_error_code(response),
            )
        return response


def _success_envelope(response: httpx.Response) -> dict[str, object]:
    if response.status_code != httpx.codes.OK:
        raise FeatureReferenceReconciliationContractError(
            "Map reconciliation success response must use HTTP 200"
        )
    try:
        payload = json.loads(response.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeatureReferenceReconciliationContractError(
            "Map reconciliation response is not valid JSON"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {"data", "meta"}:
        raise FeatureReferenceReconciliationContractError(
            "Map reconciliation envelope shape is invalid"
        )
    if not isinstance(payload["data"], dict) or not isinstance(payload["meta"], dict):
        raise FeatureReferenceReconciliationContractError(
            "Map reconciliation envelope data/meta is invalid"
        )
    try:
        FeatureReferenceReconciliationMeta.model_validate(payload["meta"])
    except ValidationError as exc:
        raise FeatureReferenceReconciliationContractError(
            "Map reconciliation response meta contract is invalid"
        ) from exc
    return payload
