"""cache-target 최초 backfill을 ordinary API lifespan 밖에서 실행·재개한다."""

from __future__ import annotations

import argparse
import asyncio
import uuid

import httpx

from app.clients.kor_travel_map_cache_target import CacheTargetServiceClient
from app.core.config import (
    KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
    settings,
)
from app.db import session as db_session
from app.services.cache_target_initial_cutover import run_initial_cache_target_cutover


async def _run(args: argparse.Namespace) -> None:
    if settings.pinvi_kor_travel_map_cache_target_sync_enabled:
        raise RuntimeError(
            "ordinary cache-target worker를 끈 상태에서만 initial cutover를 실행할 수 있습니다."
        )
    if (
        settings.pinvi_kor_travel_map_cache_target_expected_openapi_sha256
        != KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256
        or settings.pinvi_kor_travel_map_cache_target_expected_source_revision
        != KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
        or settings.pinvi_kor_travel_map_cache_target_expected_contract_generation
        != KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION
    ):
        raise RuntimeError("initial cutover service contract pin이 vendored artifact와 다릅니다.")
    command = settings.pinvi_kor_travel_map_cache_target_command_token
    consumer = settings.pinvi_kor_travel_map_cache_target_consumer_token
    recovery = settings.pinvi_kor_travel_map_cache_target_recovery_token
    if command is None or consumer is None or recovery is None:
        raise RuntimeError(
            "전용 runner에 command/consumer/recovery principal을 모두 주입해야 합니다."
        )
    base_url = settings.pinvi_kor_travel_map_api_base_url
    timeout = settings.pinvi_kor_travel_map_timeout_seconds
    command_client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url=base_url, timeout=timeout),
        role="command",
        token=command.get_secret_value(),
    )
    consumer_client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url=base_url, timeout=timeout),
        role="consumer",
        token=consumer.get_secret_value(),
    )
    recovery_client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url=base_url, timeout=timeout),
        role="recovery",
        token=recovery.get_secret_value(),
    )
    try:
        result = await run_initial_cache_target_cutover(
            db_session.async_session_factory,
            db_session.engine,
            command_client=command_client,
            consumer_client=consumer_client,
            recovery_client=recovery_client,
            consumer_id=settings.pinvi_kor_travel_map_cache_target_consumer_id,
            cutover_id=args.cutover_id,
            expected_restore_epoch=args.expected_restore_epoch,
            reason=args.reason,
            batch_size=settings.pinvi_kor_travel_map_cache_target_batch_size,
            lease_seconds=settings.pinvi_kor_travel_map_cache_target_lease_seconds,
            max_attempts=settings.pinvi_kor_travel_map_cache_target_max_attempts,
        )
    finally:
        await command_client.aclose()
        await consumer_client.aclose()
        await recovery_client.aclose()
        await db_session.engine.dispose()
    print(
        "initial cutover complete "
        f"cutover_id={result.cutover_id} request_id={result.reconciliation_request_id} "
        f"count={result.source.count} merkle_root={result.source.merkle_root} "
        f"published={result.published}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutover-id", type=uuid.UUID, required=True)
    parser.add_argument("--expected-restore-epoch", type=int, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if args.expected_restore_epoch <= 0:
        parser.error("--expected-restore-epoch must be positive")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
