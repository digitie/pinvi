"""탈퇴 사용자 익명화가 `app.users`의 모든 컬럼을 **판단하고** 넘어갔는지 (T-337).

`_EXECUTE_PII_SQL`의 `anonymized_users` UPDATE는 지울 컬럼을 손으로 나열한다. 그래서 `app.users`에
새 컬럼이 생기면 **오류 없이** 익명화에서 빠진다 — 개인정보가 조용히 남는다. T-332가 보존
아카이브에서 겪은 것과 정확히 같은 형태의 결함이고, 이쪽은 PIPA 파기 의무(`docs/compliance/pipa.md`)에
걸린다.

지금 빠진 컬럼은 **없다.** 이 테스트는 버그를 고치는 것이 아니라, 다음 컬럼이 생겼을 때 사람이
"이건 지워야 하나?"를 **반드시 한 번 판단하게** 만든다. 판단 결과는 둘 중 하나로 기록된다 —
SQL에 넣거나, 아래 `_INTENTIONALLY_PRESERVED`에 이유와 함께 넣거나.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from app.services.admin_retention import _EXECUTE_PII_SQL

pytestmark = pytest.mark.asyncio

#: 익명화하지 **않는** 컬럼과 그 이유. 여기 넣는 것은 "개인정보가 아니거나, 지우면 안 되는 것"이라는
#: 판단의 기록이다. 이유 없이 추가하지 마라 — 그러면 이 테스트는 아무것도 지키지 않게 된다.
_INTENTIONALLY_PRESERVED: dict[str, str] = {
    "user_id": "PK. 익명화된 이메일이 이 값으로 만들어지고, FK가 걸린 도메인 데이터가 남는다.",
    "roles": "익명화 대상에서 admin/operator/cpo를 제외하는 판정에 쓰인다. 개인정보가 아니다.",
    "deleted_at": "언제 탈퇴했는가 — 파기 기한을 계산하는 근거이며 그 자체가 개인정보가 아니다.",
    "created_at": "계정 생성 시점. 통계·감사용이며 개인을 식별하지 않는다.",
    "updated_at": "행 갱신 시점. 익명화 자체가 이 값을 움직인다.",
}


async def _user_columns(session_factory) -> set[str]:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        rows = await db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'app' AND table_name = 'users'"
            )
        )
        return {r[0] for r in rows}


def _anonymized_columns() -> set[str]:
    """`anonymized_users` CTE의 SET 절이 실제로 건드리는 컬럼."""
    statement = str(_EXECUTE_PII_SQL)
    block = re.search(
        r"anonymized_users AS \(\s*UPDATE app\.users users\s*SET (.*?)\s*FROM ",
        statement,
        re.DOTALL,
    )
    assert block is not None, "anonymized_users의 SET 절을 찾지 못했다"
    # `col = <expr>` 형태의 좌변만 모은다. CASE 안의 `users.email` 같은 참조는 대문자 키워드 뒤라
    # 좌변으로 잡히지 않는다. 첫 컬럼은 `SET`과 같은 줄에 있어 줄머리가 아니므로 들여쓰기를 덧대
    # 같은 규칙으로 읽는다 — 이 보정을 빼면 `email`이 조용히 누락된다.
    clause = "\n      " + block.group(1)
    return set(re.findall(r"^\s{2,}([a-z_]+)\s*=", clause, re.MULTILINE))


async def test_every_user_column_is_either_anonymized_or_justified(session_factory):  # type: ignore[no-untyped-def]
    """모든 컬럼은 지워지거나, 남기는 이유가 적혀 있어야 한다.

    이 테스트가 red면 `app.users`에 컬럼이 생겼다는 뜻이다. **테스트를 고치기 전에** 그 컬럼이
    개인정보인지 판단하라 — 맞으면 `_EXECUTE_PII_SQL`에, 아니면 `_INTENTIONALLY_PRESERVED`에 이유와
    함께 넣어라.
    """
    columns = await _user_columns(session_factory)
    anonymized = _anonymized_columns()

    unjudged = sorted(columns - anonymized - set(_INTENTIONALLY_PRESERVED))
    assert not unjudged, (
        f"익명화도 되지 않고 보존 근거도 없는 `app.users` 컬럼: {unjudged}. "
        "탈퇴 사용자의 이 값들은 파기되지 않고 남는다(PIPA). 지워야 하면 `_EXECUTE_PII_SQL`에, "
        "지우면 안 되면 `_INTENTIONALLY_PRESERVED`에 **이유와 함께** 넣어라."
    )


async def test_preserved_list_does_not_rot(session_factory):  # type: ignore[no-untyped-def]
    """없어진 컬럼이 보존 목록에 남아 있으면 목록이 실제를 반영하지 못한다."""
    columns = await _user_columns(session_factory)
    stale = sorted(set(_INTENTIONALLY_PRESERVED) - columns)
    assert not stale, f"이미 없는 컬럼이 보존 목록에 남아 있다: {stale}"

    overlap = sorted(set(_INTENTIONALLY_PRESERVED) & _anonymized_columns())
    assert not overlap, (
        f"익명화하면서 보존 근거도 적어 둔 컬럼: {overlap}. "
        "둘 중 하나가 낡았다 — 어느 쪽이 참인지 정하고 나머지를 지워라."
    )


async def test_known_pii_columns_are_actually_anonymized(session_factory):  # type: ignore[no-untyped-def]
    """대표적인 식별정보가 실제로 지워지는지 — 목록 대조만으로는 놓치는 회귀를 잡는다.

    `_anonymized_columns()`는 SQL 텍스트를 파싱하므로 파서가 망가지면 조용히 빈 집합을 돌려줄 수
    있다. 그러면 위 두 테스트가 무의미해진다. 여기서 최소한의 앵커를 박아 둔다.
    """
    anonymized = _anonymized_columns()
    for column in ("email", "password_hash", "nickname", "gender", "birth_year_month"):
        assert column in anonymized, f"{column}이 익명화 대상에서 빠졌다"
