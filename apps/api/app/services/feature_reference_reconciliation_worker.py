"""T-VN-M05 default-off Map Feature 참조 조정 paired worker."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Literal

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.kor_travel_map_feature_reference_reconciliation import (
    FeatureReferenceReconciliationLeaseConflict,
    FeatureReferenceReconciliationProblem,
    FeatureReferenceReconciliationServiceClient,
    FeatureReferenceReconciliationUnavailable,
)
from app.core.config import Settings, settings
from app.db import session as db_session
from app.middleware.api_call_logging import api_call_event_hooks
from app.services.feature_reference_reconciliation import (
    ReconciliationApplied,
    ReconciliationBlocked,
    apply_feature_reference_reconciliation_event,
)

logger = logging.getLogger(__name__)
_ACK_NAMESPACE = uuid.UUID("7242d291-579a-4b96-b035-64aa4d26b1cb")


async def consume_feature_reference_reconciliation_once(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    read_client: FeatureReferenceReconciliationServiceClient,
    ack_client: FeatureReferenceReconciliationServiceClient,
    worker_id: uuid.UUID,
) -> ReconciliationBlocked | ReconciliationApplied | None:
    """lease→local transaction→commit→ACK 한 단위를 수행한다.

    local transaction이 실패하거나 blocked이면 ACK은 호출하지 않는다. ACK 전의 process crash는
    final receipt가 남으므로 다음 lease가 같은 SHA로 재-ACK한다.
    """

    lease = await read_client.lease(worker_id=worker_id)
    if lease is None:
        return None
    async with session_factory() as db:
        local = await apply_feature_reference_reconciliation_event(db, lease)
        await db.commit()
    if isinstance(local, ReconciliationBlocked):
        return local
    await ack_client.acknowledge(
        event_id=lease.event.event_id,
        worker_id=worker_id,
        lease_epoch=lease.lease_epoch,
        event_sha256=lease.event_sha256,
        local_receipt_sha256=local.local_receipt_sha256,
        idempotency_key=uuid.uuid5(_ACK_NAMESPACE, str(lease.event.event_id)),
    )
    return local


async def _worker_loop(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    read_client: FeatureReferenceReconciliationServiceClient,
    ack_client: FeatureReferenceReconciliationServiceClient,
    worker_id: uuid.UUID,
    config: Settings,
) -> None:
    while True:
        try:
            result = await consume_feature_reference_reconciliation_once(
                session_factory,
                read_client=read_client,
                ack_client=ack_client,
                worker_id=worker_id,
            )
            if result is None:
                await asyncio.sleep(
                    config.pinvi_kor_travel_map_feature_reference_reconciliation_poll_seconds
                )
            elif isinstance(result, ReconciliationBlocked):
                # 동일 관측을 매 poll마다 append 하지 않는다. 운영자가 block 원인을 해소한 뒤
                # 다음 recheck에서 새 observation attempt를 남긴다.
                await asyncio.sleep(
                    config.pinvi_kor_travel_map_feature_reference_reconciliation_blocked_recheck_seconds
                )
        except asyncio.CancelledError:
            raise
        except FeatureReferenceReconciliationLeaseConflict:
            await asyncio.sleep(
                config.pinvi_kor_travel_map_feature_reference_reconciliation_poll_seconds
            )
        except FeatureReferenceReconciliationUnavailable:
            logger.warning("feature reference reconciliation transport failure", exc_info=True)
            await asyncio.sleep(
                config.pinvi_kor_travel_map_feature_reference_reconciliation_poll_seconds
            )
        except FeatureReferenceReconciliationProblem:
            logger.error("feature reference reconciliation service problem", exc_info=True)
            await asyncio.sleep(
                config.pinvi_kor_travel_map_feature_reference_reconciliation_poll_seconds
            )
        except Exception:
            logger.exception("feature reference reconciliation local projection failure")
            await asyncio.sleep(
                config.pinvi_kor_travel_map_feature_reference_reconciliation_poll_seconds
            )


def _client(
    *,
    role: Literal["read", "ack"],
    token: str,
    config: Settings,
) -> FeatureReferenceReconciliationServiceClient:
    return FeatureReferenceReconciliationServiceClient(
        httpx.AsyncClient(
            base_url=config.pinvi_kor_travel_map_api_base_url,
            timeout=config.pinvi_kor_travel_map_timeout_seconds,
            event_hooks=api_call_event_hooks(
                db_session.async_session_factory,
                provider=f"kor_travel_map_feature_reference_reconciliation_{role}",
            ),
        ),
        role=role,
        token=token,
    )


@asynccontextmanager
async def feature_reference_reconciliation_worker_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """default-off. subscription/readiness boundary가 없으면 API startup을 fail-close한다."""

    del app
    if not settings.pinvi_kor_travel_map_feature_reference_reconciliation_enabled:
        yield
        return
    read_secret = settings.pinvi_kor_travel_map_feature_reference_reconciliation_read_token
    ack_secret = settings.pinvi_kor_travel_map_feature_reference_reconciliation_ack_token
    if read_secret is None or ack_secret is None:
        raise RuntimeError("M05 reconciliation runtime principal이 없습니다.")
    read_client = _client(role="read", token=read_secret.get_secret_value(), config=settings)
    ack_client = _client(role="ack", token=ack_secret.get_secret_value(), config=settings)
    worker_id = uuid.uuid4()
    task: asyncio.Task[None] | None = None
    try:
        # subscription이 없을 때 Map은 503을 반환한다. background retry로 숨기지 않고
        # startup 자체를 실패시켜 pairing activation receipt 이전 오배선을 드러낸다.
        try:
            await consume_feature_reference_reconciliation_once(
                db_session.async_session_factory,
                read_client=read_client,
                ack_client=ack_client,
                worker_id=worker_id,
            )
        except FeatureReferenceReconciliationProblem as exc:
            raise RuntimeError(
                "M05 reconciliation Map subscription/readiness preflight가 실패했습니다."
            ) from exc
        task = asyncio.create_task(
            _worker_loop(
                session_factory=db_session.async_session_factory,
                read_client=read_client,
                ack_client=ack_client,
                worker_id=worker_id,
                config=settings,
            )
        )
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(TimeoutError):
                await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=5)
        await read_client.aclose()
        await ack_client.aclose()
