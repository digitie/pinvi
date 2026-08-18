"""ordinary cache-target writer를 열기 전에 restore epoch fence를 전진시킨다."""

from __future__ import annotations

import argparse
import asyncio
import json
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
from app.services.cache_target_restore_fence import run_cache_target_restore_fence


async def _run(args: argparse.Namespace) -> dict[str, int | str]:
    if settings.pinvi_kor_travel_map_cache_target_sync_enabled:
        raise RuntimeError(
            "ordinary cache-target worker를 끈 상태에서만 restore fence를 실행할 수 있습니다."
        )
    if (
        settings.pinvi_kor_travel_map_cache_target_expected_openapi_sha256
        != KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256
        or settings.pinvi_kor_travel_map_cache_target_expected_source_revision
        != KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
        or settings.pinvi_kor_travel_map_cache_target_expected_contract_generation
        != KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION
    ):
        raise RuntimeError("restore fence service contract pin이 vendored artifact와 다릅니다.")
    consumer = settings.pinvi_kor_travel_map_cache_target_consumer_token
    restore = settings.pinvi_kor_travel_map_cache_target_restore_fence_token
    if consumer is None or restore is None:
        raise RuntimeError("전용 runner에 consumer/restore-fence principal을 모두 주입해야 합니다.")

    base_url = settings.pinvi_kor_travel_map_api_base_url
    timeout = settings.pinvi_kor_travel_map_timeout_seconds
    consumer_client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url=base_url, timeout=timeout),
        role="consumer",
        token=consumer.get_secret_value(),
    )
    restore_client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url=base_url, timeout=timeout),
        role="restore",
        token=restore.get_secret_value(),
    )
    try:
        result = await run_cache_target_restore_fence(
            session_factory=db_session.async_session_factory,
            consumer_client=consumer_client,
            restore_client=restore_client,
            consumer_id=settings.pinvi_kor_travel_map_cache_target_consumer_id,
            expected_restore_epoch=args.expected_restore_epoch,
            idempotency_key=args.idempotency_key,
            reason=args.reason,
        )
    finally:
        await consumer_client.aclose()
        await restore_client.aclose()
        await db_session.engine.dispose()
    return {
        "control_version": result.receipt.data.control_version,
        "fence_id": str(result.receipt.data.fence_id),
        "restore_epoch": result.receipt.data.restore_epoch,
        "status_code": result.receipt.status_code,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-restore-epoch", type=int, required=True)
    parser.add_argument("--idempotency-key", type=uuid.UUID, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if args.expected_restore_epoch <= 0:
        parser.error("--expected-restore-epoch must be positive")
    if not args.reason or args.reason != args.reason.strip() or len(args.reason) > 1000:
        parser.error("--reason must be trimmed 1..1000 characters")
    print(json.dumps(asyncio.run(_run(args)), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
