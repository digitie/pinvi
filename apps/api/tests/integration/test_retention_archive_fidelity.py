"""보존 아카이브가 확인자료의 **무손실 사본**인지 (T-332).

`docs/data-model.md` §8.12가 아카이브를 "동일 payload로 복사"로 규정한다. 이 불변식은 그냥 좋은
성질이 아니라 필수 조건이다 — 아카이브 직후 원본이 삭제되므로 아카이브가 **유일한 사본**이 되고,
행의 `content_hash`는 원본의 모든 필드를 커밋하고 있어 하나라도 빠지면 그 행은 영구히 재검증
불가가 된다. 위변조 탐지 근거가 사라진다는 뜻이다.

이 불변식은 조용히 깨진다. `_ARCHIVE_LOCATION_SQL`이 컬럼을 명시 나열하기 때문에 원본에 컬럼이
늘어도 INSERT는 **오류 없이** 성공하고, 빠진 값은 원본 삭제와 함께 사라진다. 실제로 T-329가
`coord_source`를 추가하면서 그렇게 깨뜨렸다. 그래서 사람의 기억이 아니라 테스트가 지킨다.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from app.services.admin_retention import _ARCHIVE_LOCATION_SQL

pytestmark = pytest.mark.asyncio

#: 아카이브에만 있는 컬럼 — 사본이 아니라 "언제/어느 실행으로 옮겼는가"라는 아카이브 자체의 사실이다.
_ARCHIVE_ONLY_COLUMNS = {"retention_run_id", "archived_at"}


async def _columns(session_factory, table: str) -> dict[str, tuple]:  # type: ignore[no-untyped-def]
    """컬럼 이름 → 타입. **이름만 보면 부족하다** — 원본 `text`를 아카이브가 `varchar(16)`로 받으면
    컬럼은 있는데 값이 조용히 잘린다. 사본이 원본을 담을 수 있는지는 타입까지 봐야 안다.
    """
    async with session_factory() as db:
        rows = await db.execute(
            text(
                "SELECT column_name, data_type, character_maximum_length, "
                "numeric_precision, numeric_scale FROM information_schema.columns "
                "WHERE table_schema = 'app' AND table_name = :t"
            ),
            {"t": table},
        )
        return {r[0]: tuple(r[1:]) for r in rows}


async def test_archive_table_can_hold_every_source_column(session_factory):  # type: ignore[no-untyped-def]
    """원본의 모든 컬럼이 아카이브에도 있어야 한다.

    없으면 그 값은 아카이브 시점에 사라지고, 원본은 곧바로 삭제되므로 되돌릴 수 없다.
    """
    source = await _columns(session_factory, "location_access_log")
    archive = await _columns(session_factory, "location_access_log_archive")

    missing = sorted(set(source) - set(archive))
    assert not missing, (
        f"원본에는 있고 아카이브에는 없는 컬럼: {missing}. "
        "아카이브는 원본 삭제 후 유일한 사본이므로 이 값들은 영구히 사라진다. "
        "마이그레이션으로 아카이브 테이블에도 컬럼을 추가하라."
    )
    assert set(archive) - set(source) == _ARCHIVE_ONLY_COLUMNS

    narrowed = {
        name: (source[name], archive[name]) for name in source if source[name] != archive[name]
    }
    assert not narrowed, (
        f"원본과 타입이 다른 아카이브 컬럼: {narrowed}. "
        "컬럼이 있어도 타입이 좁으면 값이 조용히 잘린다 — 사본이 원본을 담지 못한다."
    )


async def test_archive_statement_copies_every_shared_column(session_factory):  # type: ignore[no-untyped-def]
    """테이블에 컬럼이 있어도 **INSERT 나열에서 빠지면** 값은 복사되지 않는다.

    스키마 검사만으로는 부족하다는 뜻이다 — 실제 T-332의 결함이 여기 있었다. 컬럼은 원본에만
    추가됐고 SQL은 손대지 않아, 아카이브가 조용히 NULL을 채웠다.
    """
    source = set(await _columns(session_factory, "location_access_log"))

    statement = str(_ARCHIVE_LOCATION_SQL)
    insert_columns = re.search(
        r"INSERT INTO app\.location_access_log_archive\s*\(([^)]*)\)", statement, re.DOTALL
    )
    assert insert_columns is not None, "아카이브 INSERT의 컬럼 나열을 찾지 못했다"
    listed = {c.strip() for c in insert_columns.group(1).split(",") if c.strip()}

    missing = sorted(source - listed)
    assert not missing, (
        f"아카이브 INSERT가 복사하지 않는 원본 컬럼: {missing}. "
        "테이블에 컬럼이 있어도 나열에서 빠지면 값은 복사되지 않고, 원본은 곧바로 삭제된다."
    )

    # 대상 나열만 보면 부족하다 — 이름을 넣고 값으로 `NULL`을 주면 나열은 완전한데 값은 사라진다.
    # PostgreSQL은 개수만 맞추므로 그런 statement도 오류 없이 실행된다. 그래서 값을 공급하는
    # SELECT 투영이 대상 컬럼과 **같은 순서로 같은 이름**인지까지 본다.
    projection = re.search(r"SELECT\s+(.*?)\s+FROM app\.location_access_log", statement, re.DOTALL)
    assert projection is not None, "아카이브 INSERT의 SELECT 투영을 찾지 못했다"
    selected = [c.strip() for c in projection.group(1).split(",") if c.strip()]
    target = [c.strip() for c in insert_columns.group(1).split(",") if c.strip()]
    assert len(selected) == len(target), (
        f"대상 컬럼 {len(target)}개와 SELECT 표현식 {len(selected)}개의 개수가 다르다"
    )
    mismatched = {
        t: sel
        for t, sel in zip(target, selected, strict=True)
        if t != sel and not sel.startswith(":")
    }
    assert not mismatched, (
        f"대상 컬럼과 다른 값을 공급하는 자리: {mismatched}. "
        "이름을 나열해 놓고 값으로 NULL이나 다른 컬럼을 주면 아카이브는 조용히 위조된다."
    )


async def test_archived_row_keeps_the_coordinate_source(session_factory):  # type: ignore[no-untyped-def]
    """실제로 한 행을 아카이브해 출처가 따라가는지 본다 — 계약이 아니라 동작을 본다."""
    import uuid
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.models.user import User
    from app.services.location_audit import append_location_log

    async with session_factory() as db:
        user = User(email=f"arch_{uuid.uuid4().hex[:8]}@pinvi.test", status="active")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.user_id

    old = datetime.now(UTC) - timedelta(days=400)
    async with session_factory() as db:
        await append_location_log(
            db,
            user_id=user_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("37.5665"),
            lng=Decimal("126.9780"),
            request_id=uuid.uuid4(),
            ip_hash="ab" * 32,
            coord_source="device",
            occurred_at=old,
        )

    run_id = uuid.uuid4()
    async with session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO app.retention_runs "
                "(run_id, status, mode, access_reason, actor_user_id) "
                "VALUES (:run_id, 'completed', 'execute', :reason, :actor)"
            ),
            {
                "run_id": run_id,
                "reason": "T-332 archive fidelity test",
                "actor": user_id,
            },
        )
        await db.execute(
            _ARCHIVE_LOCATION_SQL,
            {"run_id": run_id, "archive_cutoff": datetime.now(UTC) - timedelta(days=1)},
        )
        await db.commit()

    async with session_factory() as db:
        row = (
            await db.execute(
                text(
                    "SELECT coord_source, content_hash, prev_hash, lat, lng, purpose, endpoint, "
                    "ip_hash, request_id, occurred_at, user_id "
                    "FROM app.location_access_log_archive WHERE retention_run_id = :run_id"
                ),
                {"run_id": run_id},
            )
        ).mappings()
        archived = list(row)

    assert len(archived) == 1
    assert archived[0]["coord_source"] == "device"

    # 사본만으로 원래 해시를 재현할 수 있어야 한다 — 그게 아카이브가 증거인 이유다.
    from app.services.hash_chain import compute_content_hash
    from app.services.location_audit import location_log_payload

    a = archived[0]
    expected = compute_content_hash(
        a["prev_hash"],
        location_log_payload(
            user_id=a["user_id"],
            occurred_at=a["occurred_at"],
            endpoint=a["endpoint"],
            purpose=a["purpose"],
            lat=a["lat"],
            lng=a["lng"],
            request_id=a["request_id"],
            ip_hash=a["ip_hash"],
            coord_source=a["coord_source"],
        ),
    )
    assert a["content_hash"] == expected


# --------------------------------------------------------------------------------------
# 아카이브도 append-only다 (T-336)
# --------------------------------------------------------------------------------------


async def test_archive_rows_cannot_be_updated_or_deleted(session_factory):  # type: ignore[no-untyped-def]
    """원본이 삭제된 뒤 **유일한 사본**이 되는 테이블이 수정 가능해서는 안 된다.

    `trg_location_access_log_append_only`는 원본에만 걸려 있었다 — 보호가 가장 필요해지는 순간
    (아카이브 후)에 보호가 사라지는 구조였다. `session_replication_role = replica`로도 우회되지
    않아야 하므로 `ENABLE ALWAYS`다.
    """
    from sqlalchemy.exc import DBAPIError

    log_id = await _seed_archived_row(session_factory)

    statements = (
        (
            "UPDATE app.location_access_log_archive SET purpose = 'viewport_query' "
            "WHERE log_id = :log_id"
        ),
        "DELETE FROM app.location_access_log_archive WHERE log_id = :log_id",
        "TRUNCATE app.location_access_log_archive",
    )
    for statement in statements:
        async with session_factory() as db:
            await db.execute(text("SET LOCAL session_replication_role = replica"))
            with pytest.raises(DBAPIError):
                await db.execute(text(statement), {"log_id": log_id})
            await db.rollback()


async def test_retention_delete_permission_does_not_open_the_archive(session_factory):  # type: ignore[no-untyped-def]
    """retention이 원본 삭제를 여는 GUC는 **아카이브에는 적용되지 않는다**.

    가드 함수의 예외 절이 `TG_TABLE_NAME = 'location_access_log'`로 좁혀져 있어 그렇다. 이 성질이
    깨지면 retention 트랜잭션 하나가 원본과 사본을 동시에 지울 수 있게 된다.
    """
    from sqlalchemy.exc import DBAPIError

    log_id = await _seed_archived_row(session_factory)

    async with session_factory() as db:
        await db.execute(
            text("SELECT set_config('app.retention_location_delete_allowed', 'on', true)")
        )
        # 원본은 이 트랜잭션에서 지울 수 있다(정상 retention 경로).
        await db.execute(
            text("DELETE FROM app.location_access_log WHERE log_id = :log_id"), {"log_id": log_id}
        )
        # 같은 트랜잭션에서도 아카이브는 열리지 않는다.
        with pytest.raises(DBAPIError):
            await db.execute(
                text("DELETE FROM app.location_access_log_archive WHERE log_id = :log_id"),
                {"log_id": log_id},
            )
        await db.rollback()


async def _seed_archived_row(session_factory) -> int:  # type: ignore[no-untyped-def]
    """원본 1행을 만들고 아카이브까지 복사한 뒤 그 log_id를 돌려준다."""
    import uuid
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.models.user import User
    from app.services.location_audit import append_location_log

    async with session_factory() as db:
        user = User(email=f"lock_{uuid.uuid4().hex[:8]}@pinvi.test", status="active")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.user_id

    async with session_factory() as db:
        row = await append_location_log(
            db,
            user_id=user_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("37.5665"),
            lng=Decimal("126.9780"),
            request_id=uuid.uuid4(),
            ip_hash="ab" * 32,
            coord_source="device",
            occurred_at=datetime.now(UTC) - timedelta(days=400),
        )
        log_id = row.log_id

    run_id = uuid.uuid4()
    async with session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO app.retention_runs "
                "(run_id, status, mode, access_reason, actor_user_id) "
                "VALUES (:run_id, 'completed', 'execute', :reason, :actor)"
            ),
            {"run_id": run_id, "reason": "T-336 append-only test", "actor": user_id},
        )
        await db.execute(
            _ARCHIVE_LOCATION_SQL,
            {"run_id": run_id, "archive_cutoff": datetime.now(UTC) - timedelta(days=1)},
        )
        await db.commit()

    return int(log_id)


# --------------------------------------------------------------------------------------
# 체인 검증이 아카이브 경계를 넘는다 (T-335)
# --------------------------------------------------------------------------------------


async def test_chain_survives_archiving_the_older_rows(
    client, session_factory, verified_user, auth_cookies
):  # type: ignore[no-untyped-def]
    """아카이브 실행 후에도 확인자료 열람이 체인 파손을 보고하면 안 된다.

    앵커 조회가 active 테이블만 보면, 원본이 삭제된 뒤 최고참 행의 `prev_hash`가 아카이브된 해시를
    가리키는데 앵커는 `None`이라 `GENESIS_HASH`와 비교돼 **상시 불일치**한다. 위변조 탐지가 항상
    켜지면 실제 변조와 구분할 수 없다 — T-329 리뷰가 잡은 차단 결함과 같은 계열이다.
    """
    import uuid
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.models.user import User
    from app.services.location_audit import append_location_log

    async with session_factory() as db:
        cpo = User(
            email=f"bridge_cpo_{uuid.uuid4().hex[:8]}@pinvi.test",
            status="active",
            roles=["user", "cpo"],
        )
        db.add(cpo)
        await db.commit()
        await db.refresh(cpo)
        cpo_id = str(cpo.user_id)

    subject_id, _ = verified_user
    now = datetime.now(UTC)

    # 오래된 행 2건 + 최근 행 2건. 앞의 둘만 아카이브 대상이 된다.
    for age_days in (400, 380, 5, 1):
        async with session_factory() as db:
            await append_location_log(
                db,
                user_id=uuid.UUID(subject_id),
                endpoint="/features/nearby",
                purpose="nearby_attractions",
                lat=Decimal("37.5665"),
                lng=Decimal("126.9780"),
                request_id=uuid.uuid4(),
                ip_hash="ab" * 32,
                coord_source="device",
                occurred_at=now - timedelta(days=age_days),
            )

    run_id = uuid.uuid4()
    cutoff = now - timedelta(days=300)
    async with session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO app.retention_runs "
                "(run_id, status, mode, access_reason, actor_user_id) "
                "VALUES (:run_id, 'completed', 'execute', :reason, :actor)"
            ),
            {"run_id": run_id, "reason": "T-335 bridge test", "actor": uuid.UUID(subject_id)},
        )
        await db.execute(_ARCHIVE_LOCATION_SQL, {"run_id": run_id, "archive_cutoff": cutoff})
        await db.execute(
            text("SELECT set_config('app.retention_location_delete_allowed', 'on', true)")
        )
        await db.execute(
            text(
                "DELETE FROM app.location_access_log active "
                "WHERE active.occurred_at <= :cutoff AND EXISTS ("
                "  SELECT 1 FROM app.location_access_log_archive archive "
                "  WHERE archive.log_id = active.log_id)"
            ),
            {"cutoff": cutoff},
        )
        await db.commit()

    res = await client.get(
        f"/admin/audit/location?user_id={subject_id}&limit=10",
        cookies=auth_cookies(cpo_id),
    )
    assert res.status_code == 200, res.text
    assert len(res.json()["data"]) == 2
    assert res.headers.get("X-Chain-Broken") is None


async def test_append_after_full_archive_keeps_the_chain_linked(session_factory):  # type: ignore[no-untyped-def]
    """전량 아카이브 후 새로 쓰는 행은 **아카이브의 마지막 해시**에 이어져야 한다.

    쓰기 측도 active 테이블만 보고 있었다. 그대로 두면 배수 직후의 첫 행이 `GENESIS_HASH`로 체인을
    조용히 재시작하고, 끊긴 자리가 영구히 남는다 — 읽기 측만 고치면 오탐이 자리만 옮긴다.
    """
    import uuid
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.models.user import User
    from app.services.hash_chain import GENESIS_HASH
    from app.services.location_audit import append_location_log

    async with session_factory() as db:
        user = User(email=f"tail_{uuid.uuid4().hex[:8]}@pinvi.test", status="active")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.user_id

    now = datetime.now(UTC)
    async with session_factory() as db:
        first = await append_location_log(
            db,
            user_id=user_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("37.5665"),
            lng=Decimal("126.9780"),
            request_id=uuid.uuid4(),
            ip_hash="ab" * 32,
            occurred_at=now - timedelta(days=400),
        )
        archived_hash = first.content_hash

    run_id = uuid.uuid4()
    async with session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO app.retention_runs "
                "(run_id, status, mode, access_reason, actor_user_id) "
                "VALUES (:run_id, 'completed', 'execute', :reason, :actor)"
            ),
            {"run_id": run_id, "reason": "T-335 tail test", "actor": user_id},
        )
        await db.execute(
            _ARCHIVE_LOCATION_SQL,
            {"run_id": run_id, "archive_cutoff": now - timedelta(days=1)},
        )
        await db.execute(
            text("SELECT set_config('app.retention_location_delete_allowed', 'on', true)")
        )
        await db.execute(text("DELETE FROM app.location_access_log"))
        await db.commit()

    async with session_factory() as db:
        following = await append_location_log(
            db,
            user_id=user_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("35.1796"),
            lng=Decimal("129.0756"),
            request_id=uuid.uuid4(),
            ip_hash="cd" * 32,
        )

    assert following.prev_hash == archived_hash
    assert following.prev_hash != GENESIS_HASH


# --------------------------------------------------------------------------------------
# 실패한 실행도 영수증을 남긴다 (T-338)
# --------------------------------------------------------------------------------------


async def test_failed_execute_receipt_survives_the_callers_rollback(session_factory, monkeypatch):  # type: ignore[no-untyped-def]
    """영수증이 호출부의 `rollback()`을 견디는지 — **그것만** 본다.

    이전에는 영수증 행이 파괴적 작업과 같은 트랜잭션이라 호출부 rollback이 함께 지웠다.

    **이 테스트의 한계를 알고 써라.** 실패를 순수 파이썬 예외로 만들기 때문에 세션이 abort 상태가
    아니다. 그래서 기록 구현이 '같은 세션 + rollback 없이 commit'으로 퇴화해도 green이다.
    abort 상태와 락 보유 상태는 아래 두 테스트가 각각 맡는다.
    """
    import uuid

    from app.core.config import get_settings
    from app.models.user import User
    from app.services import admin_retention

    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)

    async with session_factory() as db:
        actor = User(
            email=f"ret_{uuid.uuid4().hex[:8]}@pinvi.test", status="active", roles=["user", "cpo"]
        )
        db.add(actor)
        await db.commit()
        await db.refresh(actor)
        actor_id = actor.user_id

    async def _boom(*args: object, **kwargs: object) -> dict[str, int]:
        raise RuntimeError("아카이브 중 실패")

    monkeypatch.setattr(admin_retention, "_execute_location_archive", _boom)

    async with session_factory() as db:
        with pytest.raises(admin_retention.RetentionExecutionError):
            await admin_retention.execute_retention(
                db,
                actor_user_id=actor_id,
                scope="location",
                access_reason="T-338 failure receipt test",
                confirm_phrase=settings.pinvi_retention_execute_confirm_phrase,
            )
        # 호출부가 하는 일 — 실패하면 롤백한다. 영수증은 이것을 견뎌야 한다.
        await db.rollback()

    async with session_factory() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT status, error_message FROM app.retention_runs "
                    "WHERE actor_user_id = :actor ORDER BY started_at DESC"
                ),
                {"actor": actor_id},
            )
        ).mappings()
        receipts = list(rows)

    assert len(receipts) == 1, "실패한 실행의 영수증이 남지 않았다"
    assert receipts[0]["status"] == "failed"
    assert "아카이브 중 실패" in (receipts[0]["error_message"] or "")


async def test_receipt_survives_a_database_abort_and_work_is_discarded(
    session_factory, monkeypatch
):  # type: ignore[no-untyped-def]
    """**DB 오류로 트랜잭션이 abort된 뒤에도** 영수증이 남고, 파괴적 작업은 폐기돼야 한다.

    실패를 파이썬 예외로 만들면 세션이 멀쩡해서 어떤 기록 구현이든 통과한다. 진짜 조건은 abort다 —
    그 상태에서는 rollback 없이 아무 문장도 실행되지 않는다.

    동시에 **파괴적 작업이 실제로 폐기됐는지**를 데이터로 확인한다. 영수증만 보면, 실패한 실행이
    삭제를 커밋해 버리는 구현도 green이 된다.
    """
    import uuid
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.core.config import get_settings
    from app.models.user import User
    from app.services import admin_retention
    from app.services.location_audit import append_location_log

    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)

    old = datetime.now(UTC) - timedelta(days=400)
    async with session_factory() as db:
        actor = User(
            email=f"ab_{uuid.uuid4().hex[:8]}@pinvi.test", status="active", roles=["user", "cpo"]
        )
        victim = User(
            email=f"victim_{uuid.uuid4().hex[:8]}@pinvi.test",
            nickname="지울이름",
            gender="female",
            status="deleted",
            deleted_at=old,
        )
        db.add_all([actor, victim])
        await db.commit()
        await db.refresh(actor)
        await db.refresh(victim)
        actor_id, victim_id = actor.user_id, victim.user_id
        victim_email = victim.email

    async with session_factory() as db:
        await append_location_log(
            db,
            user_id=actor_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("37.5665"),
            lng=Decimal("126.9780"),
            request_id=uuid.uuid4(),
            ip_hash="ab" * 32,
            occurred_at=old,
        )

    # 결함을 **DB에서** 주입한다. 아카이브 INSERT가 여기서 터지므로 그 시점 트랜잭션은 abort가 되고,
    # PII 익명화는 이미 실행된 뒤다 — "파괴적 작업이 일부 수행된 뒤 실패"를 정확히 만든다.
    async with session_factory() as db:
        await db.execute(
            text(
                "ALTER TABLE app.location_access_log_archive "
                "ADD CONSTRAINT ck_t340_abort CHECK (purpose <> 'nearby_attractions')"
            )
        )
        await db.commit()

    try:
        async with session_factory() as db:
            with pytest.raises(admin_retention.RetentionExecutionError):
                await admin_retention.execute_retention(
                    db,
                    actor_user_id=actor_id,
                    scope="all",
                    access_reason="T-340 abort test",
                    confirm_phrase=settings.pinvi_retention_execute_confirm_phrase,
                )
            await db.rollback()
    finally:
        # 반드시 fresh 세션에서 지운다 — 오염된 세션으로는 DDL이 실행되지 않는다. 남기면 이후의
        # 모든 아카이브 테스트가 오염된다(컨테이너가 세션 스코프다).
        async with session_factory() as db:
            await db.execute(
                text("ALTER TABLE app.location_access_log_archive DROP CONSTRAINT ck_t340_abort")
            )
            await db.commit()

    async with session_factory() as db:
        receipts = list(
            (
                await db.execute(
                    text(
                        "SELECT status, result, error_message FROM app.retention_runs "
                        "WHERE actor_user_id = :actor"
                    ),
                    {"actor": actor_id},
                )
            ).mappings()
        )
        assert len(receipts) == 1
        assert receipts[0]["status"] == "failed"
        # 파이썬 가짜 실패가 아니라 DB abort였음을 못 박는다.
        assert "ck_t340_abort" in (receipts[0]["error_message"] or "")

        # 파괴적 작업은 폐기됐다 — 익명화도, 아카이브도, 삭제도 남지 않았다.
        row = (
            (
                await db.execute(
                    text("SELECT email, nickname, gender FROM app.users WHERE user_id = :uid"),
                    {"uid": victim_id},
                )
            )
            .mappings()
            .one()
        )
        assert row["email"] == victim_email, "실패한 실행이 익명화를 커밋했다"
        assert row["nickname"] == "지울이름"
        assert row["gender"] == "female"

        live = await db.scalar(text("SELECT count(*) FROM app.location_access_log"))
        archived = await db.scalar(text("SELECT count(*) FROM app.location_access_log_archive"))
        assert live == 1, "실패한 실행이 원본 삭제를 커밋했다"
        assert archived == 0


async def test_failure_after_the_completed_update_does_not_hang(session_factory, monkeypatch):  # type: ignore[no-untyped-def]
    """`completed` UPDATE가 **성공한 뒤** 실패해도 매달리지 않아야 한다.

    그 시점 트랜잭션은 그 행에 `FOR NO KEY UPDATE` 락을 쥐고 있다. 별도 세션으로 같은 행을 UPDATE하면
    **무기한 블록된다** — 대기 그래프에 간선이 하나뿐이라 PostgreSQL이 deadlock으로 탐지하지 못하고,
    이 프로세스에는 `lock_timeout`도 `statement_timeout`도 없다. 기록 전에 rollback해 락을 먼저
    놓는 것이 그 창을 없앤다.

    **타임아웃 없이는 이 테스트를 쓰지 마라** — 회귀 시 실패가 아니라 스위트 전체가 매달린다.
    """
    import asyncio
    import uuid

    from app.core.config import get_settings
    from app.models.user import User
    from app.services import admin_retention

    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)

    async with session_factory() as db:
        actor = User(
            email=f"hang_{uuid.uuid4().hex[:8]}@pinvi.test", status="active", roles=["user", "cpo"]
        )
        db.add(actor)
        await db.commit()
        await db.refresh(actor)
        actor_id = actor.user_id

    def _boom(row: object) -> None:
        raise RuntimeError("completed UPDATE 직후 실패")

    # `_UPDATE_RUN_SQL`이 성공해 락을 잡은 **직후** 파이썬 예외를 만든다.
    monkeypatch.setattr(admin_retention, "_run_from_row", _boom)

    async with session_factory() as db:
        with pytest.raises(admin_retention.RetentionExecutionError):
            await asyncio.wait_for(
                admin_retention.execute_retention(
                    db,
                    actor_user_id=actor_id,
                    scope="location",
                    access_reason="T-340 hang test",
                    confirm_phrase=settings.pinvi_retention_execute_confirm_phrase,
                ),
                timeout=20,
            )
        await db.rollback()

    async with session_factory() as db:
        status = await db.scalar(
            text("SELECT status FROM app.retention_runs WHERE actor_user_id = :actor"),
            {"actor": actor_id},
        )
        assert status == "failed"
