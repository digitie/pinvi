"""pair 계약의 digest가 vendored 스냅샷에서 **유도**되는지 확인한다.

## 왜

이 계약은 손으로 적혀 있었다. 그 안의 16개 digest는 사실 이 저장소의 세 파일에서
계산되는 값인데, 아무도 그 관계를 확인하지 않았다 — 즉 스냅샷과 계약이 갈라질 수
있었고, 갈라져도 **격리 e2e(1~2시간)에서야** 드러난다.

`scripts/generate_m05_pair_contract.py`가 그 유도를 코드로 만들고, 이 파일이 커밋된
계약이 그 출력과 같은지 건다. 이제 스냅샷을 바꾸고 생성기를 안 돌리면 CI가 잡는다.

## v1/v2 전환 중

계약은 아직 v1이다(`source_revision` · `runtime_image_digests` 포함). 그 두 필드를
걷어내는 v2 전환은 PinVi 소비 지점 3곳과 프로덕션 activation 경로를 함께 바꿔야
하므로 별건이다. 이 파일은 **그 전환과 무관하게 참인 부분** — 16개 digest의 유도 —
만 건다. v2로 올라가면 이 검사는 그대로 성립하고, 봉투 비교가 추가된다.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[4]
_CONTRACT = _ROOT / "contracts/kor-travel-map-m05-pair-provenance-v1.json"

_DIGEST_KEYS = (
    "openapi_sha256",
    "runtime_operation_contract_sha256",
    "source_canonical_sha256",
    "source_operation_contract_sha256",
)


def _generator() -> ModuleType:
    script = _ROOT / "scripts/generate_m05_pair_contract.py"
    spec = importlib.util.spec_from_file_location("generate_m05_pair_contract", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_contract_digest_is_derived_from_a_vendored_snapshot() -> None:
    """16개 digest가 전부 스냅샷에서 계산된 값과 같아야 한다.

    하나라도 어긋나면 계약이 vendoring한 표면을 더 이상 기술하지 않는다는 뜻이고,
    그 사실은 지금까지 격리 e2e에서야 드러났다.
    """

    generated = _generator().build_contract()
    committed = json.loads(_CONTRACT.read_text(encoding="utf-8"))

    surfaces = sorted(generated["map"])
    assert surfaces == ["admin", "full", "service", "user"], surfaces

    mismatched: list[str] = []
    checked = 0
    for name in surfaces:
        for key in _DIGEST_KEYS:
            checked += 1
            want = generated["map"][name][key]
            got = committed["map"][name][key]
            if got != want:
                mismatched.append(f"{name}.{key}")

    assert checked == 16, f"digest를 {checked}개만 검사했다 — 표가 깨졌다"
    assert not mismatched, (
        "계약의 digest가 vendored 스냅샷에서 유도되지 않는다 — "
        "`python3 scripts/generate_m05_pair_contract.py --write`를 돌려라: " + repr(mismatched)
    )


def test_admin_and_full_read_the_same_snapshot() -> None:
    """`admin`과 `full`이 같은 파일에서 온다는 사실을 고정한다.

    Manager `_pair`의 경로 표도 둘 다 `packages/kor-travel-map-api/openapi.json`을
    가리킨다. 그 대응이 깨지면 두 저장소가 서로 다른 표면을 같은 것으로 취급한다.
    """

    module = _generator()
    assert module._SNAPSHOTS["admin"] == module._SNAPSHOTS["full"]
    assert module._SNAPSHOTS["service"] != module._SNAPSHOTS["admin"]
    assert module._SNAPSHOTS["user"] != module._SNAPSHOTS["admin"]


def test_generated_contract_declares_no_source_revision() -> None:
    """생성기는 **핀된 Map revision을 선언하지 않는다.**

    그 값의 생산자는 Manager runtime pin registry 하나여야 한다. 계약이 두 번째로
    선언하는 바람에 Map의 문서 한 줄이 PinVi 커밋 → 새 pinset → 1~2시간 rebuild를
    불렀고, 2026-09-01 이후 그 재핀이 네 번이었다.

    커밋된 계약은 아직 v1이라 그 필드를 갖는다 — 이 검사는 **생성기가 유도하는
    값**에 그 습관이 없는지를 본다. v2 전환이 끝나면 커밋된 계약도 같아진다.

    봉투(version)까지 단언하지는 않는다. 생성기는 커밋된 판을 그대로 되돌려 주기
    때문이다 — v2를 무조건 내면 `--write` 한 번이 소비자를 import에서 죽인다
    (`test_m05_pair_contract_generator_preserves_envelope.py`, 2026-09-03 적대
    리뷰). 유도의 내용과 봉투의 판은 서로 다른 사실이고, 여기서는 앞의 것만 본다.
    """

    generated = _generator().build_contract()
    committed = json.loads(_CONTRACT.read_text(encoding="utf-8"))

    # 봉투는 커밋된 계약을 따른다.
    assert generated["version"] == committed["version"]
    for name, entry in generated["map"].items():
        # v1 봉투에서는 비-유도 필드가 커밋된 값 그대로 옮겨진다.
        derived_keys = set(entry) - {"source_revision"}
        assert derived_keys == set(_DIGEST_KEYS), name
        if "source_revision" in entry:
            assert entry["source_revision"] == committed["map"][name]["source_revision"], name
