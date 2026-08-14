"""Map canonical collection snapshot을 PinVi curated plan으로 원자 반영한다."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map_curation import (
    CurationCollectionFetchResult,
    CurationCollectionSnapshotSet,
    CurationItemDetailSnapshot,
)
from app.models.curated_plan import (
    CuratedPlanPoi,
    CuratedTripPlan,
    KtmCurationImportReceipt,
    KtmCurationImportReceiptItem,
)
from app.schemas.notice import KorTravelMapCurationCollectionImportResponse

_SOURCE_SYSTEM = "kor-travel-map"
_IMPORT_LOCK_NAMESPACE = "KTMC"


class CurationCollectionImportError(Exception):
    code = "CURATION_COLLECTION_IMPORT_ERROR"


class CurationCollectionImportConflict(CurationCollectionImportError):
    code = "CURATION_COLLECTION_IMPORT_CONFLICT"


class CurationCollectionImportNotFound(CurationCollectionImportError):
    code = "CURATION_COLLECTION_IMPORT_NOT_FOUND"


@dataclass(frozen=True, slots=True)
class CurationCollectionImportResult:
    response: KorTravelMapCurationCollectionImportResponse
    status_code: int
    replayed: bool
    mutated: bool


def curation_collection_request_fingerprint(
    *,
    collection_id: uuid.UUID,
    mode: str,
    is_published: bool | None,
) -> str:
    payload = {
        "collection_id": str(collection_id),
        "is_published": is_published,
        "mode": mode,
        "version": "pinvi-ktm-curation-import-request/v1",
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_receipt_request(
    receipt: KtmCurationImportReceipt,
    *,
    collection_id: uuid.UUID,
    mode: str,
    is_published: bool | None,
    fingerprint: str,
) -> None:
    if (
        receipt.source_curation_collection_id != collection_id
        or receipt.mode != mode
        or receipt.requested_is_published != is_published
        or receipt.request_fingerprint != fingerprint
    ):
        raise CurationCollectionImportConflict(
            "Idempotency-Key가 다른 canonical collection import 요청에 결박됐습니다."
        )


def _completed_result(
    receipt: KtmCurationImportReceipt,
    *,
    replayed: bool,
) -> CurationCollectionImportResult:
    if (
        receipt.status != "completed"
        or receipt.response_status not in {200, 201}
        or receipt.response_body is None
    ):
        raise CurationCollectionImportConflict(
            "같은 Idempotency-Key의 canonical collection import가 완료되지 않았습니다."
        )
    try:
        response = KorTravelMapCurationCollectionImportResponse.model_validate(
            receipt.response_body
        )
    except ValidationError as exc:
        raise CurationCollectionImportConflict(
            "terminal canonical collection import response가 현재 계약에 맞지 않습니다."
        ) from exc
    if (
        response.notice_plan_id != receipt.result_plan_id
        or response.source_system != receipt.source_system
        or response.source_curation_collection_id != receipt.source_curation_collection_id
        or response.source_curation_collection_revision
        != str(receipt.source_curation_collection_revision)
        or response.source_curation_collection_etag != receipt.source_curation_collection_etag
        or response.source_curation_item_set_hash_version
        != receipt.source_curation_item_set_hash_version
        or response.source_curation_item_set_hash != receipt.source_curation_item_set_hash
        or response.source_curation_item_count != receipt.source_curation_item_count
    ):
        raise CurationCollectionImportConflict(
            "terminal canonical collection import response가 receipt source tuple과 다릅니다."
        )
    return CurationCollectionImportResult(
        response=response,
        status_code=receipt.response_status,
        replayed=replayed,
        mutated=False,
    )


async def inspect_curation_collection_import(
    db: AsyncSession,
    *,
    actor_admin_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    collection_id: uuid.UUID,
    mode: str,
    is_published: bool | None,
) -> tuple[CurationCollectionImportResult | None, str | None]:
    """원격 호출 전에 terminal replay와 create/refresh 정책을 판정한다."""

    fingerprint = curation_collection_request_fingerprint(
        collection_id=collection_id,
        mode=mode,
        is_published=is_published,
    )
    receipt = await db.scalar(
        select(KtmCurationImportReceipt).where(
            KtmCurationImportReceipt.actor_admin_id == actor_admin_id,
            KtmCurationImportReceipt.idempotency_key == idempotency_key,
        )
    )
    if receipt is not None:
        _validate_receipt_request(
            receipt,
            collection_id=collection_id,
            mode=mode,
            is_published=is_published,
            fingerprint=fingerprint,
        )
        return _completed_result(receipt, replayed=True), None

    plan = await db.scalar(
        select(CuratedTripPlan).where(
            CuratedTripPlan.source_system == _SOURCE_SYSTEM,
            CuratedTripPlan.source_curation_collection_id == collection_id,
            CuratedTripPlan.deleted_at.is_(None),
        )
    )
    if mode == "create" and plan is not None:
        raise CurationCollectionImportConflict("이미 가져온 canonical collection입니다.")
    if mode == "refresh" and plan is None:
        raise CurationCollectionImportNotFound("refresh할 canonical collection import가 없습니다.")
    conditional_etag = None
    if plan is not None and (is_published is None or plan.is_published is is_published):
        conditional_etag = plan.source_curation_collection_etag
    return None, conditional_etag


async def _lock_command_scope(
    db: AsyncSession,
    *,
    actor_admin_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    collection_id: uuid.UUID,
) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {
            "identity": (f"{_IMPORT_LOCK_NAMESPACE}:actor:{actor_admin_id}:key:{idempotency_key}"),
        },
    )
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {
            "identity": f"{_IMPORT_LOCK_NAMESPACE}:collection:{collection_id}",
        },
    )


async def _locked_plan(db: AsyncSession, collection_id: uuid.UUID) -> CuratedTripPlan | None:
    return cast(
        CuratedTripPlan | None,
        await db.scalar(
            select(CuratedTripPlan)
            .where(
                CuratedTripPlan.source_system == _SOURCE_SYSTEM,
                CuratedTripPlan.source_curation_collection_id == collection_id,
                CuratedTripPlan.deleted_at.is_(None),
            )
            .with_for_update()
        ),
    )


def _response(
    *,
    plan: CuratedTripPlan,
    created_plan: bool,
    not_modified: bool,
    copied_poi_count: int,
    removed_poi_count: int,
) -> KorTravelMapCurationCollectionImportResponse:
    assert plan.source_curation_collection_id is not None
    assert plan.source_curation_collection_revision is not None
    assert plan.source_curation_collection_etag is not None
    assert plan.source_curation_item_set_hash_version is not None
    assert plan.source_curation_item_set_hash is not None
    assert plan.source_curation_item_count is not None
    return KorTravelMapCurationCollectionImportResponse(
        notice_plan_id=plan.curated_plan_id,
        created_plan=created_plan,
        not_modified=not_modified,
        source_system=_SOURCE_SYSTEM,
        source_curation_collection_id=plan.source_curation_collection_id,
        source_curation_collection_revision=str(plan.source_curation_collection_revision),
        source_curation_collection_etag=plan.source_curation_collection_etag,
        source_curation_item_set_hash_version=cast(
            Literal["ktm-db-item-set-v1"],
            plan.source_curation_item_set_hash_version,
        ),
        source_curation_item_set_hash=plan.source_curation_item_set_hash,
        source_curation_item_count=plan.source_curation_item_count,
        copied_poi_count=copied_poi_count,
        removed_poi_count=removed_poi_count,
    )


def _receipt(
    *,
    actor_admin_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    fingerprint: str,
    plan: CuratedTripPlan,
    mode: str,
    is_published: bool | None,
) -> KtmCurationImportReceipt:
    assert plan.source_curation_collection_id is not None
    assert plan.source_curation_collection_revision is not None
    assert plan.source_curation_collection_etag is not None
    assert plan.source_curation_item_set_hash_version is not None
    assert plan.source_curation_item_set_hash is not None
    assert plan.source_curation_item_count is not None
    return KtmCurationImportReceipt(
        actor_admin_id=actor_admin_id,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        source_system=_SOURCE_SYSTEM,
        source_curation_collection_id=plan.source_curation_collection_id,
        source_curation_collection_revision=plan.source_curation_collection_revision,
        source_curation_collection_etag=plan.source_curation_collection_etag,
        source_curation_item_set_hash_version=plan.source_curation_item_set_hash_version,
        source_curation_item_set_hash=plan.source_curation_item_set_hash,
        source_curation_item_count=plan.source_curation_item_count,
        mode=mode,
        requested_is_published=is_published,
        status="pending",
    )


def _receipt_item(
    receipt_id: uuid.UUID,
    item: CurationItemDetailSnapshot,
) -> KtmCurationImportReceiptItem:
    return KtmCurationImportReceiptItem(
        receipt_id=receipt_id,
        source_curation_collection_id=item.collection_id,
        source_curation_item_id=item.curation_item_id,
        source_curation_item_revision=int(item.row_revision),
        source_curation_item_etag=f'"{item.etag}"',
        feature_uuid=item.feature.feature_id,
    )


def _plan_slug(collection_id: uuid.UUID) -> str:
    return f"kor-travel-map-{collection_id}"


def _feature_snapshot(item: CurationItemDetailSnapshot) -> dict[str, object]:
    return item.feature.model_dump(mode="json")


async def _apply_snapshot(
    db: AsyncSession,
    *,
    actor_admin_id: uuid.UUID,
    receipt: KtmCurationImportReceipt,
    plan: CuratedTripPlan,
    snapshot: CurationCollectionSnapshotSet,
    created_plan: bool,
    is_published: bool | None,
) -> tuple[int, int]:
    plan.title = snapshot.collection.title
    plan.category = snapshot.collection.theme_slug
    plan.summary = None
    plan.source_name = None
    plan.destination = None
    plan.updated_by_admin_id = actor_admin_id
    if is_published is not None:
        plan.is_published = is_published
    plan.source_system = _SOURCE_SYSTEM
    plan.source_curation_collection_id = snapshot.collection_id
    plan.source_curation_collection_revision = snapshot.row_revision
    plan.source_curation_collection_etag = snapshot.source_etag
    plan.source_curation_item_set_hash_version = snapshot.item_set_hash_version
    plan.source_curation_item_set_hash = snapshot.item_set_hash
    plan.source_curation_item_count = snapshot.item_count
    plan.source_imported_at = datetime.now(UTC)
    if not created_plan:
        plan.version += 1
    await db.flush()

    ordered_items = sorted(
        snapshot.items,
        key=lambda item: (item.item.sort_order, str(item.curation_item_id)),
    )
    for item in ordered_items:
        db.add(_receipt_item(receipt.receipt_id, item))
    await db.flush()

    current = (
        (
            await db.execute(
                select(CuratedPlanPoi)
                .where(
                    CuratedPlanPoi.curated_plan_id == plan.curated_plan_id,
                    CuratedPlanPoi.source_curation_item_id.is_not(None),
                )
                .order_by(CuratedPlanPoi.curated_poi_id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    by_item_id = {
        poi.source_curation_item_id: poi
        for poi in current
        if poi.source_curation_item_id is not None
    }
    desired_ids = {item.curation_item_id for item in ordered_items}
    occupied_sort_orders = set(
        (
            await db.scalars(
                select(CuratedPlanPoi.sort_order).where(
                    CuratedPlanPoi.curated_plan_id == plan.curated_plan_id,
                    CuratedPlanPoi.deleted_at.is_(None),
                    CuratedPlanPoi.source_curation_item_id.is_(None),
                )
            )
        ).all()
    )
    removed = 0
    for current_poi in current:
        if (
            current_poi.deleted_at is None
            and current_poi.source_curation_item_id not in desired_ids
        ):
            current_poi.deleted_at = datetime.now(UTC)
            current_poi.version += 1
            removed += 1

    for position, item in enumerate(ordered_items, start=1):
        sort_order = f"ktm-{position:04d}-{item.curation_item_id.hex}"
        while sort_order in occupied_sort_orders:
            if len(sort_order) >= 80:
                raise CurationCollectionImportConflict(
                    "canonical POI sort_order를 안전하게 배정할 수 없습니다."
                )
            sort_order += "x"
        occupied_sort_orders.add(sort_order)
        poi = by_item_id.get(item.curation_item_id)
        if poi is None:
            poi = CuratedPlanPoi(
                curated_plan_id=plan.curated_plan_id,
                day_index=1,
                sort_order=sort_order,
                currency="KRW",
            )
            db.add(poi)
        else:
            poi.version += 1
        poi.day_index = 1
        poi.sort_order = sort_order
        poi.feature_id = str(item.feature.feature_id)
        poi.feature_uuid = item.feature.feature_id
        poi.feature_snapshot = _feature_snapshot(item)
        poi.memo = item.item.summary
        poi.source_curation_import_receipt_id = receipt.receipt_id
        poi.source_curation_collection_id = snapshot.collection_id
        poi.source_curation_item_id = item.curation_item_id
        poi.source_curation_item_revision = int(item.row_revision)
        poi.source_curation_item_etag = f'"{item.etag}"'
        poi.deleted_at = None
    await db.flush()
    return len(ordered_items), removed


def _validate_snapshot_forward(
    plan: CuratedTripPlan,
    snapshot: CurationCollectionSnapshotSet,
) -> None:
    current_revision = plan.source_curation_collection_revision
    current_etag = plan.source_curation_collection_etag
    if current_revision is not None and current_revision > snapshot.row_revision:
        raise CurationCollectionImportConflict(
            "local canonical collection revision이 원격 snapshot보다 새롭습니다."
        )
    if current_revision == snapshot.row_revision and current_etag != snapshot.source_etag:
        raise CurationCollectionImportConflict(
            "같은 canonical collection revision의 ETag가 다릅니다."
        )


async def _apply_not_modified(
    db: AsyncSession,
    *,
    receipt: KtmCurationImportReceipt,
    plan: CuratedTripPlan,
    source_etag: str,
) -> None:
    if plan.source_curation_collection_etag != source_etag:
        raise CurationCollectionImportConflict(
            "conditional snapshot 이후 local collection ETag가 바뀌었습니다."
        )
    prior_receipt = await db.scalar(
        select(KtmCurationImportReceipt)
        .where(
            KtmCurationImportReceipt.status == "completed",
            # 0056 이전 terminal row는 JSON type guard가 없었다. `as_boolean()`은
            # malformed legacy string을 cast하면서 22P02를 낼 수 있으므로, exact
            # JSON boolean `false`만 authoritative proof 후보로 인정한다.
            KtmCurationImportReceipt.response_body.contains({"not_modified": False}),
            KtmCurationImportReceipt.result_plan_id == plan.curated_plan_id,
            KtmCurationImportReceipt.source_system == _SOURCE_SYSTEM,
            KtmCurationImportReceipt.source_curation_collection_id
            == plan.source_curation_collection_id,
            KtmCurationImportReceipt.source_curation_collection_revision
            == plan.source_curation_collection_revision,
            KtmCurationImportReceipt.source_curation_collection_etag
            == plan.source_curation_collection_etag,
            KtmCurationImportReceipt.source_curation_item_set_hash_version
            == plan.source_curation_item_set_hash_version,
            KtmCurationImportReceipt.source_curation_item_set_hash
            == plan.source_curation_item_set_hash,
            KtmCurationImportReceipt.source_curation_item_count == plan.source_curation_item_count,
        )
        .order_by(
            KtmCurationImportReceipt.completed_at.desc(),
            KtmCurationImportReceipt.receipt_id.desc(),
        )
        .limit(1)
        .with_for_update()
    )
    if prior_receipt is None:
        raise CurationCollectionImportConflict(
            "conditional snapshot에 대응하는 immutable import proof가 없습니다."
        )
    prior_items = (
        await db.scalars(
            select(KtmCurationImportReceiptItem)
            .where(KtmCurationImportReceiptItem.receipt_id == prior_receipt.receipt_id)
            .order_by(KtmCurationImportReceiptItem.source_curation_item_id)
        )
    ).all()
    if len(prior_items) != plan.source_curation_item_count:
        raise CurationCollectionImportConflict(
            "immutable import proof의 item count가 local plan과 다릅니다."
        )
    pois = (
        (
            await db.execute(
                select(CuratedPlanPoi)
                .where(
                    CuratedPlanPoi.curated_plan_id == plan.curated_plan_id,
                    CuratedPlanPoi.deleted_at.is_(None),
                    CuratedPlanPoi.source_curation_item_id.is_not(None),
                )
                .order_by(CuratedPlanPoi.curated_poi_id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if len(pois) != plan.source_curation_item_count:
        raise CurationCollectionImportConflict(
            "local canonical POI set이 conditional snapshot receipt와 다릅니다."
        )
    prior_proofs = {
        (
            item.source_curation_collection_id,
            item.source_curation_item_id,
            item.source_curation_item_revision,
            item.source_curation_item_etag,
            item.feature_uuid,
        )
        for item in prior_items
    }
    current_proofs = set()
    for poi in pois:
        if (
            poi.source_curation_collection_id is None
            or poi.source_curation_item_id is None
            or poi.source_curation_item_revision is None
            or poi.source_curation_item_etag is None
            or poi.feature_uuid is None
        ):
            raise CurationCollectionImportConflict("local canonical POI provenance가 불완전합니다.")
        current_proofs.add(
            (
                poi.source_curation_collection_id,
                poi.source_curation_item_id,
                poi.source_curation_item_revision,
                poi.source_curation_item_etag,
                poi.feature_uuid,
            )
        )
    if current_proofs != prior_proofs:
        raise CurationCollectionImportConflict(
            "local canonical POI set이 immutable conditional snapshot proof와 다릅니다."
        )
    for item in prior_items:
        db.add(
            KtmCurationImportReceiptItem(
                receipt_id=receipt.receipt_id,
                source_curation_collection_id=item.source_curation_collection_id,
                source_curation_item_id=item.source_curation_item_id,
                source_curation_item_revision=item.source_curation_item_revision,
                source_curation_item_etag=item.source_curation_item_etag,
                feature_uuid=item.feature_uuid,
            )
        )
    await db.flush()


async def apply_curation_collection_import(
    db: AsyncSession,
    *,
    actor_admin_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    collection_id: uuid.UUID,
    mode: str,
    is_published: bool | None,
    fetched: CurationCollectionFetchResult,
) -> CurationCollectionImportResult:
    """SERIALIZABLE transaction 안에서 plan·POI·receipt를 함께 봉인한다."""

    fingerprint = curation_collection_request_fingerprint(
        collection_id=collection_id,
        mode=mode,
        is_published=is_published,
    )
    await _lock_command_scope(
        db,
        actor_admin_id=actor_admin_id,
        idempotency_key=idempotency_key,
        collection_id=collection_id,
    )
    existing_receipt = await db.scalar(
        select(KtmCurationImportReceipt)
        .where(
            KtmCurationImportReceipt.actor_admin_id == actor_admin_id,
            KtmCurationImportReceipt.idempotency_key == idempotency_key,
        )
        .with_for_update()
    )
    if existing_receipt is not None:
        _validate_receipt_request(
            existing_receipt,
            collection_id=collection_id,
            mode=mode,
            is_published=is_published,
            fingerprint=fingerprint,
        )
        return _completed_result(existing_receipt, replayed=True)

    plan = await _locked_plan(db, collection_id)
    if mode == "create" and plan is not None:
        raise CurationCollectionImportConflict("이미 가져온 canonical collection입니다.")
    if mode == "refresh" and plan is None:
        raise CurationCollectionImportNotFound("refresh할 canonical collection import가 없습니다.")

    created_plan = plan is None
    if fetched.not_modified:
        if plan is None:
            raise CurationCollectionImportConflict(
                "local plan 없이 conditional 304를 적용할 수 없습니다."
            )
    else:
        if fetched.snapshot is None or fetched.snapshot.collection_id != collection_id:
            raise CurationCollectionImportConflict(
                "원격 canonical collection snapshot identity가 다릅니다."
            )
        if plan is None:
            assert fetched.snapshot is not None
            plan = CuratedTripPlan(
                slug=_plan_slug(collection_id),
                title=fetched.snapshot.collection.title,
                category=fetched.snapshot.collection.theme_slug,
                source_system=_SOURCE_SYSTEM,
                source_curation_collection_id=collection_id,
                source_curation_collection_revision=fetched.snapshot.row_revision,
                source_curation_collection_etag=fetched.snapshot.source_etag,
                source_curation_item_set_hash_version=(fetched.snapshot.item_set_hash_version),
                source_curation_item_set_hash=fetched.snapshot.item_set_hash,
                source_curation_item_count=fetched.snapshot.item_count,
                created_by_admin_id=actor_admin_id,
                updated_by_admin_id=actor_admin_id,
                is_published=is_published is True,
            )
            db.add(plan)
            await db.flush()

    assert plan is not None
    if fetched.not_modified:
        receipt = _receipt(
            actor_admin_id=actor_admin_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            plan=plan,
            mode=mode,
            is_published=is_published,
        )
        db.add(receipt)
        await db.flush()
        await _apply_not_modified(
            db,
            receipt=receipt,
            plan=plan,
            source_etag=fetched.source_etag,
        )
        response = _response(
            plan=plan,
            created_plan=False,
            not_modified=True,
            copied_poi_count=0,
            removed_poi_count=0,
        )
        status_code = 200
        mutated = False
    else:
        assert fetched.snapshot is not None
        # plan의 source receipt를 먼저 반영해야 pending receipt가 exact tuple을 담는다.
        snapshot = fetched.snapshot
        if not created_plan:
            _validate_snapshot_forward(plan, snapshot)
        plan.source_curation_collection_revision = snapshot.row_revision
        plan.source_curation_collection_etag = snapshot.source_etag
        plan.source_curation_item_set_hash_version = snapshot.item_set_hash_version
        plan.source_curation_item_set_hash = snapshot.item_set_hash
        plan.source_curation_item_count = snapshot.item_count
        await db.flush()
        receipt = _receipt(
            actor_admin_id=actor_admin_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            plan=plan,
            mode=mode,
            is_published=is_published,
        )
        db.add(receipt)
        await db.flush()
        copied, removed = await _apply_snapshot(
            db,
            actor_admin_id=actor_admin_id,
            receipt=receipt,
            plan=plan,
            snapshot=snapshot,
            created_plan=created_plan,
            is_published=is_published,
        )
        response = _response(
            plan=plan,
            created_plan=created_plan,
            not_modified=False,
            copied_poi_count=copied,
            removed_poi_count=removed,
        )
        status_code = 201 if created_plan else 200
        mutated = True

    receipt.status = "completed"
    receipt.result_plan_id = plan.curated_plan_id
    receipt.response_status = status_code
    receipt.response_body = response.model_dump(mode="json")
    receipt.completed_at = datetime.now(UTC)
    await db.flush()
    return CurationCollectionImportResult(
        response=response,
        status_code=status_code,
        replayed=False,
        mutated=mutated,
    )
