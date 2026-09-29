"""ETL 이미지가 Dagster를 `uv.lock`의 정확한 버전으로만 설치하는지 고정한다.

2026-09-29 n150 실측: `apps/etl/uv.lock`은 dagster 1.13.23인데 운영 이미지는
1.13.24였다. Dockerfile이 `pip install -e .`로 pyproject의 하한(`dagster>=1.9`)만
보고 빌드 시점 PyPI 최신을 받았기 때문이다 — lock은 아무것도 고정하지 않았다.

공유 Dagster plane(webserver/daemon 하나가 Map·PinVi·geo·weather의 code-server를
부른다)에서는 **host 버전 ≥ code-server 버전**이 Dagster 호환 정책이다. 고정되지
않은 설치는 rebuild 한 번으로 code-server를 host보다 새 버전으로 올릴 수 있고,
그 드리프트는 아무 경고도 남기지 않는다. 이 파일은 그 경로를 닫는다.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_ETL_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = _ETL_ROOT / "Dockerfile"
_UV_LOCK = _ETL_ROOT / "uv.lock"

# 같은 릴리스 번호로 함께 나가는 Dagster 코어 패키지들. `dagster-postgres` 같은
# 통합 라이브러리는 0.x 계열로 따로 번호가 붙지만 patch는 코어와 같이 움직인다.
_DAGSTER_CORE = ("dagster", "dagster-graphql", "dagster-pipes", "dagster-shared", "dagster-webserver")
_DAGSTER_INTEGRATIONS = ("dagster-postgres",)


def _locked_versions() -> dict[str, str]:
    lock = tomllib.loads(_UV_LOCK.read_text(encoding="utf-8"))
    return {pkg["name"]: pkg["version"] for pkg in lock["package"] if "version" in pkg}


def _dependency_install_step() -> str:
    """의존성을 설치하는 `RUN` 한 덩어리(연속 줄 포함)를 돌려준다."""
    source = _DOCKERFILE.read_text(encoding="utf-8")
    steps = re.findall(r"^RUN (?:[^\n]*\\\n)*[^\n]*$", source, flags=re.MULTILINE)
    installs = [step for step in steps if "pip install" in step]
    assert len(installs) == 1, f"pip install을 하는 RUN이 정확히 하나가 아니다: {installs!r}"
    return installs[0]


def test_the_lockfile_is_copied_into_the_build() -> None:
    source = _DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY apps/etl/uv.lock ./uv.lock" in source


def test_the_install_list_is_exported_from_the_lock_and_checked_against_pyproject() -> None:
    """`--locked`: pyproject가 lock과 어긋나면 export가 실패해 빌드가 선다."""
    step = _dependency_install_step()
    assert "uv --no-cache export --locked" in step
    assert "--no-dev" in step
    assert "--no-emit-project" in step


def test_every_pip_install_refuses_unlisted_packages() -> None:
    """`--no-deps`가 없으면 pip가 하한만 보고 목록 밖 버전을 끌어올 수 있다.

    `pip install --upgrade pip`만 예외다 — 설치 도구 자신이고 앱 의존성이 아니다.
    """
    step = _dependency_install_step()
    installs = re.findall(r"pip install[^&\n]*", step)
    app_installs = [cmd for cmd in installs if "--upgrade pip" not in cmd]
    assert app_installs, "앱 의존성을 설치하는 pip install이 없다"
    for cmd in app_installs:
        assert "--no-deps" in cmd, f"--no-deps 없는 pip install: {cmd!r}"
    assert "pip check" in step, "설치 목록이 불완전해도 빌드가 통과한다 — `pip check`가 없다"


def test_the_dagster_family_is_locked_to_one_release() -> None:
    """코어 패키지가 서로 다른 릴리스면 lock 갱신이 반쯤만 된 것이다."""
    versions = _locked_versions()
    core = {name: versions[name] for name in _DAGSTER_CORE}
    assert len(set(core.values())) == 1, f"Dagster 코어 버전이 갈라졌다: {core!r}"
    core_patch = next(iter(core.values())).split(".")[2]
    for name in _DAGSTER_INTEGRATIONS:
        assert versions[name].split(".")[2] == core_patch, (
            f"{name} {versions[name]}이 Dagster 코어 {core!r}와 같은 릴리스가 아니다"
        )
