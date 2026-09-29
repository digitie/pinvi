"""ETL CI가 도는 경로와 Aggregate gate가 `sanity`를 기다리는 경로를 한 집합으로 묶는다.

Aggregate gate가 유일한 required check다. `etl.yml`은 자기 `paths`에서 돌지만, gate는
`aggregate-ci.yml`의 `hasAny([...])` 목록에 걸린 PR에서만 `sanity`를 기다린다. 두 목록이
갈라지면 etl.yml에만 있는 경로(예: `apps/api/app/services/admin_etl.py` — ETL 테스트가
그 GraphQL 조회를 검증한다)만 바꾼 PR은 `sanity`가 빨개도 머지된다.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ETL_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "etl.yml"
_AGGREGATE_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "aggregate-ci.yml"

_HAS_ANY_BLOCK = re.compile(
    r"if \(hasAny\(\[(?P<matchers>[^\]]*)\]\)\) \{(?P<body>.*?)\n\s*\}",
    flags=re.DOTALL,
)
_MATCHER = re.compile(r'^\s*(?P<kind>startsWith|equals)\("(?P<path>[^"]+)"\),?\s*$')


def _etl_trigger_paths() -> dict[str, list[str]]:
    workflow = yaml.safe_load(_ETL_WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1은 맨 키 `on`을 bool True로 읽는다.
    triggers = workflow.get("on", workflow.get(True))
    return {event: triggers[event]["paths"] for event in ("pull_request", "push")}


def _aggregate_sanity_matchers() -> list[tuple[str, str]]:
    source = _AGGREGATE_WORKFLOW.read_text(encoding="utf-8")
    blocks = [
        m.group("matchers")
        for m in _HAS_ANY_BLOCK.finditer(source)
        if 'requiredChecks.push("sanity")' in m.group("body")
    ]
    assert len(blocks) == 1, f"`sanity`를 요구하는 hasAny 블록이 정확히 하나가 아니다: {blocks!r}"
    matchers: list[tuple[str, str]] = []
    for line in blocks[0].splitlines():
        if not line.strip() or line.strip().startswith("//"):
            continue
        parsed = _MATCHER.match(line)
        assert parsed is not None, f"해석할 수 없는 matcher 줄: {line!r}"
        matchers.append((parsed.group("kind"), parsed.group("path")))
    return matchers


def _covered(trigger: str, matchers: list[tuple[str, str]]) -> bool:
    prefixes = [path for kind, path in matchers if kind == "startsWith"]
    exact = {path for kind, path in matchers if kind == "equals"}
    if trigger.endswith("/**"):
        directory = trigger.removesuffix("**")
        assert not any(ch in directory for ch in "*?[!"), f"지원하지 않는 glob: {trigger!r}"
        return any(directory.startswith(prefix) for prefix in prefixes)
    assert not any(ch in trigger for ch in "*?[!"), f"지원하지 않는 glob: {trigger!r}"
    return trigger in exact or any(trigger.startswith(prefix) for prefix in prefixes)


def test_push_and_pull_request_run_on_the_same_paths() -> None:
    paths = _etl_trigger_paths()
    assert paths["pull_request"] == paths["push"]


def test_the_aggregate_gate_waits_for_sanity_on_every_etl_trigger_path() -> None:
    matchers = _aggregate_sanity_matchers()
    uncovered = [p for p in _etl_trigger_paths()["pull_request"] if not _covered(p, matchers)]
    assert not uncovered, (
        f"etl.yml은 돌지만 Aggregate gate가 `sanity`를 기다리지 않는 경로: {uncovered}"
    )


def test_the_aggregate_gate_never_waits_for_a_sanity_run_that_cannot_start() -> None:
    """반대 방향 — gate가 기다리는데 etl.yml이 돌지 않으면 `sanity: missing`으로 40분 뒤 죽는다."""
    triggers = _etl_trigger_paths()["pull_request"]
    exact = {t for t in triggers if not t.endswith("/**")}
    directories = {t.removesuffix("**") for t in triggers if t.endswith("/**")}
    orphans = [
        (kind, path)
        for kind, path in _aggregate_sanity_matchers()
        if not (
            (kind == "equals" and (path in exact or any(path.startswith(d) for d in directories)))
            or (kind == "startsWith" and any(path.startswith(d) for d in directories))
        )
    ]
    assert not orphans, f"Aggregate gate만 `sanity`를 요구하고 etl.yml은 돌지 않는 경로: {orphans}"
