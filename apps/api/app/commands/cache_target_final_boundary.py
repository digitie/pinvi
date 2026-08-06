"""cache-target production boundary를 strict receipt로 검증한다."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from typing import Literal, Never, cast

from app.core.config import (
    KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
    settings,
)
from app.db import session as db_session
from app.services.cache_target_final_boundary import (
    BoundaryJson,
    CacheTargetBoundaryFailure,
    CacheTargetBoundaryRequest,
    run_cache_target_boundary_finalize,
    run_cache_target_boundary_preflight,
)

_MAX_REQUEST_BYTES = 16_384
BoundaryOperation = Literal["preflight", "finalize"]


class _SecretFreeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        print('{"error_code":"invalid_arguments","phase":"startup"}', file=sys.stderr)
        raise SystemExit(2)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _SecretFreeArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("preflight", "finalize"))
    return parser.parse_args(argv)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_request(operation: BoundaryOperation) -> CacheTargetBoundaryRequest:
    raw = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
    if len(raw) > _MAX_REQUEST_BYTES or not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise CacheTargetBoundaryFailure("invalid_request", operation)
    try:
        decoded = raw[:-1].decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_reject_duplicate_keys)
        request = CacheTargetBoundaryRequest.parse(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CacheTargetBoundaryFailure(
            "invalid_request",
            operation,
        ) from exc
    if request.operation != operation:
        raise CacheTargetBoundaryFailure("operation_mismatch", request.operation)
    return request


def _runtime_source_revision(operation: BoundaryOperation) -> str:
    revision = os.environ.get("PINVI_SOURCE_REVISION", "")
    if len(revision) != 40 or revision.lower() != revision:
        raise CacheTargetBoundaryFailure(
            "runtime_source_revision_missing",
            operation,
        )
    try:
        int(revision, 16)
    except ValueError as exc:
        raise CacheTargetBoundaryFailure(
            "runtime_source_revision_missing",
            operation,
        ) from exc
    return revision


async def _run(
    args: argparse.Namespace,
    request: CacheTargetBoundaryRequest,
) -> BoundaryJson:
    operation = cast(BoundaryOperation, args.operation)
    source_revision = _runtime_source_revision(operation)
    try:
        if operation == "preflight":
            return await run_cache_target_boundary_preflight(
                db_session.async_session_factory,
                request=request,
                runtime_source_revision=source_revision,
            )
        if (
            settings.pinvi_kor_travel_map_cache_target_expected_openapi_sha256
            != KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256
            or settings.pinvi_kor_travel_map_cache_target_expected_source_revision
            != KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
            or settings.pinvi_kor_travel_map_cache_target_expected_contract_generation
            != KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION
        ):
            raise CacheTargetBoundaryFailure("service_contract_pin_mismatch", "finalize")
        return await run_cache_target_boundary_finalize(
            db_session.async_session_factory,
            request=request,
            runtime_source_revision=source_revision,
            consumer_id=settings.pinvi_kor_travel_map_cache_target_consumer_id,
        )
    finally:
        await db_session.engine.dispose()


def main() -> None:
    args = _parse_args()
    try:
        request = _read_request(cast(BoundaryOperation, args.operation))
        receipt = asyncio.run(_run(args, request))
    except CacheTargetBoundaryFailure as exc:
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
        print('{"error_code":"internal_error","phase":"runtime"}', file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
