#!/usr/bin/env python3
"""M05 pair provenance 계약(v2)을 vendored 스냅샷에서 **유도**한다.

## 왜 생성기인가

v1 계약은 손으로 적혔고, 그 안에 `source_revision`이 있었다. 그 필드는 "핀된 Map
revision"이라는 사실의 **두 번째 선언**이었다 — 정본은 Manager runtime pin
registry다. 두 저장소에 있고 릴리스 주기가 독립이라 단일 빌드가 유도할 수 없었고,
그래서 Map의 문서 한 줄이 PinVi 커밋 → 새 pinset → 1~2시간 rebuild를 불렀다.
2026-09-01 이후 그 재핀이 **네 번**이었고 그중 하나는 커밋 제목이 스스로
"docs-only bump"라고 적었다.

v2는 `source_revision`을 걷어낸다. 남는 16개 digest는 **전부 이 저장소 안의 세
파일에서 계산된다**(실측: 16/16 일치). 즉 계약은 파생물이고, 파생물은 손으로 적지
않는다.

## 사용

    python3 scripts/generate_m05_pair_contract.py            # 표준출력으로 확인
    python3 scripts/generate_m05_pair_contract.py --write    # 계약 파일 갱신

`test_m05_pair_contract_is_derived`가 이 생성기의 출력과 커밋된 계약이 같은지
확인하므로, 스냅샷을 바꾸고 이걸 안 돌리면 CI가 잡는다.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT = _ROOT / "contracts/kor-travel-map-m05-pair-provenance-v1.json"

# 계약의 네 surface가 어느 vendored 스냅샷에서 오는가.
#
# `admin`과 `full`이 같은 파일인 것은 Map이 그 둘을 같은 `openapi.json`으로 내기
# 때문이다(Manager `_pair`의 경로 표도 같다). 그 사실이 바뀌면 이 표와 Manager
# 양쪽이 함께 바뀌어야 하고, `test_m05_pair_contract_is_derived`가 어긋남을 잡는다.
_SNAPSHOTS: dict[str, str] = {
    "admin": "apps/api/tests/contract/kor-travel-map-openapi-admin.json",
    "full": "apps/api/tests/contract/kor-travel-map-openapi-admin.json",
    "service": "apps/api/tests/contract/kor-travel-map-openapi-service.json",
    "user": "apps/api/tests/contract/kor-travel-map-openapi-user.json",
}


def _attestation() -> ModuleType:
    """digest 계산의 정본은 attestation 모듈이다 — 여기서 다시 구현하지 않는다."""

    script = _ROOT / "scripts/m05_activation_attestation.py"
    spec = importlib.util.spec_from_file_location("m05_activation_attestation", script)
    if spec is None or spec.loader is None:  # pragma: no cover - 설치 손상
        raise SystemExit("attestation module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_contract() -> dict[str, object]:
    """vendored 스냅샷에서 v2 계약을 계산한다."""

    module = _attestation()
    surfaces: dict[str, dict[str, str]] = {}
    for name, relative in _SNAPSHOTS.items():
        raw = (_ROOT / relative).read_bytes()
        value = json.loads(raw)
        operation_contract = module._openapi_operation_contract_sha256(value, name=name)
        surfaces[name] = {
            "openapi_sha256": hashlib.sha256(raw).hexdigest(),
            # runtime과 source가 같은 값인 것은 vendored 스냅샷이 곧 runtime이 내는
            # 문서이기 때문이다. 둘이 갈라지는 날 이 생성기가 먼저 깨져야 한다.
            "runtime_operation_contract_sha256": operation_contract,
            "source_canonical_sha256": hashlib.sha256(
                module._canonical_json(value)
            ).hexdigest(),
            "source_operation_contract_sha256": operation_contract,
        }
    # v2에는 `source_revision`도 `runtime_image_digests`도 없다.
    #
    # 전자는 pin registry가 유일한 생산자여야 하고, 후자는 격리 경로가 이미
    # Manager receipt의 실측 image ID로 전량 대체하고 있었다(그래서 커밋된 값이
    # 두 pinset 낡은 채 방치돼 있었다).
    #
    # 그러나 **봉투 판(version)은 이 생성기가 정하지 않는다.** 커밋된 계약이
    # v1이면 v1로 되돌려 준다. 그러지 않으면 `--write` 한 번이 소비자를 죽인다 —
    # `apps/api/app/core/config.py`의 검사는 `set(raw) == {"map",
    # "runtime_image_digests", "version"}`과 `version == 1`을 요구하고, 그 검사는
    # **모듈 스코프**에서 돈다. 즉 API 컨테이너가 import에서 실패한다. Manager의
    # 격리 preflight는 v1/v2를 함께 읽으므로 회전 전에 잡지도 못하고, 실패는
    # 71분짜리 rebuild를 태운 뒤에야 드러난다(2026-09-03 적대 리뷰).
    #
    # v2 전환은 소비자를 함께 옮기는 **의도된 한 걸음**이어야 한다. 재생성이
    # 그것을 대신 결정하면 안 된다.
    return _in_committed_envelope({"map": surfaces, "version": 2})


def _in_committed_envelope(derived: dict[str, object]) -> dict[str, object]:
    """유도한 값을 **커밋된 계약과 같은 판**으로 담아 돌려준다.

    v1은 surface마다 `source_revision`을, 최상위에 `runtime_image_digests`를
    갖는다. 둘 다 이 저장소에서 유도할 수 없는 값이므로(각각 pin registry와
    Manager receipt가 정본) 커밋된 값을 **그대로 옮긴다** — 생성기는 digest만
    다시 계산하고 판과 비-유도 필드는 건드리지 않는다.
    """

    try:
        committed = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return derived
    if not isinstance(committed, dict) or committed.get("version") != 1:
        return derived

    surfaces = derived["map"]
    assert isinstance(surfaces, dict)
    committed_map = committed.get("map")
    if not isinstance(committed_map, dict) or set(committed_map) != set(surfaces):
        raise SystemExit(
            "committed v1 contract inventory differs from the derived surfaces"
        )
    for name, surface in surfaces.items():
        committed_surface = committed_map[name]
        if (
            not isinstance(committed_surface, dict)
            or "source_revision" not in committed_surface
        ):
            raise SystemExit(f"committed v1 surface {name} has no source_revision")
        surface["source_revision"] = committed_surface["source_revision"]
    if "runtime_image_digests" not in committed:
        raise SystemExit("committed v1 contract has no runtime_image_digests")
    return {
        "map": surfaces,
        "runtime_image_digests": committed["runtime_image_digests"],
        "version": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="계약 파일을 갱신한다")
    arguments = parser.parse_args()

    contract = build_contract()
    rendered = json.dumps(contract, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if arguments.write:
        _CONTRACT.write_text(rendered, encoding="utf-8")
        print(f"wrote {_CONTRACT.relative_to(_ROOT)}", file=sys.stderr)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
