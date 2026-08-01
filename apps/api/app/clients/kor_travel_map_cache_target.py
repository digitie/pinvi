"""kor-travel-map cache-target service 전용 role-bound HTTP transport."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Self
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.services.cache_target_event_consumer import (
    CacheTargetAck,
    CacheTargetClaim,
    CacheTargetSnapshot,
)

CacheTargetRole = Literal["command", "consumer", "restore", "recovery"]
FailureDisposition = Literal["retry", "halt", "reconcile", "dead_letter"]

_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"  # noqa: S105 - header name
_IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"


def classify_cache_target_failure(*, status_code: int, code: str) -> FailureDisposition:
    """HTTP/problem code를 retry budget과 operator action으로 분류한다."""
    if status_code in {408, 425, 429} or status_code >= 500:
        return "retry"
    if status_code in {401, 403}:
        return "halt"
    if status_code == 412:
        return "reconcile"
    if status_code in {400, 404, 422, 428}:
        return "dead_letter"
    if status_code == 409:
        if code in {
            "CACHE_TARGET_IDEMPOTENCY_CONFLICT",
            "IDEMPOTENCY_KEY_REUSED",
            "IDEMPOTENCY_PAYLOAD_MISMATCH",
        }:
            return "dead_letter"
        return "halt"
    return "dead_letter"


class CacheTargetNetworkError(RuntimeError):
    """응답을 받지 못해 outcome이 불확실한 transient transport failure."""


class CacheTargetContractError(ValueError):
    """Map service 응답이 pinned envelope/DTO 계약과 다름."""


class CacheTargetServiceProblem(RuntimeError):
    """Map RFC7807 응답의 typed status/code."""

    def __init__(self, *, status_code: int, code: str, retry_after: int | None) -> None:
        super().__init__(f"kor-travel-map cache-target problem: {status_code} {code}")
        self.status_code = status_code
        self.code = code
        self.retry_after = retry_after
        self.disposition = classify_cache_target_failure(status_code=status_code, code=code)


@dataclass(frozen=True, slots=True)
class CacheTargetMutationResult:
    status_code: int
    data: CacheTargetStateResult
    etag: str | None


class CacheTargetStateResult(BaseModel):
    """PUT/DELETE response data의 pinned strict projection."""

    model_config = ConfigDict(extra="forbid")

    external_system: Literal["pinvi"]
    target_key: str
    state: Literal["active", "deleted"]
    restore_epoch: StrictInt = Field(gt=0)
    source_generation: StrictInt = Field(gt=0)
    source_payload_fingerprint: str
    entity_tag: str
    target_id: uuid.UUID
    target_sequence: StrictInt = Field(gt=0)
    occurred_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("source_payload_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        if len(value) != 64 or value != value.lower():
            raise ValueError("source_payload_fingerprint가 lowercase SHA-256 hex가 아닙니다.")
        try:
            bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError(
                "source_payload_fingerprint가 lowercase SHA-256 hex가 아닙니다."
            ) from exc
        return value

    @field_validator("target_id", mode="before")
    @classmethod
    def validate_target_id(cls, value: object) -> object:
        if isinstance(value, uuid.UUID):
            return value
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError("target_id가 lowercase canonical UUID가 아닙니다.")
        return value

    @model_validator(mode="after")
    def validate_identity_and_etag(self) -> Self:
        if self.target_key != str(uuid.UUID(self.target_key)):
            raise ValueError("target_key가 canonical UUID가 아닙니다.")
        prefix = f'"{self.target_id}:'
        if not self.entity_tag.startswith(prefix) or not self.entity_tag.endswith('"'):
            raise ValueError("entity_tag가 target strong ETag 형식이 아닙니다.")
        version = self.entity_tag[len(prefix) : -1]
        if (
            not version.isascii()
            or not version.isdigit()
            or int(version) < 1
            or str(int(version)) != version
        ):
            raise ValueError("entity_tag version이 canonical positive decimal이 아닙니다.")
        return self


class CacheTargetRunningReconciliation(BaseModel):
    """stream read가 노출하는 request-bound fixed snapshot identity."""

    model_config = ConfigDict(extra="forbid")

    request_id: uuid.UUID
    status: Literal["running"]
    snapshot_id: uuid.UUID
    restore_epoch: int = Field(gt=0)
    count: int = Field(ge=0)
    merkle_root: str
    high_watermark_cursor: str
    entity_tag: str
    stream_entity_tag: str
    created_at: datetime

    @field_validator("merkle_root")
    @classmethod
    def validate_merkle_root(cls, value: str) -> str:
        if len(value) != 64 or value != value.lower():
            raise ValueError("active reconciliation Merkle root가 lowercase SHA-256이 아닙니다.")
        try:
            bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError(
                "active reconciliation Merkle root가 lowercase SHA-256이 아닙니다."
            ) from exc
        return value


class CacheTargetPreparingReconciliation(BaseModel):
    """begin 뒤 seal 전에는 snapshot identity가 아직 없다."""

    model_config = ConfigDict(extra="forbid")

    request_id: uuid.UUID
    status: Literal["preparing"]
    restore_epoch: int = Field(gt=0)
    entity_tag: str
    stream_entity_tag: str
    created_at: datetime


CacheTargetActiveReconciliation = (
    CacheTargetPreparingReconciliation | CacheTargetRunningReconciliation
)


class CacheTargetStreamState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_system: Literal["pinvi"]
    restore_epoch: int = Field(gt=0)
    control_version: int = Field(gt=0)
    entity_tag: str
    state: str
    consumer_id: str | None = None
    blocked_event_id: uuid.UUID | None = None
    active_reconciliation: CacheTargetActiveReconciliation | None = Field(
        default=None,
        discriminator="status",
    )
    updated_at: datetime | None = None


class CacheTargetRecoveryOperation(BaseModel):
    """reconciliation completion의 strict operation receipt."""

    model_config = ConfigDict(extra="forbid")

    operation_id: uuid.UUID
    status: Literal["preparing", "running", "succeeded", "failed", "superseded"]
    snapshot_id: uuid.UUID | None = None
    status_url: str | None = None
    entity_tag: str | None = None
    stream_entity_tag: str | None = None


@dataclass(frozen=True, slots=True)
class CacheTargetRecoveryResult:
    operation: CacheTargetRecoveryOperation
    etag: str


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if value is None or not value.isascii() or not value.isdigit():
        return None
    seconds = int(value)
    return seconds if 1 <= seconds <= 300 else None


def _problem_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "UNPARSEABLE_PROBLEM"
    if not isinstance(payload, dict):
        return "UNPARSEABLE_PROBLEM"
    code = payload.get("code")
    return code if isinstance(code, str) and code else "UNSPECIFIED_PROBLEM"


def _unwrap_envelope(response: httpx.Response) -> tuple[Any, dict[str, Any]]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise CacheTargetContractError("service response가 JSON이 아닙니다.") from exc
    if not isinstance(payload, dict) or set(payload) != {"data", "meta"}:
        raise CacheTargetContractError("service response envelope가 exact {data,meta}가 아닙니다.")
    if not isinstance(payload["meta"], dict):
        raise CacheTargetContractError("service response meta가 object가 아닙니다.")
    return payload["data"], payload["meta"]


def _unwrap_data(response: httpx.Response) -> Any:
    data, _ = _unwrap_envelope(response)
    return data


def _next_cursor(meta: dict[str, Any]) -> str | None:
    page = meta.get("page")
    if page is None:
        return None
    if not isinstance(page, dict):
        raise CacheTargetContractError("service response meta.page가 object가 아닙니다.")
    cursor = page.get("next_cursor")
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise CacheTargetContractError("service response next_cursor가 유효하지 않습니다.")
    return cursor


def _occurred_at(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("occurred_at은 timezone-aware datetime이어야 합니다.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_source_fingerprint(source_payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        source_payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scaled_decimal_string(value: int, *, scale: int, digits: int) -> str:
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    whole, fraction = divmod(magnitude, scale)
    return f"{sign}{whole}.{fraction:0{digits}d}"


def _active_wire_body(
    *,
    source_payload: dict[str, Any],
    command_id: uuid.UUID,
    restore_epoch: int,
    source_generation: int,
    occurred_at: datetime,
) -> dict[str, Any]:
    if set(source_payload) != {"version", "state", "coord", "radius_m", "update_enabled"}:
        raise ValueError("active source payload field가 exact v1 계약과 다릅니다.")
    if (
        source_payload.get("version") != "cache-target-source-v1"
        or source_payload.get("state") != "active"
    ):
        raise ValueError("active source payload version/state가 다릅니다.")
    coord = source_payload.get("coord")
    if not isinstance(coord, dict) or set(coord) != {"lon_e6", "lat_e6"}:
        raise ValueError("active source coord가 exact v1 계약과 다릅니다.")
    lon_e6 = coord.get("lon_e6")
    lat_e6 = coord.get("lat_e6")
    radius_m = source_payload.get("radius_m")
    update_enabled = source_payload.get("update_enabled")
    if (
        isinstance(lon_e6, bool)
        or not isinstance(lon_e6, int)
        or isinstance(lat_e6, bool)
        or not isinstance(lat_e6, int)
        or isinstance(radius_m, bool)
        or not isinstance(radius_m, int)
        or not isinstance(update_enabled, bool)
    ):
        raise ValueError("active source 정수/bool field 타입이 다릅니다.")
    if not -180_000_000 <= lon_e6 <= 180_000_000 or not -90_000_000 <= lat_e6 <= 90_000_000:
        raise ValueError("active source coord가 범위를 벗어났습니다.")
    if not 1 <= radius_m <= 100_000:
        raise ValueError("active source radius_m이 범위를 벗어났습니다.")
    return {
        "source_event_id": str(command_id),
        "restore_epoch": restore_epoch,
        "source_generation": source_generation,
        "coord": {
            "lon": _scaled_decimal_string(lon_e6, scale=1_000_000, digits=6),
            "lat": _scaled_decimal_string(lat_e6, scale=1_000_000, digits=6),
        },
        "radius_km": _scaled_decimal_string(radius_m, scale=1_000, digits=3),
        "update_enabled": update_enabled,
        "occurred_at": _occurred_at(occurred_at),
    }


def _deleted_wire_body(
    *,
    source_payload: dict[str, Any],
    command_id: uuid.UUID,
    restore_epoch: int,
    source_generation: int,
    occurred_at: datetime,
) -> dict[str, Any]:
    if source_payload != {"state": "deleted", "version": "cache-target-source-v1"}:
        raise ValueError("deleted source payload가 exact v1 계약과 다릅니다.")
    return {
        "source_event_id": str(command_id),
        "restore_epoch": restore_epoch,
        "source_generation": source_generation,
        "occurred_at": _occurred_at(occurred_at),
    }


class CacheTargetServiceClient:
    """생성 시 한 principal role에 고정되는 service OpenAPI transport."""

    def __init__(self, http: httpx.AsyncClient, *, role: CacheTargetRole, token: str) -> None:
        normalized = token.strip()
        if len(normalized) < 32 or any(character.isspace() for character in normalized):
            raise ValueError("cache target service token은 whitespace 없는 32자 이상이어야 합니다.")
        self._http = http
        self._role = role
        self._token = normalized

    async def aclose(self) -> None:
        await self._http.aclose()

    def _require_role(self, expected: CacheTargetRole) -> None:
        if self._role != expected:
            raise PermissionError(f"{expected} principal 전용 cache-target surface입니다.")

    async def _send(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, str | int] | None = None,
        idempotency_key: uuid.UUID | None = None,
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> httpx.Response:
        headers = {_SERVICE_TOKEN_HEADER: self._token}
        if idempotency_key is not None:
            headers[_IDEMPOTENCY_KEY_HEADER] = str(idempotency_key)
        if if_match is not None:
            if if_match.startswith("W/") or not (
                len(if_match) >= 2 and if_match.startswith('"') and if_match.endswith('"')
            ):
                raise ValueError("If-Match는 Map이 발급한 raw strong ETag여야 합니다.")
            headers["If-Match"] = if_match
        if if_none_match:
            headers["If-None-Match"] = "*"
        try:
            response = await self._http.request(
                method,
                path,
                json=body,
                params=params,
                headers=headers,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise CacheTargetNetworkError(
                "kor-travel-map cache-target outcome이 불확실합니다."
            ) from exc
        if response.is_error:
            raise CacheTargetServiceProblem(
                status_code=response.status_code,
                code=_problem_code(response),
                retry_after=_retry_after(response),
            )
        return response

    async def put_target(
        self,
        *,
        external_system: Literal["pinvi"],
        target_key: str,
        command_id: uuid.UUID,
        restore_epoch: int,
        source_generation: int,
        occurred_at: datetime,
        source_payload: dict[str, Any],
        expected_etag: str | None,
    ) -> CacheTargetMutationResult:
        self._require_role("command")
        body = _active_wire_body(
            source_payload=source_payload,
            command_id=command_id,
            restore_epoch=restore_epoch,
            source_generation=source_generation,
            occurred_at=occurred_at,
        )
        path = (
            f"/v1/service/cache-targets/{quote(external_system, safe='')}"
            f"/{quote(target_key, safe='')}"
        )
        response = await self._send(
            "PUT",
            path,
            body=body,
            idempotency_key=command_id,
            if_match=expected_etag,
            if_none_match=expected_etag is None,
        )
        data = CacheTargetStateResult.model_validate(_unwrap_data(response))
        self._validate_mutation_result(
            data=data,
            response=response,
            target_key=target_key,
            state="active",
            restore_epoch=restore_epoch,
            source_generation=source_generation,
            source_payload=source_payload,
            expected_etag=expected_etag,
        )
        return CacheTargetMutationResult(response.status_code, data, response.headers.get("ETag"))

    async def delete_target(
        self,
        *,
        external_system: Literal["pinvi"],
        target_key: str,
        command_id: uuid.UUID,
        restore_epoch: int,
        source_generation: int,
        occurred_at: datetime,
        source_payload: dict[str, Any],
        expected_etag: str,
    ) -> CacheTargetMutationResult:
        self._require_role("command")
        body = _deleted_wire_body(
            source_payload=source_payload,
            command_id=command_id,
            restore_epoch=restore_epoch,
            source_generation=source_generation,
            occurred_at=occurred_at,
        )
        path = (
            f"/v1/service/cache-targets/{quote(external_system, safe='')}"
            f"/{quote(target_key, safe='')}"
        )
        response = await self._send(
            "DELETE",
            path,
            body=body,
            idempotency_key=command_id,
            if_match=expected_etag,
        )
        data = CacheTargetStateResult.model_validate(_unwrap_data(response))
        self._validate_mutation_result(
            data=data,
            response=response,
            target_key=target_key,
            state="deleted",
            restore_epoch=restore_epoch,
            source_generation=source_generation,
            source_payload=source_payload,
            expected_etag=expected_etag,
        )
        return CacheTargetMutationResult(response.status_code, data, response.headers.get("ETag"))

    @staticmethod
    def _validate_mutation_result(
        *,
        data: CacheTargetStateResult,
        response: httpx.Response,
        target_key: str,
        state: Literal["active", "deleted"],
        restore_epoch: int,
        source_generation: int,
        source_payload: dict[str, Any],
        expected_etag: str | None,
    ) -> None:
        if (
            data.target_key != target_key
            or data.state != state
            or data.restore_epoch != restore_epoch
            or data.source_generation != source_generation
            or data.source_payload_fingerprint != _canonical_source_fingerprint(source_payload)
        ):
            raise CacheTargetContractError(
                "target mutation response가 요청 source identity와 다릅니다."
            )
        response_etag = response.headers.get("ETag")
        if response_etag is None or response_etag != data.entity_tag:
            raise CacheTargetContractError("target mutation ETag header/body가 다릅니다.")
        if expected_etag is not None:
            expected_target_id, separator, _version = expected_etag[1:-1].rpartition(":")
            if separator != ":" or expected_target_id != str(data.target_id):
                raise CacheTargetContractError(
                    "target mutation receipt가 If-Match target incarnation과 다릅니다."
                )

    async def claim_events(
        self,
        *,
        consumer_id: str,
        limit: int,
        lease_seconds: int,
        idempotency_key: uuid.UUID,
    ) -> CacheTargetClaim | None:
        self._require_role("consumer")
        response = await self._send(
            "POST",
            "/v1/service/cache-target-event-claims",
            body={
                "external_system": "pinvi",
                "consumer_id": consumer_id,
                "limit": limit,
                "lease_seconds": lease_seconds,
            },
            idempotency_key=idempotency_key,
        )
        data = _unwrap_data(response)
        return None if data is None else CacheTargetClaim.model_validate(data)

    async def ack_events(self, ack: CacheTargetAck) -> None:
        self._require_role("consumer")
        response = await self._send(
            "POST",
            "/v1/service/cache-target-event-acks",
            body=ack.model_dump(mode="json"),
        )
        _unwrap_data(response)

    async def nack_event(self, body: dict[str, Any]) -> None:
        self._require_role("consumer")
        response = await self._send(
            "POST",
            "/v1/service/cache-target-event-nacks",
            body=body,
        )
        _unwrap_data(response)

    async def begin_initial_reconciliation(
        self,
        *,
        consumer_id: str,
        expected_restore_epoch: int,
        reason: str,
        idempotency_key: uuid.UUID,
        stream_etag: str | None,
    ) -> CacheTargetRecoveryResult:
        self._require_role("recovery")
        response = await self._send(
            "POST",
            "/v1/service/cache-target-reconciliations",
            body={
                "external_system": "pinvi",
                "consumer_id": consumer_id,
                "expected_restore_epoch": expected_restore_epoch,
                "reason": reason,
            },
            idempotency_key=idempotency_key,
            if_match=stream_etag,
            if_none_match=stream_etag is None,
        )
        return self._recovery_result(
            response,
            expected_status="preparing",
            expected_operation_id=None,
        )

    async def seal_initial_reconciliation(
        self,
        *,
        request_id: uuid.UUID,
        consumer_id: str,
        expected_restore_epoch: int,
        expected_item_count: int,
        expected_merkle_root: str,
        idempotency_key: uuid.UUID,
        stream_etag: str,
    ) -> CacheTargetRecoveryResult:
        self._require_role("recovery")
        response = await self._send(
            "POST",
            f"/v1/service/cache-target-reconciliations/{request_id}/seals",
            body={
                "external_system": "pinvi",
                "consumer_id": consumer_id,
                "expected_restore_epoch": expected_restore_epoch,
                "expected_item_count": expected_item_count,
                "expected_merkle_root": expected_merkle_root,
            },
            idempotency_key=idempotency_key,
            if_match=stream_etag,
        )
        return self._recovery_result(
            response,
            expected_status="running",
            expected_operation_id=request_id,
        )

    @staticmethod
    def _recovery_result(
        response: httpx.Response,
        *,
        expected_status: Literal["preparing", "running"],
        expected_operation_id: uuid.UUID | None,
    ) -> CacheTargetRecoveryResult:
        operation = CacheTargetRecoveryOperation.model_validate(_unwrap_data(response))
        etag = response.headers.get("ETag")
        snapshot_identity_matches_phase = (
            operation.snapshot_id is None
            if expected_status == "preparing"
            else operation.snapshot_id is not None
        )
        if (
            operation.status != expected_status
            or (
                expected_operation_id is not None
                and operation.operation_id != expected_operation_id
            )
            or not snapshot_identity_matches_phase
            or etag is None
            or operation.entity_tag != etag
            or operation.stream_entity_tag is None
        ):
            raise CacheTargetContractError(
                "reconciliation operation identity/status/ETag가 다릅니다."
            )
        return CacheTargetRecoveryResult(operation=operation, etag=etag)

    async def complete_reconciliation(
        self,
        *,
        request_id: uuid.UUID,
        consumer_id: str,
        snapshot: CacheTargetSnapshot,
        idempotency_key: uuid.UUID,
    ) -> CacheTargetRecoveryOperation:
        self._require_role("consumer")
        response = await self._send(
            "POST",
            f"/v1/service/cache-target-reconciliations/{request_id}/completions",
            body={
                "external_system": "pinvi",
                "consumer_id": consumer_id,
                "snapshot_id": str(uuid.UUID(snapshot.snapshot_id)),
                "expected_restore_epoch": snapshot.restore_epoch,
                "actual_merkle_root": snapshot.merkle_root,
            },
            idempotency_key=idempotency_key,
        )
        operation = CacheTargetRecoveryOperation.model_validate(_unwrap_data(response))
        if operation.operation_id != request_id:
            raise CacheTargetContractError(
                "reconciliation completion operation identity가 다릅니다."
            )
        if operation.snapshot_id != uuid.UUID(snapshot.snapshot_id):
            raise CacheTargetContractError(
                "reconciliation completion snapshot identity가 다릅니다."
            )
        return operation

    async def get_snapshot(self) -> CacheTargetSnapshot:
        self._require_role("consumer")
        return await self._get_snapshot_pages("/v1/service/cache-target-snapshots/pinvi")

    async def get_reconciliation_snapshot(
        self,
        request_id: uuid.UUID,
    ) -> CacheTargetSnapshot:
        self._require_role("consumer")
        return await self._get_snapshot_pages(
            f"/v1/service/cache-target-reconciliations/{request_id}/snapshot"
        )

    async def _get_snapshot_pages(self, path: str) -> CacheTargetSnapshot:
        first: CacheTargetSnapshot | None = None
        items: list[Any] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            params: dict[str, str | int] = {"page_size": 1000}
            if cursor is not None:
                params["cursor"] = cursor
            response = await self._send("GET", path, params=params)
            raw_data, meta = _unwrap_envelope(response)
            page = CacheTargetSnapshot.model_validate(raw_data)
            if first is None:
                first = page
            elif (
                page.snapshot_id != first.snapshot_id
                or page.restore_epoch != first.restore_epoch
                or page.high_watermark_cursor != first.high_watermark_cursor
                or page.count != first.count
                or page.merkle_root != first.merkle_root
            ):
                raise CacheTargetContractError("fixed snapshot page header가 바뀌었습니다.")
            items.extend(page.items)
            next_cursor = _next_cursor(meta)
            if next_cursor is None:
                break
            if next_cursor in seen_cursors:
                raise CacheTargetContractError("fixed snapshot cursor가 반복됩니다.")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        if first is None or len(items) != first.count:
            raise CacheTargetContractError("fixed snapshot item count가 선언과 다릅니다.")
        return first.model_copy(update={"items": items})

    async def get_stream(self) -> CacheTargetStreamState:
        self._require_role("consumer")
        response = await self._send("GET", "/v1/service/cache-target-streams/pinvi")
        data = CacheTargetStreamState.model_validate(_unwrap_data(response))
        if response.headers.get("ETag") != data.entity_tag:
            raise CacheTargetContractError("stream ETag header/body가 다릅니다.")
        return data
