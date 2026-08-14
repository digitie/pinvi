"""T-VN-40C Map identity export local receipt의 실제 DB sealing 검증."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curated_plan import (
    KtmCurationCutoverMappingReceipt,
    KtmCurationCutoverMappingReceiptItem,
)
from app.models.user import User
from app.services.curation_cutover_mapping_receipt import (
    CurationCutoverMappingReceiptConflict,
    seal_curation_cutover_mapping_receipt,
)

pytestmark = pytest.mark.asyncio

_MAP_RELEASE = "a" * 40
_MAPPING_ROOT = "b" * 64
_SOURCE_ROW_HASH = "c" * 64


async def _create_admin(db: AsyncSession) -> User:
    admin = User(
        email=f"cutover-receipt-{uuid.uuid4().hex}@pinvi.test",
        nickname="mapping receipt test",
        status="active",
        email_verified_at=datetime.now(UTC),
    )
    db.add(admin)
    await db.flush()
    return admin


def _receipt(actor_admin_id: uuid.UUID, *, mapping_count: int) -> KtmCurationCutoverMappingReceipt:
    return KtmCurationCutoverMappingReceipt(
        actor_admin_id=actor_admin_id,
        map_release_revision=_MAP_RELEASE,
        mapping_root_version="ktm-curation-cutover-mapping-v1",
        mapping_root=_MAPPING_ROOT,
        mapping_count=mapping_count,
    )


def _item(receipt_id: uuid.UUID) -> KtmCurationCutoverMappingReceiptItem:
    return KtmCurationCutoverMappingReceiptItem(
        receipt_id=receipt_id,
        legacy_curated_feature_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        curation_item_id=uuid.uuid4(),
        mapping_kind="legacy_projection",
        source_row_hash=_SOURCE_ROW_HASH,
    )


def _mapping_set(*, root: str = _MAPPING_ROOT):  # type: ignore[no-untyped-def]
    from app.clients.kor_travel_map_curation import (
        CurationCutoverIdentityMapping,
        CurationCutoverMappingSet,
    )

    return CurationCutoverMappingSet(
        mapping_root_version="ktm-curation-cutover-mapping-v1",
        mapping_count=2,
        mapping_root=root,
        mappings=(
            CurationCutoverIdentityMapping(
                legacy_curated_feature_id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
                collection_id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
                curation_item_id=uuid.UUID("30000000-0000-0000-0000-000000000001"),
                mapping_kind="legacy_projection",
                source_row_hash="1" * 64,
            ),
            CurationCutoverIdentityMapping(
                legacy_curated_feature_id=uuid.UUID("10000000-0000-0000-0000-000000000002"),
                collection_id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
                curation_item_id=uuid.UUID("30000000-0000-0000-0000-000000000002"),
                mapping_kind="official_membership",
                source_row_hash="2" * 64,
            ),
        ),
    )


async def test_cutover_mapping_receipt_seals_exact_members_and_rejects_late_insert(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        admin = await _create_admin(db)
        receipt = _receipt(admin.user_id, mapping_count=1)
        db.add(receipt)
        await db.flush()
        db.add(_item(receipt.receipt_id))
        await db.flush()

        receipt.status = "completed"
        receipt.completed_at = datetime.now(UTC)
        await db.commit()
        sealed_id = receipt.receipt_id

    async with session_factory() as db:
        sealed = await db.get(KtmCurationCutoverMappingReceipt, sealed_id)
        assert sealed is not None
        assert sealed.status == "completed"
        assert (
            await db.scalar(
                select(func.count())
                .select_from(KtmCurationCutoverMappingReceiptItem)
                .where(KtmCurationCutoverMappingReceiptItem.receipt_id == sealed_id)
            )
            == 1
        )
        db.add(_item(sealed_id))
        with pytest.raises(DBAPIError) as raised:
            await db.commit()
        assert getattr(raised.value.orig, "sqlstate", None) == "55000"
        await db.rollback()


async def test_cutover_mapping_receipt_rejects_incomplete_terminal_set(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        admin = await _create_admin(db)
        receipt = _receipt(admin.user_id, mapping_count=2)
        db.add(receipt)
        await db.flush()
        db.add(_item(receipt.receipt_id))
        await db.flush()
        receipt.status = "completed"
        receipt.completed_at = datetime.now(UTC)

        with pytest.raises(DBAPIError) as raised:
            await db.commit()
        assert getattr(raised.value.orig, "sqlstate", None) == "23514"
        await db.rollback()

        persisted = await db.scalar(
            select(KtmCurationCutoverMappingReceipt.status).where(
                KtmCurationCutoverMappingReceipt.receipt_id == receipt.receipt_id
            )
        )
        assert persisted is None


async def test_cutover_mapping_capture_is_release_singleton_and_exact_replay(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        admin = await _create_admin(db)
        captured = await seal_curation_cutover_mapping_receipt(
            db,
            actor_admin_id=admin.user_id,
            mapping_set=_mapping_set(),
        )
        assert captured.replayed is False
        await db.commit()
        sealed_id = captured.receipt.receipt_id

    async with session_factory() as db:
        replay = await seal_curation_cutover_mapping_receipt(
            db,
            actor_admin_id=admin.user_id,
            mapping_set=_mapping_set(),
        )
        assert replay.replayed is True
        assert replay.receipt.receipt_id == sealed_id
        await db.commit()

    async with session_factory() as db:
        with pytest.raises(CurationCutoverMappingReceiptConflict, match="sealed mapping root"):
            await seal_curation_cutover_mapping_receipt(
                db,
                actor_admin_id=admin.user_id,
                mapping_set=_mapping_set(root="d" * 64),
            )
        await db.rollback()


async def test_cutover_mapping_receipt_catalog_has_exact_terminal_guards(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        names = set(
            (
                await db.execute(
                    text(
                        "SELECT conname FROM pg_catalog.pg_constraint AS con "
                        "JOIN pg_catalog.pg_namespace AS n "
                        "ON n.oid = con.connamespace "
                        "WHERE n.nspname = 'app' "
                        "AND con.conname = ANY(:names)"
                    ),
                    {
                        "names": [
                            "ck_ktm_curation_cutover_mapping_receipts_release",
                            "ck_ktm_curation_cutover_mapping_receipts_root",
                            "ck_ktm_curation_cutover_mapping_receipts_terminal",
                            "fk_ktm_curation_cutover_mapping_receipts_actor",
                            "pk_ktm_curation_cutover_mapping_receipts",
                            "uq_ktm_curation_cutover_mapping_receipts_map_release",
                            "uq_ktm_curation_cutover_mapping_receipts_map_root",
                            "ck_ktm_curation_cutover_mapping_receipt_items_source",
                            "fk_ktm_curation_cutover_mapping_receipt_items_receipt",
                            "pk_ktm_curation_cutover_mapping_receipt_items",
                            "uq_ktm_curation_cutover_mapping_receipt_items_curation_item",
                        ]
                    },
                )
            )
            .scalars()
            .all()
        )
        assert names == {
            "ck_ktm_curation_cutover_mapping_receipts_release",
            "ck_ktm_curation_cutover_mapping_receipts_root",
            "ck_ktm_curation_cutover_mapping_receipts_terminal",
            "fk_ktm_curation_cutover_mapping_receipts_actor",
            "pk_ktm_curation_cutover_mapping_receipts",
            "uq_ktm_curation_cutover_mapping_receipts_map_release",
            "uq_ktm_curation_cutover_mapping_receipts_map_root",
            "ck_ktm_curation_cutover_mapping_receipt_items_source",
            "fk_ktm_curation_cutover_mapping_receipt_items_receipt",
            "pk_ktm_curation_cutover_mapping_receipt_items",
            "uq_ktm_curation_cutover_mapping_receipt_items_curation_item",
        }
        release_unique = await db.scalar(
            text(
                "SELECT pg_catalog.pg_get_constraintdef(con.oid, true) "
                "FROM pg_catalog.pg_constraint AS con "
                "JOIN pg_catalog.pg_namespace AS n ON n.oid = con.connamespace "
                "WHERE n.nspname = 'app' "
                "AND con.conname = 'uq_ktm_curation_cutover_mapping_receipts_map_release'"
            )
        )
        assert release_unique == "UNIQUE (map_release_revision)"
        trigger_rows = await db.execute(
            text(
                "SELECT tgname FROM pg_catalog.pg_trigger AS trigger "
                "JOIN pg_catalog.pg_class AS relation ON relation.oid = trigger.tgrelid "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid = relation.relnamespace "
                "WHERE namespace.nspname = 'app' AND NOT trigger.tgisinternal "
                "AND relation.relname = ANY(:tables)"
            ),
            {
                "tables": [
                    "ktm_curation_cutover_mapping_receipts",
                    "ktm_curation_cutover_mapping_receipt_items",
                ]
            },
        )
        assert set(trigger_rows.scalars()) == {
            "trg_ktm_curation_cutover_mapping_receipts_guard",
            "trg_ktm_curation_cutover_mapping_receipts_truncate_guard",
            "trg_ktm_curation_cutover_mapping_receipt_items_guard",
            "trg_ktm_curation_cutover_mapping_receipt_items_truncate_guard",
        }
