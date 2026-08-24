"""좌표 범위 — 서로 다른 두 사각형에 이름을 붙인다 (T-331, ADR-064).

저장소에는 오래전부터 lat 범위가 **두 개** 있었고 어느 쪽도 무엇인지 적혀 있지 않았다.

- `33 ~ 43` — `/features/nearby`, `/regions/*`, `CoordSchema`가 쓰는 값. 한반도 전체를 덮으므로
  북한 좌표도 통과한다.
- `33 ~ 39.5` — `new_place` 제안 검증, `ktm_cache_target_heads`/`poi`의 CheckConstraint가 쓰는 값.
  Pinvi가 실제로 서비스하는 범위(남한)다.

둘은 목적이 다르다. 앞은 "이 값이 좌표로서 말이 되는가"(입력 검증)이고, 뒤는 "우리가 서비스하는
곳인가"(서비스 지역)다. 이름이 없으니 서비스 지역을 물어야 할 자리에서 입력 범위를 쓰는 일이
실제로 있었다 — 지도 자동 센터링이 평양을 '국내'로 판정했다(T-325 → T-331에서 수정).

**사각형으로는 정확할 수 없다.** 서비스 범위 사각형은 lat > 39.5(신의주·함흥·청진)와 명백한
국외만 걸러낸다. 대마도(lon 129.2~129.5, lat 34.0~34.7)와 평양(39.03)·개성(37.97)은 통과한다.
그리고 상한을 조여도 고쳐지지 않는다 — **개성(37.97)이 강원 고성(38.38)보다 남쪽이라 어떤
위도선도 남북한을 가르지 못한다.**

그래서 이 값들은 "국내인가"를 답한다고 주장하지 않는다. 답하는 것은 입력 sanity와 "제안을 받을
만한 좌표인가"이며, 틀렸을 때의 결과는 상류가 결과를 못 찾는 것뿐이다. 좌표 기반 **차단**은
현재 존재하지 않는다(ADR-018의 한국 전용 차단은 `app/middleware/geofence.py`의 IP 기반이며
좌표를 보지 않는다). 그런 기능이 생기면 사각형이 아니라 kor-travel-geo 행정구역 조회를 써야
한다 — 근거는 ADR-064.
"""

from __future__ import annotations

from typing import Final

#: 좌표 입력 유효 범위 — 한반도 전체. 검증 실패는 422다.
COORD_LON_MIN: Final = 124.0
COORD_LON_MAX: Final = 132.0
COORD_LAT_MIN: Final = 33.0
COORD_LAT_MAX: Final = 43.0

#: Pinvi 서비스 범위 — 남한. `new_place` 제안과 cache target이 이 값을 쓴다.
SERVICE_AREA_LAT_MAX: Final = 39.5


def is_in_service_area(*, lon: float, lat: float) -> bool:
    """좌표가 Pinvi 서비스 범위 안인지. 입력 유효성(`COORD_*`)과 혼동하지 마라."""
    return COORD_LON_MIN <= lon <= COORD_LON_MAX and COORD_LAT_MIN <= lat <= SERVICE_AREA_LAT_MAX
