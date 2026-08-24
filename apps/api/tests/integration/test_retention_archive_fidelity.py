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
