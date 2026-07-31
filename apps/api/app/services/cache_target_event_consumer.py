"""Map cache-target relay의 strict inbox, local checkpoint, snapshot reconcile."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache_target_contract import (
    CacheTargetMerkleRow,
    cache_target_snapshot_merkle_root,
)
from app.models.cache_target_sync import (
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
    KtmCacheTargetHead,
    KtmCacheTargetReconciliationExpectation,
)

EventType = Literal[
    "cache_target.state_applied",
    "cache_target.links_reconciled",
    "refresh_request.status_changed",
    "cache_target.reconciled",
]
TargetState = Literal["active", "deleted"]


class CacheTargetConsumerError(ValueError):
    """ACK하지 않고 typed NACK로 변환해야 하는 relay 불변식 위반."""


class CacheTargetEventGapError(CacheTargetConsumerError):
    """claim 내부 또는 직전 local prefix 다음의 relay order가 비연속임."""


class CacheTargetStaleEpochError(CacheTargetConsumerError):
    """active restore epoch와 다른 event/snapshot을 관측함."""


class CacheTargetEventConflictError(CacheTargetConsumerError):
    """같은 event identity가 다른 immutable material로 재전달됨."""


class CacheTargetEventApplyError(CacheTargetConsumerError):
    """claim 중간 event의 semantic apply가 실패해 앞 prefix만 ACK할 수 있음."""

    def __init__(
        self,
        *,
        event_index: int,
        event: CacheTargetEventRecord,
        cause: CacheTargetConsumerError,
    ) -> None:
        super().__init__(str(cause))
        self.event_index = event_index
        self.event = event
        self.cause = cause


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_sha256_hex(value: str) -> str:
    if len(value) != 64 or value != value.lower():
        raise ValueError("fingerprint는 lowercase SHA-256 hex여야 합니다.")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("fingerprint는 lowercase SHA-256 hex여야 합니다.") from exc
    return value


class CacheTargetEventRecord(_StrictModel):
    """Map event envelope. payload fingerprint는 opaque receipt로 검증한다."""

    event_id: uuid.UUID
    event_type: EventType
    event_scope: Literal["target", "stream"]
    external_system: Literal["pinvi"]
    target_key: str | None = Field(default=None, min_length=36, max_length=36)
    target_id: uuid.UUID | None = None
    restore_epoch: int = Field(gt=0)
    source_generation: int | None = Field(default=None, gt=0)
    target_sequence: int | None = Field(default=None, gt=0)
    relay_order: int = Field(gt=0)
    cursor: str = Field(min_length=1)
    source_payload_fingerprint: str
    payload_fingerprint: str
    payload: dict[str, Any]
    occurred_at: datetime

    @field_validator("target_key")
    @classmethod
    def validate_target_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = uuid.UUID(value)
        canonical = str(parsed)
        if value != canonical:
            raise ValueError("target_key는 lowercase canonical UUID여야 합니다.")
        return value

    @field_validator("source_payload_fingerprint", "payload_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        return _validate_sha256_hex(value)

    @model_validator(mode="after")
    def validate_scope_tuple(self) -> Self:
        target_tuple = (
            self.target_key,
            self.target_id,
            self.source_generation,
            self.target_sequence,
        )
        if self.event_type == "cache_target.reconciled":
            if (
                self.event_scope != "stream"
                or self.target_id is not None
                or any(value is not None for value in target_tuple)
            ):
                raise ValueError("reconciled는 target tuple이 없는 stream event여야 합니다.")
        elif self.event_scope != "target" or any(value is None for value in target_tuple):
            raise ValueError("target event는 완전한 target tuple이 필요합니다.")
        return self


class CacheTargetClaim(_StrictModel):
    """claim endpoint의 non-empty response data."""

    claim_id: uuid.UUID
    external_system: Literal["pinvi"]
    consumer_id: str = Field(min_length=1, max_length=64)
    lease_token: uuid.UUID
    status: Literal["active"]
    first_relay_order: int | None = Field(default=None, gt=0)
    last_relay_order: int | None = Field(default=None, gt=0)
    acked_through: str | None = None
    lease_expires_at: datetime
    events: list[CacheTargetEventRecord] = Field(min_length=1)
    idempotent_replay: bool

    @model_validator(mode="after")
    def validate_event_bounds(self) -> Self:
        first = self.events[0].relay_order
        last = self.events[-1].relay_order
        if self.first_relay_order is not None and self.first_relay_order != first:
            raise ValueError("first_relay_order가 events와 다릅니다.")
        if self.last_relay_order is not None and self.last_relay_order != last:
            raise ValueError("last_relay_order가 events와 다릅니다.")
        if any(event.external_system != self.external_system for event in self.events):
            raise ValueError("claim과 event external_system이 다릅니다.")
        cursors = [event.cursor for event in self.events]
        if len(set(cursors)) != len(cursors):
            raise ValueError("claim event cursor가 중복됩니다.")
        return self


class CacheTargetAppliedReceipt(_StrictModel):
    event_id: uuid.UUID
    payload_fingerprint: str

    @field_validator("payload_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        return _validate_sha256_hex(value)


class CacheTargetAck(_StrictModel):
    consumer_id: str
    claim_id: uuid.UUID
    lease_token: uuid.UUID
    through_cursor: str
    applied: list[CacheTargetAppliedReceipt]


class CacheTargetSnapshotItem(_StrictModel):
    external_system: Literal["pinvi"]
    target_key: str = Field(min_length=1)
    state: TargetState
    source_generation: int = Field(gt=0)
    source_payload_fingerprint: str

    @field_validator("target_key")
    @classmethod
    def validate_target_key(cls, value: str) -> str:
        parsed = uuid.UUID(value)
        canonical = str(parsed)
        if value != canonical:
            raise ValueError("target_key는 lowercase canonical UUID여야 합니다.")
        return value

    @field_validator("source_payload_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        return _validate_sha256_hex(value)


class CacheTargetSnapshot(_StrictModel):
    snapshot_id: str = Field(min_length=1)
    restore_epoch: int = Field(gt=0)
    high_watermark_cursor: str
    count: int = Field(ge=0)
    merkle_root: str
    items: list[CacheTargetSnapshotItem]

    @field_validator("merkle_root")
    @classmethod
    def validate_merkle_root(cls, value: str) -> str:
        return _validate_sha256_hex(value)


async def record_cache_target_reconciliation_expectation(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    snapshot: CacheTargetSnapshot,
) -> KtmCacheTargetReconciliationExpectation:
    """active request의 fixed snapshot identity를 terminal receipt보다 먼저 고정한다."""
    try:
        snapshot_id = uuid.UUID(snapshot.snapshot_id)
    except ValueError as exc:
        raise CacheTargetEventConflictError(
            "reconciliation snapshot_id가 UUID가 아닙니다."
        ) from exc
    if str(snapshot_id) != snapshot.snapshot_id:
        raise CacheTargetEventConflictError(
            "reconciliation snapshot_id가 canonical UUID가 아닙니다."
        )
    material = (
        snapshot_id,
        snapshot.restore_epoch,
        snapshot.count,
        bytes.fromhex(snapshot.merkle_root),
        snapshot.high_watermark_cursor,
    )
    expectation = await db.scalar(
        select(KtmCacheTargetReconciliationExpectation)
        .where(KtmCacheTargetReconciliationExpectation.request_id == request_id)
        .with_for_update()
    )
    if expectation is None:
        snapshot_owner = await db.scalar(
            select(KtmCacheTargetReconciliationExpectation.request_id).where(
                KtmCacheTargetReconciliationExpectation.snapshot_id == snapshot_id
            )
        )
        if snapshot_owner is not None:
            raise CacheTargetEventConflictError(
                "reconciliation snapshot_id가 다른 request에 이미 결박됐습니다."
            )
        expectation = KtmCacheTargetReconciliationExpectation(
            request_id=request_id,
            external_system="pinvi",
            snapshot_id=snapshot_id,
            restore_epoch=snapshot.restore_epoch,
            snapshot_count=snapshot.count,
            snapshot_merkle_root=bytes.fromhex(snapshot.merkle_root),
            high_watermark_cursor=snapshot.high_watermark_cursor,
            status="pending",
        )
        db.add(expectation)
        await db.flush()
        return expectation
    existing_material = (
        expectation.snapshot_id,
        expectation.restore_epoch,
        expectation.snapshot_count,
        expectation.snapshot_merkle_root,
        expectation.high_watermark_cursor,
    )
    if existing_material != material or expectation.external_system != "pinvi":
        raise CacheTargetEventConflictError(
            "같은 reconciliation request의 fixed snapshot identity가 바뀌었습니다."
        )
    if expectation.status != "pending":
        raise CacheTargetEventConflictError(
            "종결된 reconciliation expectation을 다시 active로 채택할 수 없습니다."
        )
    return expectation


def _event_material(event: CacheTargetEventRecord) -> tuple[object, ...]:
    return (
        event.event_type,
        event.event_scope,
        event.external_system,
        event.target_key,
        event.target_id,
        event.restore_epoch,
        event.source_generation,
        event.target_sequence,
        event.relay_order,
        bytes.fromhex(event.source_payload_fingerprint),
        bytes.fromhex(event.payload_fingerprint),
        event.occurred_at,
        event.payload,
    )


def _stored_event_material(event: KtmCacheTargetEvent) -> tuple[object, ...]:
    return (
        event.event_type,
        "stream" if event.event_type == "cache_target.reconciled" else "target",
        event.external_system,
        event.target_key,
        event.target_id,
        event.restore_epoch,
        event.source_generation,
        event.target_sequence,
        event.relay_order,
        event.source_payload_fingerprint,
        event.payload_fingerprint,
        event.occurred_at,
        event.payload,
    )


async def _validate_existing_claim(
    db: AsyncSession,
    *,
    claim: CacheTargetClaim,
    existing: KtmCacheTargetEventClaim,
) -> None:
    if (
        existing.consumer_id != claim.consumer_id
        or existing.lease_token != claim.lease_token
        or existing.lease_expires_at != claim.lease_expires_at
    ):
        raise CacheTargetEventConflictError("같은 claim_id의 lease material이 다릅니다.")
    items = list(
        await db.scalars(
            select(KtmCacheTargetEventClaimItem)
            .where(KtmCacheTargetEventClaimItem.claim_id == claim.claim_id)
            .order_by(KtmCacheTargetEventClaimItem.position)
        )
    )
    expected = [
        (position, event.event_id, event.cursor, bytes.fromhex(event.payload_fingerprint))
        for position, event in enumerate(claim.events, start=1)
    ]
    actual = [
        (item.position, item.event_id, item.delivery_cursor, item.payload_fingerprint)
        for item in items
    ]
    if actual != expected:
        raise CacheTargetEventConflictError("같은 claim_id의 event receipt가 다릅니다.")


async def apply_cache_target_claim(
    db: AsyncSession,
    claim: CacheTargetClaim,
    *,
    now: datetime | None = None,
) -> CacheTargetAck:
    """한 claim을 전부 local commit 가능한 상태로 만들고 ACK body를 반환한다.

    이 함수는 원격 ACK를 호출하지 않는다. 호출자는 이 transaction을 먼저 commit한 뒤
    ACK transport를 호출해야 한다.
    """
    current = now or datetime.now(UTC)
    consumer = await db.scalar(
        select(KtmCacheTargetConsumer)
        .where(KtmCacheTargetConsumer.consumer_id == claim.consumer_id)
        .with_for_update()
    )
    if consumer is None or consumer.external_system != claim.external_system:
        raise CacheTargetConsumerError("등록되지 않은 consumer claim입니다.")
    if consumer.active_restore_epoch is None:
        raise CacheTargetConsumerError("active restore epoch가 초기화되지 않았습니다.")
    if claim.lease_expires_at <= current:
        raise CacheTargetConsumerError("claim lease가 이미 만료되었습니다.")
    if any(event.restore_epoch != consumer.active_restore_epoch for event in claim.events):
        raise CacheTargetStaleEpochError("claim event가 active restore epoch와 다릅니다.")
    for previous, event in zip(claim.events, claim.events[1:], strict=False):
        if event.relay_order != previous.relay_order + 1:
            raise CacheTargetEventGapError("claim 내부 relay_order가 연속적이지 않습니다.")

    existing_claim = await db.get(KtmCacheTargetEventClaim, claim.claim_id)
    if existing_claim is not None:
        await _validate_existing_claim(db, claim=claim, existing=existing_claim)
        return _ack_for_claim(claim)

    expired_claims = list(
        await db.scalars(
            select(KtmCacheTargetEventClaim).where(
                KtmCacheTargetEventClaim.consumer_id == claim.consumer_id,
                KtmCacheTargetEventClaim.status == "active",
                KtmCacheTargetEventClaim.lease_expires_at <= current,
            )
        )
    )
    for expired_claim in expired_claims:
        expired_claim.status = "expired"
        expired_claim.completed_at = current

    last_applied_order = await db.scalar(
        select(func.max(KtmCacheTargetEvent.relay_order)).where(
            KtmCacheTargetEvent.external_system == claim.external_system,
            KtmCacheTargetEvent.restore_epoch == consumer.active_restore_epoch,
            KtmCacheTargetEvent.applied_at.is_not(None),
        )
    )
    last_order = int(last_applied_order or 0)
    new_event_count = 0
    target_event_count = 0
    stored_events: list[KtmCacheTargetEvent] = []

    for event_index, event in enumerate(claim.events):
        try:
            stored = await db.get(KtmCacheTargetEvent, event.event_id)
            if stored is not None:
                if _stored_event_material(stored) != _event_material(event):
                    raise CacheTargetEventConflictError(
                        "같은 event_id의 immutable material이 다릅니다."
                    )
                stored_events.append(stored)
                continue
            if last_order and event.relay_order != last_order + 1:
                raise CacheTargetEventGapError(
                    "local applied prefix 다음 relay_order가 누락되었습니다."
                )
            stored = KtmCacheTargetEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                external_system=event.external_system,
                target_key=event.target_key,
                target_id=event.target_id,
                restore_epoch=event.restore_epoch,
                source_generation=event.source_generation,
                target_sequence=event.target_sequence,
                relay_order=event.relay_order,
                source_payload_fingerprint=bytes.fromhex(event.source_payload_fingerprint),
                payload_fingerprint=bytes.fromhex(event.payload_fingerprint),
                occurred_at=event.occurred_at,
                payload=event.payload,
                applied_at=current,
            )
            db.add(stored)
            stored_events.append(stored)
            new_event_count += 1
            last_order = event.relay_order
            if event.event_scope == "target":
                await _apply_target_tuple(db, event=event)
                target_event_count += 1
            else:
                await _apply_stream_reconciled(
                    db,
                    consumer,
                    event=event,
                    resolved_at=current,
                )
        except CacheTargetEventApplyError:
            raise
        except CacheTargetConsumerError as exc:
            raise CacheTargetEventApplyError(
                event_index=event_index,
                event=event,
                cause=exc,
            ) from exc

    db.add(
        KtmCacheTargetEventClaim(
            claim_id=claim.claim_id,
            consumer_id=claim.consumer_id,
            lease_token=claim.lease_token,
            lease_expires_at=claim.lease_expires_at,
            status="active",
        )
    )
    await db.flush()
    for position, (event, stored) in enumerate(
        zip(claim.events, stored_events, strict=True), start=1
    ):
        db.add(
            KtmCacheTargetEventClaimItem(
                claim_id=claim.claim_id,
                event_id=stored.event_id,
                position=position,
                delivery_cursor=event.cursor,
                payload_fingerprint=bytes.fromhex(event.payload_fingerprint),
            )
        )
    if target_event_count:
        consumer.feature_cache_generation += 1
    if new_event_count:
        consumer.local_applied_cursor = claim.events[-1].cursor
    await db.flush()
    return _ack_for_claim(claim)


async def _apply_target_tuple(db: AsyncSession, *, event: CacheTargetEventRecord) -> None:
    if event.target_key is None or event.source_generation is None or event.target_sequence is None:
        raise CacheTargetEventConflictError("target event tuple이 없습니다.")
    head = await db.get(KtmCacheTargetHead, uuid.UUID(event.target_key))
    if head is None:
        return
    source_fingerprint = bytes.fromhex(event.source_payload_fingerprint)
    if event.source_generation > head.source_generation:
        raise CacheTargetEventConflictError(
            "Map source_generation이 PinVi desired head보다 큽니다."
        )
    if (
        event.source_generation == head.source_generation
        and source_fingerprint != head.source_payload_fingerprint
    ):
        raise CacheTargetEventConflictError("같은 source_generation의 fingerprint가 다릅니다.")
    current_tuple = (
        head.remote_restore_epoch or 0,
        head.remote_source_generation or 0,
        head.remote_target_sequence or 0,
    )
    incoming_tuple = (event.restore_epoch, event.source_generation, event.target_sequence)
    if incoming_tuple <= current_tuple:
        return
    head.remote_target_id = event.target_id
    head.remote_restore_epoch = event.restore_epoch
    head.remote_source_generation = event.source_generation
    head.remote_target_sequence = event.target_sequence
    status = event.payload.get("status")
    head.remote_status = str(status)[:32] if status is not None else event.event_type[:32]


async def _apply_stream_reconciled(
    db: AsyncSession,
    consumer: KtmCacheTargetConsumer,
    *,
    event: CacheTargetEventRecord,
    resolved_at: datetime,
) -> None:
    payload = event.payload
    required = {
        "actual_merkle_root",
        "expected_merkle_root",
        "request_id",
        "snapshot_id",
        "status",
        "version",
    }
    if set(payload) != required:
        raise CacheTargetEventConflictError("stream reconciled payload field가 다릅니다.")
    request_id_value = payload["request_id"]
    snapshot_id_value = payload["snapshot_id"]
    actual_merkle_root = payload["actual_merkle_root"]
    expected_merkle_root = payload["expected_merkle_root"]
    if (
        not isinstance(request_id_value, str)
        or not isinstance(snapshot_id_value, str)
        or not isinstance(actual_merkle_root, str)
        or not isinstance(expected_merkle_root, str)
        or payload["status"] != "succeeded"
        or payload["version"] != "cache-target-reconciliation-v1"
    ):
        raise CacheTargetEventConflictError("stream reconciled payload 타입이 다릅니다.")
    try:
        request_id = uuid.UUID(request_id_value)
        snapshot_id = uuid.UUID(snapshot_id_value)
        actual_root = bytes.fromhex(_validate_sha256_hex(actual_merkle_root))
        expected_root = bytes.fromhex(_validate_sha256_hex(expected_merkle_root))
    except ValueError as exc:
        raise CacheTargetEventConflictError(
            "stream reconciled request/snapshot/root가 canonical하지 않습니다."
        ) from exc
    if (
        str(request_id) != request_id_value
        or str(snapshot_id) != snapshot_id_value
        or actual_root != expected_root
        or expected_root != bytes.fromhex(event.source_payload_fingerprint)
    ):
        raise CacheTargetEventConflictError("stream reconciled receipt material이 서로 다릅니다.")
    expectation = await db.scalar(
        select(KtmCacheTargetReconciliationExpectation)
        .where(KtmCacheTargetReconciliationExpectation.request_id == request_id)
        .with_for_update()
    )
    if (
        expectation is None
        or expectation.status != "pending"
        or expectation.external_system != event.external_system
        or expectation.snapshot_id != snapshot_id
        or expectation.restore_epoch != event.restore_epoch
        or expectation.snapshot_merkle_root != expected_root
    ):
        raise CacheTargetEventConflictError(
            "stream reconciled receipt가 durable request-bound expectation과 다릅니다."
        )
    expectation.status = "received"
    expectation.receipt_event_id = event.event_id
    expectation.resolved_at = resolved_at
    consumer.reconcile_status = "matched"


def _ack_for_claim(claim: CacheTargetClaim) -> CacheTargetAck:
    return CacheTargetAck(
        consumer_id=claim.consumer_id,
        claim_id=claim.claim_id,
        lease_token=claim.lease_token,
        through_cursor=claim.events[-1].cursor,
        applied=[
            CacheTargetAppliedReceipt(
                event_id=event.event_id,
                payload_fingerprint=event.payload_fingerprint,
            )
            for event in claim.events
        ],
    )


async def load_pending_cache_target_ack(
    db: AsyncSession,
    *,
    consumer_id: str = "pinvi-cache-target-consumer",
    now: datetime | None = None,
) -> CacheTargetAck | None:
    """restart 뒤 아직 유효한 local-applied claim의 exact ACK receipt를 복원한다."""
    current = now or datetime.now(UTC)
    claims = list(
        await db.scalars(
            select(KtmCacheTargetEventClaim)
            .where(
                KtmCacheTargetEventClaim.consumer_id == consumer_id,
                KtmCacheTargetEventClaim.status == "active",
            )
            .order_by(KtmCacheTargetEventClaim.received_at, KtmCacheTargetEventClaim.claim_id)
            .with_for_update()
        )
    )
    for claim in claims:
        if claim.lease_expires_at <= current:
            claim.status = "expired"
            claim.completed_at = current
            continue
        items = list(
            await db.scalars(
                select(KtmCacheTargetEventClaimItem)
                .where(KtmCacheTargetEventClaimItem.claim_id == claim.claim_id)
                .order_by(KtmCacheTargetEventClaimItem.position)
            )
        )
        if not items or [item.position for item in items] != list(range(1, len(items) + 1)):
            raise CacheTargetEventGapError("durable claim receipt position이 연속적이지 않습니다.")
        events_by_id = {
            event.event_id: event
            for event in await db.scalars(
                select(KtmCacheTargetEvent).where(
                    KtmCacheTargetEvent.event_id.in_([item.event_id for item in items])
                )
            )
        }
        applied: list[CacheTargetAppliedReceipt] = []
        for item in items:
            event = events_by_id.get(item.event_id)
            if (
                event is None
                or event.applied_at is None
                or event.payload_fingerprint != item.payload_fingerprint
            ):
                raise CacheTargetEventConflictError(
                    "durable ACK receipt가 applied inbox와 일치하지 않습니다."
                )
            applied.append(
                CacheTargetAppliedReceipt(
                    event_id=event.event_id,
                    payload_fingerprint=item.payload_fingerprint.hex(),
                )
            )
        await db.flush()
        return CacheTargetAck(
            consumer_id=claim.consumer_id,
            claim_id=claim.claim_id,
            lease_token=claim.lease_token,
            through_cursor=items[-1].delivery_cursor,
            applied=applied,
        )
    await db.flush()
    return None


async def mark_cache_target_acknowledged(
    db: AsyncSession,
    ack: CacheTargetAck,
    *,
    now: datetime | None = None,
) -> None:
    """원격 ACK 성공 뒤 local remote cursor와 claim/item receipt를 CAS 완료한다."""
    current = now or datetime.now(UTC)
    claim = await db.scalar(
        select(KtmCacheTargetEventClaim)
        .where(KtmCacheTargetEventClaim.claim_id == ack.claim_id)
        .with_for_update()
    )
    if (
        claim is None
        or claim.consumer_id != ack.consumer_id
        or claim.lease_token != ack.lease_token
    ):
        raise CacheTargetEventConflictError(
            "ACK claim/lease identity가 durable receipt와 다릅니다."
        )
    if claim.status == "acked":
        if claim.acked_through_cursor != ack.through_cursor:
            raise CacheTargetEventConflictError("완료된 claim의 ACK cursor가 다릅니다.")
        return
    if claim.status != "active" or claim.lease_expires_at <= current:
        raise CacheTargetConsumerError("ACK할 active lease가 없습니다.")
    items = list(
        await db.scalars(
            select(KtmCacheTargetEventClaimItem)
            .where(KtmCacheTargetEventClaimItem.claim_id == ack.claim_id)
            .order_by(KtmCacheTargetEventClaimItem.position)
            .with_for_update()
        )
    )
    expected = [(item.event_id, item.payload_fingerprint.hex()) for item in items]
    actual = [(receipt.event_id, receipt.payload_fingerprint) for receipt in ack.applied]
    if not items or expected != actual or items[-1].delivery_cursor != ack.through_cursor:
        raise CacheTargetEventConflictError("ACK body가 durable applied receipt와 다릅니다.")
    for item in items:
        item.acked_at = current
    claim.status = "acked"
    claim.acked_through_cursor = ack.through_cursor
    claim.completed_at = current
    consumer = await db.scalar(
        select(KtmCacheTargetConsumer)
        .where(KtmCacheTargetConsumer.consumer_id == ack.consumer_id)
        .with_for_update()
    )
    if consumer is None:
        raise CacheTargetConsumerError("ACK consumer가 없습니다.")
    consumer.remote_acked_cursor = ack.through_cursor
    await db.flush()


async def reconcile_cache_target_snapshot(
    db: AsyncSession,
    snapshot: CacheTargetSnapshot,
    *,
    consumer_id: str = "pinvi-cache-target-consumer",
) -> bool:
    """remote fixed snapshot 자체 checksum과 PinVi desired head root를 함께 비교한다."""
    consumer = await db.scalar(
        select(KtmCacheTargetConsumer)
        .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
        .with_for_update()
    )
    if consumer is None:
        raise CacheTargetConsumerError("등록되지 않은 consumer snapshot입니다.")
    if snapshot.restore_epoch != consumer.active_restore_epoch:
        raise CacheTargetStaleEpochError("snapshot이 active restore epoch와 다릅니다.")

    remote_rows = [
        CacheTargetMerkleRow(
            external_system=item.external_system,
            target_key=item.target_key,
            state=item.state,
            source_generation=item.source_generation,
            source_payload_fingerprint=bytes.fromhex(item.source_payload_fingerprint),
        )
        for item in snapshot.items
    ]
    heads = list(
        await db.scalars(
            select(KtmCacheTargetHead).order_by(
                KtmCacheTargetHead.external_system,
                KtmCacheTargetHead.target_key,
            )
        )
    )
    local_rows = [
        CacheTargetMerkleRow(
            external_system=head.external_system,
            target_key=head.target_key,
            state=head.desired_state,  # type: ignore[arg-type]
            source_generation=head.source_generation,
            source_payload_fingerprint=head.source_payload_fingerprint,
        )
        for head in heads
    ]
    declared_root = bytes.fromhex(snapshot.merkle_root)
    matched = (
        snapshot.count == len(remote_rows)
        and snapshot.count == len(local_rows)
        and cache_target_snapshot_merkle_root(remote_rows) == declared_root
        and cache_target_snapshot_merkle_root(local_rows) == declared_root
    )
    consumer.snapshot_id = snapshot.snapshot_id
    consumer.snapshot_count = snapshot.count
    consumer.snapshot_merkle_root = declared_root
    consumer.high_watermark_cursor = snapshot.high_watermark_cursor
    consumer.reconcile_status = "matched" if matched else "mismatched"
    consumer.ready = matched
    if matched:
        consumer.feature_cache_generation += 1
    await db.flush()
    return matched
