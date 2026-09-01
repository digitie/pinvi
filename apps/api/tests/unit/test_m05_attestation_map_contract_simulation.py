"""Map OpenAPI 스키마에서 파생한 응답으로 M05 attestation 계약을 시뮬레이션한다.

`test_m05_activation_attestation.py`는 손으로 만든 응답 픽스처를 쓴다. 그 픽스처가
승인 응답의 `feature_id`와 provenance의 `feature_id`에 **같은 값**을 넣고 있었기
때문에, "provenance TEXT == 승인 UUID" 요구(#509 이전 상태)가 단위 테스트를 통과한
채로 격리 e2e까지 살아남았다 — 결함은 pinset 1회를 태운 뒤에야 드러났다(e2e15).

이 모듈은 픽스처를 손으로 만들지 않는다. vendored Map admin OpenAPI 스냅샷
(`tests/contract/kor-travel-map-openapi-admin.json`, `_kor_travel_map_snapshot_pin`이
핀)에서 **필수 필드·타입·형식(uuid vs 무형식 string)** 을 읽어 응답을 합성하고, 그
응답으로 `scripts/m05_activation_attestation.py`의 서버측 체인을 돌린다. 스키마가
`feature_id`(무형식 TEXT)와 `feature_uuid`(format: uuid)를 다른 축으로 선언하므로,
두 축을 같은 값으로 만드는 픽스처는 애초에 생성되지 않는다.

검증 대상:

1. 스키마 정합 응답으로 `_m04_server_side_chain` / `_map_case_snapshot`이 통과한다.
2. uuid 형식 필드에 TEXT를 넣거나, 무형식 TEXT 필드에 UUID를 넣으면 실패한다.
3. m04/live 체인이 요구하는 CLI 인자·환경변수 집합이 Manager 드라이버
   (`kor-travel-docker-manager/scripts/m05_isolated_e2e.py`)가 실제로 넘기는 argv와
   일치한다.

추가로 #509 이전 판정식을 소스 수준에서 되살려(`_legacy_pre_509_module`) 이 하네스가
실제로 붉게 뜨는지 회귀 재현한다.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import uuid
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import pytest

from tests.unit._kor_travel_map_snapshot_pin import (
    SNAPSHOT,
    SNAPSHOT_SHA256,
    UPSTREAM_COMMIT,
)

_PINVI_ROOT = Path(__file__).resolve().parents[4]
_ATTESTATION_SCRIPT = _PINVI_ROOT / "scripts" / "m05_activation_attestation.py"
# Manager 체크아웃은 형제 디렉터리(ADR-044 로컬 우선 조회)가 기본이고, CI가 다른
# 경로에 체크아웃하면 KTDM_ROOT로 가리킨다. 없으면 §3 테스트만 skip된다.
_MANAGER_ROOT = Path(
    os.environ.get("KTDM_ROOT") or _PINVI_ROOT.parent / "kor-travel-docker-manager"
)
_MANAGER_DRIVER = _MANAGER_ROOT / "scripts" / "m05_isolated_e2e.py"

_UUID_SEED_NAMESPACE = uuid.UUID("6f4f0a2e-6d1c-4a3f-9b6a-0f9f1b0a5c21")
_SERVICE_PRINCIPAL = "service:feature-reference-reconciliation"
_HEX64_PATTERN = "^[0-9a-f]{64}$"
_MAP_ADMIN_URL = "http://127.0.0.1:14701"

# #509가 고친 두 지점. 회귀 재현은 이 문자열을 pre-#509 형태로 되돌려 실행한다.
_CURRENT_FEATURE_REF = (
    '    feature_ref = _uuid(request_data.get("feature_id"), name="Map M04 feature ref")'
)
_LEGACY_FEATURE_REF = (
    '    feature_ref = _string(request_data.get("feature_id"), name="Map M04 feature ref")'
)
_CURRENT_BINDING = (
    '    feature_uuid = _uuid(provenance.get("feature_uuid"), name="Map M04 feature UUID")\n'
    "    if feature_uuid != feature_ref:\n"
    '        raise AttestationError("Map M04 provenance does not match the approved feature")\n'
)
_LEGACY_BINDING = (
    "    if feature_id != feature_ref:\n"
    '        raise AttestationError("Map M04 provenance does not match the approved feature")\n'
    '    feature_uuid = _uuid(provenance.get("feature_uuid"), name="Map M04 feature UUID")\n'
)


# ---------------------------------------------------------------------------
# attestation 모듈 로딩 (정상본 / #509 이전본)
# ---------------------------------------------------------------------------
def _exec_module(source: str, name: str) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(_ATTESTATION_SCRIPT)
    exec(compile(source, str(_ATTESTATION_SCRIPT), "exec"), module.__dict__)  # noqa: S102
    return module


@lru_cache(maxsize=1)
def _attestation_source() -> str:
    return _ATTESTATION_SCRIPT.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _attestation_module() -> ModuleType:
    return _exec_module(_attestation_source(), "m05_activation_attestation")


@lru_cache(maxsize=1)
def _legacy_pre_509_module() -> ModuleType:
    """#509 이전 판정식(provenance TEXT == 승인 값)을 되살린 모듈."""

    source = _attestation_source()
    patches = (
        (_CURRENT_FEATURE_REF, _LEGACY_FEATURE_REF),
        (_CURRENT_BINDING, _LEGACY_BINDING),
    )
    for current, legacy in patches:
        # 주의: 리포트를 소스 전문으로 오염시키지 않도록 count를 먼저 지역에 담는다.
        occurrences = source.count(current)
        assert occurrences == 1, (
            "#509 회귀 재현이 겨냥한 코드를 찾지 못했다. 판정식이 pre-#509로 되돌아갔거나"
            f" 리팩터링됐다 — 재현 패치를 갱신하라 (occurrences={occurrences}): {current.strip()}"
        )
        source = source.replace(current, legacy)
    return _exec_module(source, "m05_activation_attestation_pre_509")


