"""docker-app.sh compose overlay(`PINVI_DOCKER_COMPOSE_EXTRA_FILE`) 계약 게이트.

overlay는 Manager isolated M05 harness가 app-api를 첫 기동부터 external Map
network에 join시키기 위한 통로다. caller가 설정할 수 있는 환경변수는 권한
근거가 아니므로(2026-09-01 적대 리뷰), overlay는 Manager M05 isolated
admission 맥락 + root 소유 private 파일일 때만 받아들여야 하고, 미설정이면
종전과 동일한 단일 `-f` 동작이어야 한다. 이 게이트는 그 텍스트 계약이
조용히 풀리는 회귀를 막는다(레포 관행: docker-app.sh 본문 텍스트 고정).
"""

from __future__ import annotations

from pathlib import Path

_DOCKER_APP = Path(__file__).resolve().parents[4] / "scripts" / "docker-app.sh"


def _source() -> str:
    return _DOCKER_APP.read_text(encoding="utf-8")


def test_overlay_default_is_empty_and_optional() -> None:
    source = _source()
    assert 'COMPOSE_EXTRA_FILE="${PINVI_DOCKER_COMPOSE_EXTRA_FILE:-}"' in source


def test_overlay_requires_manager_admission_context_and_private_root_file() -> None:
    source = _source()
    validator_start = source.index("require_valid_compose_extra_file() {")
    validator = source[validator_start : source.index("\n}", validator_start)]
    # admission triple 없이는 overlay를 받지 않는다.
    assert "PINVI_M05_ISOLATED_MANAGER_ADMISSION_PATH" in validator
    assert "PINVI_M05_PINSET_SHA256" in validator
    assert "PINVI_M05_EXECUTION_IDENTITY_SHA256" in validator
    # 절대경로·정규파일·비심링크·root 소유·private(0600)만 허용한다.
    assert '"$COMPOSE_EXTRA_FILE" != /*' in validator
    assert '-L "$COMPOSE_EXTRA_FILE"' in validator
    assert '! -f "$COMPOSE_EXTRA_FILE"' in validator
    assert '"$extra_owner" != "0"' in validator
    assert "8#$extra_mode & 077" in validator


def test_compose_wrapper_validates_before_merging_overlay() -> None:
    source = _source()
    compose_start = source.index("compose() {")
    compose_body = source[compose_start : source.index("\n}", compose_start)]
    validate_at = compose_body.index("require_valid_compose_extra_file || return 2")
    merge_at = compose_body.index('compose_files+=(-f "$COMPOSE_EXTRA_FILE")')
    assert validate_at < merge_at
    # 미설정이면 단일 -f — canonical COMPOSE_FILE이 항상 첫 파일이다.
    assert 'local -a compose_files=(-f "$COMPOSE_FILE")' in compose_body
    assert '[[ -n "$COMPOSE_EXTRA_FILE" ]]' in compose_body


def test_canonical_direct_compose_target_guard_is_intact() -> None:
    source = _source()
    assert 'if [[ "$COMPOSE_FILE" != "infra/docker-compose.app.yml" ]]' in source
