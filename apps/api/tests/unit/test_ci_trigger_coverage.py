"""CI 트리거가 이미지 빌드 입력의 상위집합인지, 그리고 세 목록이 갈라지지 않는지 본다.

2026-09-02에 같은 결함이 두 번 값을 물렸다.

- `apps/web/Dockerfile`의 deps 스테이지가 workspace manifest 하나를 빠뜨렸는데
  `npm install`이 조용히 다른 트리를 만들어 프로덕션 이미지가 서지 않았다. 그 사실은
  CI가 아니라 **71분짜리 pinned rebuild**에서야 드러났다 — CI는 전체 체크아웃 트리를
  검증하고 이미지는 다른 트리를 만들기 때문이다.
- 그걸 고치면서 세 목록(`web.yml` PR paths · `web.yml` push paths ·
  `aggregate-ci.yml` 조건)이 또 하나의 손 유지 목록이 됐다.

이 파일은 그 두 형태를 각각 막는다.

**왜 "유도"가 아니라 "탐지"인가**: GitHub Actions의 `on.paths`에는 동적 값을 쓸 수
없다. 목록을 코드에서 계산해 넣을 방법이 없으므로 `AGENTS.md` DO NOT 15의 사다리에서
유도(1)·결박(2)에 닿지 못하고 탐지(3)에 머문다. 그 사실 자체를 여기 적어 둔다.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[4]
_WORKFLOWS = _ROOT / ".github/workflows"


def _triggers(name: str) -> dict[str, set[str]]:
    document = yaml.safe_load((_WORKFLOWS / name).read_text(encoding="utf-8"))
    # PyYAML은 YAML 1.1이라 `on:` 키를 불리언 True로 읽는다.
    on = document[True] if True in document else document["on"]
    return {
        event: set(on[event].get("paths", []))
        for event in ("pull_request", "push")
        if isinstance(on.get(event), dict)
    }


def test_pull_request_and_push_triggers_agree() -> None:
    """PR에서만 도는 트리거는 main을 지키지 못한다.

    `mobile.yml`이 루트 매니페스트 3개를 PR에서만 걸고 있었다 — lockfile만 바뀐
    머지는 main에서 아무 신호도 내지 않았다.
    """

    drifted: list[str] = []
    for name in ("api.yml", "web.yml", "etl.yml", "mobile.yml"):
        triggers = _triggers(name)
        if set(triggers) != {"pull_request", "push"}:
            continue
        only_pr = triggers["pull_request"] - triggers["push"]
        only_push = triggers["push"] - triggers["pull_request"]
        if only_pr or only_push:
            drifted.append(f"{name}: PR만={sorted(only_pr)} push만={sorted(only_push)}")

    assert not drifted, "PR/push 트리거가 갈라졌다: " + repr(drifted)


def _aggregate_clauses(marker: str, stop: str) -> set[str]:
    """`aggregate-ci.yml`의 한 블록이 거는 경로 집합."""

    source = (_WORKFLOWS / "aggregate-ci.yml").read_text(encoding="utf-8")
    start = source.index(marker)
    end = source.index(stop, start)
    segment = source[start:end]
    return set(re.findall(r'(?:equals|startsWith)\("([^"]+)"\)', segment))


def _normalise(patterns: set[str]) -> set[str]:
    """`on.paths` 글롭을 aggregate의 문자열 술어와 같은 모양으로 접는다."""

    folded: set[str] = set()
    for pattern in patterns:
        if pattern.endswith("/**"):
            folded.add(pattern[:-2])
        elif pattern.endswith("*"):
            folded.add(pattern[:-1])
        else:
            folded.add(pattern)
    return folded


def _covers(pattern: str, source: str) -> bool:
    """`on.paths` 패턴이 구체 경로를 덮는가.

    두 종류를 뭉개면 안 된다 — `scripts/m05_*`는 **문자열 접두**이고
    `apps/web/**`는 **디렉터리 접두**다. 하나로 접으면 전자가 매치하지 않아
    있지도 않은 구멍을 보고한다.
    """

    source = source.rstrip("/")
    if pattern.endswith("/**"):
        base = pattern[:-3]
        return source == base or source.startswith(base + "/")
    if pattern.endswith("*"):
        return source.startswith(pattern[:-1])
    base = pattern.rstrip("/")
    return source == base or source.startswith(base + "/")


def test_aggregate_gate_waits_for_exactly_what_the_workflow_runs() -> None:
    """게이트 조건과 워크플로 트리거가 같아야 한다 — 양쪽으로 다 위험하다.

    게이트가 **더 넓으면**: 워크플로가 뜨지 않는 변경에 대해 게이트가 그 체크를
    기다린다. `scripts/m05_hotswap_topology.sql`이 정확히 그랬다 — 게이트는
    `startsWith("scripts/m05_")`인데 `api.yml`은 `scripts/m05_*.py`만 걸어,
    오지 않을 7개 체크를 40분 폴링한 뒤 timeout이 됐다.

    게이트가 **더 좁으면**: 워크플로가 red인데 게이트가 그걸 기다리지 않아
    **실패한 체크를 달고 머지된다.** `scripts/alembic_rebaseline.py`와
    `docs/runbooks/docker-app.md`가 그랬다.
    """

    api = _normalise(_triggers("api.yml")["pull_request"])
    gate = _aggregate_clauses(
        'startsWith("apps/api/")', 'requiredChecks.push("lint-typecheck-test")'
    )

    assert gate == api, (
        "aggregate api 블록과 api.yml 트리거가 다르다 — "
        f"게이트만={sorted(gate - api)}, 워크플로만={sorted(api - gate)}"
    )


def _dockerfile_context_inputs(relative: str) -> set[str]:
    """Dockerfile이 빌드 컨텍스트에서 읽는 경로(디렉터리는 접미 `/`)."""

    text = (_ROOT / relative).read_text(encoding="utf-8")
    inputs: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("COPY "):
            continue
        if "--from=" in stripped:
            continue  # 이전 스테이지에서 오는 것은 컨텍스트 입력이 아니다
        tokens = [t for t in stripped.split()[1:] if not t.startswith("--")]
        if len(tokens) < 2:
            continue
        for source in tokens[:-1]:
            if source in {".", "./"}:
                continue  # 컨텍스트 전체 — 개별 입력으로 셀 수 없다
            if "*" in source:
                # Dockerfile의 glob은 **실제 경로로 펼쳐서** 본다. 펼치지 않으면
                # `apps/*/package.json`이 `apps/web/**`에 덮이는 것을 보지 못해
                # 있지도 않은 구멍을 보고하고, 그 오탐을 없애려고 트리거에 중복
                # 항목을 넣게 된다 — 검사기가 목록을 더럽히는 셈이다.
                matched = [
                    str(hit.relative_to(_ROOT)).replace("\\", "/")
                    for hit in _ROOT.glob(source.rstrip("/"))
                ]
                assert matched, f"Dockerfile glob이 아무것도 매치하지 않는다: {source}"
                inputs.update(matched)
                continue
            inputs.add(source)
    return inputs


def test_image_build_inputs_are_covered_by_a_ci_trigger() -> None:
    """이미지가 읽는 파일이 바뀌면 그 이미지를 빌드하는 CI가 돌아야 한다.

    `scripts/validate-image-provenance.sh`는 **세 이미지 전부**의 COPY 입력인데
    어느 워크플로의 트리거에도 없었다 — 그 파일을 고쳐도 이미지 CI가 돌지 않았다.

    자기검증: 발견한 COPY 입력이 하한 미만이면 파서가 조용히 아무것도 못 찾은
    것이므로 실패한다. 그 하한이 없으면 이 검사 자체가 다섯 번째 침묵 선언이 된다.
    """

    images = {
        "apps/api/Dockerfile": "api.yml",
        "apps/web/Dockerfile": "web.yml",
        "apps/etl/Dockerfile": "etl.yml",
    }
    uncovered: list[str] = []
    for dockerfile, workflow in images.items():
        inputs = _dockerfile_context_inputs(dockerfile)
        assert len(inputs) >= 2, (
            f"{dockerfile}에서 COPY 입력을 {len(inputs)}개만 찾았다 — 파서가 깨졌다"
        )
        triggers = _triggers(workflow)["pull_request"]
        for source in sorted(inputs):
            if any(_covers(pattern, source) for pattern in triggers):
                continue
            uncovered.append(f"{workflow}: {source} ({dockerfile})")

    assert not uncovered, (
        "이미지 빌드 입력이 CI 트리거에 없다 — 그 파일을 고쳐도 이미지가 검증되지 "
        "않는다: " + repr(uncovered)
    )


def test_triggers_do_not_name_paths_that_do_not_exist() -> None:
    """존재하지 않는 경로를 거는 항목은 아무것도 지키지 않는다.

    루트 `pyproject.toml`이 `api.yml`과 aggregate 양쪽에 있었는데 그 파일은 이
    저장소에 없다. 죽은 항목은 목록을 읽는 사람에게 커버리지를 과장한다.
    """

    dead: list[str] = []
    for name in ("api.yml", "web.yml", "etl.yml", "mobile.yml"):
        for event, patterns in _triggers(name).items():
            for pattern in sorted(patterns):
                if "*" in pattern:
                    if not list(_ROOT.glob(pattern)):
                        dead.append(f"{name}[{event}]: {pattern}")
                elif not (_ROOT / pattern).exists():
                    dead.append(f"{name}[{event}]: {pattern}")

    assert not dead, "트리거가 존재하지 않는 경로를 걸고 있다: " + repr(dead)
