"""실제 runner의 Docker argv 구성에서 geometry anchor 환경을 잃지 않는다."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_RUNNER = Path(__file__).resolve().parents[4] / "scripts/n150-playwright-runner.sh"
_ANCHORS = (
    "PINVI_E2E_GEOMETRY_AREA_ANCHOR_QUERY",
    "PINVI_E2E_GEOMETRY_SEORAK_ANCHOR_QUERY",
    "PINVI_E2E_GEOMETRY_BUKHAN_ANCHOR_QUERY",
)


def _forwarded_arguments(values: dict[str, str]) -> list[str]:
    source = _RUNNER.read_text(encoding="utf-8")
    start = source.index("allowed_env_names=(")
    end = source.index("\ndocker_args+=(", start)
    # N150 hostname/Docker 실행 guard는 그대로 둔다. 실제 allowlist/배열 구성만
    # 격리해 Bash로 실행하며 별도 복제 allowlist를 테스트하지 않는다.
    script = (
        "set -euo pipefail\ndocker_args=()\n"
        + source[start:end]
        + '\nprintf "%s\\0" "${docker_args[@]}"'
    )
    result = subprocess.run(  # noqa: S603 - 저장소의 고정 Bash 조각만 실행
        ["/bin/bash", "-c", script],
        env={"PATH": "/usr/bin:/bin", **values},
        check=True,
        capture_output=True,
        timeout=5,
    )
    return [part.decode() for part in result.stdout.split(b"\x00") if part]


@pytest.mark.parametrize("name", _ANCHORS)
def test_geometry_anchor_is_forwarded_by_name_without_value_in_argv(name: str) -> None:
    value = "설악산 국립공원; literal $(keep_as_text)"
    assert _forwarded_arguments({name: value}) == ["--env", name]


def test_unset_and_unknown_geometry_environment_are_not_forwarded() -> None:
    assert _forwarded_arguments({"PINVI_E2E_GEOMETRY_UNKNOWN_SECRET": "do-not-forward"}) == []
