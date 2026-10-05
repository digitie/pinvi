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


def _pip_installs(text: str) -> list[str]:
    """`pip install ...` 명령을 줄 끝 `\\` 연속 기호와 공백을 떼고 모은다."""
    return [
        cmd.rstrip("\\ ").strip() for cmd in re.findall(r"(?:python -m )?pip install[^&\n]*", text)
    ]


def _image_pip_version() -> str:
    """이미지가 설치 도구로 까는 pip 버전. 그 명령은 **정확히** `pip install pip==<ver>`다."""
    tools = [cmd for cmd in _pip_installs(_dependency_install_step()) if " pip==" in cmd]
    assert len(tools) == 1, tools
    matched = re.fullmatch(r"pip install pip==(\d+\.\d+(?:\.\d+)?)", tools[0])
    assert matched is not None, f"설치 도구 명령에 다른 것이 섞였다: {tools[0]!r}"
    return matched.group(1)


def _sanity_commands() -> str:
    workflow = _ETL_WORKFLOW.read_text(encoding="utf-8")
    sanity_block = workflow.split("\n  sanity:\n", 1)[1]
    # 주석은 명령이 아니다 — 옛 설치 방식을 설명하는 주석이 검사에 걸리지 않게 뺀다.
    return "\n".join(
        line for line in sanity_block.splitlines() if not line.lstrip().startswith("#")
    )


def _assert_app_installs_are_closed(installs: list[str], build_constraint: str) -> None:
    """앱 의존성 설치는 목록 밖 패키지를 받지 않고, 소스 빌드 환경도 고정돼야 한다.

    - `--no-deps`: 없으면 pip가 하한만 보고 목록 밖 버전을 끌어올 수 있다.
    - `--build-constraint`: `-r`의 git 의존성(python-kasi-api)과 `-e .`는 둘 다 build
      isolation에서 소스로 빌드된다 — 없으면 그 build 환경이 빌드 시점 최신을 받는다.
    """
    assert installs, "앱 의존성을 설치하는 pip install이 없다"
    assert any(cmd.endswith(" -e .") for cmd in installs), installs
    assert any(" -r " in cmd for cmd in installs), installs
    for cmd in installs:
        assert "--no-deps" in cmd, f"--no-deps 없는 pip install: {cmd!r}"
        assert f"--build-constraint {build_constraint} " in cmd, (
            f"build 환경이 고정되지 않은 pip install: {cmd!r}"
        )


def test_every_pip_install_refuses_unlisted_packages() -> None:
    """설치 도구 명령 하나(`pip install pip==<ver>` 그 자체)만 예외다."""
    step = _dependency_install_step()
    tool = f"pip install pip=={_image_pip_version()}"
    app_installs = [cmd for cmd in _pip_installs(step) if cmd != tool]
    _assert_app_installs_are_closed(app_installs, "/tmp/build-constraints.txt")
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
    _image_pip_version()


def test_ci_installs_the_same_pip_as_the_image() -> None:
    """`--build-constraint`의 동작은 pip 버전에 달렸다 — CI와 이미지가 같은 pip여야 한다."""
    tools = [cmd for cmd in _pip_installs(_sanity_commands()) if " pip==" in cmd]
    assert len(tools) == 1, tools
    matched = re.fullmatch(r"python -m pip install pip==(\S+) uv==\S+", tools[0])
    assert matched is not None, f"CI 설치 도구 명령에 다른 것이 섞였다: {tools[0]!r}"
    assert matched.group(1) == _image_pip_version()


# pip가 build isolation에서 **backend 선언 밖**으로 더 받는 것. hatchling의 editable
# 훅은 `get_requires_for_build_editable`에서 `editables~=0.3`을 추가로 요구한다
# (pip 26.2.1 `-v` 실측: "Getting requirements to build editable" 뒤 editables 설치).
_EDITABLE_HOOK_REQUIRES = frozenset({"editables"})
# `uv.lock`의 git 의존성은 wheel이 없어 소스로 빌드된다. 그 저장소의 `[build-system]
# requires`는 lock에 남지 않으므로 여기에 적는다 — 새 git 의존성이 생기면 아래 테스트가
# 빨개져 이 표와 build-constraints.txt를 함께 채우게 한다.
_GIT_DEPENDENCY_BUILD_REQUIRES = {
    "python-kasi-api": frozenset({"setuptools", "wheel"}),
    "kor-travel-common": frozenset({"hatchling"}),
}
# 위 backend들의 런타임 의존성(pip -v 실측: hatchling → packaging·pathspec·pluggy·
# tomlkit·trove-classifiers, wheel → packaging). backend만 고정하면 이들이 최신으로 풀린다.
_BUILD_BACKEND_DEPENDENCIES = frozenset(
    {"packaging", "pathspec", "pluggy", "tomlkit", "trove-classifiers"}
)


def _git_sourced_packages() -> set[str]:
    lock = tomllib.loads(_UV_LOCK.read_text(encoding="utf-8"))
    return {pkg["name"] for pkg in lock["package"] if "git" in pkg.get("source", {})}


def test_every_git_dependency_has_known_build_requirements() -> None:
    assert _git_sourced_packages() == set(_GIT_DEPENDENCY_BUILD_REQUIRES)


def test_the_build_environments_are_pinned() -> None:
    """`-e .`와 git 의존성의 build isolation은 제약 파일 없이 하한만 보고 최신을 받는다."""
    source = _DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY apps/etl/build-constraints.txt /tmp/build-constraints.txt" in source

    pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    backend = {
        re.split(r"[<>=!~\[ ;]", req, maxsplit=1)[0].lower()
        for req in pyproject["build-system"]["requires"]
    }
    required = backend | _EDITABLE_HOOK_REQUIRES | _BUILD_BACKEND_DEPENDENCIES
    for build_requires in _GIT_DEPENDENCY_BUILD_REQUIRES.values():
        required |= build_requires
    pins = _pinned_lines(_BUILD_CONSTRAINTS)
    assert required <= pins.keys(), f"고정 안 된 build 의존성: {sorted(required - pins.keys())}"


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
    sanity = _sanity_commands()
    assert "uv --no-cache export --locked --extra dev" in sanity
    installs = _pip_installs(sanity)
    tools = [cmd for cmd in installs if " pip==" in cmd]
    assert len(tools) == 1, tools
    # 설치 도구 명령은 정확히 한 모양만 예외다(`test_ci_installs_the_same_pip_as_the_image`).
    assert re.fullmatch(r"python -m pip install pip==\S+ uv==\S+", tools[0]), tools
    # CI는 working-directory가 apps/etl이다.
    _assert_app_installs_are_closed(
        [cmd for cmd in installs if cmd != tools[0]], "build-constraints.txt"
    )
    assert "pip check" in sanity
