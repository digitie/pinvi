"""docker-app.sh `build()`의 두 계약 게이트.

**하나.** Compose는 다중 타깃 build를 BuildKit bake 요청 하나로 바꾸고, 그
요청은 프런트엔드 세션을 동시에 여러 개 연다. 작은 호스트(n150)에서는 그것만
으로 데몬의 세션 한도를 넘겨 모든 타깃이 컨텍스트 마감까지 대기하다 조용히
죽는다 — 2026-09-03 격리 M05 e2e가 0바이트 로그를 남기고 사라진 실패다.
Manager의 pinned rebuild 경로는 같은 이유로 이미 서비스별로 굽는다. 이
게이트는 그 교훈이 docker-app.sh에서 조용히 풀리는 회귀를 막는다.

**둘.** 굽는 대상과 provenance를 검증하는 대상은 하나의 사실이다. 종전 본문은
`app-api app-web`을 build 줄과 verify 줄에 따로 적었고, 둘을 묶는 기계가
없었다. 서비스 이름이 본문에 한 번씩만 나타나게 고정해 그 이중 선언이
되살아나지 못하게 한다(레포 관행: docker-app.sh 본문 텍스트 고정).
"""

from __future__ import annotations

import re
from pathlib import Path

_DOCKER_APP = Path(__file__).resolve().parents[4] / "scripts" / "docker-app.sh"


def _source() -> str:
    return _DOCKER_APP.read_text(encoding="utf-8")


def _build_body() -> str:
    source = _source()
    start = source.index("build() {")
    return source[start : source.index("\n}", start)]


def test_build_issues_one_buildkit_request_per_service() -> None:
    body = _build_body()
    assert 'for service in "${services[@]}"; do' in body
    assert 'compose "${build_args[@]}" "$service"' in body


def test_no_compose_build_carries_more_than_one_target() -> None:
    """`compose ... build a b` 형태가 파일 어디에도 없어야 한다."""
    offenders = [
        line.strip()
        for line in _source().splitlines()
        if re.search(r"\bcompose\b.*\bbuild\b", line)
        and len(re.findall(r"(?<![\w\"$])app-[a-z0-9-]+", line)) > 1
    ]
    assert offenders == [], offenders


def test_service_list_is_declared_once_and_verification_derives_from_it() -> None:
    body = _build_body()
    assert 'pinvi_verify_runtime_image_provenance "${services[@]}"' in body
    for service in ("app-api", "app-web", "app-dagster"):
        assert body.count(service) == 1, (service, body.count(service))
