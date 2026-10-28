"""API의 Python 의존성이 CI와 이미지 모두에서 `uv.lock`에서만 오는지 고정한다.

2026-10-27: CI가 `pip install -e ".[dev]"`로 pyproject 하한만 보고 실행 시점 PyPI 최신을 받아,
코드 변경 없이 pytest 9.1.1→9.2.0 릴리스 하나로 타이밍 테스트가 빨개졌다(#609). 이미지도
같은 방식이라 같은 커밋이 빌드 시점마다 다른 의존성으로 나갔다. lock은 아무것도 고정하지
않았다. apps/etl은 2026-09-29에 같은 결함을 닫았다(`apps/etl/tests/test_dagster_version_lock.py`).

의존성은 이제 `uv-lock-refresh.yml`이 여는 갱신 브랜치로만 앞으로 간다.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

_API_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _API_ROOT.parents[1]
_DOCKERFILE = _API_ROOT / "Dockerfile"
_PYPROJECT = _API_ROOT / "pyproject.toml"
_UV_LOCK = _API_ROOT / "uv.lock"
_BUILD_CONSTRAINTS = _API_ROOT / "build-constraints.txt"
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"
_API_WORKFLOW = _WORKFLOWS / "api.yml"
_REFRESH_WORKFLOW = _WORKFLOWS / "uv-lock-refresh.yml"


def _uncommented(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _run_steps(text: str) -> list[str]:
    """Dockerfile `RUN` 한 덩어리(연속 줄 포함)씩."""
    return re.findall(r"^RUN (?:[^\n]*\\\n)*[^\n]*$", text, flags=re.MULTILINE)


def _pip_installs(text: str) -> list[str]:
    """`pip install ...` 명령(uv pip 제외)을 연속 기호와 공백을 떼고 모은다."""
    return [
        cmd.rstrip("\\ ").strip()
        for cmd in re.findall(r"(?<!uv )(?:python -m )?pip install[^&\n]*", text)
    ]


def _required_uv_version(pyproject: Path) -> str:
    required = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["uv"][
        "required-version"
    ]
    assert required.startswith("=="), required
    return str(required).removeprefix("==")


def _setup_uv_versions(workflow: Path) -> list[str]:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    versions: list[str] = []
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if not str(step.get("uses", "")).startswith("astral-sh/setup-uv@"):
                continue
            version = step.get("with", {}).get("version")
            assert version, f"setup-uv에 version이 없다(최신 uv가 풀린다): {step!r}"
            versions.append(str(version))
    return versions


def test_image_installs_dependencies_only_from_the_lock() -> None:
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY apps/api/uv.lock ./uv.lock" in dockerfile
    exports = [step for step in _run_steps(dockerfile) if "uv --no-cache export" in step]
    assert len(exports) == 1, exports
    for flag in ("--locked", "--no-dev", "--no-emit-project"):
        assert flag in exports[0], f"{flag} 없는 export: {exports[0]!r}"


def test_every_image_pip_install_refuses_unlisted_packages() -> None:
    """설치 도구 명령 하나(`pip install pip==<ver>`)만 예외다."""
    dockerfile = _uncommented(_DOCKERFILE.read_text(encoding="utf-8"))
    installs = _pip_installs(dockerfile)
    tools = [cmd for cmd in installs if " pip==" in cmd]
    assert len(tools) == 1 and re.fullmatch(r"pip install pip==\d+\.\d+(?:\.\d+)?", tools[0]), tools
    app_installs = [cmd for cmd in installs if cmd != tools[0]]
    assert any(" -r " in cmd for cmd in app_installs), app_installs
    assert any(cmd.endswith(" -e .") for cmd in app_installs), app_installs
    for cmd in app_installs:
        assert "--no-deps" in cmd, f"--no-deps 없는 pip install: {cmd!r}"
        assert "--build-constraint /tmp/build-constraints.txt " in cmd, cmd
    assert "--upgrade pip" not in dockerfile
    assert "pip check" in dockerfile


def test_ci_installs_only_with_uv_sync_locked() -> None:
    """두 Python job(lint-typecheck-test·integration-test) 모두 lock에서만 설치한다."""
    workflow = _uncommented(_API_WORKFLOW.read_text(encoding="utf-8"))
    assert workflow.count("uv sync --locked --extra dev") == 2
    assert _pip_installs(workflow) == [], "lock을 거치지 않는 pip install이 남아 있다"
    assert "cache: pip" not in workflow


def test_uv_is_one_version_everywhere() -> None:
    """lock을 만들고 푸는 uv가 pyproject·이미지·CI·갱신 workflow에서 같아야 한다."""
    # apps/etl의 같은 결박은 apps/etl/tests/test_dagster_version_lock.py가 맡는다 — 여기서
    # ETL 파일을 읽으면 그 파일만 바뀐 PR에서 api.yml이 돌지 않아 결박이 늦게 빨개진다.
    version = _required_uv_version(_PYPROJECT)

    image = re.search(
        r"^FROM ghcr\.io/astral-sh/uv:([^@\s]+)@sha256:",
        _DOCKERFILE.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    assert image is not None and image.group(1) == version, image

    assert _setup_uv_versions(_API_WORKFLOW) == [version, version]
    assert _setup_uv_versions(_REFRESH_WORKFLOW) == [version]


def test_the_lock_carries_the_dev_extra_ci_installs() -> None:
    lock = tomllib.loads(_UV_LOCK.read_text(encoding="utf-8"))
    project = next(pkg for pkg in lock["package"] if pkg["name"] == "pinvi-api")
    assert "dev" in project["metadata"]["provides-extras"]


def _pinned_lines(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, sep, version = line.partition("==")
        assert sep and version.strip(), f"{path.name}에 `==`로 고정되지 않은 줄: {raw!r}"
        pins[name.strip().lower()] = version.strip()
    return pins


# hatchling editable 훅이 backend 선언 밖으로 더 받는 것과 hatchling의 런타임 의존성.
_HATCHLING_BUILD_SET = frozenset(
    {"hatchling", "editables", "packaging", "pathspec", "pluggy", "tomlkit", "trove-classifiers"}
)
# `uv.lock`의 git 의존성은 wheel이 없어 소스로 빌드된다 — 그 build backend.
_GIT_DEPENDENCY_BUILD_REQUIRES = {"kor-travel-common": frozenset({"hatchling"})}


def test_the_build_environments_are_pinned() -> None:
    lock = tomllib.loads(_UV_LOCK.read_text(encoding="utf-8"))
    git_sourced = {pkg["name"] for pkg in lock["package"] if "git" in pkg.get("source", {})}
    assert git_sourced == set(_GIT_DEPENDENCY_BUILD_REQUIRES), git_sourced

    pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    backend = {
        re.split(r"[<>=!~\[ ;]", req, maxsplit=1)[0].lower()
        for req in pyproject["build-system"]["requires"]
    }
    required = backend | _HATCHLING_BUILD_SET
    for build_requires in _GIT_DEPENDENCY_BUILD_REQUIRES.values():
        required |= build_requires
    pins = _pinned_lines(_BUILD_CONSTRAINTS)
    assert required <= pins.keys(), f"고정 안 된 build 의존성: {sorted(required - pins.keys())}"
    assert "COPY apps/api/build-constraints.txt /tmp/build-constraints.txt" in (
        _DOCKERFILE.read_text(encoding="utf-8")
    )
