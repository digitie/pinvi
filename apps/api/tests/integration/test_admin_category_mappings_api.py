"""Admin category mapping override tests (T-264)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.kor_travel_map import get_kor_travel_map_client
from app.main import app
from app.models.audit import AdminAuditLog
from app.models.category_mapping import CategoryMappingOverride
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
    assert data["mode"] == "pinvi_override"
    assert data["total_count"] == 2
    assert data["filtered_count"] == 1
    assert data["active_count"] == 1
    assert data["inactive_count"] == 0
    assert data["db_feature_total"] == 12
    assert data["override_count"] == 0
    assert data["items"][0]["code"] == "01070100"
    assert data["items"][0]["tier1_name"] == "자연"
    assert data["items"][0]["db_feature_count"] == 12
    assert data["items"][0]["upstream_label"] == "해수욕장"
    assert data["items"][0]["effective_label"] == "해수욕장"
    assert data["items"][0]["effective_maki_icon"] == "swimming"
    assert data["items"][0]["has_override"] is False


async def test_admin_category_mappings_merges_pinvi_overrides(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-category-merge@example.com",
        roles=["user", "admin"],
    )
    operator_id = await _create_user(
        session_factory,
        email="operator-category-merge@example.com",
        roles=["user", "operator"],
    )
    async with session_factory() as db:
        db.add(
            CategoryMappingOverride(
                category_key="01070100",
                display_name_ko="부산 해수욕장",
                marker_color="P-03",
                marker_icon="beach",
                created_by_user_id=uuid.UUID(admin_id),
                updated_by_user_id=uuid.UUID(admin_id),
            )
        )
        await db.commit()

    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/category-mappings?q=부산",
            cookies=auth_cookies(operator_id),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["filtered_count"] == 1
    assert data["override_count"] == 1
    item = data["items"][0]
    assert item["code"] == "01070100"
    assert item["label"] == "해수욕장"
    assert item["display_name_ko"] == "부산 해수욕장"
    assert item["marker_color"] == "P-03"
    assert item["marker_icon"] == "beach"
    assert item["effective_label"] == "부산 해수욕장"
    assert item["effective_marker_color"] == "P-03"
    assert item["effective_maki_icon"] == "beach"
    assert item["has_override"] is True
    assert item["override_updated_by_user_id"] == admin_id


async def test_admin_category_mapping_update_writes_override_and_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-category-update@example.com",
        roles=["user", "admin"],
    )
    request_id = uuid.uuid4()
    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.patch(
            "/admin/category-mappings/01070100",
            cookies=auth_cookies(admin_id),
            headers={"X-Request-Id": str(request_id)},
            json={
                "display_name_ko": "테스트 해변",
                "marker_color": "P-04",
                "marker_icon": "park",
                "access_reason": "운영 팔레트 정정",
            },
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]
    assert item["code"] == "01070100"
    assert item["display_name_ko"] == "테스트 해변"
    assert item["effective_marker_color"] == "P-04"
    assert item["effective_maki_icon"] == "park"

    async with session_factory() as db:
        row = await db.get(CategoryMappingOverride, "01070100")
        assert row is not None
        assert row.display_name_ko == "테스트 해변"
        assert row.marker_color == "P-04"
        assert row.marker_icon == "park"
        assert row.updated_by_user_id == uuid.UUID(admin_id)

        audit = await db.scalar(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "category_mapping.update",
                AdminAuditLog.request_id == request_id,
            )
        )
        assert audit is not None
        assert audit.actor_user_id == uuid.UUID(admin_id)
        assert audit.resource_type == "category_mapping"
        assert audit.resource_id == "01070100"
        assert audit.access_reason == "운영 팔레트 정정"
        assert audit.request_id == request_id
        assert audit.after_state is not None
        assert audit.after_state["marker_color"] == "P-04"


async def test_admin_category_mapping_rollback_deletes_override_and_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-category-rollback@example.com",
        roles=["user", "admin"],
    )
    async with session_factory() as db:
        db.add(
            CategoryMappingOverride(
                category_key="01070100",
                display_name_ko="부산 해수욕장",
                marker_color="P-03",
                marker_icon="beach",
                created_by_user_id=uuid.UUID(admin_id),
                updated_by_user_id=uuid.UUID(admin_id),
            )
        )
        await db.commit()

    request_id = uuid.uuid4()
    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.request(
            "DELETE",
            "/admin/category-mappings/01070100",
            cookies=auth_cookies(admin_id),
            headers={"X-Request-Id": str(request_id)},
            json={"access_reason": "override 원복"},
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]
    assert item["code"] == "01070100"
    assert item["has_override"] is False
    assert item["effective_label"] == "해수욕장"

    async with session_factory() as db:
        assert await db.get(CategoryMappingOverride, "01070100") is None
        audit = await db.scalar(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "category_mapping.rollback",
                AdminAuditLog.request_id == request_id,
            )
        )
        assert audit is not None
        assert audit.actor_user_id == uuid.UUID(admin_id)
        assert audit.resource_id == "01070100"
        assert audit.access_reason == "override 원복"
        assert audit.request_id == request_id
        assert audit.before_state is not None
        assert audit.before_state["marker_icon"] == "beach"
        assert audit.after_state is None


@pytest.mark.parametrize(
    ("email", "roles"),
    [
        ("operator-category-patch-denied@example.com", ["user", "operator"]),
        ("regular-category-patch-denied@example.com", ["user"]),
    ],
)
async def test_admin_category_mapping_patch_denied_for_non_admin(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    email: str,
    roles: list[str],
) -> None:
    user_id = await _create_user(session_factory, email=email, roles=roles)
    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.patch(
            "/admin/category-mappings/01070100",
            cookies=auth_cookies(user_id),
            json={
                "display_name_ko": "무단 변경",
                "marker_color": "P-04",
                "marker_icon": "park",
                "access_reason": "권한 없음 검증",
            },
        )
    finally:
        _clear()

    # RBAC: 존재 자체를 숨기므로 404 (require_role("admin"))
    assert resp.status_code == 404, resp.text
    async with session_factory() as db:
        assert await db.get(CategoryMappingOverride, "01070100") is None
        audit = await db.scalar(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "category_mapping.update",
                AdminAuditLog.resource_id == "01070100",
            )
        )
        assert audit is None


@pytest.mark.parametrize(
    ("email", "roles"),
    [
        ("operator-category-delete-denied@example.com", ["user", "operator"]),
        ("regular-category-delete-denied@example.com", ["user"]),
    ],
)
async def test_admin_category_mapping_delete_denied_for_non_admin(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    email: str,
    roles: list[str],
) -> None:
    admin_id = await _create_user(
        session_factory,
        email=f"admin-seed-{email}",
        roles=["user", "admin"],
    )
    async with session_factory() as db:
        db.add(
            CategoryMappingOverride(
                category_key="01070100",
                display_name_ko="부산 해수욕장",
                marker_color="P-03",
                marker_icon="beach",
                created_by_user_id=uuid.UUID(admin_id),
                updated_by_user_id=uuid.UUID(admin_id),
            )
        )
        await db.commit()

    user_id = await _create_user(session_factory, email=email, roles=roles)
    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.request(
            "DELETE",
            "/admin/category-mappings/01070100",
            cookies=auth_cookies(user_id),
            json={"access_reason": "권한 없음 검증"},
        )
    finally:
        _clear()

    assert resp.status_code == 404, resp.text
    async with session_factory() as db:
        # override row가 그대로 남아 있어야 한다 (삭제되지 않음)
        assert await db.get(CategoryMappingOverride, "01070100") is not None
        audit = await db.scalar(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "category_mapping.rollback",
                AdminAuditLog.resource_id == "01070100",
            )
        )
        assert audit is None


async def test_admin_category_mapping_all_null_patch_rolls_back_existing(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-category-allnull@example.com",
        roles=["user", "admin"],
    )
    async with session_factory() as db:
        db.add(
            CategoryMappingOverride(
                category_key="01070100",
                display_name_ko="부산 해수욕장",
                marker_color="P-03",
                marker_icon="beach",
                created_by_user_id=uuid.UUID(admin_id),
                updated_by_user_id=uuid.UUID(admin_id),
            )
        )
        await db.commit()

    request_id = uuid.uuid4()
    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.patch(
            "/admin/category-mappings/01070100",
            cookies=auth_cookies(admin_id),
            headers={"X-Request-Id": str(request_id)},
            json={
                "display_name_ko": None,
                "marker_color": None,
                "marker_icon": None,
                "access_reason": "override 비우기",
            },
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]
    assert item["has_override"] is False
    assert item["effective_label"] == "해수욕장"

    async with session_factory() as db:
        # all-null override는 무의미 → row 삭제 + rollback 감사
        assert await db.get(CategoryMappingOverride, "01070100") is None
        update_audit = await db.scalar(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "category_mapping.update",
                AdminAuditLog.request_id == request_id,
            )
        )
        assert update_audit is None
        rollback_audit = await db.scalar(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "category_mapping.rollback",
                AdminAuditLog.request_id == request_id,
            )
        )
        assert rollback_audit is not None
        assert rollback_audit.before_state is not None
        assert rollback_audit.before_state["marker_icon"] == "beach"
        assert rollback_audit.after_state is None


async def test_admin_category_mapping_all_null_patch_without_existing_is_noop(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-category-allnull-noop@example.com",
        roles=["user", "admin"],
    )
    request_id = uuid.uuid4()
    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.patch(
            "/admin/category-mappings/01070100",
            cookies=auth_cookies(admin_id),
            headers={"X-Request-Id": str(request_id)},
            json={
                "display_name_ko": None,
                "marker_color": None,
                "marker_icon": None,
                "access_reason": "override 없음",
            },
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]
    assert item["has_override"] is False

    async with session_factory() as db:
        # override가 없었으므로 row도, 감사도 생기지 않는다 (noise 없음)
        assert await db.get(CategoryMappingOverride, "01070100") is None
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))
        assert audit is None


async def test_admin_category_mapping_delete_without_override_short_circuits(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-category-delete-noop@example.com",
        roles=["user", "admin"],
    )
    request_id = uuid.uuid4()
    fake = _FakeCategoryClient()
    _override(fake)
    try:
        resp = await client.request(
            "DELETE",
            "/admin/category-mappings/01070100",
            cookies=auth_cookies(admin_id),
            headers={"X-Request-Id": str(request_id)},
            json={"access_reason": "없는 override 원복"},
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]
    assert item["code"] == "01070100"
    assert item["has_override"] is False

    async with session_factory() as db:
        # override가 없으면 rollback 감사 noise를 남기지 않는다
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))
        assert audit is None


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
