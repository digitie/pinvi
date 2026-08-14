"""sealed Map mapping evidence로 legacy curated plan을 canonical collection으로 전환한다."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map_curation import CurationCollectionFetchResult
from app.core.config import KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
from app.models.curated_plan import (
    CuratedPlanPoi,
    CuratedTripPlan,
    KtmCurationCutoverBackfillReceipt,
    KtmCurationCutoverMappingReceipt,
    KtmCurationCutoverMappingReceiptItem,
    KtmCurationImportReceipt,
)
from app.services.curation_collection_import import (
    CurationCollectionImportResult,
    _apply_snapshot,
    _completed_result,
    _lock_command_scope,
    _receipt,
    _response,
    curation_collection_request_fingerprint,
)
from app.services.curation_cutover_legacy_preflight import (
    CurationCutoverLegacyPlanMapping,
    CurationCutoverLegacyPreflightConflict,
    inspect_curation_cutover_legacy_provenance,
)

_SOURCE_SYSTEM = "kor-travel-map"
_MODE = "cutover-backfill"
_LOCK_NAMESPACE = "KTMC"


class CurationCutoverBackfillError(Exception):
    code = "CURATION_CUTOVER_BACKFILL_ERROR"


class CurationCutoverBackfillConflict(CurationCutoverBackfillError):
    code = "CURATION_CUTOVER_BACKFILL_CONFLICT"


class CurationCutoverBackfillNotFound(CurationCutoverBackfillError):
    code = "CURATION_CUTOVER_BACKFILL_NOT_FOUND"


@dataclass(frozen=True, slots=True)
class CurationCutoverBackfillPreparation:
    mapping_receipt_id: uuid.UUID
    legacy_curated_feature_id: uuid.UUID
    collection_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class CurationCutoverBackfillResult:
    receipt: KtmCurationCutoverBackfillReceipt
    import_result: CurationCollectionImportResult

    @property
    def replayed(self) -> bool:
        return self.import_result.replayed


def curation_cutover_backfill_request_fingerprint(*, curated_plan_id: uuid.UUID) -> str:
    """idempotency key가 다른 legacy plan으로 전용되는 것을 막는 closed request hash."""

    encoded = json.dumps(
        {
            "curated_plan_id": str(curated_plan_id),
            "version": "pinvi-ktm-curation-cutover-backfill-request/v1",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mapping_for_plan(
    *,
    plan_id: uuid.UUID,
    mappings: tuple[CurationCutoverLegacyPlanMapping, ...],
) -> CurationCutoverLegacyPlanMapping:
    matched = tuple(mapping for mapping in mappings if mapping.curated_plan_id == plan_id)
    if not matched:
        raise CurationCutoverBackfillNotFound(
            "canonical backfill 대상인 active legacy Map plan이 없습니다."
        )
    if len(matched) != 1:
        raise CurationCutoverBackfillConflict(
            "legacy plan의 sealed canonical mapping이 하나로 수렴하지 않습니다."
        )
    return matched[0]


async def _prepare(
    db: AsyncSession,
    *,
    curated_plan_id: uuid.UUID,
) -> CurationCutoverBackfillPreparation:
    report = await inspect_curation_cutover_legacy_provenance(db)
    try:
        report.require_ready()
    except CurationCutoverLegacyPreflightConflict as exc:
        raise CurationCutoverBackfillConflict(str(exc)) from exc
    if report.receipt_id is None:
        raise CurationCutoverBackfillConflict("sealed mapping receipt가 없습니다.")
    mapping = _mapping_for_plan(plan_id=curated_plan_id, mappings=report.plan_mappings)
    return CurationCutoverBackfillPreparation(
        mapping_receipt_id=report.receipt_id,
        legacy_curated_feature_id=mapping.legacy_curated_feature_id,
        collection_id=mapping.collection_id,
    )


async def _lock_backfill_plan_scope(db: AsyncSession, *, curated_plan_id: uuid.UUID) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {"identity": f"{_LOCK_NAMESPACE}:cutover-backfill-plan:{curated_plan_id}"},
    )


async def _completed_backfill_result(
    db: AsyncSession,
    *,
    receipt: KtmCurationCutoverBackfillReceipt,
    curated_plan_id: uuid.UUID,
    fingerprint: str,
) -> CurationCutoverBackfillResult:
    if (
        receipt.curated_plan_id != curated_plan_id
        or receipt.request_fingerprint != fingerprint
    ):
        raise CurationCutoverBackfillConflict(
            "Idempotency-Key가 다른 canonical cutover backfill 요청에 결박됐습니다."
        )
    if receipt.status != "completed" or receipt.import_receipt_id is None:
        raise CurationCutoverBackfillConflict(
            "같은 Idempotency-Key의 canonical cutover backfill이 완료되지 않았습니다."
        )
    mapping_receipt = await db.get(
        KtmCurationCutoverMappingReceipt,
        receipt.mapping_receipt_id,
    )
    if (
        mapping_receipt is None
        or mapping_receipt.status != "completed"
        or mapping_receipt.map_release_revision != KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
    ):
        raise CurationCutoverBackfillConflict(
            "terminal cutover backfill의 sealed Map release evidence가 현재 계약과 다릅니다."
        )
    import_receipt = await db.get(KtmCurationImportReceipt, receipt.import_receipt_id)
    if import_receipt is None or import_receipt.mode != _MODE:
        raise CurationCutoverBackfillConflict(
            "terminal cutover backfill의 canonical import receipt가 없습니다."
        )
    return CurationCutoverBackfillResult(
        receipt=receipt,
        import_result=_completed_result(import_receipt, replayed=True),
    )


async def inspect_curation_cutover_backfill(
    db: AsyncSession,
    *,
    actor_admin_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    curated_plan_id: uuid.UUID,
) -> tuple[CurationCutoverBackfillResult | None, CurationCutoverBackfillPreparation]:
    """remote snapshot 전 terminal replay 또는 sealed mapping collection을 판정한다."""

    fingerprint = curation_cutover_backfill_request_fingerprint(
        curated_plan_id=curated_plan_id
    )
    existing = await db.scalar(
        select(KtmCurationCutoverBackfillReceipt).where(
            KtmCurationCutoverBackfillReceipt.actor_admin_id == actor_admin_id,
            KtmCurationCutoverBackfillReceipt.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        replay = await _completed_backfill_result(
            db,
            receipt=existing,
            curated_plan_id=curated_plan_id,
            fingerprint=fingerprint,
        )
        mapping = await db.scalar(
            select(KtmCurationCutoverMappingReceiptItem).where(
                KtmCurationCutoverMappingReceiptItem.receipt_id == existing.mapping_receipt_id,
                KtmCurationCutoverMappingReceiptItem.legacy_curated_feature_id
                == existing.legacy_curated_feature_id,
            )
        )
        if mapping is None:
            raise CurationCutoverBackfillConflict(
                "terminal cutover backfill의 sealed mapping member가 없습니다."
            )
        return (
            replay,
            CurationCutoverBackfillPreparation(
                mapping_receipt_id=existing.mapping_receipt_id,
                legacy_curated_feature_id=existing.legacy_curated_feature_id,
                collection_id=mapping.collection_id,
            ),
        )
    return None, await _prepare(db, curated_plan_id=curated_plan_id)


async def apply_curation_cutover_backfill(
    db: AsyncSession,
    *,
    actor_admin_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    curated_plan_id: uuid.UUID,
    fetched: CurationCollectionFetchResult,
) -> CurationCutoverBackfillResult:
    """SSI transaction에서 legacy plan을 one-shot canonical import로 전환한다.

    remote snapshot은 route가 이 호출 전에 전부 읽고 검증한다. 여기서는 current sealed
    mapping/preflight를 다시 잠그고 대조해 stale remote input이나 local provenance drift를
    전체 rollback한다.
    """

    if fetched.not_modified or fetched.snapshot is None:
        raise CurationCutoverBackfillConflict(
            "legacy plan의 최초 canonical backfill에는 complete snapshot이 필요합니다."
        )
    fingerprint = curation_cutover_backfill_request_fingerprint(
        curated_plan_id=curated_plan_id
    )

    # Existing canonical import와 actor/key 및 collection fence를 공유한다.
    await _lock_command_scope(
        db,
        actor_admin_id=actor_admin_id,
        idempotency_key=idempotency_key,
        collection_id=fetched.snapshot.collection_id,
    )
    await _lock_backfill_plan_scope(db, curated_plan_id=curated_plan_id)

    existing = await db.scalar(
        select(KtmCurationCutoverBackfillReceipt)
        .where(
            KtmCurationCutoverBackfillReceipt.actor_admin_id == actor_admin_id,
            KtmCurationCutoverBackfillReceipt.idempotency_key == idempotency_key,
        )
        .with_for_update()
    )
    if existing is not None:
        return await _completed_backfill_result(
            db,
            receipt=existing,
            curated_plan_id=curated_plan_id,
            fingerprint=fingerprint,
        )

    preparation = await _prepare(db, curated_plan_id=curated_plan_id)
    snapshot = fetched.snapshot
    if snapshot.collection_id != preparation.collection_id:
        raise CurationCutoverBackfillConflict(
            "remote canonical snapshot collection이 sealed legacy mapping과 다릅니다."
        )

    mapping_item = await db.scalar(
        select(KtmCurationCutoverMappingReceiptItem)
        .where(
            KtmCurationCutoverMappingReceiptItem.receipt_id
            == preparation.mapping_receipt_id,
            KtmCurationCutoverMappingReceiptItem.legacy_curated_feature_id
            == preparation.legacy_curated_feature_id,
            KtmCurationCutoverMappingReceiptItem.collection_id == snapshot.collection_id,
        )
        .with_for_update()
    )
    if mapping_item is None:
        raise CurationCutoverBackfillConflict(
            "sealed mapping member가 requested canonical collection과 다릅니다."
        )

    plan = await db.scalar(
        select(CuratedTripPlan)
        .where(
            CuratedTripPlan.curated_plan_id == curated_plan_id,
            CuratedTripPlan.source_system == _SOURCE_SYSTEM,
            CuratedTripPlan.source_curation_collection_id.is_(None),
            CuratedTripPlan.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if plan is None:
        raise CurationCutoverBackfillNotFound(
            "canonical backfill 대상인 active legacy Map plan이 없습니다."
        )
    try:
        plan_legacy_id = uuid.UUID(plan.source_curated_feature_id or "")
    except ValueError as exc:
        raise CurationCutoverBackfillConflict(
            "legacy plan source_curated_feature_id가 UUID가 아닙니다."
        ) from exc
    if plan_legacy_id != preparation.legacy_curated_feature_id:
        raise CurationCutoverBackfillConflict(
            "legacy plan identity가 sealed mapping member와 다릅니다."
        )

    duplicate_canonical_plan = await db.scalar(
        select(CuratedTripPlan)
        .where(
            CuratedTripPlan.source_system == _SOURCE_SYSTEM,
            CuratedTripPlan.source_curation_collection_id == snapshot.collection_id,
            CuratedTripPlan.curated_plan_id != curated_plan_id,
            CuratedTripPlan.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if duplicate_canonical_plan is not None:
        raise CurationCutoverBackfillConflict(
            "sealed canonical collection을 이미 다른 active plan이 소유합니다."
        )

    generic_existing = await db.scalar(
        select(KtmCurationImportReceipt)
        .where(
            KtmCurationImportReceipt.actor_admin_id == actor_admin_id,
            KtmCurationImportReceipt.idempotency_key == idempotency_key,
        )
        .with_for_update()
    )
    if generic_existing is not None:
        raise CurationCutoverBackfillConflict(
            "Idempotency-Key가 다른 canonical collection import에 이미 사용됐습니다."
        )
    prior_backfill = await db.scalar(
        select(KtmCurationCutoverBackfillReceipt)
        .where(KtmCurationCutoverBackfillReceipt.curated_plan_id == curated_plan_id)
        .with_for_update()
    )
    if prior_backfill is not None:
        raise CurationCutoverBackfillConflict(
            "legacy plan의 canonical cutover backfill은 이미 terminal receipt를 가집니다."
        )

    backfill_receipt = KtmCurationCutoverBackfillReceipt(
        actor_admin_id=actor_admin_id,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        mapping_receipt_id=preparation.mapping_receipt_id,
        legacy_curated_feature_id=preparation.legacy_curated_feature_id,
        curated_plan_id=curated_plan_id,
        status="pending",
    )
    db.add(backfill_receipt)

    # generic receipt는 canonical source tuple을 input으로 가지므로, pending receipt 전에
    # snapshot tuple만 반영한다. plan title/POI mutation은 _apply_snapshot이 이어서 맡는다.
    plan.source_curation_collection_id = snapshot.collection_id
    plan.source_curation_collection_revision = snapshot.row_revision
    plan.source_curation_collection_etag = snapshot.source_etag
    plan.source_curation_item_set_hash_version = snapshot.item_set_hash_version
    plan.source_curation_item_set_hash = snapshot.item_set_hash
    plan.source_curation_item_count = snapshot.item_count
    await db.flush()

    import_receipt = _receipt(
        actor_admin_id=actor_admin_id,
        idempotency_key=idempotency_key,
        fingerprint=curation_collection_request_fingerprint(
            collection_id=snapshot.collection_id,
            mode=_MODE,
            is_published=plan.is_published,
        ),
        plan=plan,
        mode=_MODE,
        is_published=plan.is_published,
    )
    db.add(import_receipt)
    await db.flush()

    # preflight가 legacy provenance를 검사했어도, terminal guard와 같은 row lock 안에서
    # active legacy source POI만 다시 soft-delete한다. source tuple 모두 NULL인 manual POI는
    # 그대로 남아 sort_order 충돌 회피 대상으로 _apply_snapshot에 보인다.
    plan_pois = (
        (
            await db.execute(
                select(CuratedPlanPoi)
                .where(CuratedPlanPoi.curated_plan_id == curated_plan_id)
                .order_by(CuratedPlanPoi.curated_poi_id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    removed_legacy_poi_count = 0
    for poi in plan_pois:
        if poi.deleted_at is None and (
            poi.source_curated_feature_id is not None
            or poi.source_curated_feature_item_id is not None
        ):
            poi.deleted_at = datetime.now(UTC)
            poi.version += 1
            removed_legacy_poi_count += 1
    await db.flush()

    copied_poi_count, removed_canonical_poi_count = await _apply_snapshot(
        db,
        actor_admin_id=actor_admin_id,
        receipt=import_receipt,
        plan=plan,
        snapshot=snapshot,
        created_plan=False,
        # legacy plan의 publish state는 backfill command input이 아니다.
        is_published=None,
    )
    response = _response(
        plan=plan,
        created_plan=False,
        not_modified=False,
        copied_poi_count=copied_poi_count,
        removed_poi_count=removed_legacy_poi_count + removed_canonical_poi_count,
    )
    import_receipt.status = "completed"
    import_receipt.result_plan_id = plan.curated_plan_id
    import_receipt.response_status = 201
    import_receipt.response_body = response.model_dump(mode="json")
    import_receipt.completed_at = datetime.now(UTC)
    await db.flush()

    backfill_receipt.import_receipt_id = import_receipt.receipt_id
    backfill_receipt.status = "completed"
    backfill_receipt.completed_at = datetime.now(UTC)
    await db.flush()
    return CurationCutoverBackfillResult(
        receipt=backfill_receipt,
        import_result=CurationCollectionImportResult(
            response=response,
            status_code=201,
            replayed=False,
            mutated=True,
        ),
    )
