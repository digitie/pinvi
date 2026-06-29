"""MCP token API + read-only MCP transport 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.kor_travel_map import KorTravelMapClient
from app.main import app
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


class _StubKorTravelMapClient(KorTravelMapClient):
    """isinstance 통과용 stub — search_features만 고정 응답(http 불필요)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def search_features(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "items": [{"feature_id": "ktm-1", "name": "해운대 해수욕장", "kind": "place"}],
            "meta": {"page": {"size": kwargs.get("page_size")}},
        }


async def test_mcp_read_only_tool_scenario(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    """E2E 시나리오 7 — MCP 토큰으로 읽기 전용 tool 5종 호출 + 회수 실증."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)

    created_trip = await client.post("/trips", json={"title": "MCP 실증 여행"}, cookies=cookies)
    assert created_trip.status_code == 201, created_trip.text
    trip_id = created_trip.json()["data"]["trip_id"]

    issued = await client.post(
        "/users/me/mcp-tokens", json={"name": "Claude Code"}, cookies=cookies
    )
    assert issued.status_code == 201, issued.text
    raw_token = issued.json()["data"]["token"]
    token_id = issued.json()["data"]["token_id"]
    auth = {"Authorization": f"Bearer {raw_token}"}

    # 읽기 전용 5종만 노출(쓰기 tool 없음).
    tools = await client.get("/mcp/tools", headers=auth)
    assert tools.status_code == 200, tools.text
    names = {t["name"] for t in tools.json()["data"]}
    assert names == {"list_trips", "get_trip", "list_pois", "search_features", "get_user_profile"}

    listed = await client.post(
        "/mcp/tools/list_trips", headers=auth, json={"arguments": {"bucket": "all"}}
    )
    assert listed.status_code == 200, listed.text
    assert [i["title"] for i in listed.json()["data"]["result"]["items"]] == ["MCP 실증 여행"]

    got = await client.post(
        "/mcp/tools/get_trip", headers=auth, json={"arguments": {"trip_id": trip_id}}
    )
    assert got.status_code == 200, got.text
    assert "trip" in got.json()["data"]["result"]
    assert "days" in got.json()["data"]["result"]

    pois = await client.post(
        "/mcp/tools/list_pois", headers=auth, json={"arguments": {"trip_id": trip_id}}
    )
    assert pois.status_code == 200, pois.text
    assert pois.json()["data"]["result"]["items"] == []

    profile = await client.post("/mcp/tools/get_user_profile", headers=auth, json={"arguments": {}})
    assert profile.status_code == 200, profile.text
    assert "@" in profile.json()["data"]["result"]["email"]

    # search_features — kor_travel_map client stub 주입(app.state isinstance 게이트).
    app.state.kor_travel_map_client = _StubKorTravelMapClient()
    try:
        search = await client.post(
            "/mcp/tools/search_features",
            headers=auth,
            json={"arguments": {"q": "해운대", "limit": 5}},
        )
    finally:
        app.state.kor_travel_map_client = None
    assert search.status_code == 200, search.text
    assert search.json()["data"]["result"]["items"][0]["name"] == "해운대 해수욕장"

    # 미존재 tool → 404, 잘못된 인자 → 422.
    unknown = await client.post("/mcp/tools/delete_trip", headers=auth, json={"arguments": {}})
    assert unknown.status_code == 404
    bad = await client.post(
        "/mcp/tools/get_trip", headers=auth, json={"arguments": {"trip_id": "not-a-uuid"}}
    )
    assert bad.status_code == 422

    # 토큰 회수 후 호출 차단.
    revoked = await client.delete(f"/users/me/mcp-tokens/{token_id}", cookies=cookies)
    assert revoked.status_code == 204
    denied = await client.post("/mcp/tools/list_trips", headers=auth, json={"arguments": {}})
    assert denied.status_code == 401
