"""Map M05 Feature 참조 조정의 PinVi 로컬 증거 조회 schema."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AdminFeatureReferenceReconciliationAttempt(BaseModel):
    """Map event를 검사한 append-only 관측 1건."""

    event_id: uuid.UUID
    attempt_sequence: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["blocked", "applied"]
    block_fingerprint_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    observation_root_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime


class AdminFeatureReferenceReconciliationReceipt(BaseModel):
    """Map ACK 전에 commit된 terminal local receipt."""

    event_id: uuid.UUID
    event_sequence: int = Field(ge=1)
    event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["rebind", "detach"]
    old_feature_id: str
    old_feature_uuid: uuid.UUID
    replacement_feature_id: str | None = None
    replacement_feature_uuid: uuid.UUID | None = None
    impact_root_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    impact_count: int = Field(ge=0)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_at: datetime


class AdminFeatureReferenceReconciliationImpact(BaseModel):
    """terminal receipt에 고정된 PinVi local row 단위 결과."""

    event_id: uuid.UUID
    impact_index: int = Field(ge=0)
    target_relation: Literal["trip_day_pois", "curated_plan_pois", "feature_suggestions"]
    target_id: uuid.UUID
    old_feature_id: str
    old_feature_uuid: uuid.UUID
    replacement_feature_id: str | None = None
    replacement_feature_uuid: uuid.UUID | None = None
    outcome: Literal["rebind", "detach", "already_reconciled"]
    recorded_at: datetime


class AdminFeatureReferenceReconciliationSummary(BaseModel):
    """운영 목록의 terminal receipt 또는 현재 blocked event."""

    event_id: uuid.UUID
    status: Literal["blocked", "applied"]
    event_sequence: int = Field(ge=1)
    event_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    receipt: AdminFeatureReferenceReconciliationReceipt | None = None
    latest_attempt: AdminFeatureReferenceReconciliationAttempt

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> AdminFeatureReferenceReconciliationSummary:
        if self.status == "applied":
            if self.receipt is None or self.latest_attempt.status != "applied":
                raise ValueError("applied evidence requires receipt and applied latest attempt")
        elif self.receipt is not None or self.latest_attempt.status != "blocked":
            raise ValueError("blocked evidence requires no receipt and blocked latest attempt")
        return self


class AdminFeatureReferenceReconciliationPagedResponse(BaseModel):
    items: list[AdminFeatureReferenceReconciliationSummary] = Field(default_factory=list)
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    limit: int = Field(ge=1, le=100)


class AdminFeatureReferenceReconciliationDetail(BaseModel):
    """한 Map event의 local evidence. blocked event에는 receipt가 없다."""

    event_id: uuid.UUID
    status: Literal["blocked", "applied"]
    receipt: AdminFeatureReferenceReconciliationReceipt | None = None
    attempts: list[AdminFeatureReferenceReconciliationAttempt] = Field(default_factory=list)
    impacts: list[AdminFeatureReferenceReconciliationImpact] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> AdminFeatureReferenceReconciliationDetail:
        latest = self.attempts[0] if self.attempts else None
        if self.status == "applied":
            if self.receipt is None or latest is None or latest.status != "applied":
                raise ValueError("applied evidence requires receipt and applied latest attempt")
        elif (
            self.receipt is not None or latest is None or latest.status != "blocked" or self.impacts
        ):
            raise ValueError(
                "blocked evidence requires no receipt, blocked latest attempt, and no impacts"
            )
        return self
