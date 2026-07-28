"""kor_travel_map admin OpenAPI에서 detail-snapshot 계약 subset을 결정적으로 추출한다 (T-VN-H07D).

Pinvi 런타임이 소비하는 admin 표면은 `GET /v1/admin/curated-features/{id}/detail-snapshot`
(kor_travel_map 쪽 문서 경로는 `/v1/admin/features/curated/{id}/detail-snapshot`이고 Pinvi가
호출하는 경로는 같은 핸들러의 `include_in_schema=False` 호환 alias다). Map full 스펙은 1 MB가
넘어 통째로 vendor하면 무관한 변경마다 diff가 나므로, **그 경로와 응답 스키마의 전이적 폐포만**
잘라 vendor한다.

추출은 결정적이다(정렬된 key, 고정 indent) — 같은 입력이면 같은 바이트가 나오므로 CI가 같은
스크립트를 다시 돌려 vendored 파일과 byte 비교할 수 있다.

사용:
    python apps/api/scripts/vendor_kor_travel_map_admin_snapshot.py \\
        --source <kor-travel-map>/packages/kor-travel-map-api/openapi.json \\
        --output apps/api/tests/contract/kor-travel-map-openapi-admin-detail-snapshot.json
    # 검증만(쓰지 않고 diff 여부만 종료코드로):
    ... --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = "/v1/admin/features/curated/{curated_feature_id}/detail-snapshot"
_REF = "$ref"
_COMPONENT_PREFIX = "#/components/schemas/"


def _iter_refs(node: Any) -> list[str]:
    """node 아래의 모든 component schema 이름."""
    found: list[str] = []
    if isinstance(node, dict):
        ref = node.get(_REF)
        if isinstance(ref, str) and ref.startswith(_COMPONENT_PREFIX):
            found.append(ref[len(_COMPONENT_PREFIX) :])
        for value in node.values():
            found.extend(_iter_refs(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_iter_refs(value))
    return found


def _closure(schemas: dict[str, Any], seeds: list[str]) -> dict[str, Any]:
    """seed 스키마에서 도달 가능한 전이적 폐포."""
    pending = list(seeds)
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        schema = schemas.get(name)
        if schema is None:
            raise SystemExit(f"source 스펙에 schema 없음: {name}")
        seen.add(name)
        pending.extend(_iter_refs(schema))
    return {name: schemas[name] for name in sorted(seen)}


def _security_scheme_names(operation: dict[str, Any]) -> list[str]:
    """operation의 `security` 요구에 등장하는 scheme 이름."""
    names: set[str] = set()
    for method in operation.values():
        if not isinstance(method, dict):
            continue
        for requirement in method.get("security", []) or []:
            if isinstance(requirement, dict):
                names.update(requirement)
    return sorted(names)


def build_subset(source: dict[str, Any]) -> dict[str, Any]:
    paths = source.get("paths", {})
    if SNAPSHOT_PATH not in paths:
        raise SystemExit(f"source 스펙에 경로 없음: {SNAPSHOT_PATH}")
    operation = paths[SNAPSHOT_PATH]
    schemas = source["components"]["schemas"]
    subset_schemas = _closure(schemas, _iter_refs(operation))

    # operation이 요구하는 securityScheme도 함께 잘라낸다. 빠뜨리면 subset의 `security`가
    # 매달린 참조가 되고, admin 인증 헤더 계약(`X-Kor-Travel-Map-Admin-Proxy-Secret`)이
    # 게이트 밖에 남는다 — user 표면 게이트는 같은 계약을 이미 고정하고 있다.
    source_schemes = source.get("components", {}).get("securitySchemes", {})
    scheme_names = _security_scheme_names(operation)
    missing = [name for name in scheme_names if name not in source_schemes]
    if missing:
        raise SystemExit(f"source 스펙에 securityScheme 없음: {missing}")
    subset_schemes = {name: source_schemes[name] for name in scheme_names}

    return {
        "openapi": source.get("openapi"),
        "info": {
            "title": "kor-travel-map admin detail-snapshot contract subset",
            "version": source.get("info", {}).get("version"),
        },
        "paths": {SNAPSHOT_PATH: operation},
        "components": {"schemas": subset_schemas, "securitySchemes": subset_schemes},
    }


def render(subset: dict[str, Any]) -> str:
    return json.dumps(subset, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="쓰지 않고 기존 vendored 파일과 다른지만 확인(다르면 종료코드 1).",
    )
    args = parser.parse_args(argv)

    source = json.loads(args.source.read_text(encoding="utf-8"))
    rendered = render(build_subset(source))

    if args.check:
        if not args.output.exists():
            print(f"vendored 파일 없음: {args.output}", file=sys.stderr)
            return 1
        current = args.output.read_text(encoding="utf-8")
        if current != rendered:
            print(
                f"drift: {args.output} 가 {args.source} 에서 추출한 결과와 다르다",
                file=sys.stderr,
            )
            return 1
        print(f"ok: {args.output} 는 source와 일치한다")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output} ({len(rendered.encode())} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
