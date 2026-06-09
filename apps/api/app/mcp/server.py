"""FastAPI MCP transport endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.deps import DbSession
from app.mcp.auth import require_mcp_read
from app.mcp.tools import TOOL_DESCRIPTORS, call_tool
from app.schemas.envelope import Envelope
from app.schemas.mcp import McpToolCallRequest, McpToolCallResponse, McpToolDescriptor
from app.services.mcp_tokens import McpPrincipal

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/tools", response_model=Envelope[list[McpToolDescriptor]])
async def list_mcp_tools(
    _principal: Annotated[McpPrincipal, Depends(require_mcp_read)],
) -> Envelope[list[McpToolDescriptor]]:
    return Envelope.of(TOOL_DESCRIPTORS)


@router.get("/sse")
async def mcp_sse(
    _principal: Annotated[McpPrincipal, Depends(require_mcp_read)],
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        payload = {"tools": [tool.model_dump() for tool in TOOL_DESCRIPTORS]}
        import json

        yield f"event: tools\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/tools/{tool_name}", response_model=Envelope[McpToolCallResponse])
async def call_mcp_tool(
    tool_name: str,
    body: McpToolCallRequest,
    request: Request,
    principal: Annotated[McpPrincipal, Depends(require_mcp_read)],
    db: DbSession,
) -> Envelope[McpToolCallResponse]:
    result = await call_tool(
        name=tool_name,
        arguments=body.arguments,
        user_id=principal.user_id,
        db=db,
        request=request,
    )
    return Envelope.of(McpToolCallResponse(tool=tool_name, result=result))
