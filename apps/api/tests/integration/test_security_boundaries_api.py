"""Sprint 6 security boundary regression tests (T-283)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    email_prefix: str,
    roles: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="보안 경계 테스트",
            status="active",
            roles=roles or ["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _issue_mcp_token(client: Any, *, cookies: dict[str, str], name: str) -> str:
    issued = await client.post(
        "/users/me/mcp-tokens",
        json={"name": name},
        cookies=cookies,
    )
    assert issued.status_code == 201, issued.text
    raw_token = issued.json()["data"]["token"]
    assert raw_token.startswith("mcp_")
    return str(raw_token)


async def test_mcp_token_and_web_access_token_are_not_interchangeable(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    mcp_token = await _issue_mcp_token(client, cookies=cookies, name="security boundary")
    web_access_token = cookies["pinvi_access"]

    web_with_mcp = await client.get(
        "/trips",
        headers={"Authorization": f"Bearer {mcp_token}"},
    )
    assert web_with_mcp.status_code == 401
    assert web_with_mcp.json()["error"]["code"] == "TOKEN_INVALID"

    mcp_with_web = await client.get(
        "/mcp/tools",
        headers={"Authorization": f"Bearer {web_access_token}"},
    )
    assert mcp_with_web.status_code == 401
    assert mcp_with_web.json()["error"]["code"] == "TOKEN_INVALID"


async def test_share_token_is_route_scoped_hidden_and_revocable(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "공유 보안"}, cookies=cookies)
    assert created.status_code == 201, created.text
    trip_id = created.json()["data"]["trip_id"]
    other_created = await client.post("/trips", json={"title": "다른 여행"}, cookies=cookies)
    assert other_created.status_code == 201, other_created.text
    other_trip_id = other_created.json()["data"]["trip_id"]

    issued = await client.post(
        f"/trips/{trip_id}/share-tokens",
        json={"visibility": "view_only"},
        cookies=cookies,
    )
    assert issued.status_code == 201, issued.text
    share = issued.json()["data"]
    token = share["token"]

    owner_detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert owner_detail.status_code == 200, owner_detail.text
    owner_share = owner_detail.json()["data"]["share_links"][0]
    assert owner_share["share_id"] == share["share_id"]
    assert "token" not in owner_share
    assert token not in owner_detail.text

    wrong_trip = await client.get(f"/trips/{other_trip_id}/shared/{token}")
    assert wrong_trip.status_code == 404

    shared = await client.get(f"/trips/{trip_id}/shared/{token}")
    assert shared.status_code == 200, shared.text
    shared_data = shared.json()["data"]
    assert shared_data["visibility"] == "view_only"
    assert "share_links" not in shared_data
    assert "companions" not in shared_data

    revoked = await client.delete(
        f"/trips/{trip_id}/share-tokens/{share['share_id']}",
        cookies=cookies,
    )
    assert revoked.status_code == 204

    after_revoke = await client.get(f"/trips/{trip_id}/shared/{token}")
    assert after_revoke.status_code == 404


async def test_admin_only_storage_upload_purpose_rejects_user_and_mcp_credentials(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    mcp_token = await _issue_mcp_token(client, cookies=cookies, name="storage boundary")
    body = {
        "filename": "cover.jpg",
        "content_type": "image/jpeg",
        "content_length": 1024,
        "purpose": "curated_plan_attachment",
    }

    missing_auth = await client.post("/storage/upload-urls", json=body)
    assert missing_auth.status_code == 401

    hidden_from_user = await client.post("/storage/upload-urls", json=body, cookies=cookies)
    assert hidden_from_user.status_code == 404

    mcp_bearer = await client.post(
        "/storage/upload-urls",
        json=body,
        headers={"Authorization": f"Bearer {mcp_token}"},
    )
    assert mcp_bearer.status_code == 401
    assert mcp_bearer.json()["error"]["code"] == "TOKEN_INVALID"

    admin_id = await _create_user(
        session_factory,
        email_prefix="storage-admin",
        roles=["user", "admin"],
    )
    allowed = await client.post(
        "/storage/upload-urls",
        json=body,
        cookies=auth_cookies(str(admin_id)),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["data"]["storage_key"].startswith(
        f"user-uploads/curated_plan_attachment/{admin_id}/"
    )


async def test_security_incident_console_hides_from_operator_role(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    operator_id = await _create_user(
        session_factory,
        email_prefix="incident-operator",
        roles=["user", "operator"],
    )
    hidden = await client.get("/admin/incidents", cookies=auth_cookies(str(operator_id)))

    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