# ---------------------------------------------------------------------------
# vendored OpenAPI 스냅샷에서 파생한 응답 합성/검증
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _spec() -> dict[str, Any]:
    raw = SNAPSHOT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SNAPSHOT_SHA256, (
        f"vendored Map OpenAPI 스냅샷이 핀({UPSTREAM_COMMIT})과 다르다"
    )
    loaded = json.loads(raw)
    assert isinstance(loaded, dict)
    return loaded


def _schemas() -> dict[str, Any]:
    components = _spec()["components"]["schemas"]
    assert isinstance(components, dict)
    return components


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        ref = str(schema["$ref"])
        assert ref.startswith("#/components/schemas/"), ref
        schema = _schemas()[ref.rsplit("/", 1)[1]]
    return schema


def _branch(schema: dict[str, Any]) -> dict[str, Any]:
    """anyOf/oneOf에서 null이 아닌 첫 분기를 고른다(nullable 필드는 값이 있는 쪽)."""

    schema = _resolve(schema)
    for key in ("anyOf", "oneOf"):
        options = schema.get(key)
        if isinstance(options, list) and options:
            for option in options:
                resolved = _resolve(option)
                if resolved.get("type") != "null":
                    return _branch(resolved)
            return _resolve(options[0])
    return schema


def _string_value(schema: dict[str, Any], path: str) -> str:
    fmt = schema.get("format")
    if fmt == "uuid":
        return str(uuid.uuid5(_UUID_SEED_NAMESPACE, path))
    if fmt == "date-time":
        return "2026-09-01T00:00:00+00:00"
    pattern = schema.get("pattern")
    if pattern is not None:
        assert pattern == _HEX64_PATTERN, f"미지원 pattern {pattern!r} at {path}"
        return hashlib.sha256(path.encode("utf-8")).hexdigest()
    # 무형식 string은 **절대 UUID 모양이 아니어야** 한다. 그래야 uuid 축과 TEXT
    # 축을 뒤섞는 결함이 픽스처 우연으로 가려지지 않는다(e2e15의 근본 원인).
    return "text-" + re.sub(r"[^0-9A-Za-z_]+", "-", path).strip("-").lower()


