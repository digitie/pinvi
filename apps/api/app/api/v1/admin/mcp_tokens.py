"""`/admin/mcp-tokens/*` — MCP token 운영 관리."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.envelope import Envelope
from app.schemas.mcp import (
    AdminMcpTokenIssueRequest,
    McpTokenIssueResponse,
    McpTokenResponse,
    McpTokenRevokeRequest,
)
from app.services.admin_audit import append_admin_audit
from app.services.mcp_tokens import (
    McpTokenNotFoundError,
    default_mcp_expires_at,
    issue_mcp_token,
    list_admin_mcp_tokens,
    mask_mcp_token,
    revoke_mcp_token,
    token_after_state,
)

router = APIRouter(prefix="/admin/mcp-tokens", tags=["admin"])


def _parse_request_id(value: str | None) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "X-Request-Id 형식이 올바르지 않습니다.",
            },
        ) from exc


def _effective_expires_at(body: AdminMcpTokenIssueRequest) -> datetime | None:
    if "expires_at" in body.model_fields_set:
        return body.expires_at
    return default_mcp_expires_at()


def _to_response(row) -> McpTokenResponse:  # type: ignore[no-untyped-def]
    return McpTokenResponse(
        token_id=row.token_id,
        user_id=row.user_id,
        name=row.name,
        scopes=row.scopes,
        masked_token=mask_mcp_token(row),
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


@router.get("", response_model=Envelope[list[McpTokenResponse]])
async def list_mcp_tokens_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator", "cpo"))],
    db: DbSession,
    user_id: uuid.UUID | None = None,
    status_filter: Annotated[
        Literal["active", "expired", "revoked"] | None, Query(alias="status")
    ] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> Envelope[list[McpTokenResponse]]:
    rows = await list_admin_mcp_tokens(
        db,
        user_id=user_id,
        status_filter=status_filter,
        q=q,
        limit=limit,
    )
    return Envelope.of([_to_response(row) for row in rows])


@router.post("", response_model=Envelope[McpTokenIssueResponse], status_code=201)
async def issue_mcp_token_endpoint(
    body: AdminMcpTokenIssueRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[McpTokenIssueResponse]:
    try:
        row, raw = await issue_mcp_token(
            db,
            user_id=body.user_id,
            name=body.name,
            expires_at=_effective_expires_at(body),
            scopes=body.scopes,
        )
    except McpTokenNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="mcp_token.issue",
        resource_type="mcp_token",
        resource_id=str(row.token_id),
        before_state=None,
        after_state=token_after_state(row),
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(row)
    base = _to_response(row)
    return Envelope.of(McpTokenIssueResponse(**base.model_dump(), token=raw))


@router.post("/{token_id}/revoke", response_model=Envelope[McpTokenResponse])
async def revoke_mcp_token_endpoint(
    token_id: uuid.UUID,
    body: McpTokenRevokeRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[McpTokenResponse]:
    try:
        row, before_state = await revoke_mcp_token(db, token_id=token_id)
    except McpTokenNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="mcp_token.revoke",
        resource_type="mcp_token",
        resource_id=str(row.token_id),
        before_state=before_state,
        after_state=token_after_state(row),
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    await db.refresh(row)
    return Envelope.of(_to_response(row))
