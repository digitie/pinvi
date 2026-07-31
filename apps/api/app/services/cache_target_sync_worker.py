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
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.kor_travel_map_cache_target import (
    CacheTargetNetworkError,
    CacheTargetServiceClient,
    CacheTargetServiceProblem,
    CacheTargetStreamState,
)
from app.core.config import Settings, settings
from app.db import session as db_session
from app.models.cache_target_sync import KtmCacheTargetConsumer, KtmCacheTargetHead
from app.services.cache_target_command_publisher import publish_cache_target_batch
from app.services.cache_target_event_consumer import (
    CacheTargetConsumerError,
    apply_cache_target_claim,
    load_pending_cache_target_ack,
    mark_cache_target_acknowledged,
    reconcile_cache_target_snapshot,
)

logger = logging.getLogger(__name__)


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


async def bootstrap_cache_target_sync(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_client: CacheTargetServiceClient,
    consumer_id: str,
) -> None:
    """remote stream/snapshot을 DB transaction 밖에서 읽고 atomic하게 채택한다."""
    stream = await consumer_client.get_stream()
    if stream.consumer_id is not None and stream.consumer_id != consumer_id:
        raise RuntimeError("Map stream principal consumer_id가 PinVi 설정과 다릅니다.")
    if stream.state != "active" or stream.blocked_event_id is not None:
        raise RuntimeError("Map cache target stream이 active/unblocked 상태가 아닙니다.")
    snapshot = await consumer_client.get_snapshot()
    if snapshot.restore_epoch != stream.restore_epoch:
        raise RuntimeError("Map stream과 fixed snapshot restore epoch가 다릅니다.")
    async with session_factory() as db:
        await _adopt_stream_epoch(db, stream=stream, consumer_id=consumer_id)
        matched = await reconcile_cache_target_snapshot(
            db, snapshot, consumer_id=consumer_id
        )
        if not matched:
            await db.commit()
            raise RuntimeError("PinVi/Map cache target fixed snapshot Merkle가 다릅니다.")
        await db.commit()


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
        consumer_ready = await db.scalar(
            select(KtmCacheTargetConsumer.ready).where(
                KtmCacheTargetConsumer.consumer_id == consumer_id
            )
        )
    if consumer_ready is not True:
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
        return True
    await client.ack_events(ack)
    async with session_factory() as db:
        await mark_cache_target_acknowledged(db, ack)
        await db.commit()
    return True


async def _consumer_loop(client: CacheTargetServiceClient, config: Settings) -> None:
    while True:
        try:
            worked = await consume_cache_target_once(
                db_session.async_session_factory,
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
        )
        tasks = [
            asyncio.create_task(_command_loop(command_client, settings)),
            asyncio.create_task(_consumer_loop(consumer_client, settings)),
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