def _build(schema: dict[str, Any], *, path: str) -> Any:
    schema = _branch(schema)
    if "const" in schema:
        return schema["const"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    kind = schema.get("type")
    if kind == "object":
        properties = schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            # additionalProperties: true 인 자유 형식 객체 — 스키마가 아무것도
            # 고정하지 않는다는 사실 자체가 검증 대상이다.
            return {}
        required = schema.get("required", [])
        assert isinstance(required, list)
        return {name: _build(properties[name], path=f"{path}.{name}") for name in required}
    if kind == "array":
        return []
    if kind == "string":
        return _string_value(schema, path)
    if kind == "integer":
        return int(schema.get("minimum", 1))
    if kind == "number":
        return float(schema.get("minimum", 0.0))
    if kind == "boolean":
        return True
    if kind == "null":
        return None
    raise AssertionError(f"미지원 스키마 타입 {kind!r} at {path}")


def _set_path(value: Any, dotted: str, new: Any) -> None:
    cursor = value
    parts = dotted.split(".")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if part.isdigit() else cursor[part]
    last = parts[-1]
    if last.isdigit():
        cursor[int(last)] = new
    else:
        assert isinstance(cursor, dict)
        cursor[last] = new


def _component(name: str, overrides: dict[str, Any] | None = None) -> Any:
    value = _build({"$ref": f"#/components/schemas/{name}"}, path=name)
    for dotted, new in (overrides or {}).items():
        _set_path(value, dotted, new)
    return value


def _conformance_errors(value: Any, schema: dict[str, Any], path: str) -> list[str]:
    """합성/변조한 응답이 실제로 스키마에 맞는지(또는 어긋나는지) 판정한다."""

    resolved = _resolve(schema)
    for key in ("anyOf", "oneOf"):
        options = resolved.get(key)
        if isinstance(options, list) and options:
            if any(not _conformance_errors(value, option, path) for option in options):
                return []
            return [f"{path}: anyOf 분기 어느 것에도 맞지 않는다"]
    if "const" in resolved and value != resolved["const"]:
        return [f"{path}: const {resolved['const']!r} != {value!r}"]
    enum = resolved.get("enum")
    if isinstance(enum, list) and value not in enum:
        return [f"{path}: enum {enum!r}에 없는 값 {value!r}"]
    kind = resolved.get("type")
    errors: list[str] = []
    if kind == "null":
        return [] if value is None else [f"{path}: null이 아니다"]
    if kind == "object":
        if not isinstance(value, dict):
            return [f"{path}: object가 아니다"]
        raw_properties = resolved.get("properties")
        properties: dict[str, Any] = raw_properties if isinstance(raw_properties, dict) else {}
        for name in resolved.get("required", []):
            if name not in value:
                errors.append(f"{path}.{name}: 필수 필드 누락")
        if resolved.get("additionalProperties") is False:
            errors.extend(
                f"{path}.{name}: 선언되지 않은 필드" for name in value if name not in properties
            )
        for name, item in value.items():
            if name in properties:
                errors.extend(_conformance_errors(item, properties[name], f"{path}.{name}"))
        return errors
    if kind == "array":
        if not isinstance(value, list):
            return [f"{path}: array가 아니다"]
        items = resolved.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                errors.extend(_conformance_errors(item, items, f"{path}[{index}]"))
        return errors
    if kind == "string":
        if not isinstance(value, str):
            return [f"{path}: string이 아니다"]
        fmt = resolved.get("format")
        if fmt == "uuid":
            try:
                if str(uuid.UUID(value)) != value:
                    raise ValueError
            except ValueError:
                errors.append(f"{path}: format uuid 위반 ({value!r})")
        if fmt == "date-time" and re.match(r"\d{4}-\d{2}-\d{2}T", value) is None:
            errors.append(f"{path}: format date-time 위반 ({value!r})")
        pattern = resolved.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            errors.append(f"{path}: pattern {pattern} 위반 ({value!r})")
        return errors
    if kind == "integer" and type(value) is not int:
        return [f"{path}: integer가 아니다"]
    if kind == "number" and (not isinstance(value, int | float) or isinstance(value, bool)):
        return [f"{path}: number가 아니다"]
    if kind == "boolean" and not isinstance(value, bool):
        return [f"{path}: boolean이 아니다"]
    minimum = resolved.get("minimum")
    maximum = resolved.get("maximum")
    if isinstance(value, int | float) and not isinstance(value, bool):
        if minimum is not None and value < minimum:
            errors.append(f"{path}: minimum {minimum} 위반")
        if maximum is not None and value > maximum:
            errors.append(f"{path}: maximum {maximum} 위반")
    return errors


def _errors_for(value: Any, component: str) -> list[str]:
    return _conformance_errors(value, {"$ref": f"#/components/schemas/{component}"}, component)


def _assert_conformant(value: Any, component: str) -> None:
    errors = _errors_for(value, component)
    assert not errors, f"{component} 응답이 vendored 스키마에 어긋난다: {errors}"


def _declared_format(component: str, dotted: str) -> str | None:
    schema: dict[str, Any] = {"$ref": f"#/components/schemas/{component}"}
    for part in dotted.split("."):
        resolved = _branch(schema)
        properties = resolved.get("properties")
        assert isinstance(properties, dict) and part in properties, (
            f"{component}.{dotted}: 스키마가 이 경로를 선언하지 않는다"
        )
        schema = properties[part]
    return _branch(schema).get("format")


# ---------------------------------------------------------------------------
# 스키마 파생 응답 세트
# ---------------------------------------------------------------------------
_APPROVED_FEATURE_UUID = str(uuid.uuid5(_UUID_SEED_NAMESPACE, "m05/manual-feature-uuid"))
_STORAGE_FEATURE_ID = "f_global_p_0123456789abcdef"
_REQUEST_ID = str(uuid.uuid5(_UUID_SEED_NAMESPACE, "m05/feature-request-id"))
_CASE_ID = str(uuid.uuid5(_UUID_SEED_NAMESPACE, "m05/case-id"))
_EVENT_ID = str(uuid.uuid5(_UUID_SEED_NAMESPACE, "m05/event-id"))


def _feature_request_response(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "data.request_id": _REQUEST_ID,
        "data.status": "approved",
        # Map의 feature_requests.resolved_feature_id는 UUID(as_uuid=False) 컬럼이라
        # 런타임 값은 UUID다. OpenAPI는 무형식 string으로만 선언한다 —
        # test_map_contract_leaves_feature_request_feature_id_unpinned 참조.
        "data.feature_id": _APPROVED_FEATURE_UUID,
    }
    base.update(overrides)
    return _component("FeatureRequestResponse", base)


def _provenance_response(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "data.feature_id": _STORAGE_FEATURE_ID,
        "data.feature_uuid": _APPROVED_FEATURE_UUID,
        "data.claim.feature_id": _APPROVED_FEATURE_UUID,
        "data.origin.origin_kind": "manual_request",
    }
    base.update(overrides)
    return _component("AdminManualFeatureProvenanceResponse", base)


def _subscription(event_sha: str) -> Any:
    return _component(
        "FeatureReferenceReconciliationSubscriptionDeliveryData",
        {
            "principal_id": _SERVICE_PRINCIPAL,
            "initial_event_sequence": 0,
            "acked_through_sequence": 1,
            "ack.event_id": _EVENT_ID,
            "ack.event_sha256": event_sha,
        },
    )


def _case_response(**overrides: Any) -> Any:
    event_sha = hashlib.sha256(b"m05/event-sha").hexdigest()
    base: dict[str, Any] = {
        "data.case_id": _CASE_ID,
        "data.status": "terminal",
        "data.event.case_id": _CASE_ID,
        "data.event.event_id": _EVENT_ID,
        "data.event.event_sequence": 1,
        "data.event.action": "rebind",
        "data.event.old_feature.feature_id": _STORAGE_FEATURE_ID,
        "data.event.old_feature.feature_uuid": _APPROVED_FEATURE_UUID,
        # manual_feature는 스키마상 자유 형식 객체다(전용 테스트 참조).
        # 체인이 실제로 읽는 두 키만 실 식별자 형태로 채운다.
        "data.manual_feature": {
            "feature_id": _STORAGE_FEATURE_ID,
            "feature_uuid": _APPROVED_FEATURE_UUID,
        },
        "data.subscriptions": [_subscription(event_sha)],
    }
    base.update(overrides)
    return _component("ManualProviderDedupCaseDetailResponse", base)


def _route_http_json(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    routes: dict[str, Any],
    seen: list[str] | None = None,
) -> None:
    def fake(url: str, *_args: Any, **_kwargs: Any) -> tuple[Any, bytes]:
        if seen is not None:
            seen.append(url)
        for suffix, payload in routes.items():
            if url.endswith(suffix):
                return payload, json.dumps(payload).encode("utf-8")
        raise AssertionError(f"체인이 예상 밖의 URL을 호출했다: {url}")

    monkeypatch.setattr(module, "_http_json", fake)


def _chain_routes(
    *,
    request_response: Any | None = None,
    provenance_response: Any | None = None,
) -> dict[str, Any]:
    return {
        f"/v1/admin/features/{_APPROVED_FEATURE_UUID}/creation-provenance": (
            provenance_response if provenance_response is not None else _provenance_response()
        ),
        f"/v1/admin/feature-requests/{_REQUEST_ID}": (
            request_response if request_response is not None else _feature_request_response()
        ),
    }


def _run_chain(module: ModuleType, map_case: Any | None = None) -> dict[str, str]:
    result = module._m04_server_side_chain(
        map_admin_url=_MAP_ADMIN_URL,
        m04={"feature_request_id": _REQUEST_ID},
        map_case=_case_response()["data"] if map_case is None else map_case,
    )
    assert isinstance(result, dict)
    return result


# ---------------------------------------------------------------------------
# 1. 스키마 정합 응답으로 체인이 통과하는가
# ---------------------------------------------------------------------------
def test_synthesized_responses_conform_to_the_vendored_map_schemas() -> None:
    _assert_conformant(_feature_request_response(), "FeatureRequestResponse")
    _assert_conformant(_provenance_response(), "AdminManualFeatureProvenanceResponse")
    _assert_conformant(_case_response(), "ManualProviderDedupCaseDetailResponse")


def test_map_case_snapshot_accepts_schema_derived_case_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    case = _case_response()
    _route_http_json(module, monkeypatch, {f"/manual-provider-dedup-cases/{_CASE_ID}": case})

    data, ack, data_hash, ack_hash = module._map_case_snapshot(
        map_admin_url=_MAP_ADMIN_URL, case_id=_CASE_ID, event_id=_EVENT_ID
    )

    assert data == case["data"]
    assert ack["event_id"] == _EVENT_ID
    assert data_hash == hashlib.sha256(module._canonical_json(case["data"])).hexdigest()
    assert ack_hash == hashlib.sha256(module._canonical_json(ack)).hexdigest()
    # 스키마의 event 객체에는 event_sha256이 아예 없다 — ACK fallback은 방어
    # 코드가 아니라 계약이 강제하는 유일 경로다.
    event_properties = _schemas()["FeatureReferenceReconciliationEventData"]["properties"]
    assert "event_sha256" not in event_properties
    assert module._map_case_event_hash(data, ack) == ack["event_sha256"]


def test_m04_server_side_chain_passes_on_schema_derived_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    request_response = _feature_request_response()
    provenance_response = _provenance_response()
    seen: list[str] = []
    _route_http_json(
        module,
        monkeypatch,
        _chain_routes(request_response=request_response, provenance_response=provenance_response),
        seen,
    )

    chain = _run_chain(module)

    assert chain == {
        "feature_request_id": _REQUEST_ID,
        "map_feature_id": _STORAGE_FEATURE_ID,
        "map_feature_uuid": _APPROVED_FEATURE_UUID,
        "map_provenance_sha256": hashlib.sha256(
            module._canonical_json(provenance_response["data"])
        ).hexdigest(),
        "map_request_sha256": hashlib.sha256(
            module._canonical_json(request_response["data"])
        ).hexdigest(),
    }
    # provenance는 반드시 **승인 UUID**로 조회돼야 한다. TEXT storage id로 조회하면
    # Map은 404를 주고, 그 404는 eligibility 위반으로 위장된다(e2e15와 같은 클래스).
    provenance_calls = [url for url in seen if url.endswith("/creation-provenance")]
    assert provenance_calls == [
        f"{_MAP_ADMIN_URL}/v1/admin/features/{_APPROVED_FEATURE_UUID}/creation-provenance"
    ]
    assert _STORAGE_FEATURE_ID not in provenance_calls[0]


# ---------------------------------------------------------------------------
# 2. uuid ↔ TEXT 축을 섞으면 실패하는가
# ---------------------------------------------------------------------------
def test_m04_chain_rejects_text_in_the_uuid_typed_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    assert _declared_format("FeatureRequestResponse", "data.request_id") == "uuid"

    mutated = _feature_request_response(**{"data.request_id": _STORAGE_FEATURE_ID})
    assert _errors_for(mutated, "FeatureRequestResponse"), "변조가 스키마 위반이 아니다"
    _route_http_json(module, monkeypatch, _chain_routes(request_response=mutated))

    with pytest.raises(module.AttestationError, match="Map M04 request ID must be a canonical"):
        _run_chain(module)


def test_m04_chain_rejects_text_in_the_uuid_typed_provenance_feature_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    assert _declared_format("AdminManualFeatureProvenanceResponse", "data.feature_uuid") == "uuid"

    mutated = _provenance_response(**{"data.feature_uuid": _STORAGE_FEATURE_ID})
    assert _errors_for(mutated, "AdminManualFeatureProvenanceResponse")
    _route_http_json(module, monkeypatch, _chain_routes(provenance_response=mutated))

    with pytest.raises(module.AttestationError, match="Map M04 feature UUID must be a canonical"):
        _run_chain(module)


def test_m04_chain_rejects_text_in_the_uuid_typed_case_feature_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    reference = _schemas()["FeatureReferenceReconciliationFeatureReference"]
    assert reference["properties"]["feature_uuid"]["format"] == "uuid"

    case = _case_response(**{"data.event.old_feature.feature_uuid": _STORAGE_FEATURE_ID})
    assert _errors_for(case, "ManualProviderDedupCaseDetailResponse")
    _route_http_json(module, monkeypatch, _chain_routes())

    with pytest.raises(module.AttestationError, match="canonical UUID"):
        _run_chain(module, map_case=case["data"])


def test_m04_chain_rejects_uuid_written_into_the_text_typed_provenance_feature_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """무형식 TEXT 축(`feature_id`)에 UUID를 넣는 것은 **스키마 정합**이다.

    그래서 이 값은 스키마 검증만으로는 걸리지 않고, 체인의 축 분리로만 걸린다.
    #509 이전 코드가 정확히 이 조합을 요구했다.
    """

    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    assert _declared_format("AdminManualFeatureProvenanceResponse", "data.feature_id") is None

    mutated = _provenance_response(**{"data.feature_id": _APPROVED_FEATURE_UUID})
    _assert_conformant(mutated, "AdminManualFeatureProvenanceResponse")
    _route_http_json(module, monkeypatch, _chain_routes(provenance_response=mutated))

    with pytest.raises(
        module.AttestationError, match="M04 approved feature does not match the M05 old feature"
    ):
        _run_chain(module)


def test_map_contract_declares_feature_id_and_feature_uuid_as_separate_axes() -> None:
    """같은 이름의 두 필드가 서로 다른 형식으로 선언돼 있다는 사실 자체를 핀한다."""

    assert _declared_format("AdminManualFeatureProvenanceResponse", "data.feature_id") is None
    assert _declared_format("AdminManualFeatureProvenanceResponse", "data.feature_uuid") == "uuid"
    # 같은 응답 **안**에서 claim.feature_id는 uuid 형식이고 data.feature_uuid와
    # 같아야 한다고 문서화돼 있다 — 최상위 feature_id가 TEXT 축이라는 증거.
    claim_format = _declared_format("AdminManualFeatureProvenanceResponse", "data.claim.feature_id")
    assert claim_format == "uuid"
    reference = _schemas()["FeatureReferenceReconciliationFeatureReference"]
    assert reference["properties"]["feature_id"].get("format") is None
    assert reference["properties"]["feature_uuid"]["format"] == "uuid"


def test_map_contract_leaves_feature_request_feature_id_unpinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """승인 응답 `feature_id`는 uuid로 핀돼 있지 않다 — PinVi는 미핀 축을 신뢰한다.

    Map의 `feature_requests.resolved_feature_id`는 `UUID(as_uuid=False)` 컬럼이라
    런타임 값은 UUID지만, OpenAPI는 무형식 string으로만 선언한다. 즉 **스키마상
    합법인 응답**(비-UUID 문자열)이 attestation을 소각시킬 수 있다. Map이 이 필드를
    uuid로 좁히면 이 테스트가 스스로 skip으로 바뀐다.
    """

    declared = _declared_format("FeatureRequestResponse", "data.feature_id")
    assert declared in (None, "uuid"), (
        "Map이 feature_id 형식을 uuid가 아닌 값으로 좁혔다 — 체인의 _uuid 요구를 재검토하라"
    )
    if declared == "uuid":
        pytest.skip("Map이 feature_id를 uuid로 핀했다 — 미핀 갭이 닫혔다")

    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    schema_legal = _feature_request_response(**{"data.feature_id": "f_global_p_deadbeefdeadbeef"})
    _assert_conformant(schema_legal, "FeatureRequestResponse")
    _route_http_json(module, monkeypatch, _chain_routes(request_response=schema_legal))

    with pytest.raises(module.AttestationError, match="Map M04 feature ref must be a canonical"):
        _run_chain(module)


def test_map_contract_leaves_dedup_case_manual_feature_unstructured() -> None:
    """체인이 읽는 `manual_feature.{feature_id,feature_uuid}`는 스키마가 고정하지 않는다."""

    manual = _schemas()["ManualProviderDedupCaseDetailData"]["properties"]["manual_feature"]
    if manual.get("properties"):
        # Map이 나중에 구조를 고정하면 축 형식이 체인 기대와 같아야 한다.
        assert manual["properties"]["feature_id"].get("format") is None
        assert manual["properties"]["feature_uuid"].get("format") == "uuid"
        return
    assert manual.get("type") == "object"
    assert manual.get("additionalProperties") is True, manual


# ---------------------------------------------------------------------------
# #509 회귀 재현
# ---------------------------------------------------------------------------
def test_pre_509_binding_fails_against_schema_derived_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#509 이전 판정식을 되살리면 이 하네스가 붉게 뜬다(당시 픽스처는 통과했다)."""

    legacy = _legacy_pre_509_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    _route_http_json(legacy, monkeypatch, _chain_routes())

    with pytest.raises(
        legacy.AttestationError, match="Map M04 provenance does not match the approved feature"
    ):
        _run_chain(legacy)


def test_pre_509_binding_only_holds_where_storage_identity_is_itself_a_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """legacy 판정식이 통과하는 유일한 세계는 TEXT 축 전체가 UUID인 세계다.

    Map은 storage identity를 TEXT(`f_global_p_…`)로 발급하므로 그 세계는 존재하지
    않는다 — 즉 pre-#509 관문은 원리적으로 항상 실패한다(e2e15 실측과 일치).
    """

    legacy = _legacy_pre_509_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    uuid_everywhere = _case_response(
        **{
            "data.event.old_feature.feature_id": _APPROVED_FEATURE_UUID,
            "data.manual_feature": {
                "feature_id": _APPROVED_FEATURE_UUID,
                "feature_uuid": _APPROVED_FEATURE_UUID,
            },
        }
    )
    _route_http_json(
        legacy,
        monkeypatch,
        _chain_routes(
            provenance_response=_provenance_response(**{"data.feature_id": _APPROVED_FEATURE_UUID})
        ),
    )

    chain = _run_chain(legacy, map_case=uuid_everywhere["data"])

    assert chain["map_feature_id"] == chain["map_feature_uuid"]
    # 실제 Map storage identity는 UUID가 아니다.
    assert _STORAGE_FEATURE_ID != _APPROVED_FEATURE_UUID
    assert _declared_format("AdminManualFeatureProvenanceResponse", "data.feature_id") is None


# ---------------------------------------------------------------------------
# 3. Manager 드라이버 argv ↔ attestation 계약
# ---------------------------------------------------------------------------
class _Argv(NamedTuple):
    literal: str | None
    source: str


_requires_manager = pytest.mark.skipif(
    not _MANAGER_DRIVER.is_file(),
    reason=f"Manager 체크아웃이 없다: {_MANAGER_DRIVER}",
)


@lru_cache(maxsize=1)
def _manager_tree() -> ast.Module:
    return ast.parse(_MANAGER_DRIVER.read_text(encoding="utf-8"))


def _dict_literal_keys(tree: ast.AST, name: str) -> set[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        return {
            key.value
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
    raise AssertionError(f"Manager 드라이버에 {name} dict 리터럴이 없다")


def _manager_constant(name: str) -> str:
    for node in ast.walk(_manager_tree()):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                assert isinstance(node.value.value, str)
                return node.value.value
    raise AssertionError(f"Manager 드라이버에 {name} 상수가 없다")


@lru_cache(maxsize=1)
def _manager_invocations() -> dict[str, tuple[tuple[_Argv, ...], frozenset[str]]]:
    """`_command(... m05_activation_attestation.py, "<sub>", ...)` 호출부를 추출한다."""

    tree = _manager_tree()
    found: dict[str, tuple[tuple[_Argv, ...], frozenset[str]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "_command"):
            continue
        argv = tuple(
            _Argv(
                arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None,
                ast.unparse(arg),
            )
            for arg in node.args
        )
        script_index = next(
            (i for i, a in enumerate(argv) if "m05_activation_attestation.py" in a.source),
            None,
        )
        if script_index is None:
            continue
        subcommand = argv[script_index + 1].literal
        assert subcommand in {"m04", "live"}, f"알 수 없는 서브커맨드 {subcommand!r}"
        env_keys: set[str] = set()
        for keyword in node.keywords:
            if keyword.arg == "env" and isinstance(keyword.value, ast.Name):
                env_keys = _dict_literal_keys(tree, keyword.value.id)
        assert subcommand not in found, f"{subcommand} 호출부가 둘 이상이다"
        found[subcommand] = (argv[script_index + 1 :], frozenset(env_keys))
    return found


def _parsed_manager_args(subcommand: str) -> Any:
    module = _attestation_module()
    argv, _env = _manager_invocations()[subcommand]
    rendered = [a.literal if a.literal is not None else "PLACEHOLDER" for a in argv]
    return module._parser().parse_args(rendered)


def _expected_ui_command(function: str) -> list[str | None]:
    tree = ast.parse(_attestation_source())
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function
    )
    for node in ast.walk(target):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "expected_command" for t in node.targets):
            continue
        expected: list[str | None] = []
        for element in node.value.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                expected.append(element.value)
            else:
                expected.append(None)
        return expected
    raise AssertionError(f"{function}에 expected_command 리터럴이 없다")


def _env_reads(function: str) -> dict[str, bool]:
    """함수 본문의 os.environ 접근 → {이름: 필수 여부}."""

    tree = ast.parse(_attestation_source())
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function
    )
    reads: dict[str, bool] = {}
    for node in ast.walk(target):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "os.environ.get":
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            name = node.args[0].value
            if not isinstance(name, str):
                continue
            has_default = (
                len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)
                and bool(node.args[1].value)
            )
            reads[name] = reads.get(name, True) and not has_default
        elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                reads[node.slice.value] = True
    return reads


