"""실패한 retention execute도 admin_audit_log에 흔적을 남긴다 (T-342).

`docs/compliance/lbs-act.md` §3.4는 "모든 실행은 `retention_runs`와 `admin_audit_log`에 evidence를
남긴다"고 적는다. `retention_runs`는 T-338/T-339이 실패해도 남게 고쳤지만, `admin_audit_log`는
성공 경로에서만 적재됐다 — 문서와 코드가 갈라져 있었다. 이 파일은 그 간극을 메운 뒤 남는지 확인한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _audit_rows(session_factory, actor_id):  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT action, resource_id FROM app.admin_audit_log "
                    "WHERE actor_user_id = :actor AND action = 'retention.execute_failed'"
                ),
                {"actor": actor_id},
            )
        ).mappings()
        return list(rows)


async def test_service_layer_failure_still_leaves_an_audit_row(
    client, session_factory, verified_user, auth_cookies, monkeypatch
):  # type: ignore[no-untyped-def]
    """실행이 서비스 레이어(파괴 SQL 실행 중)에서 실패해도 `admin_audit_log`에 시도 기록이 남는다.

    DB CHECK 위반으로 진짜 abort를 만든다 — 이 경로가 route의 **첫 번째** except 블록
    (`execute_retention()` 자체의 `RetentionExecutionError`)을 타므로, `append_admin_audit`이
    라우트 후단과 달리 이번엔 monkeypatch되지 않는다.
    """
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)
    cpo_id, _ = verified_user

    async with session_factory() as db:
        from app.models.user import User

        cpo = await db.get(User, uuid.UUID(cpo_id))
        cpo.roles = ["user", "cpo"]  # type: ignore[union-attr]
        await db.commit()

    old = datetime.now(UTC) - timedelta(days=400)
    async with session_factory() as db:
        from app.services.location_audit import append_location_log

        await append_location_log(
            db,
            user_id=uuid.UUID(cpo_id),
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("37.5665"),
            lng=Decimal("126.9780"),
            request_id=uuid.uuid4(),
            ip_hash="ab" * 32,
            occurred_at=old,
        )

    async with session_factory() as db:
        await db.execute(
            text(
                "ALTER TABLE app.location_access_log_archive "
                "DROP CONSTRAINT IF EXISTS ck_t342_abort"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE app.location_access_log_archive "
                "ADD CONSTRAINT ck_t342_abort CHECK (purpose <> 'nearby_attractions')"
            )
        )
        await db.commit()

    try:
        res = await client.post(
            "/admin/retention/execute",
            json={
                "scope": "location",
                "access_reason": "T-342 service-layer failure test",
                "confirm_phrase": settings.pinvi_retention_execute_confirm_phrase,
            },
            cookies=auth_cookies(cpo_id),
        )
    finally:
        async with session_factory() as db:
            await db.execute(
                text(
                    "ALTER TABLE app.location_access_log_archive "
                    "DROP CONSTRAINT IF EXISTS ck_t342_abort"
                )
            )
            await db.commit()

    assert res.status_code == 503, res.text

    rows = await _audit_rows(session_factory, uuid.UUID(cpo_id))
    assert len(rows) == 1, "서비스 레이어 실패가 admin_audit_log에 남지 않았다"
    assert rows[0]["resource_id"] is not None, (
        "run이 만들어진 뒤의 실패이니 resource_id가 있어야 한다"
    )


async def test_gate_rejection_still_leaves_an_audit_row_without_a_run(
    client, session_factory, verified_user, auth_cookies, monkeypatch
):  # type: ignore[no-untyped-def]
    """kill-switch에 막혀 run조차 만들어지지 않아도 "시도했다"는 기록은 남아야 한다.

    누가 언제 kill-switch 상태에서 실행을 시도했는지는 실행이 성공했는지와 무관하게 감사 가치가
    있다 — 반복 시도는 우회 시도의 신호일 수 있다. 이 경로는 run이 없으므로 `resource_id`가 없다.
    """
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", False, raising=False)
    cpo_id, _ = verified_user

    async with session_factory() as db:
        from app.models.user import User

        cpo = await db.get(User, uuid.UUID(cpo_id))
        cpo.roles = ["user", "cpo"]  # type: ignore[union-attr]
        await db.commit()

    res = await client.post(
        "/admin/retention/execute",
        json={
            "scope": "location",
            "access_reason": "T-342 kill-switch test",
            "confirm_phrase": settings.pinvi_retention_execute_confirm_phrase,
        },
        cookies=auth_cookies(cpo_id),
    )
    assert res.status_code == 409, res.text

    rows = await _audit_rows(session_factory, uuid.UUID(cpo_id))
    assert len(rows) == 1
    assert rows[0]["resource_id"] is None, "run을 만들기도 전에 막혔으니 resource_id가 없어야 한다"
