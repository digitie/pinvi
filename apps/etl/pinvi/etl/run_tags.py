"""PinVi job이 run마다 싣는 Dagster tag.

**왜 instance 설정이 아니라 job tag인가.** `run_monitoring.max_runtime_seconds`는
instance 전역 값이다. PinVi가 자기 instance(`apps/etl/dagster.yaml`)를 쓰는 동안은
그 한 줄로 충분하지만, 공유 Dagster plane(Map·geo·weather와 한 daemon)에서는
instance 값이 테넌트 공통 하나로 정해지고(Map의 21600초) PinVi의 상한은 사라진다.
Dagster는 run tag `dagster/max_runtime`을 instance 값보다 우선하므로, PinVi의
상한을 job에 실어 두면 어느 instance에서 돌든 같은 값이 적용된다.

값 3600초의 근거는 `apps/etl/dagster.yaml`의 `max_runtime_seconds` 주석이다 —
자체 instance를 쓰는 동안 두 값은 테스트(`tests/test_dagster_topology.py`)로
같게 묶인다.

**알려진 예외 — ad-hoc materialization은 instance 기본값을 받는다.** asset UI의
Materialize와 backfill은 Dagster가 만드는 암묵 job `__ASSET_JOB`으로 돈다. 그 job은
PinVi가 정의하지 않으므로 이 tag가 실리지 않고, run은 instance의
`max_runtime_seconds`를 받는다 — 자체 instance에서는 3600초로 같지만 공유 instance
에서는 21600초다. 공유 instance 기본값은 Manager 소유라 여기서 바꾸지 않는다.
필요하면 Launchpad에서 그 run에 `dagster/max_runtime`을 직접 단다. tag 없는 job이
이 하나뿐인지는 `tests/test_definitions.py`가 고정한다.
"""

from __future__ import annotations

PINVI_RUN_MAX_RUNTIME_SECONDS = 3600

# Dagster tag 값은 문자열이다.
PINVI_JOB_TAGS: dict[str, str] = {
    "dagster/max_runtime": str(PINVI_RUN_MAX_RUNTIME_SECONDS),
}
