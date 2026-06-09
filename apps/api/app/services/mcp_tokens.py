"""MCP token 발급/검증/회수."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from sqlalchemy import Select, String, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.mcp_token import McpToken
from app.models.user import User

_ALGORITHM = "HS256"
_TOKEN_PREFIX = "mcp_"  # noqa: S105 - 토큰 접두어 문자열이며 secret이 아니다.
_READ_SCOPE = "mcp:read"


class McpTokenError(Exception):
    code = "TOKEN_INVALID"


class McpTokenNotFoundError(McpTokenError):
    code = "RESOURCE_NOT_FOUND"


class McpTokenPermissionError(McpTokenError):
    code = "PERMISSION_DENIED"


@dataclass(frozen=True)
class McpPrincipal:
    user_id: uuid.UUID
    token_id: uuid.UUID
    scopes: tuple[str, ...]


def default_mcp_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.tripmate_mcp_token_default_days)


def create_mcp_jwt(
    *,
    user_id: uuid.UUID,
    token_id: uuid.UUID,
    scopes: list[str],
    expires_at: datetime | None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": str(token_id),
        "scope": " ".join(scopes),
        "typ": "mcp",
        "iat": now,
    }
    if expires_at is not None:
        payload["exp"] = expires_at
    encoded = jwt.encode(payload, settings.tripmate_mcp_jwt_secret, algorithm=_ALGORITHM)
    return _TOKEN_PREFIX + str(encoded)


def mask_mcp_token(row: McpToken) -> str:
    return f"{row.token_prefix}...{row.token_suffix}"


async def issue_mcp_token(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    expires_at: datetime | None,
    scopes: Sequence[str] | None = None,
) -> tuple[McpToken, str]:
    effective_scopes = list(scopes or [_READ_SCOPE])
    if set(effective_scopes) != {_READ_SCOPE}:
        raise McpTokenPermissionError("MCP 1차 구현은 mcp:read scope만 허용합니다.")
    user = await db.scalar(select(User).where(User.user_id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise McpTokenNotFoundError("사용자를 찾을 수 없습니다.")

    token_id = uuid.uuid4()
    raw = create_mcp_jwt(
        user_id=user_id,
        token_id=token_id,
        scopes=effective_scopes,
        expires_at=expires_at,
    )
    row = McpToken(
        token_id=token_id,
        user_id=user_id,
        name=name,
        scopes=effective_scopes,
        expires_at=expires_at,
        token_hash=hash_password(raw),
        token_prefix=raw[:12],
        token_suffix=raw[-8:],
    )
    db.add(row)
    await db.flush()
    return row, raw


async def list_user_mcp_tokens(db: AsyncSession, *, user_id: uuid.UUID) -> list[McpToken]:
    result = await db.execute(
        select(McpToken)
        .where(McpToken.user_id == user_id)
        .order_by(McpToken.created_at.desc(), McpToken.token_id.desc())
    )
    return list(result.scalars())


async def list_admin_mcp_tokens(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[McpToken]:
    now = datetime.now(UTC)
    query: Select[tuple[McpToken]] = select(McpToken)
    filters: list[Any] = []
    if user_id is not None:
        filters.append(McpToken.user_id == user_id)
    if status_filter == "active":
        filters.append(McpToken.revoked_at.is_(None))
        filters.append(or_(McpToken.expires_at.is_(None), McpToken.expires_at > now))
    elif status_filter == "expired":
        filters.append(McpToken.revoked_at.is_(None))
        filters.append(McpToken.expires_at.is_not(None))
        filters.append(McpToken.expires_at <= now)
    elif status_filter == "revoked":
        filters.append(McpToken.revoked_at.is_not(None))
    if q:
        normalized_q = f"%{q.strip()}%"
        filters.append(
            or_(
                McpToken.name.ilike(normalized_q),
                cast(McpToken.token_id, String).ilike(normalized_q),
            )
        )
    if filters:
        query = query.where(*filters)
    result = await db.execute(
        query.order_by(McpToken.created_at.desc(), McpToken.token_id.desc()).limit(limit)
    )
    return list(result.scalars())


async def revoke_mcp_token(
    db: AsyncSession,
    *,
    token_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> tuple[McpToken, dict[str, Any]]:
    filters: list[Any] = [McpToken.token_id == token_id]
    if user_id is not None:
        filters.append(McpToken.user_id == user_id)
    row = await db.scalar(select(McpToken).where(*filters))
    if row is None:
        raise McpTokenNotFoundError("MCP 토큰을 찾을 수 없습니다.")
    before = {
        "token_id": str(row.token_id),
        "user_id": str(row.user_id),
        "name": row.name,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await db.flush()
    return row, before


async def authenticate_mcp_token(db: AsyncSession, *, raw_token: str) -> McpPrincipal:
    if not raw_token.startswith(_TOKEN_PREFIX):
        raise McpTokenError("MCP 토큰 형식이 올바르지 않습니다.")
    try:
        payload = jwt.decode(
            raw_token.removeprefix(_TOKEN_PREFIX),
            settings.tripmate_mcp_jwt_secret,
            algorithms=[_ALGORITHM],
        )
    except JWTError as exc:
        raise McpTokenError(str(exc)) from exc
    if payload.get("typ") != "mcp":
        raise McpTokenError("MCP 토큰 typ 클레임이 잘못되었습니다.")
    try:
        token_id = uuid.UUID(str(payload["jti"]))
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise McpTokenError("MCP 토큰 subject가 올바르지 않습니다.") from exc
    scopes = tuple(str(payload.get("scope", "")).split())
    if _READ_SCOPE not in scopes:
        raise McpTokenPermissionError("mcp:read scope가 없습니다.")

    row = await db.scalar(
        select(McpToken).where(
            McpToken.token_id == token_id,
            McpToken.user_id == user_id,
        )
    )
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None:
        raise McpTokenError("MCP 토큰이 회수되었거나 존재하지 않습니다.")
    if row.expires_at is not None and row.expires_at <= now:
        raise McpTokenError("MCP 토큰이 만료되었습니다.")
    if not verify_password(raw_token, row.token_hash):
        raise McpTokenError("MCP 토큰 검증에 실패했습니다.")
    user = await db.scalar(
        select(User).where(
            User.user_id == user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            and_(User.status != "disabled", User.status != "deleted"),
        )
    )
    if user is None:
        raise McpTokenError("사용자를 찾을 수 없습니다.")
    return McpPrincipal(user_id=user_id, token_id=token_id, scopes=scopes)


def token_after_state(row: McpToken) -> dict[str, Any]:
    return {
        "token_id": str(row.token_id),
        "user_id": str(row.user_id),
        "name": row.name,
        "scopes": row.scopes,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }
