"""`GET /admin/retention/runs`·`/summary`가 실패 원인 원문을 노출하지 않는다 (T-347).

`/execute`의 503 응답은 이미 원문(SQL + 바인드 파라미터일 수 있는 예외 전문)을 감췄다(T-339).
그런데 `error_message` 원문이 이 두 endpoint로는 그대로 나갔고, 그 role 집합(admin/operator/cpo)이
execute의 집합(admin/cpo)보다 **넓다** — 실행 권한이 없는 operator가 원시 SQL을 읽을 수 있었다.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _make_operator(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        operator = User(
            email=f"operator_{uuid.uuid4().hex[:8]}@pinvi.test",
            status="active",
            roles=["user", "operator"],
        )
        db.add(operator)
        await db.commit()
        await db.refresh(operator)
        return operator.user_id


async def _seed_failed_run(session_factory, *, actor_id: uuid.UUID) -> str:  # type: ignore[no-untyped-def]
    """SQL 원문이 담긴 `failed` 영수증을 직접 심는다."""
    raw_error = "psycopg.errors.UniqueViolation: duplicate key value ... ck_t347_marker ..."
    async with session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO app.retention_runs "
                "(run_id, status, mode, access_reason, actor_user_id, error_message) "
                "VALUES (:run_id, 'failed', 'execute', :reason, :actor, :error)"
            ),
            {
                "run_id": uuid.uuid4(),
                "reason": "T-347 masking test",
                "actor": actor_id,
                "error": raw_error,
            },
        )
        await db.commit()
    return raw_error


async def test_runs_list_masks_error_message_for_operator(client, session_factory, auth_cookies):  # type: ignore[no-untyped-def]
    operator_id = await _make_operator(session_factory)
    raw_error = await _seed_failed_run(session_factory, actor_id=operator_id)

    res = await client.get("/admin/retention/runs", cookies=auth_cookies(str(operator_id)))
    assert res.status_code == 200, res.text

    items = res.json()["data"]["items"]
    failed = next(item for item in items if item["status"] == "failed")
    assert failed["error_message"] is not None
    assert raw_error not in failed["error_message"], "원시 SQL이 응답에 그대로 노출됐다"
    assert "ck_t347_marker" not in failed["error_message"]


async def test_summary_masks_error_message_in_latest_runs(client, session_factory, auth_cookies):  # type: ignore[no-untyped-def]
    operator_id = await _make_operator(session_factory)
    raw_error = await _seed_failed_run(session_factory, actor_id=operator_id)

    res = await client.get("/admin/retention/summary", cookies=auth_cookies(str(operator_id)))
    assert res.status_code == 200, res.text

    latest_runs = res.json()["data"]["latest_runs"]
    failed = next((r for r in latest_runs if r["status"] == "failed"), None)
    assert failed is not None, "summary.latest_runs에 방금 심은 실패 run이 없다"
    assert raw_error not in failed["error_message"]


async def test_db_column_keeps_the_original_text(session_factory):  # type: ignore[no-untyped-def]
    """마스킹은 응답 레이어뿐 — DB 컬럼 원문은 runbook §5.2 진단 경로를 위해 그대로 남는다."""
    operator_id = await _make_operator(session_factory)
    raw_error = await _seed_failed_run(session_factory, actor_id=operator_id)

    async with session_factory() as db:
        stored = await db.scalar(
            text("SELECT error_message FROM app.retention_runs WHERE actor_user_id = :actor"),
            {"actor": operator_id},
        )
    assert stored == raw_error
