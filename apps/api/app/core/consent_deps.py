"""위치 동의 dependency — 서버가 좌표를 받기 전에 동의를 확인한다 (T-327).

`docs/architecture/user-location.md` §2는 "동의 철회 시 서버는 다음 요청부터 위치 추론·기록을
거부한다"고, `docs/api/users.md` §3.3은 "`location_collection` 철회 → 사용자 좌표 응답 차단"이라고
적는다. 둘 다 미구현이어서 게이트가 전적으로 클라이언트 책임이었다 — 클라이언트를 우회하면
철회한 사용자의 좌표도 서버가 그대로 받았다.

`lbs_tos`와 `location_collection`을 **모두** 요구한다. 프런트의
`packages/domain/src/locationConsent.ts::hasLocationConsent`가 이미 그렇게 판정하므로, 서버가
느슨하면 두 판정이 갈라진다.

**주의**: 이 게이트는 "사용자 자신의 위치"를 받는 경로에만 건다. 지도 클릭·검색 결과처럼 사용자
위치가 아닌 좌표까지 막으면 동의와 무관한 기능이 깨진다.

게이트는 좌표의 **출처**(`app.core.coord_source.CoordSource`)로 갈린다 — `device`(사용자 자신의
위치)만 막고 `map_pick`(지도에서 고른 지점)은 막지 않는다(ADR-063).

- `GET /features/nearby` — 항상 게이트. endpoint의 의미상 좌표가 사용자 위치일 수밖에 없어
  출처 선언을 받지 않고 서버가 `device`로 고정한다.
- `GET /search`(near-me 분기) — 항상 게이트. 좌표가 **선택적**이라 dependency로 걸면 좌표 없는
  키워드 검색까지 막히므로 핸들러 안 분기에서 검사한다.
- `GET /regions/covering-point`, `GET /regions/within-radius`, `GET /geo/reverse` — 출처를
  query로 받고 `device`일 때만 게이트. 기본값은 `map_pick`이다.
- `POST /features/requests` — 출처를 body로 받고 `device`일 때만 게이트. 기본값은 `map_pick`이다.

출처는 클라이언트의 선언이라 거짓말할 수 있다. 그 한계와 그럼에도 이 설계를 택한 근거는
`app/core/coord_source.py`와 ADR-063에 있다.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, status

from app.core.deps import CurrentUserId, DbSession
from app.services.consent import has_valid_consents

LOCATION_CONSENT_TYPES: tuple[str, ...] = ("lbs_tos", "location_collection")

_FORBIDDEN_DETAIL = {
    "code": "LOCATION_CONSENT_REQUIRED",
    "message": "위치정보 이용 동의가 필요합니다. 설정에서 동의한 뒤 다시 시도해 주세요.",
}


async def assert_location_consent(db: DbSession, *, user_id: uuid.UUID) -> None:
    """동의가 없으면 403. 핸들러 안에서 조건부로 검사할 때 쓴다.

    좌표를 **선택적으로** 받는 endpoint(`/search`의 near-me 분기 등)는 dependency로 걸 수 없다 —
    좌표 없는 요청까지 막히기 때문이다.
    """
    ok = await has_valid_consents(db, user_id=user_id, consent_types=LOCATION_CONSENT_TYPES)
    if not ok:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_DETAIL)


def require_location_consent() -> Callable[[CurrentUserId, DbSession], Awaitable[None]]:
    """좌표를 **항상** 받는 endpoint용 dependency.

    버전은 걸러내지 않는다. 허용 목록 대조는 기록 시점(`ConsentItem.version`)에 하고, 읽기에서
    다시 걸면 과거 버전으로 동의한 사용자의 유효한 동의가 소급해서 무효가 된다.
    """

    async def dependency(current_user_id: CurrentUserId, db: DbSession) -> None:
        await assert_location_consent(db, user_id=uuid.UUID(current_user_id))

    return dependency
