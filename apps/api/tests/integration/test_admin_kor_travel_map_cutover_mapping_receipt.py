"""Map cutover identity mapping capture admin command integration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.asyncio


async def _admin(session_factory) -> str:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        admin = User(
            email=f"mapping_capture_{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="mapping capture admin",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()
        return str(admin.user_id)


def _mapping_set(*, root: str = "a" * 64):  # type: ignore[no-untyped-def]
    from app.clients.kor_travel_map_curation import (
        CurationCutoverIdentityMapping,
        CurationCutoverMappingSet,
    )

    return CurationCutoverMappingSet(
        mapping_root_version="ktm-curation-cutover-mapping-v1",
        mapping_count=1,
        mapping_root=root,
        mappings=(
            CurationCutoverIdentityMapping(
                legacy_curated_feature_id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
                collection_id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
                curation_item_id=uuid.UUID("30000000-0000-0000-0000-000000000001"),
                mapping_kind="legacy_projection",
                source_row_hash="b" * 64,
            ),
        ),
    )


class _FakeMappingClient:
    def __init__(self, mapping_set) -> None:  # type: ignore[no-untyped-def]
        self.mapping_set = mapping_set
        self.calls = 0

    async def get_identity_mappings(self):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.mapping_set


async def test_admin_capture_seals_mapping_root_and_replays_exactly(
    client, session_factory, auth_cookies
) -> None:  # type: ignore[no-untyped-def]
    from app.clients.kor_travel_map_curation import get_curation_cutover_mapping_service_client
    from app.main import app
    from app.models.audit import AdminAuditLog
    from app.models.curated_plan import KtmCurationCutoverMappingReceipt

    admin_id = await _admin(session_factory)
    fake = _FakeMappingClient(_mapping_set())
    app.dependency_overrides[get_curation_cutover_mapping_service_client] = lambda: fake
    try:
        created = await client.post(
            "/admin/notice-plans/curation-cutover/mapping-receipts",
            cookies=auth_cookies(admin_id),
        )
        assert created.status_code == 201, created.text
        created_data = created.json()["data"]
        assert created_data["replayed"] is False
        assert created_data["mapping_count"] == 1

        replay = await client.post(
            "/admin/notice-plans/curation-cutover/mapping-receipts",
            cookies=auth_cookies(admin_id),
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["data"] == {**created_data, "replayed": True}

        async with session_factory() as db:
            assert await db.scalar(select(func.count(KtmCurationCutoverMappingReceipt.receipt_id))) == 1
            assert await db.scalar(select(func.count(AdminAuditLog.log_id))) == 1

        fake.mapping_set = _mapping_set(root="c" * 64)
        conflict = await client.post(
            "/admin/notice-plans/curation-cutover/mapping-receipts",
            cookies=auth_cookies(admin_id),
        )
        assert conflict.status_code == 409, conflict.text
        assert fake.calls == 3
    finally:
        app.dependency_overrides.pop(get_curation_cutover_mapping_service_client, None)


async def test_admin_capture_audit_failure_rolls_back_mapping_receipt(
    client, session_factory, auth_cookies, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from app.api.v1.admin import notice_plans as router_module
    from app.clients.kor_travel_map_curation import get_curation_cutover_mapping_service_client
    from app.main import app
    from app.models.curated_plan import KtmCurationCutoverMappingReceipt

    async def _fail_audit(*_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("audit unavailable")

    admin_id = await _admin(session_factory)
    app.dependency_overrides[get_curation_cutover_mapping_service_client] = lambda: _FakeMappingClient(
        _mapping_set()
    )
    monkeypatch.setattr(router_module, "append_admin_audit", _fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            await client.post(
                "/admin/notice-plans/curation-cutover/mapping-receipts",
                cookies=auth_cookies(admin_id),
            )
        async with session_factory() as db:
            assert await db.scalar(select(func.count(KtmCurationCutoverMappingReceipt.receipt_id))) == 0
    finally:
        app.dependency_overrides.pop(get_curation_cutover_mapping_service_client, None)
