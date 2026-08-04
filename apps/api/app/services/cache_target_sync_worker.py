"""cache target snapshot bootstrap과 command/claim/ACK-NACK lifespan worker."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import socket
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.clients.kor_travel_map_cache_target import (
    CacheTargetNetworkError,
    CacheTargetPreparingReconciliation,
    CacheTargetServiceClient,
    CacheTargetServiceProblem,
    CacheTargetStreamState,
)
from app.core.config import Settings, settings
from app.db import session as db_session
from app.models.cache_target_sync import (
    KtmCacheTargetConsumer,
    KtmCacheTargetHead,
    KtmCacheTargetReconciliationExpectation,
)
from app.services.cache_target_command_publisher import publish_cache_target_batch
from app.services.cache_target_event_consumer import (
    CacheTargetAck,
    CacheTargetClaim,
    CacheTargetConsumerError,
    CacheTargetEventApplyError,
    apply_cache_target_claim,
    load_pending_cache_target_ack,
    mark_cache_target_acknowledged,
    reconcile_cache_target_snapshot,
    record_cache_target_reconciliation_expectation,
)

logger = logging.getLogger(__name__)
_RECONCILIATION_COMPLETION_NAMESPACE = uuid.UUID("6dd91420-bdf2-4e50-896e-3a6509d55f3d")
_SNAPSHOT_TRAVERSAL_LOCK_NAMESPACE = 1_263_816_009
_SNAPSHOT_TRAVERSAL_LOCK_RESOURCE = 42


@asynccontextmanager
async def _snapshot_traversal_lock(engine: AsyncEngine) -> AsyncIterator[None]:
    """Pin DB 하나에서 process/event-loop 전체 snapshot traversal을 직렬화한다."""
    async with engine.connect() as connection:
        try:
            await connection.execute(
                text("SELECT pg_advisory_lock(:namespace, :resource)"),
                {
                    "namespace": _SNAPSHOT_TRAVERSAL_LOCK_NAMESPACE,
                    "resource": _SNAPSHOT_TRAVERSAL_LOCK_RESOURCE,
                },
            )
            await connection.commit()
            yield
        finally:
            # unlock query와 pool check-in 사이의 cancellation 창을 만들지 않는다.
            # 전용 physical DB session 자체를 닫으면 PostgreSQL이 session lock을
            # 정상·예외·취소 경로에서 동일하게 해제한다.
            invalidation = asyncio.create_task(connection.invalidate())
            try:
                await asyncio.shield(invalidation)
            except asyncio.CancelledError:
                await invalidation
                raise


def _claim_prefix(claim: CacheTargetClaim, *, event_count: int) -> CacheTargetClaim:
    if not 0 < event_count < len(claim.events):
        raise ValueError("claim prefix는 전체 claim보다 짧은 non-empty prefix여야 합니다.")
    events = claim.events[:event_count]
    material = claim.model_dump(mode="json")
    material["events"] = [event.model_dump(mode="json") for event in events]
    material["last_relay_order"] = events[-1].relay_order
    material["acked_through"] = None
    return CacheTargetClaim.model_validate(material)


async def _commit_claim_prefix(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    claim: CacheTargetClaim,
    event_count: int,
) -> CacheTargetAck:
    prefix = _claim_prefix(claim, event_count=event_count)
    async with session_factory() as db:
        ack = await apply_cache_target_claim(db, prefix)
        await db.commit()
    return ack


async def _block_cache_target_consumer(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_id: str,
) -> None:
    async with session_factory() as db:
        consumer = await db.scalar(
            select(KtmCacheTargetConsumer)
            .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
            .with_for_update()
        )
        if consumer is not None:
            consumer.ready = False
            consumer.reconcile_status = "blocked"
        await db.commit()


async def _adopt_stream_epoch(
    db: AsyncSession,
    *,
    stream: CacheTargetStreamState,
    consumer_id: str,
) -> KtmCacheTargetConsumer:
    consumer = await db.scalar(
        select(KtmCacheTargetConsumer)
        .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
        .with_for_update()
    )
    if consumer is None:
        consumer = KtmCacheTargetConsumer(
            consumer_id=consumer_id,
            external_system="pinvi",
            active_restore_epoch=stream.restore_epoch,
            stream_control_etag=stream.entity_tag,
            reconcile_status="checking",
            ready=False,
        )
        db.add(consumer)
        await db.flush()
        return consumer
    if consumer.active_restore_epoch != stream.restore_epoch:
        await db.execute(
            update(KtmCacheTargetReconciliationExpectation)
            .where(KtmCacheTargetReconciliationExpectation.status == "pending")
            .values(status="invalidated", resolved_at=func.now())
        )
        consumer.active_restore_epoch = stream.restore_epoch
        consumer.local_applied_cursor = None
        consumer.remote_acked_cursor = None
        consumer.high_watermark_cursor = None
        consumer.snapshot_id = None
        consumer.snapshot_count = None
        consumer.snapshot_merkle_root = None
        consumer.feature_cache_generation += 1
        await db.execute(
            update(KtmCacheTargetHead).values(
                remote_target_id=None,
                remote_etag=None,
                remote_restore_epoch=None,
                remote_source_generation=None,
                remote_target_sequence=None,
                remote_status=None,
            )
        )
    consumer.stream_control_etag = stream.entity_tag
    consumer.reconcile_status = "checking"
    consumer.ready = False
    await db.flush()
    return consumer


async def _bootstrap_cache_target_sync_locked(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_client: CacheTargetServiceClient,
    consumer_id: str,
    batch_size: int,
    lease_seconds: int,
    max_attempts: int,
) -> None:
    """remote stream/snapshot을 DB transaction 밖에서 읽고 atomic하게 채택한다."""
    stream = await consumer_client.get_stream()
    if stream.consumer_id is not None and stream.consumer_id != consumer_id:
        raise RuntimeError("Map stream principal consumer_id가 PinVi 설정과 다릅니다.")
    active = stream.active_reconciliation
    recovering_blocked_stream = stream.blocked_event_id is not None
    if recovering_blocked_stream and active is None:
        raise RuntimeError("Map cache target stream이 blocked 상태입니다.")
    if active is None:
        if stream.state not in {"active", "ready"}:
            raise RuntimeError("Map cache target stream이 ready 상태가 아닙니다.")
        snapshot = await consumer_client.get_snapshot()
    else:
        if isinstance(active, CacheTargetPreparingReconciliation):
            raise RuntimeError(
                "preparing reconciliation은 전용 initial-cutover runner가 seal해야 합니다."
            )
        expected_state = "blocked" if stream.blocked_event_id is not None else "fenced"
        if stream.state != expected_state:
            raise RuntimeError(f"active reconciliation stream이 {expected_state} 상태가 아닙니다.")
        snapshot = await consumer_client.get_reconciliation_snapshot(active.request_id)
        if (
            snapshot.snapshot_id != str(active.snapshot_id)
            or snapshot.restore_epoch != active.restore_epoch
            or snapshot.high_watermark_cursor != active.high_watermark_cursor
            or snapshot.count != active.count
            or snapshot.merkle_root != active.merkle_root
        ):
            raise RuntimeError("request-bound fixed snapshot이 stream descriptor와 다릅니다.")
    if snapshot.restore_epoch != stream.restore_epoch:
        raise RuntimeError("Map stream과 fixed snapshot restore epoch가 다릅니다.")
    resume_recovery_drain = False
    async with session_factory() as db:
        if active is None:
            consumer = await db.scalar(
                select(KtmCacheTargetConsumer)
                .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
                .with_for_update()
            )
            if (
                consumer is not None
                and not consumer.ready
                and consumer.active_restore_epoch == stream.restore_epoch
            ):
                pending_request_id = await db.scalar(
                    select(KtmCacheTargetReconciliationExpectation.request_id)
                    .where(
                        KtmCacheTargetReconciliationExpectation.external_system == "pinvi",
                        KtmCacheTargetReconciliationExpectation.restore_epoch
                        == stream.restore_epoch,
                        KtmCacheTargetReconciliationExpectation.status == "pending",
                    )
                    .limit(1)
                )
                if pending_request_id is not None:
                    if stream.state != "ready":
                        raise RuntimeError(
                            "unfinished reconciliation recovery의 Map stream이 ready 상태가 "
                            "아닙니다."
                        )
                    resume_recovery_drain = True
        await _adopt_stream_epoch(db, stream=stream, consumer_id=consumer_id)
        if active is not None:
            await record_cache_target_reconciliation_expectation(
                db,
                request_id=active.request_id,
                snapshot=snapshot,
            )
        matched = await reconcile_cache_target_snapshot(db, snapshot, consumer_id=consumer_id)
        if active is not None or resume_recovery_drain:
            consumer = await db.get(KtmCacheTargetConsumer, consumer_id)
            if consumer is None:
                raise RuntimeError("reconciliation consumer가 사라졌습니다.")
            consumer.ready = False
        if not matched:
            await db.commit()
            raise RuntimeError("PinVi/Map cache target fixed snapshot Merkle가 다릅니다.")
        await db.commit()
    if active is None and not resume_recovery_drain:
        return
    confirmed = stream
    if active is not None:
        completion = await consumer_client.complete_reconciliation(
            request_id=active.request_id,
            consumer_id=consumer_id,
            snapshot=snapshot,
            idempotency_key=uuid.uuid5(
                _RECONCILIATION_COMPLETION_NAMESPACE,
                str(active.request_id),
            ),
        )
        if completion.status != "succeeded":
            raise RuntimeError("Map reconciliation completion이 succeeded가 아닙니다.")
        confirmed = await consumer_client.get_stream()
        if (
            confirmed.consumer_id not in {None, consumer_id}
            or confirmed.restore_epoch != stream.restore_epoch
            or confirmed.state != "ready"
            or confirmed.blocked_event_id is not None
            or confirmed.active_reconciliation is not None
        ):
            raise RuntimeError("Map reconciliation completion 뒤 ready 전이가 확인되지 않았습니다.")
    if recovering_blocked_stream or resume_recovery_drain:
        while await consume_cache_target_once(
            session_factory,
            client=consumer_client,
            consumer_id=consumer_id,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            recovery_drain=True,
        ):
            pass
        confirmed = await consumer_client.get_stream()
        if (
            confirmed.consumer_id not in {None, consumer_id}
            or confirmed.restore_epoch != stream.restore_epoch
            or confirmed.state != "ready"
            or confirmed.blocked_event_id is not None
            or confirmed.active_reconciliation is not None
        ):
            raise RuntimeError("recovery replay drain 뒤 Map stream이 ready 상태가 아닙니다.")
    async with session_factory() as db:
        consumer = await db.scalar(
            select(KtmCacheTargetConsumer)
            .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
            .with_for_update()
        )
        pending_request_id = None
        if recovering_blocked_stream or resume_recovery_drain:
            pending_request_id = await db.scalar(
                select(KtmCacheTargetReconciliationExpectation.request_id)
                .where(
                    KtmCacheTargetReconciliationExpectation.external_system == "pinvi",
                    KtmCacheTargetReconciliationExpectation.restore_epoch == snapshot.restore_epoch,
                    KtmCacheTargetReconciliationExpectation.status == "pending",
                )
                .limit(1)
            )
        if pending_request_id is not None:
            raise RuntimeError(
                "recovery replay drain 뒤 reconciliation receipt가 미수신 상태입니다."
            )
        if (
            consumer is None
            or consumer.active_restore_epoch != snapshot.restore_epoch
            or consumer.snapshot_id != snapshot.snapshot_id
            or consumer.snapshot_merkle_root != bytes.fromhex(snapshot.merkle_root)
            or consumer.reconcile_status != "matched"
            or consumer.ready
        ):
            raise RuntimeError("completion 뒤 local snapshot identity가 바뀌었습니다.")
        consumer.stream_control_etag = confirmed.entity_tag
        consumer.ready = True
        await db.commit()


async def bootstrap_cache_target_sync(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_client: CacheTargetServiceClient,
    consumer_id: str,
    batch_size: int,
    lease_seconds: int,
    max_attempts: int,
) -> None:
    """Pin DB advisory lock 안에서 system snapshot bootstrap을 한 번씩 실행한다."""
    bind = session_factory.kw.get("bind")
    if not isinstance(bind, AsyncEngine):
        raise RuntimeError("cache target snapshot lock에 AsyncEngine bind가 필요합니다.")
    async with _snapshot_traversal_lock(bind):
        await _bootstrap_cache_target_sync_locked(
            session_factory,
            consumer_client=consumer_client,
            consumer_id=consumer_id,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )


def build_cache_target_nack(
    *,
    claim_id: uuid.UUID,
    lease_token: uuid.UUID,
    event_id: uuid.UUID,
    consumer_id: str,
    error: Exception,
    permanent: bool,
    max_attempts: int,
) -> dict[str, object]:
    error_class = type(error).__name__
    fingerprint = hashlib.sha256(error_class.encode("utf-8")).hexdigest()
    return {
        "external_system": "pinvi",
        "consumer_id": consumer_id,
        "claim_id": str(claim_id),
        "lease_token": str(lease_token),
        "event_id": str(event_id),
        "disposition": "permanent" if permanent else "transient",
        "error_class": error_class,
        "error_code": "PINVI_EVENT_INVARIANT" if permanent else "PINVI_APPLY_TRANSIENT",
        "error_fingerprint": fingerprint,
        "backoff_seconds": 30,
        "max_attempts": max_attempts,
    }


async def consume_cache_target_once(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    client: CacheTargetServiceClient,
    consumer_id: str,
    batch_size: int,
    lease_seconds: int,
    max_attempts: int,
    recovery_drain: bool = False,
) -> bool:
    """durable 재ACK를 우선하고 없으면 한 claim을 apply→ACK한다."""
    async with session_factory() as db:
        pending_ack = await load_pending_cache_target_ack(db, consumer_id=consumer_id)
        await db.commit()
    if pending_ack is not None:
        await client.ack_events(pending_ack)
        async with session_factory() as db:
            await mark_cache_target_acknowledged(db, pending_ack)
            await db.commit()
        return True

    async with session_factory() as db:
        consumer = await db.scalar(
            select(KtmCacheTargetConsumer).where(KtmCacheTargetConsumer.consumer_id == consumer_id)
        )
    if consumer is None or (
        not consumer.ready and not (recovery_drain and consumer.reconcile_status == "matched")
    ):
        return False

    claim = await client.claim_events(
        consumer_id=consumer_id,
        limit=batch_size,
        lease_seconds=lease_seconds,
        idempotency_key=uuid.uuid4(),
    )
    if claim is None:
        return False
    try:
        async with session_factory() as db:
            ack = await apply_cache_target_claim(db, claim)
            await db.commit()
    except CacheTargetEventApplyError as exc:
        if exc.event_index:
            prefix_ack = await _commit_claim_prefix(
                session_factory,
                claim=claim,
                event_count=exc.event_index,
            )
            await client.ack_events(prefix_ack)
            async with session_factory() as db:
                await mark_cache_target_acknowledged(db, prefix_ack)
                await db.commit()
        try:
            await client.nack_event(
                build_cache_target_nack(
                    claim_id=claim.claim_id,
                    lease_token=claim.lease_token,
                    event_id=exc.event.event_id,
                    consumer_id=consumer_id,
                    error=exc.cause,
                    permanent=True,
                    max_attempts=max_attempts,
                )
            )
        except CacheTargetServiceProblem as problem:
            if problem.status_code == 409 and problem.code == "dead_letter_requires_prefix_ack":
                await _block_cache_target_consumer(
                    session_factory,
                    consumer_id=consumer_id,
                )
            raise
        await _block_cache_target_consumer(session_factory, consumer_id=consumer_id)
        return True
    except CacheTargetConsumerError as exc:
        await client.nack_event(
            build_cache_target_nack(
                claim_id=claim.claim_id,
                lease_token=claim.lease_token,
                event_id=claim.events[0].event_id,
                consumer_id=consumer_id,
                error=exc,
                permanent=True,
                max_attempts=max_attempts,
            )
        )
        await _block_cache_target_consumer(session_factory, consumer_id=consumer_id)
        return True
    except DBAPIError as exc:
        await client.nack_event(
            build_cache_target_nack(
                claim_id=claim.claim_id,
                lease_token=claim.lease_token,
                event_id=claim.events[0].event_id,
                consumer_id=consumer_id,
                error=exc,
                permanent=False,
                max_attempts=max_attempts,
            )
        )
        if recovery_drain:
            await _block_cache_target_consumer(
                session_factory,
                consumer_id=consumer_id,
            )
            raise CacheTargetConsumerError(
                "blocked replay drain의 local DB apply가 실패했습니다."
            ) from exc
        return True
    await client.ack_events(ack)
    async with session_factory() as db:
        await mark_cache_target_acknowledged(db, ack)
        await db.commit()
    return True


async def _consumer_loop(
    client: CacheTargetServiceClient,
    config: Settings,
    *,
    session_factory: async_sessionmaker[AsyncSession] = db_session.async_session_factory,
) -> None:
    while True:
        try:
            worked = await consume_cache_target_once(
                session_factory,
                client=client,
                consumer_id=config.pinvi_kor_travel_map_cache_target_consumer_id,
                batch_size=config.pinvi_kor_travel_map_cache_target_batch_size,
                lease_seconds=config.pinvi_kor_travel_map_cache_target_lease_seconds,
                max_attempts=config.pinvi_kor_travel_map_cache_target_max_attempts,
            )
            if not worked:
                await asyncio.sleep(config.pinvi_kor_travel_map_cache_target_poll_seconds)
        except asyncio.CancelledError:
            raise
        except (CacheTargetNetworkError, CacheTargetServiceProblem):
            logger.warning("cache target consumer transport failure", exc_info=True)
            await asyncio.sleep(config.pinvi_kor_travel_map_cache_target_poll_seconds)
        except Exception:
            logger.exception("cache target consumer fatal failure")
            try:
                await _block_cache_target_consumer(
                    session_factory,
                    consumer_id=config.pinvi_kor_travel_map_cache_target_consumer_id,
                )
            except Exception:
                logger.exception("cache target consumer fail-closed state update failed")
            await asyncio.sleep(config.pinvi_kor_travel_map_cache_target_poll_seconds)


async def _command_loop(client: CacheTargetServiceClient, config: Settings) -> None:
    owner = f"{socket.gethostname()}:{uuid.uuid4()}"
    while True:
        try:
            result = await publish_cache_target_batch(
                db_session.async_session_factory,
                client=client,
                lease_owner=owner,
                consumer_id=config.pinvi_kor_travel_map_cache_target_consumer_id,
                limit=config.pinvi_kor_travel_map_cache_target_batch_size,
                lease_seconds=config.pinvi_kor_travel_map_cache_target_lease_seconds,
                max_attempts=config.pinvi_kor_travel_map_cache_target_max_attempts,
            )
            if result.halted:
                raise RuntimeError("cache target command publisher가 fail-closed halt했습니다.")
            if result.claimed < config.pinvi_kor_travel_map_cache_target_batch_size:
                await asyncio.sleep(config.pinvi_kor_travel_map_cache_target_poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("cache target command publisher failure", exc_info=True)
            await asyncio.sleep(config.pinvi_kor_travel_map_cache_target_poll_seconds)


@asynccontextmanager
async def cache_target_sync_worker_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """default-off paired worker. enable 실패는 startup 자체를 실패시킨다."""
    del app
    if not settings.pinvi_kor_travel_map_cache_target_sync_enabled:
        yield
        return
    command_secret = settings.pinvi_kor_travel_map_cache_target_command_token
    consumer_secret = settings.pinvi_kor_travel_map_cache_target_consumer_token
    if command_secret is None or consumer_secret is None:
        raise RuntimeError("cache target runtime principal이 없습니다.")
    command_client = CacheTargetServiceClient(
        httpx.AsyncClient(
            base_url=settings.pinvi_kor_travel_map_api_base_url,
            timeout=settings.pinvi_kor_travel_map_timeout_seconds,
        ),
        role="command",
        token=command_secret.get_secret_value(),
    )
    consumer_client = CacheTargetServiceClient(
        httpx.AsyncClient(
            base_url=settings.pinvi_kor_travel_map_api_base_url,
            timeout=settings.pinvi_kor_travel_map_timeout_seconds,
        ),
        role="consumer",
        token=consumer_secret.get_secret_value(),
    )
    tasks: list[asyncio.Task[None]] = []
    try:
        await bootstrap_cache_target_sync(
            db_session.async_session_factory,
            consumer_client=consumer_client,
            consumer_id=settings.pinvi_kor_travel_map_cache_target_consumer_id,
            batch_size=settings.pinvi_kor_travel_map_cache_target_batch_size,
            lease_seconds=settings.pinvi_kor_travel_map_cache_target_lease_seconds,
            max_attempts=settings.pinvi_kor_travel_map_cache_target_max_attempts,
        )
        tasks = [
            asyncio.create_task(_command_loop(command_client, settings)),
            asyncio.create_task(
                _consumer_loop(
                    consumer_client,
                    settings,
                    session_factory=db_session.async_session_factory,
                )
            ),
        ]
        yield
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            with suppress(TimeoutError):
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
        await command_client.aclose()
        await consumer_client.aclose()
