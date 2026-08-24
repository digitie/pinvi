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
        # purpose 목록을 담는 상수 정의에서만 읽는다. 파일 전체에서 따옴표를 긁으면 같은
        # 마이그레이션의 다른 리터럴(`'device'`, `'map_pick'`, `'succeeded'` 등)까지 "계약된
        # purpose"로 세어 검사가 조용히 헐거워진다(T-329 리뷰 지적).
        blocks = re.findall(
            r"^_\w*PURPOSES\w*\s*=\s*(.+?)(?=^\w|\Z)", upgrade_src, re.MULTILINE | re.DOTALL
        )
        purposes = {p for b in blocks for p in re.findall(r"'([a-z_]+)'", b)}
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


def test_viewport_and_feature_weather_are_no_longer_audited_as_user_location() -> None:
    """지도 뷰포트와 feature 날씨는 **사용자의 위치가 아니다** (T-330).

    `/features/in-bounds`의 bbox는 사용자가 보고 있는 화면 영역이고, `/features/{id}/weather`의
    좌표는 그 feature의 위치다. 둘 다 개인위치정보가 아니므로 확인자료에 넣으면 기록이 부정확해진다.
    실제로 두 경로는 좌표 파라미터를 선언하지도 않아 감사 행을 만든 적이 없었고, 오직 query에
    `lat`/`lng`를 손으로 덧붙였을 때만 거짓 행이 생겼다.

    DB CHECK의 `viewport_query`/`weather_at_coord`는 **그대로 둔다** — 과거에 그렇게 적재된 행이
    있을 수 있고, 제약을 좁혀도 기존 행은 재검증되지 않아 얻는 것이 없다.
    """
    assert _classify_purpose("/features/in-bounds") is None
    assert _classify_purpose("/features/f_1/weather") is None
    assert {"viewport_query", "weather_at_coord"} <= _contracted_purposes()
