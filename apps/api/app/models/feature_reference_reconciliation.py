"""Map M05 Feature 참조 조정의 PinVi append-only local evidence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.db.base import Base

_SHA256_CHECK = r"^[0-9a-f]{64}$"
_FEATURE_PAIR_COMPLETE = "old_feature_id IS NOT NULL AND old_feature_uuid IS NOT NULL"
_REPLACEMENT_PAIR = (
    "(replacement_feature_id IS NULL AND replacement_feature_uuid IS NULL) OR "
    "(replacement_feature_id IS NOT NULL AND replacement_feature_uuid IS NOT NULL)"
)


class KtmFeatureReferenceReconciliationDeliveryAttempt(Base):
    """동일 Map event를 검사한 각 결과 — blocked도 삭제·갱신하지 않는다."""

    __tablename__ = "ktm_feature_reference_reconciliation_delivery_attempts"
    __table_args__ = (
        CheckConstraint("attempt_sequence > 0", name=conv("ck_ktm_frr_attempt_sequence")),
        CheckConstraint("event_sequence > 0", name=conv("ck_ktm_frr_attempt_event_sequence")),
        CheckConstraint(
            f"event_sha256 ~ '{_SHA256_CHECK}'", name=conv("ck_ktm_frr_attempt_event_sha")
        ),
        CheckConstraint(
            f"observation_root_sha256 ~ '{_SHA256_CHECK}'",
            name=conv("ck_ktm_frr_attempt_observation_root"),
        ),
        CheckConstraint(
            "(status = 'blocked' AND block_fingerprint_sha256 IS NOT NULL) OR "
            "(status = 'applied' AND block_fingerprint_sha256 IS NULL)",
            name=conv("ck_ktm_frr_attempt_status"),
        ),
        CheckConstraint(
            f"block_fingerprint_sha256 IS NULL OR block_fingerprint_sha256 ~ '{_SHA256_CHECK}'",
            name=conv("ck_ktm_frr_attempt_block_fingerprint"),
        ),
        UniqueConstraint("event_id", "attempt_sequence", name="uq_ktm_frr_attempt_event_sequence"),
        Index("ix_ktm_frr_attempt_event_observed", "event_id", "observed_at"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    attempt_sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    block_fingerprint_sha256: Mapped[str | None] = mapped_column(String(64))
    observation_root_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KtmFeatureReferenceReconciliationAppliedReceipt(Base):
    """Map ACK의 local_receipt_sha256이 가리키는 유일한 terminal local receipt."""

    __tablename__ = "ktm_feature_reference_reconciliation_applied_receipts"
    __table_args__ = (
        CheckConstraint("event_sequence > 0", name=conv("ck_ktm_frr_receipt_event_sequence")),
        CheckConstraint(
            f"event_sha256 ~ '{_SHA256_CHECK}'", name=conv("ck_ktm_frr_receipt_event_sha")
        ),
        CheckConstraint(f"receipt_sha256 ~ '{_SHA256_CHECK}'", name=conv("ck_ktm_frr_receipt_sha")),
        CheckConstraint(
            f"impact_root_sha256 ~ '{_SHA256_CHECK}'", name=conv("ck_ktm_frr_receipt_impact_root")
        ),
        CheckConstraint("impact_count >= 0", name=conv("ck_ktm_frr_receipt_impact_count")),
        CheckConstraint(_FEATURE_PAIR_COMPLETE, name=conv("ck_ktm_frr_receipt_old_pair")),
        CheckConstraint(_REPLACEMENT_PAIR, name=conv("ck_ktm_frr_receipt_replacement_pair")),
        CheckConstraint(
            "(action = 'rebind' AND replacement_feature_id IS NOT NULL) OR "
            "(action = 'detach' AND replacement_feature_id IS NULL)",
            name=conv("ck_ktm_frr_receipt_action"),
        ),
        UniqueConstraint("event_sequence", name="uq_ktm_frr_receipt_event_sequence"),
        UniqueConstraint("event_sha256", name="uq_ktm_frr_receipt_event_sha"),
        UniqueConstraint("receipt_sha256", name="uq_ktm_frr_receipt_sha"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    event_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    old_feature_id: Mapped[str] = mapped_column(Text(), nullable=False)
    old_feature_uuid: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    replacement_feature_id: Mapped[str | None] = mapped_column(Text())
    replacement_feature_uuid: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    impact_root_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    impact_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KtmFeatureReferenceReconciliationImpact(Base):
    """terminal receipt에 포함한 local row 단위 결과."""

    __tablename__ = "ktm_feature_reference_reconciliation_impacts"
    __table_args__ = (
        CheckConstraint("impact_index >= 0", name=conv("ck_ktm_frr_impact_index")),
        CheckConstraint(
            "target_relation IN ('trip_day_pois', 'curated_plan_pois', 'feature_suggestions')",
            name=conv("ck_ktm_frr_impact_target_relation"),
        ),
        CheckConstraint(_FEATURE_PAIR_COMPLETE, name=conv("ck_ktm_frr_impact_old_pair")),
        CheckConstraint(_REPLACEMENT_PAIR, name=conv("ck_ktm_frr_impact_replacement_pair")),
        CheckConstraint(
            "(outcome = 'rebind' AND replacement_feature_id IS NOT NULL) OR "
            "(outcome = 'detach' AND replacement_feature_id IS NULL) OR "
            "outcome = 'already_reconciled'",
            name=conv("ck_ktm_frr_impact_outcome"),
        ),
        UniqueConstraint("event_id", "impact_index", name="uq_ktm_frr_impact_index"),
        UniqueConstraint(
            "event_id", "target_relation", "target_id", name="uq_ktm_frr_impact_target"
        ),
        Index("ix_ktm_frr_impact_target", "target_relation", "target_id"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "app.ktm_feature_reference_reconciliation_applied_receipts.event_id",
            ondelete="RESTRICT",
            name="fk_ktm_frr_impact_receipt",
        ),
        primary_key=True,
    )
    impact_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_relation: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    old_feature_id: Mapped[str] = mapped_column(Text(), nullable=False)
    old_feature_uuid: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    replacement_feature_id: Mapped[str | None] = mapped_column(Text())
    replacement_feature_uuid: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