@_requires_manager
@pytest.mark.parametrize("subcommand", ("m04", "live"))
def test_manager_argv_parses_against_the_attestation_cli(subcommand: str) -> None:
    """드라이버 argv가 attestation parser를 그대로 통과해야 한다.

    누락된 required 인자/알 수 없는 플래그는 argparse가 SystemExit(2)로 끝내고,
    격리 run은 pinset 1회를 태운 뒤에야 그 사실을 알려준다.
    """

    args = _parsed_manager_args(subcommand)

    assert args.command == subcommand
    assert args.scope == "isolated"
    assert args.require_root_owned is True


@_requires_manager
def test_manager_live_argv_supplies_the_isolated_provenance_quartet() -> None:
    """scope=isolated에서 `_live`가 넷을 모두 요구한다 — 하나만 빠져도 본문에서 소각."""

    args = _parsed_manager_args("live")

    assert args.isolated_runtime_provenance is not None
    assert args.isolated_manager_source_revision is not None
    assert args.isolated_pinset_sha256 is not None
    assert args.isolated_execution_identity_sha256 is not None


@_requires_manager
@pytest.mark.parametrize(
    ("subcommand", "handler"),
    (("m04", "_m04"), ("live", "_live")),
)
def test_manager_ui_command_matches_the_pinned_playwright_invocation(
    subcommand: str, handler: str
) -> None:
    """드라이버가 넘기는 Playwright 명령이 핸들러의 `expected_command`와 일치하는가."""

    argv, _env = _manager_invocations()[subcommand]
    separator = next(index for index, arg in enumerate(argv) if arg.literal == "--")
    runner = argv[separator + 1]
    tail = [arg.literal for arg in argv[separator + 2 :]]
    expected = _expected_ui_command(handler)

    assert runner.literal is None and "n150-playwright-runner.sh" in runner.source
    assert expected[0] is None, "expected_command[0]은 runner 경로 표현식이어야 한다"
    assert tail == expected[1:], (
        f"{subcommand} Playwright 명령이 어긋난다\n드라이버: {tail}\n핸들러: {expected[1:]}"
    )


