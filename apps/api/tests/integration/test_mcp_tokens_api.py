"""MCP token API + read-only MCP transport 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.models.audit import AdminAuditLog
from app.models.mcp_token import McpToken
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    email: str,
    roles: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash="x",
            nickname="MCP 테스트",
            status="active",
            roles=roles or ["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def test_user_issues_uses_and_revokes_mcp_token(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)

    created_trip = await client.post(
        "/trips",
        json={"title": "MCP 부산 여행"},
        cookies=cookies,
    )
    assert created_trip.status_code == 201, created_trip.text

    issued = await client.post(
        "/users/me/mcp-tokens",
        json={"name": "Claude Desktop"},
        cookies=cookies,
    )
    assert issued.status_code == 201, issued.text
    issued_data = issued.json()["data"]
    raw_token = issued_data["token"]
    assert raw_token.startswith("mcp_")
    assert issued_data["masked_token"].startswith("mcp_")

    listed = await client.get("/users/me/mcp-tokens", cookies=cookies)
    assert listed.status_code == 200
    assert listed.json()["data"][0]["token_id"] == issued_data["token_id"]
    assert "token" not in listed.json()["data"][0]

    sse = await client.get("/mcp/sse", headers={"Authorization": f"Bearer {raw_token}"})
    assert sse.status_code == 200, sse.text
    assert "event: tools" in sse.text
    assert "list_trips" in sse.text

    tool = await client.post(
        "/mcp/tools/list_trips",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"arguments": {"bucket": "all"}},
    )
    assert tool.status_code == 200, tool.text
    result = tool.json()["data"]["result"]
    assert [item["title"] for item in result["items"]] == ["MCP 부산 여행"]
    assert result["has_more"] is False

    async with session_factory() as db:
        stored = await db.scalar(
            select(McpToken).where(McpToken.token_id == uuid.UUID(issued_data["token_id"]))
        )
        assert stored is not None
        assert stored.last_used_at is not None

    revoked = await client.delete(
        f"/users/me/mcp-tokens/{issued_data['token_id']}",
        cookies=cookies,
    )
    assert revoked.status_code == 204

    denied = await client.get("/mcp/tools", headers={"Authorization": f"Bearer {raw_token}"})
    assert denied.status_code == 401


async def test_admin_issues_lists_and_revokes_mcp_token_with_audit(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="mcp-admin@example.com",
        roles=["user", "admin"],
    )
    target_id = await _create_user(session_factory, email="mcp-user@example.com")
    cookies = auth_cookies(str(admin_id))

    issue_request_id = uuid.uuid4()
    issued = await client.post(
        "/admin/mcp-tokens",
        headers={"X-Request-Id": str(issue_request_id)},
        json={
            "user_id": str(target_id),
            "name": "고객 지원 대리 발급",
            "access_reason": "고객 요청",
        },
        cookies=cookies,
    )
    assert issued.status_code == 201, issued.text
    token_id = issued.json()["data"]["token_id"]
    assert issued.json()["data"]["user_id"] == str(target_id)
    assert issued.json()["data"]["token"].startswith("mcp_")

    listed = await client.get("/admin/mcp-tokens?status=active", cookies=cookies)
    assert listed.status_code == 200
    assert [row["token_id"] for row in listed.json()["data"]] == [token_id]

    revoke_request_id = uuid.uuid4()
    revoked = await client.post(
        f"/admin/mcp-tokens/{token_id}/revoke",
        headers={"X-Request-Id": str(revoke_request_id)},
        json={"access_reason": "토큰 유출 의심"},
        cookies=cookies,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["revoked_at"] is not None

    async with session_factory() as db:
        issue_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == issue_request_id)
        )
        revoke_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == revoke_request_id)
        )

    assert issue_audit is not None
    assert issue_audit.action == "mcp_token.issue"
    assert issue_audit.resource_id == token_id
    assert revoke_audit is not None
    assert revoke_audit.action == "mcp_token.revoke"
    assert revoke_audit.access_reason == "토큰 유출 의심"
