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
_PYPROJECT = _ETL_ROOT / "pyproject.toml"
_BUILD_CONSTRAINTS = _ETL_ROOT / "build-constraints.txt"
_ETL_WORKFLOW = _ETL_ROOT.parents[1] / ".github" / "workflows" / "etl.yml"

# 같은 릴리스 번호로 함께 나가는 Dagster 코어 패키지들. `dagster-postgres` 같은
# 통합 라이브러리는 0.x 계열로 따로 번호가 붙지만 patch는 코어와 같이 움직인다.
_DAGSTER_CORE = (
    "dagster",
    "dagster-graphql",
    "dagster-pipes",
    "dagster-shared",
    "dagster-webserver",
)
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

    `pip install pip==<ver>`만 예외다 — 설치 도구 자신이고 앱 의존성이 아니다.
    """
    step = _dependency_install_step()
    installs = re.findall(r"pip install[^&\n]*", step)
    app_installs = [cmd for cmd in installs if not cmd.startswith("pip install pip==")]
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


def _pinned_lines(path: Path) -> dict[str, str]:
    """`name==version` 줄만 모은다(주석·빈 줄 제외). `==`가 아닌 줄은 실패다."""
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, sep, version = line.partition("==")
        assert sep and version.strip(), f"{path.name}에 `==`로 고정되지 않은 줄: {raw!r}"
        pins[name.strip().lower()] = version.strip()
    return pins


def test_the_installer_itself_is_pinned() -> None:
    """`pip install --upgrade pip`는 빌드 시점 최신 pip를 받는다 — 설치 도구도 고정한다."""
    step = _dependency_install_step()
    assert "--upgrade pip" not in step
    assert re.search(r"pip install pip==\d+\.\d+(\.\d+)?\s", step), step


def test_the_build_backend_is_pinned_for_the_editable_install() -> None:
    """`-e .`의 build isolation은 `hatchling>=`를 최신으로 푼다 — 제약 파일로 고정한다."""
    source = _DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY apps/etl/build-constraints.txt /tmp/build-constraints.txt" in source
    (editable,) = re.findall(r"pip install[^&\n]*-e \.", _dependency_install_step())
    assert "--build-constraint /tmp/build-constraints.txt" in editable

    pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    backend = {
        re.split(r"[<>=!~\[ ;]", req, maxsplit=1)[0].lower()
        for req in pyproject["build-system"]["requires"]
    }
    pins = _pinned_lines(_BUILD_CONSTRAINTS)
    assert backend <= pins.keys(), f"고정 안 된 build backend: {sorted(backend - pins.keys())}"


def test_uv_is_one_version_everywhere() -> None:
    """lock을 푸는 uv가 이미지·CI·`[tool.uv] required-version`에서 같은 버전이어야 한다."""
    pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    required = pyproject["tool"]["uv"]["required-version"]
    assert required.startswith("=="), required
    version = required.removeprefix("==")

    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")
    image = re.search(r"^FROM ghcr\.io/astral-sh/uv:([^@\s]+)@", dockerfile, flags=re.MULTILINE)
    assert image is not None and image.group(1) == version, image

    workflow = _ETL_WORKFLOW.read_text(encoding="utf-8")
    ci_versions = re.findall(r"\buv==(\S+)", workflow)
    assert ci_versions == [version], ci_versions


def test_ci_sanity_installs_from_the_lock_like_the_image() -> None:
    """CI가 하한만 보고 최신을 받으면 테스트는 이미지와 다른 버전으로 초록이 된다."""
    workflow = _ETL_WORKFLOW.read_text(encoding="utf-8")
    sanity_block = workflow.split("\n  sanity:\n", 1)[1]
    # 주석은 명령이 아니다 — 옛 설치 방식을 설명하는 주석이 검사에 걸리지 않게 뺀다.
    sanity = "\n".join(
        line for line in sanity_block.splitlines() if not line.lstrip().startswith("#")
    )
    assert "uv --no-cache export --locked --extra dev" in sanity
    installs = re.findall(r"pip install[^\n]*", sanity)
    app_installs = [cmd for cmd in installs if not cmd.startswith("pip install pip==")]
    assert app_installs, "sanity job에 앱 의존성 설치가 없다"
    for cmd in app_installs:
        assert "--no-deps" in cmd, f"--no-deps 없는 pip install: {cmd!r}"
    assert "pip check" in sanity
