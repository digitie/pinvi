"""MCP token / tool schemas — ADR-019."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

McpScope = Literal["mcp:read"]
McpTokenStatus = Literal["active", "expired", "revoked"]


def default_mcp_scopes() -> list[McpScope]:
    return ["mcp:read"]


class McpTokenIssueRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_at: datetime | None = None
    scopes: list[McpScope] = Field(default_factory=default_mcp_scopes)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = " ".join(value.split())
        if not stripped:
            raise ValueError("name은 공백만 입력할 수 없습니다.")
        return stripped

    @field_validator("expires_at")
    @classmethod
    def _future_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        if normalized <= datetime.now(UTC):
            raise ValueError("expires_at은 현재 시각 이후여야 합니다.")
        return normalized


class AdminMcpTokenIssueRequest(McpTokenIssueRequest):
    user_id: uuid.UUID
    access_reason: str = Field(min_length=1, max_length=500)


class McpTokenRevokeRequest(BaseModel):
    access_reason: str = Field(min_length=1, max_length=500)


class McpTokenResponse(BaseModel):
    token_id: uuid.UUID
    user_id: uuid.UUID | None = None
    name: str
    scopes: list[McpScope]
    masked_token: str
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class McpTokenIssueResponse(McpTokenResponse):
    token: str


class McpToolDescriptor(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any]


class McpToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpToolCallResponse(BaseModel):
    tool: str
    result: dict[str, Any]
