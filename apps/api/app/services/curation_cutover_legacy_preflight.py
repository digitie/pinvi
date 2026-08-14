"""T-VN-40C legacy Map provenance를 sealed mapping receipt와 대조한다.

이 모듈은 읽기 전용이다. 실제 canonical backfill command는 같은 ``SERIALIZABLE``
transaction에서 이 검증을 다시 실행해야 하며, 이 report만으로 변환을 허용해서는 안 된다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
from app.models.curated_plan import (
    CuratedPlanPoi,
    CuratedTripPlan,
    KtmCurationCutoverMappingReceipt,
    KtmCurationCutoverMappingReceiptItem,
)

_KOR_TRAVEL_MAP_SOURCE_SYSTEM = "kor-travel-map"


class CurationCutoverLegacyPreflightConflict(Exception):
    """sealed mapping evidence 또는 legacy provenance가 canonical backfill에 부적합하다."""

    code = "CURATION_CUTOVER_LEGACY_PREFLIGHT_CONFLICT"


@dataclass(frozen=True, slots=True)
class CurationCutoverLegacyPreflightIssue:
    code: str
    detail: str
    curated_plan_id: uuid.UUID | None = None
    curated_poi_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class CurationCutoverLegacyPlanMapping:
    curated_plan_id: uuid.UUID
    legacy_curated_feature_id: uuid.UUID
    collection_id: uuid.UUID
    curation_item_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class CurationCutoverLegacyPreflightResult:
    map_release_revision: str
    receipt_id: uuid.UUID | None
    mapping_root: str | None
    mapping_count: int
    legacy_plan_count: int
    legacy_source_poi_count: int
    manual_poi_count: int
    plan_mappings: tuple[CurationCutoverLegacyPlanMapping, ...]
    issues: tuple[CurationCutoverLegacyPreflightIssue, ...]

    @property
    def ready(self) -> bool:
        return not self.issues

    def require_ready(self) -> None:
        if self.ready:
            return
        codes = ", ".join(sorted({issue.code for issue in self.issues}))
        raise CurationCutoverLegacyPreflightConflict(
            f"legacy provenance preflight가 실패했습니다: {codes}"
        )


def _parse_legacy_feature_id(value: str | None) -> uuid.UUID | None:
    if value is None or not value.strip():
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def _sealed_mapping_receipt(
    db: AsyncSession,
) -> tuple[
    KtmCurationCutoverMappingReceipt | None,
    tuple[KtmCurationCutoverMappingReceiptItem, ...],
    tuple[CurationCutoverLegacyPreflightIssue, ...],
]:
    receipt = await db.scalar(
        select(KtmCurationCutoverMappingReceipt)
        .where(
            KtmCurationCutoverMappingReceipt.map_release_revision
            == KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
        )
        .with_for_update(read=True)
    )
    if receipt is None:
        return (
            None,
            (),
            (
                CurationCutoverLegacyPreflightIssue(
                    code="mapping-receipt-missing",
                    detail="현재 vendored Map release의 sealed mapping receipt가 없습니다.",
                ),
            ),
        )
    if receipt.status != "completed":
        return (
            receipt,
            (),
            (
                CurationCutoverLegacyPreflightIssue(
                    code="mapping-receipt-not-completed",
                    detail="현재 Map release의 mapping receipt가 completed 상태가 아닙니다.",
                ),
            ),
        )

    items = tuple(
        (
            await db.scalars(
                select(KtmCurationCutoverMappingReceiptItem)
                .where(KtmCurationCutoverMappingReceiptItem.receipt_id == receipt.receipt_id)
                .order_by(KtmCurationCutoverMappingReceiptItem.legacy_curated_feature_id)
                .with_for_update(read=True)
            )
        ).all()
    )
    if len(items) != receipt.mapping_count:
        return (
            receipt,
            items,
            (
                CurationCutoverLegacyPreflightIssue(
                    code="mapping-receipt-member-count-mismatch",
                    detail="sealed mapping receipt의 member 수가 root envelope count와 다릅니다.",
                ),
            ),
        )
    return receipt, items, ()


async def inspect_curation_cutover_legacy_provenance(
    db: AsyncSession,
) -> CurationCutoverLegacyPreflightResult:
    """활성 legacy Map plan/POI provenance의 backfill 적합성을 전수 대조한다."""

    receipt, receipt_items, receipt_issues = await _sealed_mapping_receipt(db)
    issues = list(receipt_issues)
    mapping_by_legacy_id = {item.legacy_curated_feature_id: item for item in receipt_items}

    plans = tuple(
        (
            await db.scalars(
                select(CuratedTripPlan)
                .where(
                    CuratedTripPlan.source_system == _KOR_TRAVEL_MAP_SOURCE_SYSTEM,
                    CuratedTripPlan.source_curation_collection_id.is_(None),
                    CuratedTripPlan.deleted_at.is_(None),
                )
                .order_by(CuratedTripPlan.curated_plan_id)
                .with_for_update(read=True)
            )
        ).all()
    )

    valid_plan_ids: dict[uuid.UUID, list[CuratedTripPlan]] = {}
    parsed_plan_ids: dict[uuid.UUID, uuid.UUID] = {}
    for plan in plans:
        legacy_id = _parse_legacy_feature_id(plan.source_curated_feature_id)
        if legacy_id is None:
            issues.append(
                CurationCutoverLegacyPreflightIssue(
                    code="legacy-plan-source-id-invalid",
                    detail="legacy Map plan의 source_curated_feature_id가 UUID가 아닙니다.",
                    curated_plan_id=plan.curated_plan_id,
                )
            )
            continue
        parsed_plan_ids[plan.curated_plan_id] = legacy_id
        valid_plan_ids.setdefault(legacy_id, []).append(plan)
        if receipt is not None and not receipt_issues and legacy_id not in mapping_by_legacy_id:
            issues.append(
                CurationCutoverLegacyPreflightIssue(
                    code="legacy-plan-mapping-missing",
                    detail="legacy Map plan identity가 sealed mapping receipt에 없습니다.",
                    curated_plan_id=plan.curated_plan_id,
                )
            )

    for legacy_id, same_source_plans in valid_plan_ids.items():
        if len(same_source_plans) <= 1:
            continue
        for plan in same_source_plans:
            issues.append(
                CurationCutoverLegacyPreflightIssue(
                    code="legacy-plan-source-id-duplicate",
                    detail=f"legacy Map identity {legacy_id}를 활성 plan이 둘 이상 사용합니다.",
                    curated_plan_id=plan.curated_plan_id,
                )
            )

    plans_by_collection: dict[uuid.UUID, list[CuratedTripPlan]] = {}
    if receipt is not None and not receipt_issues:
        for plan in plans:
            legacy_id = parsed_plan_ids.get(plan.curated_plan_id)
            mapping = mapping_by_legacy_id.get(legacy_id) if legacy_id is not None else None
            if mapping is not None:
                plans_by_collection.setdefault(mapping.collection_id, []).append(plan)
    for collection_id, same_collection_plans in plans_by_collection.items():
        if len(same_collection_plans) <= 1:
            continue
        for plan in same_collection_plans:
            issues.append(
                CurationCutoverLegacyPreflightIssue(
                    code="legacy-plan-canonical-collection-duplicate",
                    detail=(
                        f"canonical collection {collection_id}로 활성 legacy plan이 둘 이상 "
                        "수렴합니다. 명시적 merge 정책 없이는 자동 backfill할 수 없습니다."
                    ),
                    curated_plan_id=plan.curated_plan_id,
                )
            )

    plan_ids = tuple(plan.curated_plan_id for plan in plans)
    pois: tuple[CuratedPlanPoi, ...]
    if plan_ids:
        pois = tuple(
            (
                await db.scalars(
                    select(CuratedPlanPoi)
                    .where(
                        CuratedPlanPoi.curated_plan_id.in_(plan_ids),
                        CuratedPlanPoi.deleted_at.is_(None),
                    )
                    .order_by(CuratedPlanPoi.curated_plan_id, CuratedPlanPoi.curated_poi_id)
                    .with_for_update(read=True)
                )
            ).all()
        )
    else:
        pois = ()

    plan_legacy_ids = parsed_plan_ids
    source_poi_count = 0
    manual_poi_count = 0
    for poi in pois:
        source_feature_id = poi.source_curated_feature_id
        source_item_id = poi.source_curated_feature_item_id
        if source_feature_id is None and source_item_id is None:
            manual_poi_count += 1
            continue
        source_poi_count += 1
        if source_feature_id is None or source_item_id is None:
            issues.append(
                CurationCutoverLegacyPreflightIssue(
                    code="legacy-poi-provenance-partial",
                    detail="legacy Map POI는 feature와 item provenance를 함께 가져야 합니다.",
                    curated_plan_id=poi.curated_plan_id,
                    curated_poi_id=poi.curated_poi_id,
                )
            )
            continue
        if not source_item_id.strip():
            issues.append(
                CurationCutoverLegacyPreflightIssue(
                    code="legacy-poi-source-item-id-invalid",
                    detail="legacy Map POI의 source_curated_feature_item_id가 비어 있습니다.",
                    curated_plan_id=poi.curated_plan_id,
                    curated_poi_id=poi.curated_poi_id,
                )
            )
            continue
        source_legacy_id = _parse_legacy_feature_id(source_feature_id)
        if source_legacy_id is None:
            issues.append(
                CurationCutoverLegacyPreflightIssue(
                    code="legacy-poi-source-id-invalid",
                    detail="legacy Map POI의 source_curated_feature_id가 UUID가 아닙니다.",
                    curated_plan_id=poi.curated_plan_id,
                    curated_poi_id=poi.curated_poi_id,
                )
            )
            continue
        parent_legacy_id = plan_legacy_ids.get(poi.curated_plan_id)
        if parent_legacy_id is None or source_legacy_id != parent_legacy_id:
            issues.append(
                CurationCutoverLegacyPreflightIssue(
                    code="legacy-poi-source-id-mismatch",
                    detail="legacy Map POI provenance가 parent plan identity와 다릅니다.",
                    curated_plan_id=poi.curated_plan_id,
                    curated_poi_id=poi.curated_poi_id,
                )
            )

    plan_mappings = tuple(
        CurationCutoverLegacyPlanMapping(
            curated_plan_id=plan.curated_plan_id,
            legacy_curated_feature_id=legacy_id,
            collection_id=mapping_by_legacy_id[legacy_id].collection_id,
            curation_item_id=mapping_by_legacy_id[legacy_id].curation_item_id,
        )
        for plan in plans
        if (legacy_id := parsed_plan_ids.get(plan.curated_plan_id)) is not None
        and legacy_id in mapping_by_legacy_id
    )
    mapping_count = receipt.mapping_count if receipt is not None else 0
    return CurationCutoverLegacyPreflightResult(
        map_release_revision=KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
        receipt_id=receipt.receipt_id if receipt is not None else None,
        mapping_root=receipt.mapping_root if receipt is not None else None,
        mapping_count=mapping_count,
        legacy_plan_count=len(plans),
        legacy_source_poi_count=source_poi_count,
        manual_poi_count=manual_poi_count,
        plan_mappings=plan_mappings,
        issues=tuple(issues),
    )
