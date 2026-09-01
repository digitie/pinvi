"""Map M05 event를 PinVi local evidence로 안전하게 투영한다.

이 module은 HTTP/worker를 소유하지 않는다. 호출자는 하나의 database transaction을 열고
``apply_feature_reference_reconciliation_event``의 결과가 ``Applied``일 때에만 commit 뒤
Map ACK을 수행한다. blocked 결과도 append-only attempt로 commit하지만 ACK하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.clients.kor_travel_map_feature_reference_reconciliation import (
    FeatureReference,
    FeatureReferenceReconciliationLease,
)
from app.models.curated_plan import CuratedPlanPoi
from app.models.feature_reference_reconciliation import (
    KtmFeatureReferenceReconciliationAppliedReceipt,
    KtmFeatureReferenceReconciliationDeliveryAttempt,
    KtmFeatureReferenceReconciliationImpact,
)
from app.models.feature_suggestion import FeatureSuggestion
from app.models.poi import TripDayPoi

_RECEIPT_VERSION = "pinvi-feature-reference-reconciliation-receipt-v1"
_OBSERVATION_VERSION = "pinvi-feature-reference-reconciliation-observation-v1"


class FeatureReferenceReconciliationApplyError(RuntimeError):
    """같은 event id가 다른 material로 재사용되는 등 fail-close DB 불변식 위반."""


@dataclass(frozen=True, slots=True)
class ReconciliationBlocked:
    """local mutation 없이 durable blocked observation을 보존한 결과."""

    event_id: uuid.UUID
    attempt_sequence: int
    block_fingerprint_sha256: str


@dataclass(frozen=True, slots=True)
class ReconciliationApplied:
    """final receipt가 현재 transaction에 추가된, 또는 기존 receipt를 재사용한 결과."""

    event_id: uuid.UUID
    local_receipt_sha256: str
    replayed_local_receipt: bool


type ReconciliationApplication = ReconciliationBlocked | ReconciliationApplied


@dataclass(frozen=True, slots=True)
class _ImpactMaterial:
    target_relation: Literal["trip_day_pois", "curated_plan_pois", "feature_suggestions"]
    target_id: uuid.UUID
    old_feature: FeatureReference
    replacement_feature: FeatureReference | None
    outcome: Literal["rebind", "detach", "already_reconciled"]

    def canonical(self) -> dict[str, object]:
        return {
            "target_relation": self.target_relation,
            "target_id": str(self.target_id),
            "old_feature": _feature_canonical(self.old_feature),
            "replacement_feature": _feature_canonical(self.replacement_feature),
            "outcome": self.outcome,
        }


def _canonical_sha256(value: object) -> str:
    material = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _feature_canonical(reference: FeatureReference | None) -> dict[str, object] | None:
    if reference is None:
        return None
    return {
        "feature_id": reference.feature_id,
        "feature_uuid": str(reference.feature_uuid),
        "row_revision": reference.row_revision,
    }


def _row_is_reconcilable(
    feature_id: str | None,
    feature_uuid: uuid.UUID | None,
    reference: FeatureReference,
) -> bool:
    """행이 old reference를 가리키고 있고 안전하게 rebind할 수 있는가.

    exact 짝은 물론, **legacy 축만 맞고 canonical UUID shadow가 아직 비어
    있는 행**도 포함한다. `feature_uuid`는 검증된 alias map 이관이 채우기
    전까지 정상적으로 NULL이고(models/poi.py), 일상적인 POI 추가 경로는
    `feature_id`만 채운다. 그 NULL을 "값이 어긋났다"로 읽으면 평범한 행 하나가
    reconciliation 피드를 영구히 막는다 — blocked event는 ack되지 않고 Map은
    같은 event를 계속 재공급하므로 head-of-line stall이 된다.

    rebind는 두 컬럼을 함께 쓰므로, 이런 행을 처리하면 짝이 **복구**된다.
    """

    if feature_id != reference.feature_id:
        return False
    return feature_uuid is None or feature_uuid == reference.feature_uuid


def _reconcilable_condition(
    id_column: ColumnElement[str | None],
    uuid_column: ColumnElement[uuid.UUID | None],
    reference: FeatureReference,
) -> ColumnElement[bool]:
    """`_row_is_reconcilable`의 SQL 대응."""

    return and_(
        id_column == reference.feature_id,
        or_(uuid_column.is_(None), uuid_column == reference.feature_uuid),
    )


def _conflicting_condition(
    id_column: ColumnElement[str | None],
    uuid_column: ColumnElement[uuid.UUID | None],
    reference: FeatureReference,
) -> ColumnElement[bool]:
    """두 축이 **실제로 어긋난** 행 — 여기서만 block해야 한다.

    UUID만 맞고 `feature_id`가 다르거나 NULL인 방향은 rebind 대상으로 넣지
    않는다. `feature_id`는 client가 준 자유 문자열이라 UUID만 보고 써 넣으면
    값을 합성하게 된다 — 그건 cutover가 명시적으로 거부하는 자기-정본화다.
    """

    return or_(
        and_(
            id_column == reference.feature_id,
            uuid_column.is_not(None),
            uuid_column != reference.feature_uuid,
        ),
        and_(
            uuid_column == reference.feature_uuid,
            id_column.is_distinct_from(reference.feature_id),
        ),
    )


def _pair_condition(
    id_column: ColumnElement[str | None],
    uuid_column: ColumnElement[uuid.UUID | None],
    reference: FeatureReference,
) -> ColumnElement[bool]:
    """rebind 대상과 conflict를 **한 번에** 잠근다(각 행을 두 번 읽지 않는다)."""

    return or_(
        _reconcilable_condition(id_column, uuid_column, reference),
        _conflicting_condition(id_column, uuid_column, reference),
    )


def _block(
    *,
    relation: str,
    target_id: uuid.UUID,
    reason: Literal["partial_pair", "curation_receipt_bound", "nonterminal_suggestion"],
) -> dict[str, str]:
    return {"reason": reason, "relation": relation, "target_id": str(target_id)}


async def _next_attempt_sequence(db: AsyncSession, *, event_id: uuid.UUID) -> int:
    current = await db.scalar(
        select(
            func.coalesce(
                func.max(KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence), 0
            )
        ).where(KtmFeatureReferenceReconciliationDeliveryAttempt.event_id == event_id)
    )
    return int(current or 0) + 1


async def _latest_blocked_attempt(
    db: AsyncSession,
    *,
    event_id: uuid.UUID,
) -> KtmFeatureReferenceReconciliationDeliveryAttempt | None:
    """동일 event의 마지막 blocked 관측을 advisory lock 안에서 읽는다."""

    return cast(
        KtmFeatureReferenceReconciliationDeliveryAttempt | None,
        await db.scalar(
            select(KtmFeatureReferenceReconciliationDeliveryAttempt)
            .where(
                KtmFeatureReferenceReconciliationDeliveryAttempt.event_id == event_id,
                KtmFeatureReferenceReconciliationDeliveryAttempt.status == "blocked",
            )
            .order_by(KtmFeatureReferenceReconciliationDeliveryAttempt.attempt_sequence.desc())
            .limit(1)
            .with_for_update()
        ),
    )


async def _lock_event(db: AsyncSession, *, event_id: uuid.UUID) -> None:
    """row 부재 event도 동일 xact에서 직렬화한다."""

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:event_id AS text), 0))"),
        {"event_id": str(event_id)},
    )


def _assert_same_receipt_material(
    receipt: KtmFeatureReferenceReconciliationAppliedReceipt,
    lease: FeatureReferenceReconciliationLease,
) -> None:
    event = lease.event
    replacement = event.replacement_feature
    if (
        receipt.event_sequence != event.event_sequence
        or receipt.event_sha256 != lease.event_sha256
        or receipt.action != event.action
        or receipt.old_feature_id != event.old_feature.feature_id
        or receipt.old_feature_uuid != event.old_feature.feature_uuid
        or receipt.replacement_feature_id
        != (replacement.feature_id if replacement is not None else None)
        or receipt.replacement_feature_uuid
        != (replacement.feature_uuid if replacement is not None else None)
    ):
        raise FeatureReferenceReconciliationApplyError(
            "동일 event_id의 final receipt material이 Map lease와 다릅니다."
        )


async def _load_trip_rows(
    db: AsyncSession,
    *,
    reference: FeatureReference,
) -> tuple[list[TripDayPoi], list[TripDayPoi]]:
    rows = list(
        (
            await db.scalars(
                select(TripDayPoi)
                .where(
                    TripDayPoi.deleted_at.is_(None),
                    _pair_condition(
                        TripDayPoi.feature_id, TripDayPoi.feature_uuid, reference
                    ),
                )
                .order_by(TripDayPoi.attachment_id)
                .with_for_update()
            )
        ).all()
    )
    return (
        [row for row in rows if _row_is_reconcilable(row.feature_id, row.feature_uuid, reference)],
        [row for row in rows if not _row_is_reconcilable(row.feature_id, row.feature_uuid, reference)],
    )


async def _load_curated_rows(
    db: AsyncSession,
    *,
    reference: FeatureReference,
) -> tuple[list[CuratedPlanPoi], list[CuratedPlanPoi]]:
    rows = list(
        (
            await db.scalars(
                select(CuratedPlanPoi)
                .where(
                    CuratedPlanPoi.deleted_at.is_(None),
                    _pair_condition(
                        CuratedPlanPoi.feature_id, CuratedPlanPoi.feature_uuid, reference
                    ),
                )
                .order_by(CuratedPlanPoi.curated_poi_id)
                .with_for_update()
            )
        ).all()
    )
    return (
        [row for row in rows if _row_is_reconcilable(row.feature_id, row.feature_uuid, reference)],
        [row for row in rows if not _row_is_reconcilable(row.feature_id, row.feature_uuid, reference)],
    )


async def _load_suggestion_rows(
    db: AsyncSession,
    *,
    reference: FeatureReference,
) -> tuple[list[FeatureSuggestion], list[FeatureSuggestion]]:
    rows = list(
        (
            await db.scalars(
                select(FeatureSuggestion)
                .where(
                    FeatureSuggestion.suggestion_type.in_(("correction", "closure")),
                    _pair_condition(
                        FeatureSuggestion.target_feature_id,
                        FeatureSuggestion.target_feature_uuid,
                        reference,
                    ),
                )
                .order_by(FeatureSuggestion.request_id)
                .with_for_update()
            )
        ).all()
    )
    return (
        [
            row
            for row in rows
            if _row_is_reconcilable(row.target_feature_id, row.target_feature_uuid, reference)
        ],
        [
            row
            for row in rows
            if not _row_is_reconcilable(row.target_feature_id, row.target_feature_uuid, reference)
        ],
    )


def _observation(
    *,
    lease: FeatureReferenceReconciliationLease,
    blocks: list[dict[str, str]],
    impacts: list[_ImpactMaterial],
) -> str:
    return _canonical_sha256(
        {
            "version": _OBSERVATION_VERSION,
            "event_id": str(lease.event.event_id),
            "event_sequence": lease.event.event_sequence,
            "event_sha256": lease.event_sha256,
            "blocks": sorted(
                blocks, key=lambda row: (row["relation"], row["target_id"], row["reason"])
            ),
            "impacts": [impact.canonical() for impact in impacts],
        }
    )


def _receipt_sha256(
    *,
    lease: FeatureReferenceReconciliationLease,
    impact_root_sha256: str,
    impact_count: int,
) -> str:
    event = lease.event
    return _canonical_sha256(
        {
            "version": _RECEIPT_VERSION,
            "event_id": str(event.event_id),
            "event_sequence": event.event_sequence,
            "event_sha256": lease.event_sha256,
            "action": event.action,
            "old_feature": _feature_canonical(event.old_feature),
            "replacement_feature": _feature_canonical(event.replacement_feature),
            "impact_root_sha256": impact_root_sha256,
            "impact_count": impact_count,
        }
    )


async def apply_feature_reference_reconciliation_event(
    db: AsyncSession,
    lease: FeatureReferenceReconciliationLease,
) -> ReconciliationApplication:
    """lease event를 local transaction에 적용한다. 이 함수는 commit하지 않는다."""

    event = lease.event
    await _lock_event(db, event_id=event.event_id)
    existing = await db.scalar(
        select(KtmFeatureReferenceReconciliationAppliedReceipt)
        .where(KtmFeatureReferenceReconciliationAppliedReceipt.event_id == event.event_id)
        .with_for_update()
    )
    if existing is not None:
        _assert_same_receipt_material(existing, lease)
        return ReconciliationApplied(
            event_id=event.event_id,
            local_receipt_sha256=existing.receipt_sha256,
            replayed_local_receipt=True,
        )

    trip_matches, trip_partials = await _load_trip_rows(db, reference=event.old_feature)
    curated_matches, curated_partials = await _load_curated_rows(db, reference=event.old_feature)
    suggestion_matches, suggestion_partials = await _load_suggestion_rows(
        db, reference=event.old_feature
    )

    blocks: list[dict[str, str]] = []
    blocks.extend(
        _block(relation="trip_day_pois", target_id=row.attachment_id, reason="partial_pair")
        for row in trip_partials
    )
    blocks.extend(
        _block(relation="curated_plan_pois", target_id=row.curated_poi_id, reason="partial_pair")
        for row in curated_partials
    )
    blocks.extend(
        _block(relation="feature_suggestions", target_id=row.request_id, reason="partial_pair")
        for row in suggestion_partials
    )
    for curated_row in curated_matches:
        if curated_row.source_curation_import_receipt_id is not None:
            blocks.append(
                _block(
                    relation="curated_plan_pois",
                    target_id=curated_row.curated_poi_id,
                    reason="curation_receipt_bound",
                )
            )
    for suggestion_row in suggestion_matches:
        if suggestion_row.status in {"pending", "approved"}:
            blocks.append(
                _block(
                    relation="feature_suggestions",
                    target_id=suggestion_row.request_id,
                    reason="nonterminal_suggestion",
                )
            )

    if blocks:
        ordered_blocks = sorted(
            blocks,
            key=lambda row: (row["relation"], row["target_id"], row["reason"]),
        )
        block_fingerprint_sha256 = _canonical_sha256(ordered_blocks)
        observation_root_sha256 = _observation(
            lease=lease,
            blocks=ordered_blocks,
            impacts=[],
        )
        previous = await _latest_blocked_attempt(db, event_id=event.event_id)
        if (
            previous is not None
            and previous.event_sequence == event.event_sequence
            and previous.event_sha256 == lease.event_sha256
            and previous.block_fingerprint_sha256 == block_fingerprint_sha256
            and previous.observation_root_sha256 == observation_root_sha256
        ):
            # 영구 blocker라도 같은 관측은 하나의 immutable evidence로만 남긴다.
            # advisory lock이 row 부재/동시 worker도 직렬화하므로 별도 unique index가 필요 없다.
            return ReconciliationBlocked(
                event_id=event.event_id,
                attempt_sequence=previous.attempt_sequence,
                block_fingerprint_sha256=block_fingerprint_sha256,
            )
        attempt = KtmFeatureReferenceReconciliationDeliveryAttempt(
            event_id=event.event_id,
            attempt_sequence=await _next_attempt_sequence(db, event_id=event.event_id),
            event_sequence=event.event_sequence,
            event_sha256=lease.event_sha256,
            status="blocked",
            block_fingerprint_sha256=block_fingerprint_sha256,
            observation_root_sha256=observation_root_sha256,
        )
        db.add(attempt)
        await db.flush()
        return ReconciliationBlocked(
            event_id=event.event_id,
            attempt_sequence=attempt.attempt_sequence,
            block_fingerprint_sha256=attempt.block_fingerprint_sha256 or "",
        )

    replacement = event.replacement_feature
    outcome: Literal["rebind", "detach"] = event.action
    impacts: list[_ImpactMaterial] = []
    for trip_row in trip_matches:
        impacts.append(
            _ImpactMaterial(
                target_relation="trip_day_pois",
                target_id=trip_row.attachment_id,
                old_feature=event.old_feature,
                replacement_feature=replacement,
                outcome=outcome,
            )
        )
        trip_row.feature_id = replacement.feature_id if replacement is not None else None
        trip_row.feature_uuid = replacement.feature_uuid if replacement is not None else None
        if replacement is None:
            trip_row.feature_link_broken_at = func.now()
    for curated_row in curated_matches:
        impacts.append(
            _ImpactMaterial(
                target_relation="curated_plan_pois",
                target_id=curated_row.curated_poi_id,
                old_feature=event.old_feature,
                replacement_feature=replacement,
                outcome=outcome,
            )
        )
        curated_row.feature_id = replacement.feature_id if replacement is not None else None
        curated_row.feature_uuid = replacement.feature_uuid if replacement is not None else None
    for suggestion_row in suggestion_matches:
        # terminal suggestions는 historical evidence라 target tuple을 수정하지 않는다.
        if suggestion_row.status in {"rejected", "added", "duplicate"}:
            continue
        impacts.append(
            _ImpactMaterial(
                target_relation="feature_suggestions",
                target_id=suggestion_row.request_id,
                old_feature=event.old_feature,
                replacement_feature=replacement,
                outcome=outcome,
            )
        )
        suggestion_row.target_feature_id = (
            replacement.feature_id if replacement is not None else None
        )
        suggestion_row.target_feature_uuid = (
            replacement.feature_uuid if replacement is not None else None
        )

    impacts.sort(key=lambda impact: (impact.target_relation, str(impact.target_id)))
    impact_root_sha256 = _canonical_sha256([impact.canonical() for impact in impacts])
    receipt_sha256 = _receipt_sha256(
        lease=lease,
        impact_root_sha256=impact_root_sha256,
        impact_count=len(impacts),
    )
    receipt = KtmFeatureReferenceReconciliationAppliedReceipt(
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        event_sha256=lease.event_sha256,
        action=event.action,
        old_feature_id=event.old_feature.feature_id,
        old_feature_uuid=event.old_feature.feature_uuid,
        replacement_feature_id=replacement.feature_id if replacement is not None else None,
        replacement_feature_uuid=replacement.feature_uuid if replacement is not None else None,
        impact_root_sha256=impact_root_sha256,
        impact_count=len(impacts),
        receipt_sha256=receipt_sha256,
    )
    attempt = KtmFeatureReferenceReconciliationDeliveryAttempt(
        event_id=event.event_id,
        attempt_sequence=await _next_attempt_sequence(db, event_id=event.event_id),
        event_sequence=event.event_sequence,
        event_sha256=lease.event_sha256,
        status="applied",
        observation_root_sha256=_observation(lease=lease, blocks=[], impacts=impacts),
    )
    db.add(receipt)
    db.add(attempt)
    db.add_all(
        KtmFeatureReferenceReconciliationImpact(
            event_id=event.event_id,
            impact_index=index,
            target_relation=impact.target_relation,
            target_id=impact.target_id,
            old_feature_id=impact.old_feature.feature_id,
            old_feature_uuid=impact.old_feature.feature_uuid,
            replacement_feature_id=(
                impact.replacement_feature.feature_id
                if impact.replacement_feature is not None
                else None
            ),
            replacement_feature_uuid=(
                impact.replacement_feature.feature_uuid
                if impact.replacement_feature is not None
                else None
            ),
            outcome=impact.outcome,
        )
        for index, impact in enumerate(impacts)
    )
    await db.flush()
    return ReconciliationApplied(
        event_id=event.event_id,
        local_receipt_sha256=receipt_sha256,
        replayed_local_receipt=False,
    )
