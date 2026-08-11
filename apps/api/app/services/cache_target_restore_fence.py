"""restore 전용 principal이 writer 재개 전 Map stream epoch를 봉인한다."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.clients.kor_travel_map_cache_target import (
    CacheTargetContractError,
    CacheTargetRestoreFenceResult,
    CacheTargetServiceClient,
)


@dataclass(frozen=True, slots=True)
class CacheTargetRestoreFenceRunResult:
    """원격 restore receipt와 재조회한 stream tuple."""

    receipt: CacheTargetRestoreFenceResult


async def run_cache_target_restore_fence(
    *,
    consumer_client: CacheTargetServiceClient,
    restore_client: CacheTargetServiceClient,
    consumer_id: str,
    expected_restore_epoch: int,
    idempotency_key: uuid.UUID,
    reason: str,
) -> CacheTargetRestoreFenceRunResult:
    """GET의 raw ETag를 CAS에 쓰고 새 fenced stream을 다시 읽어 결박한다.

    이 함수는 ordinary writer를 시작하지 않는다. 호출자는 별도 배포 단계에서만
    새 epoch의 reconciliation/cutover를 완료한 뒤 sync worker를 열어야 한다.
    """
    before = await consumer_client.get_stream()
    if before.consumer_id not in {None, consumer_id}:
        raise CacheTargetContractError("restore 전 Map stream consumer binding이 다릅니다.")
    if before.restore_epoch != expected_restore_epoch:
        raise CacheTargetContractError("restore 전 Map stream epoch이 expected 값과 다릅니다.")

    receipt = await restore_client.advance_restore_fence(
        consumer_id=consumer_id,
        expected_restore_epoch=expected_restore_epoch,
        reason=reason,
        idempotency_key=idempotency_key,
        stream_etag=before.entity_tag,
    )
    after = await consumer_client.get_stream()
    if (
        after.consumer_id not in {None, consumer_id}
        or after.restore_epoch != receipt.data.restore_epoch
        or after.control_version != receipt.data.control_version
        or after.entity_tag != receipt.etag
        or after.state != "fenced"
        or after.blocked_event_id is not None
        or after.active_reconciliation is not None
    ):
        raise CacheTargetContractError("restore fence 뒤 Map stream tuple이 receipt와 다릅니다.")
    return CacheTargetRestoreFenceRunResult(receipt=receipt)
