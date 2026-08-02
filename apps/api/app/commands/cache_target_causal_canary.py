"""running ordinary API container에서 cache-target causal canary를 실행한다."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import uuid
from collections.abc import Sequence
from typing import Never

import httpx

from app.clients.kor_travel_map_cache_target import CacheTargetServiceClient
from app.core.config import (
    CACHE_TARGET_SERVICE_CONTRACT_GENERATION,
    CACHE_TARGET_SERVICE_FUNCTIONAL_OWNER_REVISION,
    CACHE_TARGET_SERVICE_OPENAPI_SHA256,
    settings,
)
from app.db import session as db_session
from app.services.cache_target_causal_canary import (
    CacheTargetCanaryFailure,
    run_cache_target_causal_canary,
)


async def _run(args: argparse.Namespace) -> dict[str, int | str]:
    if not settings.pinvi_kor_travel_map_cache_target_sync_enabled:
        raise CacheTargetCanaryFailure("cache_target_sync_disabled", "startup")
    if (
        settings.pinvi_kor_travel_map_cache_target_expected_openapi_sha256
        != CACHE_TARGET_SERVICE_OPENAPI_SHA256
        or settings.pinvi_kor_travel_map_cache_target_expected_source_revision
        != CACHE_TARGET_SERVICE_FUNCTIONAL_OWNER_REVISION
        or settings.pinvi_kor_travel_map_cache_target_expected_contract_generation
        != CACHE_TARGET_SERVICE_CONTRACT_GENERATION
    ):
        raise CacheTargetCanaryFailure("service_contract_pin_mismatch", "startup")
    command = settings.pinvi_kor_travel_map_cache_target_command_token
    consumer = settings.pinvi_kor_travel_map_cache_target_consumer_token
    if command is None or consumer is None:
        raise CacheTargetCanaryFailure("ordinary_credentials_missing", "startup")
    # command token은 ordinary background worker만 사용한다. 존재 여부만 확인하고
    # canary process에서는 recovery/restore credential과 함께 읽거나 전달하지 않는다.
    command.get_secret_value()
    if (
        not math.isfinite(settings.pinvi_kor_travel_map_timeout_seconds)
        or settings.pinvi_kor_travel_map_timeout_seconds <= 0
    ):
        raise CacheTargetCanaryFailure("invalid_timeout_config", "startup")
    client = CacheTargetServiceClient(
        httpx.AsyncClient(
            base_url=settings.pinvi_kor_travel_map_api_base_url,
            timeout=settings.pinvi_kor_travel_map_timeout_seconds,
        ),
        role="consumer",
        token=consumer.get_secret_value(),
    )
    try:
        receipt = await run_cache_target_causal_canary(
            db_session.async_session_factory,
            db_session.engine,
            consumer_client=client,
            consumer_id=settings.pinvi_kor_travel_map_cache_target_consumer_id,
            run_id=args.run_id,
            timeout_seconds=args.timeout_seconds,
        )
        return receipt.json_object()
    finally:
        await client.aclose()
        await db_session.engine.dispose()


class _SecretFreeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        print('{"error_code":"invalid_arguments","phase":"startup"}', file=sys.stderr)
        raise SystemExit(2)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _SecretFreeArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=uuid.UUID, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("invalid timeout")
    return args


def main() -> None:
    args = _parse_args()
    try:
        receipt = asyncio.run(_run(args))
    except CacheTargetCanaryFailure as exc:
        print(
            json.dumps(
                {"error_code": exc.code, "phase": exc.phase},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except Exception:
        print(
            '{"error_code":"internal_error","phase":"runtime"}',
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
