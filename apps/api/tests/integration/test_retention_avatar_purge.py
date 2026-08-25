"""PII 익명화가 avatar의 RustFS 실제 객체도 지운다 (T-346).

`_EXECUTE_PII_SQL`은 `avatar_bucket`/`avatar_storage_key` **포인터**만 NULL로 만들었다. 이미지
파일 자체는 RustFS에 그대로 남는 결함이었다 — runbook §5.1의 "삭제·익명화가 실제로 일어났다"는
정의가 코드보다 강했다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.config import get_settings

pytestmark = pytest.mark.asyncio


async def _seed_deletable_user_with_avatar(session_factory, *, storage_key: str) -> uuid.UUID:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        user = User(
            email=f"avatar_{uuid.uuid4().hex[:8]}@pinvi.test",
            status="deleted",
            roles=["user"],
            is_active=False,
            deleted_at=datetime.now(UTC) - timedelta(days=31),
            avatar_bucket="pinvi-attachments",
            avatar_storage_key=storage_key,
            avatar_content_type="image/png",
            avatar_byte_size=1024,
            avatar_kind="upload",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _make_cpo(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        cpo = User(
            email=f"cpo_avatar_{uuid.uuid4().hex[:8]}@pinvi.test",
            status="active",
            roles=["user", "cpo"],
        )
        db.add(cpo)
        await db.commit()
        await db.refresh(cpo)
        return cpo.user_id


async def test_anonymized_users_avatar_object_is_deleted_from_rustfs(
    client, session_factory, auth_cookies, monkeypatch
):  # type: ignore[no-untyped-def]
    """익명화된 사용자의 avatar 키로 `delete_object`가 정확히 1회 불려야 한다."""
    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)

    storage_key = f"avatars/{uuid.uuid4().hex}.png"
    user_id = await _seed_deletable_user_with_avatar(session_factory, storage_key=storage_key)
    cpo_id = await _make_cpo(session_factory)

    deleted_keys: list[str] = []

    async def _fake_delete_object(*, key: str) -> None:
        deleted_keys.append(key)

    from app.services import admin_retention

    monkeypatch.setattr(admin_retention.rustfs_admin, "delete_object", _fake_delete_object)

    res = await client.post(
        "/admin/retention/execute",
        json={
            "scope": "pii",
            "access_reason": "T-346 avatar purge test",
            "confirm_phrase": settings.pinvi_retention_execute_confirm_phrase,
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "completed"
    assert deleted_keys == [storage_key]

    async with session_factory() as db:
        row = (
            (
                await db.execute(
                    text(
                        "SELECT avatar_bucket, avatar_storage_key FROM app.users "
                        "WHERE user_id = :uid"
                    ),
                    {"uid": user_id},
                )
            )
            .mappings()
            .one()
        )
        assert row["avatar_bucket"] is None
        assert row["avatar_storage_key"] is None


async def test_rustfs_delete_failure_does_not_abort_the_run(
    client, session_factory, auth_cookies, monkeypatch
):  # type: ignore[no-untyped-def]
    """RustFS 삭제 하나가 실패해도 PII 익명화 자체는 완료돼야 한다.

    avatar 파일 하나가 RustFS에 남는 대가가, PII 익명화(더 급한 컴플라이언스 요구)까지
    롤백시키는 대가보다 작다 — 실패는 `result`에 남기고 run은 `completed`로 끝난다.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)

    storage_key = f"avatars/{uuid.uuid4().hex}.png"
    user_id = await _seed_deletable_user_with_avatar(session_factory, storage_key=storage_key)
    cpo_id = await _make_cpo(session_factory)

    async def _boom(*, key: str) -> None:
        raise RuntimeError("RustFS 연결 실패")

    from app.services import admin_retention

    monkeypatch.setattr(admin_retention.rustfs_admin, "delete_object", _boom)

    res = await client.post(
        "/admin/retention/execute",
        json={
            "scope": "pii",
            "access_reason": "T-346 avatar purge failure test",
            "confirm_phrase": settings.pinvi_retention_execute_confirm_phrase,
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert res.status_code == 200, res.text
    run = res.json()["data"]
    assert run["status"] == "completed"
    assert run["result"]["pii"]["anonymized_users"] == 1
    assert run["result"]["pii"]["avatar_delete_failures"] == [storage_key]

    async with session_factory() as db:
        # 익명화 자체는 정상 진행됐다 — avatar 삭제 실패가 이걸 되돌리지 않는다.
        email = await db.scalar(
            text("SELECT email FROM app.users WHERE user_id = :uid"), {"uid": user_id}
        )
        assert email == f"deleted+{user_id}@deleted.pinvi.local"
