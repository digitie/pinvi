"""ETL 컨테이너의 HEALTHCHECK가 code location 로드를 실제로 묻는지 본다.

종전 probe는 `/server_info`였다. 그건 webserver가 **정적으로** 주는 버전 문서라
code location이 죽어도 200을 낸다 — code location은 별도로 로드되고, 실패해도
webserver 자체는 살아 있기 때문이다. 그래서 컨테이너는 끝까지 healthy로 보고
됐고, PII 보존 job이 조용히 멈춰도 아무도 몰랐다. "게이트가 있는데 아무것도
막지 않는" 상태다.

정상이면 `repositoriesOrError`가 `RepositoryConnection`을, code location이
깨지면 `PythonError`를 돌려준다(운영 컨테이너 실측, dagster 1.13.20). curl이
실패하면 출력이 비어 `grep -q`가 떨어지므로 전송 실패 경로도 함께 닫힌다.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_DOCKERFILE = _ROOT / "apps" / "etl" / "Dockerfile"


def _healthcheck() -> str:
    source = _DOCKERFILE.read_text(encoding="utf-8")
    start = source.index("HEALTHCHECK ")
    return source[start : source.index("\nCMD ", start)]


def test_the_healthcheck_asks_whether_the_code_location_loaded() -> None:
    healthcheck = _healthcheck()
    assert "/graphql" in healthcheck
    assert "repositoriesOrError" in healthcheck
    assert '"__typename":"RepositoryConnection"' in healthcheck


def test_the_static_version_document_is_no_longer_the_probe() -> None:
    """`/server_info`는 code location 실패를 못 잡는다 — probe로 되돌아오면 안 된다."""
    assert "/server_info" not in _healthcheck()


def test_a_transport_failure_still_fails_the_probe() -> None:
    """curl이 실패하면 출력이 비고, `grep -q`가 그 경로를 닫는다."""
    healthcheck = _healthcheck()
    assert "curl -fsS" in healthcheck
    assert "grep -q" in healthcheck
    assert "|| exit 1" in healthcheck
