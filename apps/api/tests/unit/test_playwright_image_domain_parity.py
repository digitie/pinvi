"""Playwright runner image ref 도메인을 세 선언에 걸쳐 결박한다.

같은 이미지 참조를 검사하는 정규식이 세 곳에 따로 선언돼 있었고, 그중
`app/core/config.py`만 tag를 **필수**로 요구했다. Manager가 고정한 runner
핀은 digest-only(`mcr.microsoft.com/playwright@sha256:...`)라, 같은 값이
attestation/receipt에서는 통과하고 settings에서는 거부됐다 — 이중(삼중)
선언 결함이다. 스크립트는 root 실행용 stdlib-only라 import로 공유할 수
없으므로, 저장소 관례대로 미러 결박 테스트로 못 박는다.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONFIG = _REPO_ROOT / "apps/api/app/core/config.py"
_RECEIPT = _REPO_ROOT / "scripts/m05_activation_receipt.py"
_ATTESTATION = _REPO_ROOT / "scripts/m05_activation_attestation.py"

# 세 선언에서 뽑아낸 뒤 문자 단위로 비교할 정본 도메인.
_CANONICAL = r"mcr\.microsoft\.com/playwright(?::[A-Za-z0-9][A-Za-z0-9._-]*)?@sha256:[0-9a-f]{64}"


def _declared_patterns(path: Path) -> list[str]:
    r"""`mcr\.microsoft` 를 포함하는 raw-string 리터럴을 이어 붙여 돌려준다."""

    source = path.read_text(encoding="utf-8")
    patterns: list[str] = []
    parts: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        literal = re.fullmatch(r'r"([^"]*)",?', stripped)
        if literal is None:
            if parts:
                patterns.append("".join(parts))
                parts = []
            continue
        body = literal.group(1)
        if not parts and "mcr" not in body:
            continue
        parts.append(body)
    if parts:
        patterns.append("".join(parts))
    return [pattern for pattern in patterns if "mcr" in pattern]


def test_every_declaration_uses_the_same_image_domain() -> None:
    for path in (_CONFIG, _RECEIPT, _ATTESTATION):
        declared = _declared_patterns(path)
        assert declared, f"{path.name}에서 playwright 이미지 정규식을 찾지 못했다"
        for pattern in declared:
            assert pattern.removesuffix(chr(92) + "Z") == _CANONICAL, (path.name, pattern)


def test_the_domain_accepts_the_pinned_digest_only_reference() -> None:
    """Manager가 실제로 넘기는 tag 없는 핀이 세 곳 모두에서 통과해야 한다."""

    digest_only = "mcr.microsoft.com/playwright@sha256:" + "d" * 64
    tagged = "mcr.microsoft.com/playwright:v1.62.1-noble@sha256:" + "d" * 64
    compiled = re.compile(_CANONICAL)
    assert compiled.fullmatch(digest_only) is not None
    assert compiled.fullmatch(tagged) is not None
    # digest 없는 참조는 계속 거부돼야 한다 — 핀이 아니다.
    assert compiled.fullmatch("mcr.microsoft.com/playwright:v1.62.1-noble") is None
    assert compiled.fullmatch("ghcr.io/evil/playwright@sha256:" + "d" * 64) is None
