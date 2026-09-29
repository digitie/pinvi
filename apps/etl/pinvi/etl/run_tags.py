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
"""

from __future__ import annotations

PINVI_RUN_MAX_RUNTIME_SECONDS = 3600

# Dagster tag 값은 문자열이다.
PINVI_JOB_TAGS: dict[str, str] = {
    "dagster/max_runtime": str(PINVI_RUN_MAX_RUNTIME_SECONDS),
}