@_requires_manager
@pytest.mark.parametrize(
    ("subcommand", "functions"),
    (("m04", ("_m04",)), ("live", ("_live", "_map_headers"))),
)
def test_manager_supplies_exactly_the_environment_the_handler_reads(
    subcommand: str, functions: tuple[str, ...]
) -> None:
    """핸들러가 읽는 필수 환경변수 == 드라이버가 넘기는 환경변수.

    빠지면 본문 진입 후 무조건 소각이고, 남으면 계약 drift다.
    """

    reads: dict[str, bool] = {}
    for function in functions:
        for name, is_required in _env_reads(function).items():
            reads[name] = reads.get(name, True) and is_required
    required = {name for name, is_required in reads.items() if is_required}
    optional = set(reads) - required
    _argv, provided = _manager_invocations()[subcommand]

    assert required <= provided, (
        f"드라이버가 넘기지 않는 필수 환경변수: {sorted(required - provided)}"
    )
    assert provided <= required | optional, (
        f"핸들러가 읽지 않는 환경변수를 넘긴다: {sorted(provided - (required | optional))}"
    )


@_requires_manager
def test_manager_playwright_runner_image_matches_the_attestation_pattern() -> None:
    """이미지 참조가 attestation의 정규식과 어긋나면 본문 진입 직후 소각된다(e2e13 클래스)."""

    module = _attestation_module()
    image = _manager_constant("_PLAYWRIGHT_RUNNER_IMAGE")

    assert module._PLAYWRIGHT_IMAGE_RE.fullmatch(image) is not None, image
    assert module._DIGEST_RE.fullmatch("sha256:" + image.rsplit("sha256:", 1)[1]) is not None
