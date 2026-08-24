"""위치 감사 `purpose` 계약이 코드와 DB 제약 사이에서 갈라지지 않게 고정한다 (T-328).

미들웨어가 발행하는 purpose가 `ck_location_access_log_purpose`에 없으면, outbox 적재는 성공하고
체인 적재만 실패한다 — 즉 **런타임에만, 그것도 조용히** 드러난다. 실제로 `/search`의
`third_party_place_search`가 그 상태였고, drain이 배치 전체를 abort시켜 이후 감사 기록이 멈췄다.

이 테스트는 마이그레이션 소스를 정본으로 읽어 두 목록의 일치를 강제한다. 통합 테스트(DB 필요)와
달리 어디서나 돌기 때문에, 새 purpose를 추가하면서 마이그레이션을 잊으면 곧바로 red가 된다.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.middleware.location_audit import PURPOSE_BY_PATH, _classify_purpose

_MIGRATIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _contracted_purposes() -> set[str]:
    """CHECK 제약을 마지막으로 정의한 마이그레이션에서 허용 목록을 읽는다."""
    latest: tuple[str, set[str]] | None = None
    for path in sorted(_MIGRATIONS.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "ck_location_access_log_purpose" not in source:
            continue
        # upgrade()가 세우는 목록만 본다 — downgrade()의 구 목록에 속으면 안 된다.
        upgrade_src = source.split("def downgrade", 1)[0]
        quoted = set(re.findall(r"'([a-z_]+)'", upgrade_src))
        purposes = {p for p in quoted if p not in {"app", "purpose"}}
        if purposes:
            latest = (path.name, purposes)
    assert latest is not None, "purpose CHECK 제약을 정의하는 마이그레이션을 찾지 못했다"
    return latest[1]


def _emitted_purposes() -> set[str]:
    """미들웨어가 실제로 발행할 수 있는 purpose 전체."""
    emitted = set(PURPOSE_BY_PATH.values())
    # 경로 패턴으로 분기하는 것들은 대표 경로로 확인한다.
    for path in ("/features/f_1/weather", "/features/requests"):
        purpose = _classify_purpose(path)
        if purpose is not None:
            emitted.add(purpose)
    return emitted


def test_every_emitted_purpose_is_allowed_by_the_db_constraint() -> None:
    emitted = _emitted_purposes()
    contracted = _contracted_purposes()
    missing = sorted(emitted - contracted)
    assert not missing, (
        f"미들웨어가 발행하지만 CHECK 제약에 없는 purpose: {missing}. "
        "새 purpose를 추가했다면 마이그레이션으로 제약도 함께 넓혀야 한다."
    )


def test_search_third_party_purpose_is_contracted() -> None:
    """회귀 고정 — 이 값이 빠지면 `/search` 감사가 다시 멈춘다."""
    assert PURPOSE_BY_PATH["/search"] == "third_party_place_search"
    assert "third_party_place_search" in _contracted_purposes()
