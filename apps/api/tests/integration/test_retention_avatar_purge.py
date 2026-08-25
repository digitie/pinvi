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


async def test_avatar_delete_runs_after_pii_anonymization_is_committed(
    client, session_factory, auth_cookies, monkeypatch
):  # type: ignore[no-untyped-def]
    """avatar RustFS 삭제가 시작되는 시점에는 PII 익명화가 이미 커밋돼 있어야 한다(T-346 수정).

    적대적 리뷰로 발견된 회귀: 예전에는 avatar 삭제가 아직 커밋되지 않은 파괴 트랜잭션 안에서
    일어났다 — RustFS I/O 대기 중 T-341의 `idle_in_transaction_session_timeout`(60초)에 걸리면
    이미 끝난 PII 익명화까지 롤백될 위험이 있었다(avatar 파일 하나가 남는 대가가 PII 롤백보다
    낫다는 이 모듈 자신의 설계 의도와 정반대).

    `delete_object`가 불리는 시점에 **별도 커넥션**으로 조회해서 이미 익명화된 이메일이 보이면,
    그 시점에 원래 트랜잭션이 이미 커밋됐다는 뜻이다(READ COMMITTED에서 미커밋 변경은 다른
    커넥션에 보이지 않는다).
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)

    storage_key = f"avatars/{uuid.uuid4().hex}.png"
    user_id = await _seed_deletable_user_with_avatar(session_factory, storage_key=storage_key)
    cpo_id = await _make_cpo(session_factory)

    visible_during_delete: list[str | None] = []

    async def _fake_delete_object(*, key: str) -> None:
        async with session_factory() as probe_db:
            email = await probe_db.scalar(
                text("SELECT email FROM app.users WHERE user_id = :uid"), {"uid": user_id}
            )
        visible_during_delete.append(email)

    from app.services import admin_retention

    monkeypatch.setattr(admin_retention.rustfs_admin, "delete_object", _fake_delete_object)

    res = await client.post(
        "/admin/retention/execute",
        json={
            "scope": "pii",
            "access_reason": "T-346 avatar-delete-after-commit regression test",
            "confirm_phrase": settings.pinvi_retention_execute_confirm_phrase,
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert res.status_code == 200, res.text
    assert visible_during_delete == [f"deleted+{user_id}@deleted.pinvi.local"]


async def test_avatar_purge_partial_failure_only_flags_the_failed_key(
    client, session_factory, auth_cookies, monkeypatch
):  # type: ignore[no-untyped-def]
    """avatar 보유 사용자 2명 중 1명만 RustFS 삭제 실패해도 실패 키만 정확히 기록된다.

    단일 사용자 시나리오만 커버하던 기존 테스트의 회귀 방지 공백(적대적 리뷰 지적)을 메운다.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)

    ok_key = f"avatars/{uuid.uuid4().hex}.png"
    fail_key = f"avatars/{uuid.uuid4().hex}.png"
    ok_user_id = await _seed_deletable_user_with_avatar(session_factory, storage_key=ok_key)
    fail_user_id = await _seed_deletable_user_with_avatar(session_factory, storage_key=fail_key)
    cpo_id = await _make_cpo(session_factory)

    deleted_keys: list[str] = []

    async def _partial_delete(*, key: str) -> None:
        if key == fail_key:
            raise RuntimeError("RustFS 연결 실패")
        deleted_keys.append(key)

    from app.services import admin_retention

    monkeypatch.setattr(admin_retention.rustfs_admin, "delete_object", _partial_delete)

    res = await client.post(
        "/admin/retention/execute",
        json={
            "scope": "pii",
            "access_reason": "T-346 avatar partial failure test",
            "confirm_phrase": settings.pinvi_retention_execute_confirm_phrase,
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert res.status_code == 200, res.text
    run = res.json()["data"]
    assert run["status"] == "completed"
    assert run["result"]["pii"]["anonymized_users"] == 2
    assert run["result"]["pii"]["avatar_delete_failures"] == [fail_key]
    assert deleted_keys == [ok_key]

    async with session_factory() as db:
        ok_email = await db.scalar(
            text("SELECT email FROM app.users WHERE user_id = :uid"), {"uid": ok_user_id}
        )
        fail_email = await db.scalar(
            text("SELECT email FROM app.users WHERE user_id = :uid"), {"uid": fail_user_id}
        )
    assert ok_email == f"deleted+{ok_user_id}@deleted.pinvi.local"
    assert fail_email == f"deleted+{fail_user_id}@deleted.pinvi.local"
