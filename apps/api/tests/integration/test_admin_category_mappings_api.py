"""Admin category mapping read-only proxy tests (T-213)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.clients.kor_travel_map import get_kor_travel_map_client
from app.main import app
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    email: str,
    roles: list[str] | None = None,
) -> str:
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash="x",
            status="active",
            roles=roles or ["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.user_id)


class _FakeCategoryClient:
    def __init__(self) -> None:
        self.calls: dict[str, Any] = {}

    async def categories(
        self, *, include_counts: bool = False, active_only: bool = False
    ) -> dict[str, Any]:
        self.calls["categories"] = {
            "include_counts": include_counts,
            "active_only": active_only,
        }
        return {
            "include_counts": include_counts,
            "items": [
                {
                    "code": "01070100",
                    "label": "해수욕장",
                    "parent_code": "010701",
                    "depth": 3,
                    "path": ["자연", "해안", "해수욕장"],
                    "maki_icon": "swimming",
                    "is_active": True,
                    "sort_order": 5,
                    "tier1_code": "01",
                    "tier1_name": "자연",
                    "tier2_code": "0107",
                    "tier2_name": "해안",
                    "tier3_code": "010701",
                    "tier3_name": "해수욕",
                    "tier4_code": "01070100",
                    "tier4_name": "해수욕장",
                    "db_active": True,
                    "db_feature_count": 12,
                },
                {
                    "code": "02010100",
                    "label": "카페",
                    "parent_code": "020101",
                    "depth": 3,
                    "path": ["상업", "음식", "카페"],
                    "maki_icon": "cafe",
                    "is_active": False,
                    "sort_order": 8,
                    "db_active": False,
                    "db_feature_count": 3,
                },
            ],
        }


def _override(fake: _FakeCategoryClient) -> None:
    app.dependency_overrides[get_kor_travel_map_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_client, None)


async def test_admin_category_mappings_proxies_and_filters_catalog(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    user_id = await _create_user(
        session_factory,
        email="operator-category@example.com",
        roles=["user", "operator"],
    )
    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/category-mappings?q=해수&include_counts=true&active_only=false",
            cookies=auth_cookies(user_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert fake.calls["categories"] == {"include_counts": True, "active_only": False}
    assert data["source_of_truth"] == "kor-travel-map:/v1/categories"
    assert data["mode"] == "read_only"
    assert data["total_count"] == 2
    assert data["filtered_count"] == 1
    assert data["active_count"] == 1
    assert data["inactive_count"] == 0
    assert data["db_feature_total"] == 12
    assert data["items"][0]["code"] == "01070100"
    assert data["items"][0]["tier1_name"] == "자연"
    assert data["items"][0]["db_feature_count"] == 12


async def test_admin_category_mappings_is_hidden_for_regular_user(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    user_id = await _create_user(
        session_factory,
        email="regular-category@example.com",
        roles=["user"],
    )
    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.get("/admin/category-mappings", cookies=auth_cookies(user_id))
    finally:
        _clear()

    assert resp.status_code == 404
    assert fake.calls == {}
