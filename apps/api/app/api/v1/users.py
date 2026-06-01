"""`/users/me/*` — `docs/api/users.md`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUserId, DbSession
from app.schemas.consent import (
    ConsentItem,
    ConsentResponse,
    ConsentType,
    ConsentWithdrawRequest,
    ProfileCompleteRequest,
)
from app.schemas.envelope import Envelope
from app.services.consent import (
    ConsentNotFoundError,
    list_user_consents,
    record_consents,
    withdraw_consent,
)

router = APIRouter(prefix="/users/me", tags=["users"])


@router.post(
    "/profile/complete",
    response_model=Envelope[list[ConsentResponse]],
)
async def complete_profile(
    body: ProfileCompleteRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[ConsentResponse]]:
    # 사용자 모델 갱신은 별 service에서 (Sprint 2 후속 — 본 endpoint는 동의 + 닉네임만)
    rows = await record_consents(db, user_id=uuid.UUID(current_user_id), consents=body.consents)
    return Envelope.of(
        [
            ConsentResponse(
                consent_type=row.consent_type,
                version=row.version,
                agreed_at=row.agreed_at,
                withdrawn_at=row.withdrawn_at,
            )
            for row in rows
        ]
    )


def _to_consent_responses(rows: list) -> list[ConsentResponse]:  # type: ignore[type-arg]
    return [
        ConsentResponse(
            consent_type=row.consent_type,
            version=row.version,
            agreed_at=row.agreed_at,
            withdrawn_at=row.withdrawn_at,
        )
        for row in rows
    ]


@router.put("/consents", response_model=Envelope[list[ConsentResponse]])
async def put_consents(
    body: list[ConsentItem],
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[ConsentResponse]]:
    """동의 항목 기록 (idempotent). `docs/api/users.md` §3."""
    rows = await record_consents(db, user_id=uuid.UUID(current_user_id), consents=body)
    return Envelope.of(_to_consent_responses(rows))


@router.delete("/consents/{consent_type}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consent(
    consent_type: ConsentType,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    """동의 철회 + 부작용 (demographic_use → 인구통계 컬럼 NULL)."""
    try:
        await withdraw_consent(db, user_id=uuid.UUID(current_user_id), consent_type=consent_type)
    except ConsentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get("/consents", response_model=Envelope[list[ConsentResponse]])
async def get_consents(
    current_user_id: CurrentUserId, db: DbSession
) -> Envelope[list[ConsentResponse]]:
    rows = await list_user_consents(db, user_id=uuid.UUID(current_user_id))
    return Envelope.of(
        [
            ConsentResponse(
                consent_type=row.consent_type,
                version=row.version,
                agreed_at=row.agreed_at,
                withdrawn_at=row.withdrawn_at,
            )
            for row in rows
        ]
    )


@router.post(
    "/consents/withdraw",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def withdraw_consent_endpoint(
    body: ConsentWithdrawRequest, current_user_id: CurrentUserId, db: DbSession
) -> None:
    try:
        await withdraw_consent(
            db, user_id=uuid.UUID(current_user_id), consent_type=body.consent_type
        )
    except ConsentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
