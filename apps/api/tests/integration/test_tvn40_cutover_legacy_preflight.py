"""T-VN-40C legacy provenance preflight의 실제 PostgreSQL 검증."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
from app.models.curated_plan import (
    CuratedPlanPoi,
    CuratedTripPlan,
    KtmCurationCutoverMappingReceipt,
    KtmCurationCutoverMappingReceiptItem,
)
from app.models.user import User
from app.services.curation_cutover_legacy_preflight import (
    CurationCutoverLegacyPlanMapping,
    CurationCutoverLegacyPreflightConflict,
    CurationCutoverLegacyPreflightIssue,
    inspect_curation_cutover_legacy_provenance,
)

pytestmark = pytest.mark.asyncio

_ROOT = "a" * 64
_ROW_HASH = "b" * 64


async def _admin(db: AsyncSession) -> User:
    admin = User(
        email=f"legacy-preflight-{uuid.uuid4().hex}@pinvi.test",
        nickname="legacy preflight test",
        status="active",
        email_verified_at=datetime.now(UTC),
    )
    db.add(admin)
    await db.flush()
    return admin


async def _seal_mapping(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID,
    legacy_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    collection_id = uuid.uuid4()
    curation_item_id = uuid.uuid4()
    await _seal_mapping_set(
        db,
        admin_id=admin_id,
        mappings=((legacy_id, collection_id, curation_item_id),),
    )
    return collection_id, curation_item_id


async def _seal_mapping_set(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID,
    mappings: tuple[tuple[uuid.UUID, uuid.UUID, uuid.UUID], ...],
) -> None:
    receipt = KtmCurationCutoverMappingReceipt(
        actor_admin_id=admin_id,
        map_release_revision=KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
        mapping_root_version="ktm-curation-cutover-mapping-v1",
        mapping_root=_ROOT,
        mapping_count=len(mappings),
    )
    db.add(receipt)
    await db.flush()
    db.add_all(
        [
            KtmCurationCutoverMappingReceiptItem(
                receipt_id=receipt.receipt_id,
                legacy_curated_feature_id=legacy_id,
                collection_id=collection_id,
                curation_item_id=curation_item_id,
                mapping_kind="legacy_projection",
                source_row_hash=_ROW_HASH,
            )
            for legacy_id, collection_id, curation_item_id in mappings
        ]
    )
    await db.flush()
    receipt.status = "completed"
    receipt.completed_at = datetime.now(UTC)
    await db.flush()


async def _legacy_plan(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID,
    source_curated_feature_id: str,
) -> CuratedTripPlan:
    plan = CuratedTripPlan(
        slug=f"legacy-{uuid.uuid4().hex}",
        title="legacy Map plan",
        category="recommended",
        source_system="kor-travel-map",
        source_curated_feature_id=source_curated_feature_id,
        created_by_admin_id=admin_id,
        updated_by_admin_id=admin_id,
    )
    db.add(plan)
    await db.flush()
    return plan


async def _poi(
    db: AsyncSession,
    *,
    plan: CuratedTripPlan,
    source_curated_feature_id: str | None,
    source_curated_feature_item_id: str | None,
) -> CuratedPlanPoi:
    poi = CuratedPlanPoi(
        curated_plan_id=plan.curated_plan_id,
        day_index=1,
        sort_order=uuid.uuid4().hex,
        source_curated_feature_id=source_curated_feature_id,
        source_curated_feature_item_id=source_curated_feature_item_id,
    )
    db.add(poi)
    await db.flush()
    return poi


async def test_legacy_preflight_accepts_exact_mapping_and_manual_pois(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    legacy_id = uuid.uuid4()
    async with session_factory() as db:
        admin = await _admin(db)
        collection_id, curation_item_id = await _seal_mapping(
            db, admin_id=admin.user_id, legacy_id=legacy_id
        )
        plan = await _legacy_plan(
            db, admin_id=admin.user_id, source_curated_feature_id=str(legacy_id)
        )
        await _poi(
            db,
            plan=plan,
            source_curated_feature_id=str(legacy_id),
            source_curated_feature_item_id="legacy-item-1",
        )
        await _poi(
            db,
            plan=plan,
            source_curated_feature_id=None,
            source_curated_feature_item_id=None,
        )
        await db.commit()

    async with session_factory() as db:
        result = await inspect_curation_cutover_legacy_provenance(db)

    assert result.ready is True
    assert result.mapping_count == 1
    assert result.legacy_plan_count == 1
    assert result.legacy_source_poi_count == 1
    assert result.manual_poi_count == 1
    assert result.issues == ()
    assert result.plan_mappings == (
        CurationCutoverLegacyPlanMapping(
            curated_plan_id=plan.curated_plan_id,
            legacy_curated_feature_id=legacy_id,
            collection_id=collection_id,
            curation_item_id=curation_item_id,
        ),
    )


async def test_legacy_preflight_reports_all_identity_and_poi_provenance_conflicts(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    mapped_id = uuid.uuid4()
    orphan_id = uuid.uuid4()
    async with session_factory() as db:
        admin = await _admin(db)
        await _seal_mapping(db, admin_id=admin.user_id, legacy_id=mapped_id)
        duplicate_a = await _legacy_plan(
            db, admin_id=admin.user_id, source_curated_feature_id=str(mapped_id)
        )
        duplicate_b = await _legacy_plan(
            db, admin_id=admin.user_id, source_curated_feature_id=str(mapped_id).upper()
        )
        invalid = await _legacy_plan(
            db, admin_id=admin.user_id, source_curated_feature_id="legacy::not-a-uuid"
        )
        orphan = await _legacy_plan(
            db, admin_id=admin.user_id, source_curated_feature_id=str(orphan_id)
        )
        await _poi(
            db,
            plan=duplicate_a,
            source_curated_feature_id=str(orphan_id),
            source_curated_feature_item_id="legacy-item-mismatch",
        )
        await _poi(
            db,
            plan=duplicate_b,
            source_curated_feature_id=str(mapped_id),
            source_curated_feature_item_id=None,
        )
        await _poi(
            db,
            plan=invalid,
            source_curated_feature_id="legacy::not-a-uuid",
            source_curated_feature_item_id="legacy-item-invalid-parent",
        )
        await _poi(
            db,
            plan=orphan,
            source_curated_feature_id=str(orphan_id),
            source_curated_feature_item_id="legacy-item-orphan",
        )
        await _poi(
            db,
            plan=orphan,
            source_curated_feature_id=str(orphan_id),
            source_curated_feature_item_id=" ",
        )
        await db.commit()

    async with session_factory() as db:
        result = await inspect_curation_cutover_legacy_provenance(db)

    assert result.ready is False
    assert result.legacy_plan_count == 4
    assert result.legacy_source_poi_count == 5
    assert result.manual_poi_count == 0
    assert {issue.code for issue in result.issues} == {
        "legacy-plan-canonical-collection-duplicate",
        "legacy-plan-source-id-duplicate",
        "legacy-plan-source-id-invalid",
        "legacy-plan-mapping-missing",
        "legacy-poi-provenance-partial",
        "legacy-poi-source-id-invalid",
        "legacy-poi-source-item-id-invalid",
        "legacy-poi-source-id-mismatch",
    }
    assert len(
        [issue for issue in result.issues if issue.code == "legacy-plan-source-id-duplicate"]
    ) == 2
    with pytest.raises(CurationCutoverLegacyPreflightConflict, match="legacy-plan"):
        result.require_ready()


async def test_legacy_preflight_requires_a_completed_current_mapping_receipt(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        result = await inspect_curation_cutover_legacy_provenance(db)

    assert result.ready is False
    assert result.receipt_id is None
    assert result.issues == (
        CurationCutoverLegacyPreflightIssue(
            code="mapping-receipt-missing",
            detail="현재 vendored Map release의 sealed mapping receipt가 없습니다.",
        ),
    )


async def test_legacy_preflight_rejects_multiple_plans_for_one_canonical_collection(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    first_legacy_id = uuid.uuid4()
    second_legacy_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    async with session_factory() as db:
        admin = await _admin(db)
        await _seal_mapping_set(
            db,
            admin_id=admin.user_id,
            mappings=(
                (first_legacy_id, collection_id, uuid.uuid4()),
                (second_legacy_id, collection_id, uuid.uuid4()),
            ),
        )
        await _legacy_plan(
            db, admin_id=admin.user_id, source_curated_feature_id=str(first_legacy_id)
        )
        await _legacy_plan(
            db, admin_id=admin.user_id, source_curated_feature_id=str(second_legacy_id)
        )
        await db.commit()

    async with session_factory() as db:
        result = await inspect_curation_cutover_legacy_provenance(db)

    assert result.ready is False
    assert {issue.code for issue in result.issues} == {
        "legacy-plan-canonical-collection-duplicate"
    }
    assert len(result.plan_mappings) == 2
