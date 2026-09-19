"""Dagster 배포 topology 계약 — instance storage/workspace가 실제로 배송되는지 고정한다.

2026-09-19 N150 실측(PR #558)으로 `apps/etl/dagster.yaml`이 없어 PinVi Dagster가
컨테이너 로컬 SQLite로 조용히 떨어져 있었고, `dagster-postgres` 의존성도 없었다.
그 회귀는 이 파일이 생기기 전에는 어떤 테스트도 잡지 못했다 — 이미지에 굽는
`dagster.yaml`/`workspace.yaml`은 Python import 그래프 밖에 있어
`test_definitions.py`(코드 로케이션만 본다)가 다루지 않는다. 이 파일은 그
사각지대를 덮는다.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

_ETL_ROOT = Path(__file__).resolve().parents[1]
_DAGSTER_YAML = _ETL_ROOT / "dagster.yaml"
_WORKSPACE_YAML = _ETL_ROOT / "workspace.yaml"
_PYPROJECT = _ETL_ROOT / "pyproject.toml"


def _pyproject() -> dict[str, object]:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def test_dagster_postgres_is_a_declared_dependency() -> None:
    """이 패키지가 없으면 Dagster가 경고 한 줄만 남기고 SQLite로 조용히 떨어진다."""
    deps = _pyproject()["project"]["dependencies"]  # type: ignore[index]
    assert any(str(dep).startswith("dagster-postgres") for dep in deps), (
        "`dagster-postgres`가 apps/etl/pyproject.toml dependencies에 없다 — "
        "dagster.yaml이 postgres storage를 선언해도 이 패키지가 없으면 "
        "instance 기동이 SQLite로 조용히 대체된다."
    )


def test_dagster_yaml_declares_postgres_storage() -> None:
    """instance storage 셋(run/event log/schedule)이 전부 Postgres여야 한다.

    셋 중 하나만 옮기면 "일부는 postgres, 일부는 SQLite"인 가장 나쁜 상태가
    되므로(apps/etl/dagster.yaml 주석 참조) 셋을 따로 재지 않고 shorthand
    `storage.postgres` 형태 하나로만 통과시킨다.
    """
    config = yaml.safe_load(_DAGSTER_YAML.read_text(encoding="utf-8"))
    storage = config.get("storage") or {}
    assert "postgres" in storage, (
        "apps/etl/dagster.yaml의 storage가 postgres shorthand를 쓰지 않는다 — "
        f"실제: {sorted(storage)}. run/event log/schedule 중 일부만 postgres로 "
        "옮기는 실수를 이 shorthand 하나가 구조적으로 막는다."
    )
    postgres_url = storage["postgres"].get("postgres_url") or {}
    assert postgres_url.get("env") == "PINVI_DAGSTER_PG_URL", (
        "dagster.yaml의 postgres_url env 이름이 PINVI_DAGSTER_PG_URL이 아니다 — "
        "Manager compose가 이 정확한 이름으로 값을 주입한다."
    )


def test_dagster_yaml_enables_run_monitoring() -> None:
    """`run_monitoring`이 꺼지면 죽은 run이 영원히 STARTED로 남아도 아무도 모른다.

    형제 프로젝트 kor-travel-weather가 같은 호스트에서 이것 때문에 수집을 두 번
    잃었다(두 번째는 18시간).
    """
    config = yaml.safe_load(_DAGSTER_YAML.read_text(encoding="utf-8"))
    run_monitoring = config.get("run_monitoring") or {}
    assert run_monitoring.get("enabled") is True, (
        "apps/etl/dagster.yaml의 run_monitoring이 꺼져 있다 — 프로세스가 사라진 "
        "run을 회수하는 유일한 기제다."
    )
    assert isinstance(run_monitoring.get("max_runtime_seconds"), int), (
        "run_monitoring.max_runtime_seconds가 없다 — 살아 있지만 끼인 run은 "
        "liveness 검사로 잡히지 않으므로 이 상한만이 그것을 끝낸다."
    )


def test_workspace_yaml_grpc_server_matches_the_code_location() -> None:
    """workspace.yaml의 location_name이 실제 code location 모듈과 어긋나면 안 된다.

    ADR-069 — webserver/daemon은 이 파일을 통해 code-server(gRPC)에 접속하고
    더 이상 `pinvi.etl.definitions`를 직접 import하지 않는다.
    """
    workspace = yaml.safe_load(_WORKSPACE_YAML.read_text(encoding="utf-8"))
    load_from = workspace.get("load_from") or []
    assert len(load_from) == 1, f"load_from 항목이 정확히 1개가 아니다: {load_from!r}"
    grpc_server = load_from[0].get("grpc_server") or {}
    module_name = _pyproject()["tool"]["dagster"]["module_name"]  # type: ignore[index]
    assert grpc_server.get("location_name") == module_name, (
        f"workspace.yaml의 location_name({grpc_server.get('location_name')!r})이 "
        f"pyproject.toml의 [tool.dagster].module_name({module_name!r})과 다르다 — "
        "code-server가 로드하는 모듈과 webserver/daemon이 찾는 위치가 어긋난다."
    )
    assert isinstance(grpc_server.get("port"), int), "grpc_server.port가 정수로 선언돼 있지 않다."


def test_workspace_yaml_uses_loopback_not_a_service_name() -> None:
    """PinVi 배포는 host network mode다 — bridge network 서비스명 DNS가 없다.

    kor-travel-weather의 workspace.yaml은 `host: dagster-code-server`(bridge
    network 서비스명)를 쓰지만, PinVi는 Manager compose와 자체 dev compose 모두
    `network_mode: host`로 뜬다(ADR-047, ADR-069) — 서비스명으로 바꾸면 DNS
    해석이 실패해 코드 로케이션 로드 자체가 안 된다.
    """
    workspace = yaml.safe_load(_WORKSPACE_YAML.read_text(encoding="utf-8"))
    grpc_server = workspace["load_from"][0]["grpc_server"]
    assert grpc_server.get("host") == "127.0.0.1", (
        f"workspace.yaml의 host가 127.0.0.1이 아니다: {grpc_server.get('host')!r} — "
        "host network mode에서는 서비스명이 resolve되지 않는다(ADR-069 참조)."
    )
