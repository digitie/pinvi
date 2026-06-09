"""`/users/me/*` — `docs/api/users.md`."""

from __future__ import annotations

import uuid
from datetime import datetime

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
from app.schemas.mcp import McpTokenIssueRequest, McpTokenIssueResponse, McpTokenResponse
from app.services.consent import (
    ConsentNotFoundError,
    list_user_consents,
    record_consents,
    withdraw_consent,
)
from app.services.mcp_tokens import (
    McpTokenNotFoundError,
    default_mcp_expires_at,
    issue_mcp_token,
    list_user_mcp_tokens,
    mask_mcp_token,
    revoke_mcp_token,
)

router = APIRouter(prefix="/users/me", tags=["users"])


def _effective_expires_at(body: McpTokenIssueRequest) -> datetime | None:
    if "expires_at" in body.model_fields_set:
        return body.expires_at
    return default_mcp_expires_at()


def _mcp_token_response(row) -> McpTokenResponse:  # type: ignore[no-untyped-def]
    return McpTokenResponse(
        token_id=row.token_id,
        name=row.name,
        scopes=row.scopes,
        masked_token=mask_mcp_token(row),
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


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


@router.get("/mcp-tokens", response_model=Envelope[list[McpTokenResponse]])
async def list_mcp_tokens_endpoint(
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[McpTokenResponse]]:
    rows = await list_user_mcp_tokens(db, user_id=uuid.UUID(current_user_id))
    return Envelope.of([_mcp_token_response(row) for row in rows])


@router.post("/mcp-tokens", response_model=Envelope[McpTokenIssueResponse], status_code=201)
async def issue_mcp_token_endpoint(
    body: McpTokenIssueRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[McpTokenIssueResponse]:
    row, raw = await issue_mcp_token(
        db,
        user_id=uuid.UUID(current_user_id),
        name=body.name,
        expires_at=_effective_expires_at(body),
        scopes=body.scopes,
    )
    await db.commit()
    await db.refresh(row)
    base = _mcp_token_response(row)
    return Envelope.of(McpTokenIssueResponse(**base.model_dump(), token=raw))


@router.delete("/mcp-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_mcp_token_endpoint(
    token_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    try:
        await revoke_mcp_token(db, token_id=token_id, user_id=uuid.UUID(current_user_id))
    except McpTokenNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await db.commit()


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
