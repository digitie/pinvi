"""Map T-VN-40C identity mapping export를 PinVi의 유일한 local evidence로 봉인한다."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map_curation import (
    CurationCutoverIdentityMapping,
    CurationCutoverMappingSet,
)
from app.core.config import KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
from app.models.curated_plan import (
    KtmCurationCutoverMappingReceipt,
    KtmCurationCutoverMappingReceiptItem,
)

_MAPPING_ROOT_VERSION = "ktm-curation-cutover-mapping-v1"
_MAPPING_LOCK_NAMESPACE = "KTMC"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_MAPPING_KINDS = frozenset({"legacy_projection", "official_membership", "manual_membership"})


class CurationCutoverMappingReceiptConflict(Exception):
    """Map release와 local sealed mapping evidence가 하나로 수렴하지 않는다."""

    code = "CURATION_CUTOVER_MAPPING_RECEIPT_CONFLICT"


@dataclass(frozen=True, slots=True)
class CurationCutoverMappingReceiptResult:
    receipt: KtmCurationCutoverMappingReceipt
    replayed: bool


def _validate_mapping_set(mapping_set: CurationCutoverMappingSet) -> None:
    if mapping_set.mapping_root_version != _MAPPING_ROOT_VERSION:
        raise CurationCutoverMappingReceiptConflict("Map mapping root version이 지원되지 않습니다.")
    if (
        mapping_set.mapping_count < 0
        or len(mapping_set.mappings) != mapping_set.mapping_count
        or _HEX64_RE.fullmatch(mapping_set.mapping_root) is None
    ):
        raise CurationCutoverMappingReceiptConflict(
            "Map mapping root/count envelope이 유효하지 않습니다."
        )

    seen_legacy_ids: set[uuid.UUID] = set()
    seen_item_ids: set[uuid.UUID] = set()
    previous_legacy_id: uuid.UUID | None = None
    for mapping in mapping_set.mappings:
        if mapping.mapping_kind not in _MAPPING_KINDS:
            raise CurationCutoverMappingReceiptConflict("Map mapping kind가 지원되지 않습니다.")
        if _HEX64_RE.fullmatch(mapping.source_row_hash) is None:
            raise CurationCutoverMappingReceiptConflict(
                "Map mapping source row hash가 유효하지 않습니다."
            )
        if mapping.legacy_curated_feature_id in seen_legacy_ids:
            raise CurationCutoverMappingReceiptConflict("Map legacy identity가 중복됐습니다.")
        if mapping.curation_item_id in seen_item_ids:
            raise CurationCutoverMappingReceiptConflict(
                "Map canonical item identity가 중복됐습니다."
            )
        if (
            previous_legacy_id is not None
            and mapping.legacy_curated_feature_id.bytes <= previous_legacy_id.bytes
        ):
            raise CurationCutoverMappingReceiptConflict(
                "Map mapping keyset 순서가 전진하지 않습니다."
            )
        seen_legacy_ids.add(mapping.legacy_curated_feature_id)
        seen_item_ids.add(mapping.curation_item_id)
        previous_legacy_id = mapping.legacy_curated_feature_id


def _mapping_tuple(
    mapping: CurationCutoverIdentityMapping | KtmCurationCutoverMappingReceiptItem,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str, str]:
    return (
        mapping.legacy_curated_feature_id,
        mapping.collection_id,
        mapping.curation_item_id,
        mapping.mapping_kind,
        mapping.source_row_hash,
    )


async def _lock_release_scope(db: AsyncSession) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {
            "identity": f"{_MAPPING_LOCK_NAMESPACE}:release:{KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION}"
        },
    )


async def seal_curation_cutover_mapping_receipt(
    db: AsyncSession,
    *,
    actor_admin_id: uuid.UUID,
    mapping_set: CurationCutoverMappingSet,
) -> CurationCutoverMappingReceiptResult:
    """하나의 vendored Map release에서 단 하나의 complete mapping root만 봉인한다.

    호출자는 ``SERIALIZABLE`` transaction과 admin audit를 소유한다. advisory lock은 같은
    release의 동시 fetch가 서로 다른 receipt를 만들지 못하게 하고, DB unique constraint는
    process 밖 writer에도 단일 release evidence를 강제한다.
    """

    _validate_mapping_set(mapping_set)
    await _lock_release_scope(db)
    existing = await db.scalar(
        select(KtmCurationCutoverMappingReceipt)
        .where(
            KtmCurationCutoverMappingReceipt.map_release_revision
            == KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
        )
        .with_for_update()
    )
    if existing is not None:
        if (
            existing.status != "completed"
            or existing.mapping_root_version != mapping_set.mapping_root_version
            or existing.mapping_root != mapping_set.mapping_root
            or existing.mapping_count != mapping_set.mapping_count
        ):
            raise CurationCutoverMappingReceiptConflict(
                "같은 Map release의 sealed mapping root가 현재 export와 다릅니다."
            )
        stored_items = (
            await db.scalars(
                select(KtmCurationCutoverMappingReceiptItem)
                .where(KtmCurationCutoverMappingReceiptItem.receipt_id == existing.receipt_id)
                .order_by(KtmCurationCutoverMappingReceiptItem.legacy_curated_feature_id)
                .with_for_update()
            )
        ).all()
        if tuple(map(_mapping_tuple, stored_items)) != tuple(
            map(_mapping_tuple, mapping_set.mappings)
        ):
            raise CurationCutoverMappingReceiptConflict(
                "sealed local mapping member set이 현재 Map export와 다릅니다."
            )
        return CurationCutoverMappingReceiptResult(receipt=existing, replayed=True)

    receipt = KtmCurationCutoverMappingReceipt(
        actor_admin_id=actor_admin_id,
        map_release_revision=KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
        mapping_root_version=mapping_set.mapping_root_version,
        mapping_root=mapping_set.mapping_root,
        mapping_count=mapping_set.mapping_count,
    )
    db.add(receipt)
    await db.flush()
    db.add_all(
        [
            KtmCurationCutoverMappingReceiptItem(
                receipt_id=receipt.receipt_id,
                legacy_curated_feature_id=mapping.legacy_curated_feature_id,
                collection_id=mapping.collection_id,
                curation_item_id=mapping.curation_item_id,
                mapping_kind=mapping.mapping_kind,
                source_row_hash=mapping.source_row_hash,
            )
            for mapping in mapping_set.mappings
        ]
    )
    await db.flush()
    receipt.status = "completed"
    receipt.completed_at = datetime.now(UTC)
    await db.flush()
    return CurationCutoverMappingReceiptResult(receipt=receipt, replayed=False)
